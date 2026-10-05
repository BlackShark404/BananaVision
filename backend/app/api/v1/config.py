"""
System configuration routes.
"""

from __future__ import annotations

import csv
import io
from app.services.power_control import schedule_power_action

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, AdminUser, CurrentUser
from app.models.device import Device
from app.models.scan import Scan
from app.models.admin_profile import AdminProfile
from app.models.activity_log import ActivityLog
from app.models.system_config import SystemConfig
from app.services.camera_manager import camera_manager
from app.services import configuration
from app.services.runtime_operations import station_lock
from app.schemas.common import SystemConfigResponse, SystemConfigUpdate


router = APIRouter(prefix="/config", tags=["Config"])


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
    config = await configuration.update_config(db, changes, body.expected_revision, admin_profile_id)
    db.add(ActivityLog(user_id=admin.id, action="config_changed",
        details=f"Updated config revision {config.revision}: {changes}",
        ip_address=request.client.host if request.client else None))
    await db.commit()
    if 'camera_ids' in changes or 'camera_device_ids' in changes:
        await configuration.apply_camera_config(config)
    return configuration.config_response(config)


@router.get("/export")
async def export_database(db: DbSession, admin: AdminUser):
    """Export scan summaries to CSV. This file cannot restore the database."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.status_logs))
        .order_by(Scan.date_time, Scan.id)
    )
    scans = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness", "Confidence", "Inventory Status"])

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


@router.post("/shutdown")
async def shutdown_system(db: DbSession, admin: AdminUser, request: Request):
    """Shutdown the system using OS-level commands."""
    await schedule_power_action("shutdown")
    db.add(ActivityLog(
        user_id=admin.id,
        action="system_shutdown",
        details="OS accepted scheduled system shutdown",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

    return {"message": "Operating system accepted the scheduled shutdown"}


@router.post("/restart")
async def restart_system(db: DbSession, admin: AdminUser, request: Request):
    """Restart the system using OS-level commands."""
    await schedule_power_action("restart")
    db.add(ActivityLog(
        user_id=admin.id,
        action="system_restart",
        details="OS accepted scheduled system restart",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

    return {"message": "Operating system accepted the scheduled restart"}
