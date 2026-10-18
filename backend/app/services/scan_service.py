"""
Scan pipeline orchestrator — coordinates the full capture → detect → fuse → predict flow.
"""

from __future__ import annotations

from app.services.scan_evidence import evidence_url

import logging
import uuid
import asyncio
from app.config import get_settings
from app.services.capture_cleanup import remove_scan_captures
from app.services.runtime_operations import station_lock, coordinator, run_blocking
from app.services.configuration import get_config
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan
from app.models.scan_history import ScanEvent
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.scan_detection import ScanDetection
from app.models.scan_image import ScanImage
from app.models.activity_log import ActivityLog
from app.models.app_notification import AppNotification
from app.core.exceptions import ModelInferenceError, NotFoundException
from app.services.camera_manager import camera_manager
from app.services.classification import banana_classifier, _parse_class_label
from app.services.banana_detector import banana_pre_detector
from app.services.fusion_engine import fusion_engine
from app.services.spoilage import spoilage_predictor
from app.services.feature_engineering import calc_vpd
from app.models.intake import Intake
from app.services.sensor_reader import sensor_reader
from app.ws.manager import ws_manager
from app.ws import events
from app.schemas.enums import InventoryStatusEnum

logger = logging.getLogger(__name__)


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
        expected_camera_count = len(config.camera_device_ids)
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

        any_banana_found = False
        for cap in captures:
            pre_result = await run_blocking(banana_pre_detector.detect, cap.frame)
            if pre_result.banana_detected:
                any_banana_found = True
                break

        if not any_banana_found:
            raise ModelInferenceError(
                "BananaPreDetector",
                "🍌 No banana found — please place the banana on the tray and try again.",
            )

        # ── Step 4: YOLO cultivar/ripeness inference on each image ────
        await send_scan_event(events.SCAN_DETECTING, {
            "scan_id": scan_id_str,
            "progress_pct": 50,
        })

        classification_results = []
        db_detections: list[ScanDetection] = []
        db_images: list[ScanImage] = []

        for cap in captures:
            # Classify
            result = await run_blocking(
                banana_classifier.predict, cap.frame,
                confidence_threshold=confidence_threshold, camera_label=cap.camera_label,
            )
            classification_results.append((cap.camera_id, cap.camera_label, result))

            # Store per-camera detection record
            db_detections.append(ScanDetection(
                scan_id=scan_id,
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
            raise ModelInferenceError(
                "BananaClassifier",
                "No banana detected in any camera frame. "
                "Please position the banana hand and try again.",
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
        # New objects do not receive selectin eager loads. Initialize relationships
        # read by response serialization so it cannot trigger implicit async DB I/O.
        scan = Scan(
            id=scan_id,
            operator_id=operator_id,
            intake_id=intake_id,
            intake=intake_obj,
            notes=[],
            date_time=now_manila(),
            flagged=fused.auto_flagged,
            source_text=supplier_name,
            operator_name_snapshot=operator_name,
            source_name_snapshot=supplier_name or (intake_obj.source if intake_obj else None),
        )

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

        status_log = ScanStatusLog(
            scan_id=scan_id,
            inventory_status=InventoryStatusEnum.IN_STOCK,
        )

        original_ai = ScanOriginalAiResult(
            scan_id=scan_id,
            cultivar=fused.cultivar,
            ripeness=fused.ripeness,
            confidence=fused.confidence,
            finger_count=fused.finger_count,
        )

        original_ai.spoilage_days = spoilage_days
        scan.classification = classification
        scan.status_logs = [status_log]
        scan.original_ai_result = original_ai

        db.add(scan)
        db.add(classification)
        db.add(status_log)
        db.add(original_ai)

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
                f"{fused.confidence}% confidence, {fused.finger_count} fingers"
            ),
            ip_address=client_ip,
        ))

        # Auto-create notifications
        db.add(AppNotification(
            type="scan_complete",
            title="Scan Completed",
            message=(
                f"{fused.cultivar} · {fused.ripeness} · "
                f"{fused.confidence}% confidence · {fused.finger_count} fingers"
            ),
            href=f"/scans/{scan_id_str}",
            user_id=account_id,
        ))

        if fused.auto_flagged:
            db.add(AppNotification(
                type="scan_flagged",
                title="Scan Auto-Flagged",
                message=(
                    f"{fused.cultivar} · {fused.ripeness} · "
                    f"{fused.confidence}% confidence — flagged for review"
                ),
                href=f"/scans/{scan_id_str}",
                user_id=None,  # Visible to all users (admins)
            ))

        await db.flush()

        db.add(
            ScanEvent(
                scan_id=scan.id,
                revision=scan.revision,
                kind="created",
                actor_id=account_id,
                actor_name=operator_name,
                timestamp=scan.date_time,
                new_values={
                    "inventory_status": "In Stock",
                    "intake_provenance": scan.intake_provenance,
                    "intake_origin_id": str(scan.intake_origin_id)
                    if scan.intake_origin_id
                    else None,
                    "operator": operator_name,
                    "source": scan.source_name_snapshot,
                },
                evidence_id=f"status:{status_log.id}",
            )
        )
        # Completion events must never advertise an uncommitted scan.
        await db.commit()
        committed = True

        # ── Step 8: Broadcast completed ──────────────────────────────────
        scan_result = {
            "id": scan_id_str,
            "revision": scan.revision,
            "scan_id": scan_id_str,
            "cultivar": fused.cultivar,
            "ripeness": fused.ripeness,
            "confidence": fused.confidence,
            "finger_count": fused.finger_count,
            "temperature": temperature,
            "humidity": humidity,
            "vpd": vpd,
            "treatment": intake_treatment.value if intake_treatment else None,
            "spoilage_days": spoilage_days,
            "operator": operator_name,
            "operator_name": operator_name,
            "supplier": supplier_name,
            "source_text": supplier_name,
            "intake_id": str(scan.intake_id) if scan.intake_id else None,
            "inventory_status": status_log.inventory_status.value,
            "status_updated_at": status_log.updated_at.isoformat(),
            "thumbnail_url": evidence_url(classification.thumbnail_url),
            "is_overridden": scan.is_overridden,
            "updated_at": scan.updated_at.isoformat(),
            "flagged": fused.auto_flagged,
            "conflict_detected": fused.conflict_detected,
            "camera_count": fused.camera_count,
            "scanned_at": scan.date_time.isoformat(),
            "date_time": scan.date_time.isoformat(),
            "images": [
                {"camera_id": img.camera_id, "file_path": evidence_url(img.file_path) or ""}
                for img in db_images
            ],
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
        if fused.auto_flagged:
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
        else:
            user_error = "Something went wrong during the scan. Please try again."

        await send_scan_event(events.SCAN_FAILED, {
            "scan_id": scan_id_str,
            "error": user_error,
            "stage": "pipeline",
        })
        logger.error(f"Scan pipeline failed: {exc}")
        raise
