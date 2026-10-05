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
from app.services.runtime_operations import station_lock
from app.schemas.common import SystemConfigResponse, SystemConfigUpdate


router = APIRouter(prefix="/config", tags=["Config"])


@router.get("", response_model=SystemConfigResponse)
async def get_config(db: DbSession, user: CurrentUser):
    """Get system configuration."""
    result = await db.execute(select(SystemConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = SystemConfig(
            camera_ids="CAM-001, CAM-002, CAM-003, CAM-004",
            confidence_threshold=85,
            data_retention_enabled=True
        )
        db.add(config)
        await db.flush()

    return SystemConfigResponse(
        camera_ids=config.camera_ids,
        confidence_threshold=float(config.confidence_threshold),
        data_retention_enabled=config.data_retention_enabled,
    )


@router.patch("", response_model=SystemConfigResponse)
async def update_config(body: SystemConfigUpdate, db: DbSession, admin: AdminUser, request: Request):
    """Update system configuration; serialize camera identity changes with scans."""
    if body.camera_ids is None:
        return await _update_config(body, db, admin, request)
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan or mapping before changing camera IDs")
    async with station_lock:
        return await _update_config(body, db, admin, request)


async def _update_config(body, db, admin, request):
    result = await db.execute(select(SystemConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = SystemConfig(
            camera_ids="CAM-001, CAM-002",
            confidence_threshold=85,
            data_retention_enabled=True
        )
        db.add(config)
        await db.flush()

    if body.camera_ids is not None:
        previous_camera_ids = config.camera_ids
        config.camera_ids = body.camera_ids

        # ── SCANNER-02: Upsert devices instead of delete-all + recreate ──
        # Parse the new camera IDs from the config string
        parsed_ids = [s.strip() for s in body.camera_ids.split(",") if s.strip()]
        previous_ids = [value.strip() for value in previous_camera_ids.split(",") if value.strip()]
        devices = (await db.execute(select(Device))).scalars().all()
        by_id = {device.camera_id: device for device in devices}
        ordered = [by_id.get(cam_id) for cam_id in previous_ids]
        # Temporarily free all unique labels, including stale legacy health records.
        for device in devices:
            device.camera_id = f"pending-{device.id}"
        await db.flush()
        kept = set()
        for idx, cam_id in enumerate(parsed_ids):
            device = ordered[idx] if idx < len(ordered) else None
            if device:
                device.camera_id = cam_id
                kept.add(device.id)
            else:
                db.add(Device(camera_id=cam_id, label=f"Scanner {idx + 1}",
                              status="Offline", resolution=None, last_seen=None))
        for device in devices:
            if device.id not in kept:
                await db.delete(device)

    if body.confidence_threshold is not None:
        config.confidence_threshold = int(body.confidence_threshold)
    if body.data_retention_enabled is not None:
        config.data_retention_enabled = body.data_retention_enabled

    admin_prof_id = await db.scalar(select(AdminProfile.id).where(AdminProfile.account_id == admin.id))
    config.updated_by_admin = admin_prof_id

    db.add(ActivityLog(
        user_id=admin.id,
        action="config_changed",
        details=f"Updated config: {body.model_dump(exclude_none=True)}",
        ip_address=request.client.host if request.client else None,
    ))

    await db.flush()
    # Publish display IDs only after commit; captures and health use the same labels.
    if body.camera_ids is not None:
        await db.commit()
        camera_manager.set_logical_ids(parsed_ids)
    return await get_config(db, admin)


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
