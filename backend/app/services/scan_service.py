"""
Scan pipeline orchestrator — coordinates the full capture → detect → fuse → predict flow.
"""

from __future__ import annotations

from app.services.scan_evidence import evidence_url

import logging
import uuid
import asyncio
from fastapi import HTTPException
from app.config import get_settings
from app.services.capture_cleanup import remove_scan_captures
from app.services.runtime_operations import station_lock, coordinator, run_blocking
from app.services.configuration import get_config
from app.core.time import now_manila

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.services.scan_creation import create_scan_record
from app.services.scan_records import serialize_scan
from app.models.scan_detection import ScanDetection
from app.models.scan_image import ScanImage
from app.models.device import Device
from app.models.activity_log import ActivityLog
from app.models.app_notification import AppNotification
from app.core.exceptions import (
    ConflictException,
    ModelInferenceError,
    NotFoundException,
    ScanRejectedError,
)
from app.schemas.enums import IntakeStatusEnum
from app.services.camera_manager import camera_manager
from app.services.classification import banana_classifier, _parse_class_label
from app.services.banana_detector import banana_pre_detector
from app.services import ood_gate
from app.services.fusion_engine import fusion_engine
from app.services.spoilage import spoilage_predictor
from app.services.feature_engineering import calc_vpd
from app.models.intake import Intake
from app.services.sensor_reader import sensor_reader
from app.ws.manager import ws_manager
from app.ws import events

logger = logging.getLogger(__name__)

CAPTURE_UNAVAILABLE_CODE = "capture_unavailable"
CAPTURE_UNAVAILABLE_MESSAGE = (
    "No camera frame was captured. Check the cameras and try again."
)


def estimated_fingers(count: int) -> str:
    """Wording for an AI finger count in notifications and the activity log."""
    return f"Est. {count} {'finger' if count == 1 else 'fingers'}"


def rejection_payload(exc: ScanRejectedError) -> dict:
    """Machine-readable rejection fields shared by the HTTP and WebSocket contracts."""
    is_ood = exc.code == ood_gate.REJECTION_CODE
    return {
        "code": exc.code,
        "status": "rejected" if is_ood else "unavailable",
        "is_ood": is_ood,
        "reason": exc.reason,
    }


async def _record_rejection(
    db: AsyncSession, account_id: uuid.UUID, exc: ScanRejectedError, client_ip: str | None,
) -> None:
    """Keep an audit row for a rejected scan; never mask the rejection itself."""
    try:
        db.add(ActivityLog(
            user_id=account_id,
            action="scan_rejected",
            details=f"Scan rejected ({exc.reason}): {exc.audit}",
            ip_address=client_ip,
        ))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Could not record the rejected scan in the activity log")


async def execute_scan_pipeline(
    db: AsyncSession,
    operator_id: uuid.UUID,
    account_id: uuid.UUID,
    operator_name: str,
    intake_id: uuid.UUID | None = None,
    supplier_name: str | None = None,
    client_ip: str | None = None,
) -> Scan:
    async with coordinator.operation():
        async with station_lock:
            coordinator.assert_ready()
            return await _execute_scan_pipeline(
                db, operator_id, account_id, operator_name, intake_id, supplier_name, client_ip=client_ip,
            )


async def _execute_scan_pipeline(
    db: AsyncSession, operator_id: uuid.UUID, account_id: uuid.UUID, operator_name: str,
    intake_id: uuid.UUID | None = None, supplier_name: str | None = None,
    client_ip: str | None = None,
) -> Scan:
    """
    Execute the full scan pipeline:
        1. Broadcast scan:started
        2. Capture from all cameras (parallel)
        3. Broadcast per-camera capture status
        4. Run YOLO on each image
        5. Broadcast detection results
        6. Fuse multi-camera results
        7. Get sensor data + predict spoilage
        8. Persist everything to DB
        9. Broadcast scan:completed

    Returns:
        The persisted Scan ORM object.
    """
    scan_id = uuid.uuid4()
    scan_id_str = str(scan_id)
    committed = False

    async def send_scan_event(event: str, data: dict):
        # Scan progress and results share the same account boundary as HTTP detail.
        await ws_manager.send_to_room(events.ROOM_KIOSK, event, data, account_id=account_id)

    # ── Step 1: Broadcast scan started ───────────────────────────────────
    await send_scan_event(events.SCAN_STARTED, {
        "scan_id": scan_id_str,
        "operator": operator_name,
        "supplier": supplier_name,
    })

    try:
        config = await get_config(db)
        review_confidence_threshold = config.confidence_threshold / 100.0
        # Retain moderate-confidence boxes before fusion. The stricter saved
        # threshold governs review, rather than discarding camera evidence.
        confidence_threshold = min(
            review_confidence_threshold, get_settings().yolo_confidence_threshold,
        )
        expected_camera_count = len(config.camera_slots)
        # ── Step 2: Capture from all cameras ─────────────────────────────
        await send_scan_event(events.SCAN_CAPTURING, {
            "scan_id": scan_id_str,
            "camera_id": "all",
            "camera_label": "All Cameras",
            "index": 0,
            "total": len(camera_manager.online_cameras),
        })

        captures = await camera_manager.capture_all()
        captures = await run_blocking(camera_manager.save_captures, captures, scan_id_str)
        if not captures:
            # A camera fault is not an out-of-distribution object: it must not be
            # shown or logged as "no supported banana".
            raise ScanRejectedError(
                CAPTURE_UNAVAILABLE_CODE, CAPTURE_UNAVAILABLE_MESSAGE,
                code=CAPTURE_UNAVAILABLE_CODE, audit="no camera produced a frame",
            )

        # Broadcast individual captures
        for i, cap in enumerate(captures):
            await send_scan_event(events.SCAN_CAPTURED, {
                "scan_id": scan_id_str,
                "camera_id": cap.camera_id,
                "camera_label": cap.camera_label,
                "image_url": evidence_url(cap.file_path),
                "index": i + 1,
                "total": len(captures),
            })

        # ── Step 3: Banana pre-detection gate ────────────────────────────
        # Run base COCO YOLO on each frame to verify a banana is present
        # before running the custom cultivar/ripeness model.
        await send_scan_event(events.SCAN_DETECTING, {
            "scan_id": scan_id_str,
            "progress_pct": 30,
        })

        # Every view is checked: its banana evidence later decides which cultivar
        # boxes of that same frame are trusted (out-of-distribution rejection).
        settings = get_settings()
        gate_policy = ood_gate.policy_from_settings(settings)
        fail_open = getattr(settings, "ood_gate_fail_open", False)
        # One entry per capture, in capture order.
        view_evidence: list[ood_gate.ViewEvidence] = []
        for cap in captures:
            pre_result = await run_blocking(banana_pre_detector.detect, cap.frame)
            if not getattr(pre_result, "available", True) and not fail_open:
                # Without the verifier every object would reach the closed-set model.
                raise ScanRejectedError(
                    ood_gate.GATE_UNAVAILABLE_CODE, ood_gate.GATE_UNAVAILABLE_MESSAGE,
                    code=ood_gate.GATE_UNAVAILABLE_CODE,
                    audit=f"banana verifier unavailable on {cap.camera_label}",
                )
            boxes = getattr(pre_result, "boxes", None)
            view_evidence.append(ood_gate.ViewEvidence(
                camera_id=cap.camera_id, camera_label=cap.camera_label,
                evidence=boxes if gate_policy.box_support_filter else None,
                banana_score=float(getattr(pre_result, "best_confidence", 0.0) or 0.0),
                has_banana=bool(pre_result.banana_detected),
            ))
        # Per-view scores are the only station evidence left after a rejection.
        view_scores = ", ".join(
            f"{view.camera_label} {view.banana_score:.2f}" for view in view_evidence
        )

        gate_decision = ood_gate.decide_scan(view_evidence, gate_policy)
        if not gate_decision.accepted:
            raise ScanRejectedError(
                ood_gate.REASON_NO_BANANA, ood_gate.REJECTION_MESSAGE,
                audit=(
                    f"banana evidence in {gate_decision.banana_views} of {len(captures)} "
                    f"views ({gate_decision.required_views} required); "
                    f"banana scores: {view_scores}"
                ),
            )

        # ── Step 4: YOLO cultivar/ripeness inference on each image ────
        await send_scan_event(events.SCAN_DETECTING, {
            "scan_id": scan_id_str,
            "progress_pct": 50,
        })

        classification_results = []
        db_detections: list[ScanDetection] = []
        db_images: list[ScanImage] = []

        # Build camera_id → device.id map for linking detections/images to devices
        device_rows = (await db.execute(select(Device.camera_id, Device.id))).all()
        device_map: dict[str, uuid.UUID] = {row.camera_id: row.id for row in device_rows}

        ood_rejected_boxes = 0
        for cap, view in zip(captures, view_evidence, strict=True):
            # The cultivar model still sees every view. With evidence, only boxes
            # that banana evidence covers survive and the dropped count is kept;
            # without it (legacy detector or filter off) every box is kept.
            gate_arguments = {} if view.evidence is None else {
                "banana_evidence": view.evidence,
                "support_margin": gate_policy.support_margin,
            }
            result = await run_blocking(
                banana_classifier.predict, cap.frame,
                confidence_threshold=confidence_threshold, camera_label=cap.camera_label,
                **gate_arguments,
            )
            ood_rejected_boxes += getattr(result, "ood_rejected_boxes", 0)
            classification_results.append((cap.camera_id, cap.camera_label, result))

            # Store per-camera detection record
            db_detections.append(ScanDetection(
                scan_id=scan_id,
                device_id=device_map.get(cap.camera_id),
                camera_id=cap.camera_id,
                camera_label=cap.camera_label,
                detected_cultivar=result.cultivar,
                detected_ripeness=result.ripeness,
                confidence=result.confidence,
                finger_count=result.finger_count,
                bounding_boxes=[
                    {"x": d.x, "y": d.y, "w": d.w, "h": d.h, "cls": d.cls, "conf": d.confidence}
                    for d in result.detections
                ],
                inference_time_ms=result.inference_time_ms,
            ))

            # Store image record
            if cap.file_path:
                import os
                file_stat = os.stat(cap.file_path) if os.path.exists(cap.file_path) else None
                db_images.append(ScanImage(
                    scan_id=scan_id,
                    device_id=device_map.get(cap.camera_id),
                    camera_id=cap.camera_id,
                    file_path=cap.file_path,
                    width=cap.frame.shape[1] if cap.frame is not None else None,
                    height=cap.frame.shape[0] if cap.frame is not None else None,
                    file_size_bytes=file_stat.st_size if file_stat else None,
                ))

            # Broadcast per-camera detection
            await send_scan_event(events.SCAN_DETECTED, {
                "scan_id": scan_id_str,
                "camera_id": cap.camera_id,
                "cultivar": result.cultivar,
                "ripeness": result.ripeness,
                "confidence": result.confidence,
                "finger_count": result.finger_count,
                "inference_ms": result.inference_time_ms,
            })

        # ── Step 5: Fuse multi-camera results ────────────────────────────
        await send_scan_event(events.SCAN_ANALYZING, {
            "scan_id": scan_id_str,
            "progress_pct": 80,
        })

        fused = fusion_engine.fuse(
            classification_results, expected_camera_count=expected_camera_count,
            review_confidence_threshold=review_confidence_threshold,
        )

        # Guard: if no banana was detected, abort the scan gracefully
        if fused.cultivar == "Unknown" or fused.ripeness == "Unknown":
            raise ScanRejectedError(
                ood_gate.REASON_NO_TARGET_CULTIVAR, ood_gate.REJECTION_MESSAGE,
                audit=(
                    f"no supported cultivar; {ood_rejected_boxes} cultivar boxes had no "
                    f"banana evidence; banana scores: {view_scores}"
                ),
            )
        # The gate never changes an accepted scan silently: dropped boxes can be a
        # foreign object or a missed finger, so a person confirms the result.
        auto_flagged = bool(fused.auto_flagged) or ood_rejected_boxes > 0
        if ood_rejected_boxes:
            logger.info(
                "OOD gate dropped %s cultivar boxes without banana evidence in scan %s; "
                "flagged for review (banana scores: %s)",
                ood_rejected_boxes, scan_id_str, view_scores,
            )

        # Cross-view cultivar harmonization:
        # A single harvested banana bunch is botanically uniform. When multi-camera fusion
        # reaches consensus on cultivar without conflict, harmonize any dissenting per-camera
        # detection records and bounding box class labels to the bunch cultivar.
        has_cultivar_conflict = getattr(fused, "cultivar_conflict", getattr(fused, "conflict_detected", False))
        if not has_cultivar_conflict and fused.cultivar != "Unknown":
            consensus_cultivar = fused.cultivar
            consensus_prefix = consensus_cultivar.lower()
            for det in db_detections:
                if det.detected_cultivar and det.detected_cultivar != consensus_cultivar:
                    logger.info(
                        f"Harmonizing camera {det.camera_label} cultivar "
                        f"from {det.detected_cultivar} to consensus {consensus_cultivar}"
                    )
                    det.detected_cultivar = consensus_cultivar
                if det.bounding_boxes:
                    harmonized_boxes = []
                    for bbox in det.bounding_boxes:
                        box_dict = dict(bbox)
                        cls_name = box_dict.get("cls", "")
                        cult, rip = _parse_class_label(cls_name)
                        if cult and cult != consensus_cultivar:
                            rip_str = f"_{rip.lower().replace(' ', '_')}" if rip else ""
                            box_dict["cls"] = f"{consensus_prefix}{rip_str}"
                        harmonized_boxes.append(box_dict)
                    det.bounding_boxes = harmonized_boxes

        # ── Step 6: Get sensor data + compute features + predict spoilage ─
        sensor_data = sensor_reader.latest
        temperature = sensor_data.temperature if sensor_data else None
        humidity = sensor_data.humidity if sensor_data else None

        # Compute engineered features (VPD only — dew_point and heat_index
        # are redundant with raw temp/humidity for tree-based models)
        vpd = None
        if temperature is not None and humidity is not None:
            vpd = calc_vpd(temperature, humidity)

        # Get treatment from linked intake
        intake_treatment = None
        intake_obj = None
        if intake_id:
            intake_result = await db.execute(
                select(Intake)
                .where(Intake.id == intake_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            intake_obj = intake_result.scalar_one_or_none()
            if intake_obj is None:
                raise NotFoundException("Intake")
            if intake_obj.status != IntakeStatusEnum.ACTIVE:
                raise ConflictException(
                    "This intake is no longer active. Select an active intake before scanning."
                )
            if intake_obj.treatment:
                intake_treatment = intake_obj.treatment

        spoilage_days = await run_blocking(spoilage_predictor.predict,
            cultivar=fused.cultivar,
            ripeness=fused.ripeness,
            temperature=temperature,
            humidity=humidity,
            vpd=vpd,
            treatment=intake_treatment.value if intake_treatment else None,
        )

        # ── Step 7: Persist scan to DB ───────────────────────────────────
        classification = ScanClassification(
            scan_id=scan_id,
            cultivar=fused.cultivar,
            ripeness=fused.ripeness,
            confidence=fused.confidence,
            temperature=temperature,
            humidity=humidity,
            spoilage_days=spoilage_days,
            finger_count=fused.finger_count,
            thumbnail_url=captures[0].file_path if captures else None,
            dew_point=None,
            vpd=vpd,
            heat_index=None,
            treatment=intake_treatment,
        )

        scan = await create_scan_record(
            db, scan_id=scan_id, operator_id=operator_id, operator_name=operator_name,
            intake=intake_obj, source_text=supplier_name, date_time=now_manila(),
            classification=classification, flagged=auto_flagged,
            actor_id=account_id, actor_name=operator_name,
        )

        scan.detections = db_detections
        scan.images = db_images

        for det in db_detections:
            db.add(det)
        for img in db_images:
            db.add(img)

        # Activity log
        db.add(ActivityLog(
            user_id=account_id,
            action="scan_created",
            details=(
                f"Scanned {fused.cultivar} ({fused.ripeness}) — "
                f"{fused.confidence}% confidence, {estimated_fingers(fused.finger_count)}"
                + (
                    f"; {ood_rejected_boxes} boxes without banana evidence dropped, "
                    "flagged for review"
                    if ood_rejected_boxes else ""
                )
            ),
            ip_address=client_ip,
        ))

        # Auto-create notifications
        db.add(AppNotification(
            type="scan_complete",
            title="Scan Completed",
            message=(
                f"{fused.cultivar} · {fused.ripeness} · "
                f"{fused.confidence}% confidence · {estimated_fingers(fused.finger_count)}"
            ),
            href=f"/scans/{scan_id_str}",
            user_id=account_id,
        ))

        if auto_flagged:
            db.add(AppNotification(
                type="scan_flagged",
                title="Scan Auto-Flagged",
                message=(
                    f"{fused.cultivar} · {fused.ripeness} · "
                    f"{fused.confidence}% confidence — flagged for review"
                ),
                href=f"/scans/{scan_id_str}",
                user_id=None,  # Broadcast; read state is per user.
            ))

        await db.flush()

        # Completion events must never advertise an uncommitted scan.
        await db.commit()
        committed = True

        # ── Step 8: Broadcast completed ──────────────────────────────────
        scan_result = {
            **serialize_scan(scan).model_dump(mode="json"),
            "scan_id": scan_id_str,
            "operator": operator_name,
            "supplier": scan.source_text,
            "conflict_detected": fused.conflict_detected,
            "camera_count": fused.camera_count,
            "scanned_at": scan.date_time.isoformat(),
            "detections": [
                {
                    "camera_id": det.camera_id,
                    "camera_label": det.camera_label,
                    "detected_cultivar": det.detected_cultivar,
                    "detected_ripeness": det.detected_ripeness,
                    "confidence": float(det.confidence) if det.confidence is not None else None,
                    "finger_count": det.finger_count,
                    "bounding_boxes": det.bounding_boxes or [],
                    "inference_time_ms": float(det.inference_time_ms)
                    if det.inference_time_ms is not None
                    else None,
                }
                for det in db_detections
            ],
        }

        await send_scan_event(events.SCAN_COMPLETED, scan_result)
        await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.SCAN_COMPLETED, scan_result)

        # Broadcast notification if flagged
        if auto_flagged:
            await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.NOTIFICATION, {
                "type": "scan_flagged",
                "title": "Scan Auto-Flagged",
                "message": (
                    f"{fused.cultivar} · {fused.ripeness} · "
                    f"{fused.confidence}% confidence — flagged for review"
                ),
                "href": f"/scans/{scan_id_str}",
            })

        logger.info(
            f"Scan {scan_id_str} completed: {fused.cultivar} {fused.ripeness} "
            f"({fused.confidence}%) — {spoilage_days} days"
        )

        return scan

    except (Exception, asyncio.CancelledError) as exc:
        if not committed:
            remove_scan_captures(get_settings().capture_path, scan_id_str)
        if isinstance(exc, asyncio.CancelledError):
            raise
        # Broadcast failure — use .message for ModelInferenceError to avoid
        # showing internal model names to the operator.
        if isinstance(exc, ModelInferenceError):
            user_error = exc.message
        elif isinstance(exc, HTTPException):
            user_error = str(exc.detail)
        else:
            user_error = "Something went wrong during the scan. Please try again."

        failure = {
            "scan_id": scan_id_str,
            "error": user_error,
            "stage": "pipeline",
        }
        if isinstance(exc, ScanRejectedError):
            # Additive fields: older clients keep reading `error`.
            failure.update(rejection_payload(exc))
        await send_scan_event(events.SCAN_FAILED, failure)
        if isinstance(exc, ScanRejectedError) and exc.code == ood_gate.REJECTION_CODE:
            # An expected outcome, not a fault. Captures are removed, so this line
            # and the activity row are the record of what the station saw.
            logger.info("OOD gate rejected scan %s (%s): %s", scan_id_str, exc.reason, exc.audit)
            await _record_rejection(db, account_id, exc, client_ip)
        else:
            logger.error(f"Scan pipeline failed: {exc}")
        raise
