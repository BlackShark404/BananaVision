"""
System configuration routes.
"""

from __future__ import annotations

import csv
import io
import os
import platform
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, AdminUser, CurrentUser
from app.models.device import Device
from app.models.scan import Scan
from app.models.admin_profile import AdminProfile
from app.models.activity_log import ActivityLog
from app.models.system_config import SystemConfig
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
    """Update system configuration."""
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
        config.camera_ids = body.camera_ids

        # Synchronize Device table with new camera IDs
        await db.execute(delete(Device))
        parsed_ids = [s.strip() for s in body.camera_ids.split(",") if s.strip()]
        for idx, cam_id in enumerate(parsed_ids):
            db.add(Device(
                camera_id=cam_id,
                label=f"Scanner {idx + 1}",
                status="Online",
                resolution="1920x1080",
                last_seen=datetime.now(timezone.utc)
            ))

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
    return await get_config(db, admin)


@router.get("/export")
async def export_database(db: DbSession, admin: AdminUser):
    """Export database logs and inventory to CSV."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.status_logs))
    )
    scans = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Scan ID", "Date Time", "Cultivar", "Ripeness", "Confidence", "Inventory Status"])

    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([scan.id, scan.date_time.isoformat(), cultivar, ripeness, confidence, status])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bananavision_inventory_export.csv"}
    )


@router.post("/shutdown")
async def shutdown_system(db: DbSession, admin: AdminUser, request: Request):
    """Shutdown the system using OS-level commands."""
    db.add(ActivityLog(
        user_id=admin.id,
        action="system_shutdown",
        details="Initiated system shutdown",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

    # Execute actual OS shutdown
    current_os = platform.system().lower()
    try:
        if "windows" in current_os:
            subprocess.Popen(["shutdown", "/s", "/t", "10"])
        elif "darwin" in current_os or "mac" in current_os:
            subprocess.Popen(["sudo", "shutdown", "-h", "+1"])
        else:  # Linux
            subprocess.Popen(["sudo", "shutdown", "-h", "now"])
    except Exception as e:
        print(f"Failed to execute shutdown: {e}")

    return {"message": "System shutdown initiated"}


@router.post("/restart")
async def restart_system(db: DbSession, admin: AdminUser, request: Request):
    """Restart the system using OS-level commands."""
    db.add(ActivityLog(
        user_id=admin.id,
        action="system_restart",
        details="Initiated system restart",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

    # Execute actual OS restart
    current_os = platform.system().lower()
    try:
        if "windows" in current_os:
            subprocess.Popen(["shutdown", "/r", "/t", "10"])
        elif "darwin" in current_os or "mac" in current_os:
            subprocess.Popen(["sudo", "shutdown", "-r", "+1"])
        else:  # Linux
            subprocess.Popen(["sudo", "shutdown", "-r", "now"])
    except Exception as e:
        print(f"Failed to execute restart: {e}")

    return {"message": "System restart initiated"}
