"""
Device routes.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.time import now_manila
from app.models.device import Device
from app.schemas.common import DeviceResponse
from app.schemas.enums import DeviceStatusEnum
from app.services.camera_manager import camera_manager
from app.services.runtime_operations import run_blocking

settings = get_settings()
router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(db: DbSession, user: CurrentUser):
    """List all camera devices with live status from camera_manager."""
    probe_results = await run_blocking(camera_manager.probe_all)
    physical_by_name = dict(
        zip(camera_manager._logical_ids, camera_manager._device_ids, strict=False)
    )
    now = now_manila()

    result = await db.execute(select(Device).order_by(Device.camera_id))
    devices = result.scalars().all()

    # Sync each DB row with live camera_manager state
    changed = False
    for device in devices:
        dev_id = physical_by_name.get(device.camera_id)
        live_status = DeviceStatusEnum.ONLINE if dev_id is not None and probe_results.get(dev_id, False) else DeviceStatusEnum.OFFLINE
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
