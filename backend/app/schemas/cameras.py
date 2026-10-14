"""Administrative capture-device inventory contracts."""
from pydantic import BaseModel, Field


class CameraDeviceResponse(BaseModel):
    device_id: int = Field(ge=0)
    name: str
    device_uid: str | None
    configured_camera_id: str | None
    online: bool


class CameraDiscoveryResponse(BaseModel):
    backend: str
    devices: list[CameraDeviceResponse]
    error: str | None
