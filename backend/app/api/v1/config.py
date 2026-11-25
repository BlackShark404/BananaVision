"""
System configuration routes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.export_format import (
    SCAN_EXPORT_HEADERS,
    ExportCell,
    format_scan_export_cells,
    to_pdf_rows,
    to_xlsx_rows,
)
from app.core.http import get_client_ip
from app.core.pdf import build_pdf
from app.core.time import now_manila
from app.core.xlsx import build_xlsx
from app.models.admin_profile import AdminProfile
from app.models.intake import Intake
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.schemas.common import SystemConfigResponse, SystemConfigUpdate
from app.services import audit, configuration
from app.services.camera_manager import camera_manager  # noqa: F401 - tests patch via this module
from app.services.runtime_operations import station_lock

router = APIRouter(prefix="/config", tags=["Config"])


def audit_values(config) -> dict:
    """Saved settings as plain values, read before the update refreshes the same objects."""
    camera_ids, device_ids = configuration.camera_slot_values(config.camera_slots)
    return {
        'camera_ids': camera_ids,
        'camera_device_ids': ', '.join(str(value) for value in device_ids),
        'confidence_threshold': config.confidence_threshold,
        'data_retention_enabled': config.data_retention_enabled,
    }


@router.get("", response_model=SystemConfigResponse)
async def get_config(db: DbSession, user: CurrentUser):
    return configuration.config_response(await configuration.get_config(db))


@router.patch("", response_model=SystemConfigResponse)
async def update_config(body: SystemConfigUpdate, db: DbSession, admin: AdminUser, request: Request):
    if body.camera_ids is None and body.camera_device_ids is None:
        return await _update_config(body, db, admin, request)
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan or mapping before changing cameras")
    async with station_lock:
        return await _update_config(body, db, admin, request)


async def _update_config(body, db, admin, request):
    changes = body.model_dump(exclude_unset=True, exclude={'expected_revision'})
    admin_profile_id = await db.scalar(select(AdminProfile.id).where(AdminProfile.account_id == admin.id))
    before = audit_values(await configuration.get_config(db))
    config = await configuration.update_config(db, changes, body.expected_revision, admin_profile_id)
    described = audit.describe_changes(before, audit_values(config))
    if described:  # Saving unchanged values is not an event.
        await audit.record(
            db, audit.AuditAction.CONFIG_CHANGED,
            f"Config revision {body.expected_revision} → {config.revision}: {described}",
            actor=admin, ip=get_client_ip(request),
        )
    await db.commit()
    if 'camera_ids' in changes or 'camera_device_ids' in changes:
        await configuration.apply_camera_config(config)
        await configuration.sync_devices(db)
    return configuration.config_response(config)


@router.get("/export")
async def export_database(
    db: DbSession,
    admin: AdminUser,
    request: Request,
    format: Annotated[Literal["xlsx", "pdf"], Query()] = "xlsx",
):
    """Export scan summaries to Excel (.xlsx) or PDF (.pdf). Cannot restore the database."""
    result = await db.execute(
        select(Scan)
        .options(
            selectinload(Scan.classification),
            selectinload(Scan.status_logs),
            selectinload(Scan.original_ai_result),
            selectinload(Scan.operator).selectinload(OperatorProfile.account),
            selectinload(Scan.intake).selectinload(Intake.supplier),
        )
        .order_by(Scan.date_time, Scan.id)
    )
    scans = result.scalars().all()
    # The row commits with this request before the file is sent; without it, no file.
    await audit.record(
        db, audit.AuditAction.DATA_EXPORTED,
        f"Exported inventory summary ({format}): {len(scans)} scan{'' if len(scans) == 1 else 's'}",
        actor=admin, ip=get_client_ip(request),
    )

    as_of = now_manila()
    rows: list[list[ExportCell]] = []
    for scan in scans:
        classification = scan.classification
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "In Stock"
        if scan.intake and scan.intake.supplier:
            source = scan.intake.supplier.name
        else:
            source = (scan.source_text or "").strip()
        operator_name = (
            scan.operator_name_snapshot
            or (
                scan.operator.account.full_name
                if scan.operator and scan.operator.account
                else ""
            )
        )
        rows.append(format_scan_export_cells(
            scan_id=scan.id,
            date_time=scan.date_time,
            source_name=source,
            cultivar=classification.cultivar if classification else None,
            ripeness=classification.ripeness if classification else None,
            finger_count=classification.finger_count if classification else None,
            is_overridden=bool(scan.is_overridden),
            original_finger_count=(
                scan.original_ai_result.finger_count if scan.original_ai_result else None
            ),
            spoilage_days=classification.spoilage_days if classification else None,
            inventory_status=status,
            flagged=bool(scan.flagged),
            confidence=classification.confidence if classification else None,
            temperature=classification.temperature if classification else None,
            humidity=classification.humidity if classification else None,
            operator_name=operator_name,
            as_of=as_of,
        ))

    if format == "pdf":
        pdf_bytes = build_pdf(
            SCAN_EXPORT_HEADERS,
            to_pdf_rows(rows),
            title="BananaVision — Inventory Scan Summary",
            exported_at=as_of,
            orientation="landscape",
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": (
                'attachment; filename="bananavision_inventory_export.pdf"'
            )},
        )

    xlsx_bytes = build_xlsx(
        SCAN_EXPORT_HEADERS, to_xlsx_rows(rows), sheet_name="sheet1", timestamp=as_of,
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": (
            'attachment; filename="bananavision_inventory_export.xlsx"'
        )},
    )


