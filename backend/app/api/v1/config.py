"""
System configuration routes.
"""

from __future__ import annotations

import csv
import io
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.http import get_client_ip
from app.core.xlsx import build_xlsx, number_text
from app.models.admin_profile import AdminProfile
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
    format: Annotated[Literal["csv", "xlsx"], Query()] = "csv",
):
    """Export scan summaries to CSV or XLSX. This file cannot restore the database."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.status_logs))
        .order_by(Scan.date_time, Scan.id)
    )
    scans = result.scalars().all()
    # The row commits with this request before the file is sent; without it, no file.
    await audit.record(
        db, audit.AuditAction.DATA_EXPORTED,
        f"Exported inventory summary ({format}): {len(scans)} scan{'' if len(scans) == 1 else 's'}",
        actor=admin, ip=get_client_ip(request),
    )

    headers = [
        "Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness",
        "Confidence", "Inventory Status",
    ]

    if format == "xlsx":
        xlsx_rows = []
        for scan in scans:
            cultivar = scan.classification.cultivar if scan.classification else "N/A"
            ripeness = scan.classification.ripeness if scan.classification else "N/A"
            confidence = scan.classification.confidence if scan.classification else "N/A"
            status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
            cultivar_text = (
                str(getattr(cultivar, "value", cultivar))
                if cultivar is not None else None
            )
            ripeness_text = (
                str(getattr(ripeness, "value", ripeness))
                if ripeness is not None else None
            )
            status_text = (
                str(getattr(status, "value", status))
                if status is not None else None
            )

            if confidence == "N/A":
                conf_cell = ("N/A", "inlineStr")
            elif confidence is None:
                conf_cell = None
            else:
                try:
                    float(confidence)
                    conf_cell = (number_text(confidence), "n")
                except (ValueError, TypeError):
                    conf_cell = (str(confidence), "inlineStr")
            xlsx_rows.append([
                (str(scan.id), "inlineStr"),
                (scan.date_time.isoformat(), "inlineStr"),
                (cultivar_text, "inlineStr") if cultivar_text is not None else None,
                (ripeness_text, "inlineStr") if ripeness_text is not None else None,
                conf_cell,
                (status_text, "inlineStr") if status_text is not None else None,
            ])
        xlsx_bytes = build_xlsx(headers, xlsx_rows, sheet_name="sheet1")
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": (
                'attachment; filename="bananavision_inventory_export.xlsx"'
            )},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([scan.id, scan.date_time.isoformat(), getattr(cultivar, "value", cultivar),
                         getattr(ripeness, "value", ripeness), confidence, getattr(status, "value", status)])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bananavision_inventory_export.csv"}
    )


