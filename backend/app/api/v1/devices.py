"""
Device routes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser
from app.models.device import Device
from app.schemas.common import DeviceResponse
from app.schemas.enums import DeviceStatusEnum
from app.services.camera_manager import camera_manager
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(db: DbSession, user: CurrentUser):
    """List all camera devices with live status from camera_manager."""
    probe_results = camera_manager.probe_all()
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Device).order_by(Device.camera_id))
    devices = result.scalars().all()

    # Sync each DB row with live camera_manager state
    changed = False
    for device in devices:
        # Map DB camera_id (e.g. "CAM-001") back to device index
        try:
            idx = int(device.camera_id.split("-")[1]) - 1
            dev_id = settings.camera_device_ids[idx] if idx < len(settings.camera_device_ids) else None
        except (ValueError, IndexError):
            dev_id = None

        if dev_id is not None:
            live_status = DeviceStatusEnum.ONLINE if probe_results.get(dev_id, False) else DeviceStatusEnum.OFFLINE
            if device.status != live_status:
                device.status = live_status
                if live_status == DeviceStatusEnum.ONLINE:
                    device.last_seen = now
                changed = True
            elif live_status == DeviceStatusEnum.ONLINE and device.last_seen is None:
                device.last_seen = now
                changed = True

    if changed:
        await db.commit()

    return [DeviceResponse.model_validate(d) for d in devices]
