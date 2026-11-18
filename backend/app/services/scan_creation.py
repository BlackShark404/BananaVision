"""Persist a new scan and its initial evidence; the caller owns the transaction.

Live capture and demo generation supply their own measurements/predictions. This
boundary never runs hardware or recalculates an existing prediction.
"""

from uuid import uuid4

from app.models.scan import Scan
from app.models.scan_history import ScanEvent
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.scan_status_log import ScanStatusLog
from app.schemas.enums import InventoryStatusEnum

# Start of the created entry's reason text when the system flagged the scan.
AUTO_FLAG_PREFIX = "Auto-flagged: "


async def create_scan_record(
    db, *, operator_id, operator_name, classification, date_time,
    actor_id, actor_name, intake=None, source_text=None, scan_id=None,
    flagged=False, reason=None, flag_reason=None,
):
    """Create the scan and its "created" history entry.

    A scan the system flags records why on that entry, so Scan History shows it.
    """
    system_flag = bool(flagged and flag_reason)
    if system_flag and reason is None:
        reason = AUTO_FLAG_PREFIX + str(flag_reason)
    if source_text is None and intake is not None:
        source_text = intake.supplier.name if intake.supplier else intake.source
    status = ScanStatusLog(inventory_status=InventoryStatusEnum.IN_STOCK, updated_at=date_time)
    scan = Scan(
        id=scan_id or uuid4(), operator_id=operator_id,
        operator_name_snapshot=operator_name, source_text=source_text,
        source_name_snapshot=source_text, intake=intake,
        intake_id=intake.id if intake is not None else None,
        date_time=date_time, updated_at=date_time, flagged=flagged,
        classification=classification, status_logs=[status],
        original_ai_result=ScanOriginalAiResult(
            cultivar=classification.cultivar, ripeness=classification.ripeness,
            confidence=classification.confidence, finger_count=classification.finger_count,
            spoilage_days=classification.spoilage_days, created_at=date_time,
        ),
        # Avoid implicit async loads when serializing the newly created graph.
        notes=[], images=[], detections=[],
    )
    db.add(scan)
    await db.flush()
    db.add(ScanEvent(
        scan_id=scan.id, revision=scan.revision, kind="created", timestamp=date_time,
        actor_id=actor_id, actor_name=actor_name, reason=reason,
        new_values={
            "inventory_status": "In Stock", "intake_provenance": scan.intake_provenance,
            "intake_origin_id": str(scan.intake_origin_id) if scan.intake_origin_id else None,
            "operator": operator_name, "source": scan.source_name_snapshot,
            **({"flagged": True} if system_flag else {}),
        },
        evidence_id=f"status:{status.id}",
    ))
    return scan
