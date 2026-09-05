"""
Device routes.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser
from app.models.device import Device
from app.schemas.common import DeviceResponse


router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(db: DbSession, user: CurrentUser):
    """List all camera devices and their status."""
    result = await db.execute(select(Device).order_by(Device.camera_id))
    return [DeviceResponse.model_validate(d) for d in result.scalars().all()]
