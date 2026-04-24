"""
Scan pipeline orchestrator — coordinates the full capture → detect → fuse → predict flow.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.scan_detection import ScanDetection
from app.models.scan_image import ScanImage
from app.models.activity_log import ActivityLog
from app.services.camera_manager import camera_manager
from app.services.classification import banana_classifier
from app.services.fusion_engine import fusion_engine
from app.services.spoilage import spoilage_predictor
from app.services.sensor_reader import sensor_reader
from app.ws.manager import ws_manager
from app.ws import events

logger = logging.getLogger(__name__)


async def execute_scan_pipeline(
    db: AsyncSession,
    operator_id: uuid.UUID,
    operator_name: str,
    intake_id: uuid.UUID | None = None,
    supplier_name: str | None = None,
) -> Scan:
    """
    Execute the full scan pipeline:
        1. Broadcast scan:started
        2. Capture from all cameras (parallel)
        3. Broadcast per-camera capture status
        4. Run YOLOv8n on each image
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

    # ── Step 1: Broadcast scan started ───────────────────────────────────
    await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_STARTED, {
        "scan_id": scan_id_str,
        "operator": operator_name,
        "supplier": supplier_name,
    })

    try:
        # ── Step 2: Capture from all cameras ─────────────────────────────
        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_CAPTURING, {
            "scan_id": scan_id_str,
            "camera_id": "all",
            "camera_label": "All Cameras",
            "index": 0,
            "total": len(camera_manager.online_cameras),
        })

        captures = await camera_manager.capture_all()
        captures = camera_manager.save_captures(captures, scan_id_str)

        # Broadcast individual captures
        for i, cap in enumerate(captures):
            await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_CAPTURED, {
                "scan_id": scan_id_str,
                "camera_id": cap.camera_id,
                "camera_label": cap.camera_label,
                "image_url": cap.file_path,
                "index": i + 1,
                "total": len(captures),
            })

        # ── Step 3: YOLOv8n inference on each image ──────────────────────
        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_DETECTING, {
            "scan_id": scan_id_str,
            "progress_pct": 50,
        })

        classification_results = []
        db_detections: list[ScanDetection] = []
        db_images: list[ScanImage] = []

        for cap in captures:
            # Classify
            result = banana_classifier.predict(cap.frame)
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
            await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_DETECTED, {
                "scan_id": scan_id_str,
                "camera_id": cap.camera_id,
                "cultivar": result.cultivar,
                "ripeness": result.ripeness,
                "confidence": result.confidence,
                "finger_count": result.finger_count,
                "inference_ms": result.inference_time_ms,
            })

        # ── Step 4: Fuse multi-camera results ────────────────────────────
        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_ANALYZING, {
            "scan_id": scan_id_str,
            "progress_pct": 80,
        })

        fused = fusion_engine.fuse(classification_results)

        # ── Step 5: Get sensor data + predict spoilage ───────────────────
        sensor_data = sensor_reader.latest
        temperature = sensor_data.temperature if sensor_data else None
        humidity = sensor_data.humidity if sensor_data else None

        spoilage_days = spoilage_predictor.predict(
            cultivar=fused.cultivar,
            ripeness=fused.ripeness,
            temperature=temperature,
            humidity=humidity,
        )

        # ── Step 6: Persist scan to DB ───────────────────────────────────
        scan = Scan(
            id=scan_id,
            operator_id=operator_id,
            intake_id=intake_id,
            date_time=datetime.now(timezone.utc),
            flagged=fused.auto_flagged,
            source_text=supplier_name,
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
        )

        status_log = ScanStatusLog(
            scan_id=scan_id,
            inventory_status="In Stock",
        )

        original_ai = ScanOriginalAiResult(
            scan_id=scan_id,
            cultivar=fused.cultivar,
            ripeness=fused.ripeness,
            confidence=fused.confidence,
            finger_count=fused.finger_count,
        )

        scan.classification = classification
        scan.status_logs = [status_log]
        scan.original_ai_result = original_ai

        db.add(scan)
        db.add(classification)
        db.add(status_log)
        db.add(original_ai)

        for det in db_detections:
            db.add(det)
        for img in db_images:
            db.add(img)

        # Activity log
        db.add(ActivityLog(
            user_id=operator_id,
            action="scan_created",
            details=(
                f"Scanned {fused.cultivar} ({fused.ripeness}) — "
                f"{fused.confidence}% confidence, {fused.finger_count} fingers"
            ),
        ))

        await db.flush()

        # ── Step 7: Broadcast completed ──────────────────────────────────
        scan_result = {
            "scan_id": scan_id_str,
            "cultivar": fused.cultivar,
            "ripeness": fused.ripeness,
            "confidence": fused.confidence,
            "finger_count": fused.finger_count,
            "temperature": temperature,
            "humidity": humidity,
            "spoilage_days": spoilage_days,
            "operator": operator_name,
            "supplier": supplier_name,
            "flagged": fused.auto_flagged,
            "conflict_detected": fused.conflict_detected,
            "camera_count": fused.camera_count,
            "scanned_at": scan.date_time.isoformat(),
        }

        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_COMPLETED, scan_result)
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

    except Exception as exc:
        # Broadcast failure
        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SCAN_FAILED, {
            "scan_id": scan_id_str,
            "error": str(exc),
            "stage": "pipeline",
        })
        logger.error(f"Scan pipeline failed: {exc}")
        raise
