from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.core.http import get_client_ip
import asyncio
import cv2
import logging
import uuid
from app.services.runtime_operations import station_lock, run_blocking, coordinator
from pydantic import BaseModel, Field, StrictInt, field_validator

from app.services.camera_manager import camera_manager
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/cameras", tags=["Cameras"])


from app.api.deps import DbSession, AdminUser
from sqlalchemy.future import select
from app.services import configuration
from app.models.admin_profile import AdminProfile
from app.models.activity_log import ActivityLog
from app.services.maintenance_state import operation_result, record_operation

@router.get("")
async def list_cameras(db: DbSession):
    """
    List all configured cameras with their device IDs and online status.
    No auth required — used by the kiosk to map cameras to preview streams.
    """
    config = await configuration.get_config(db)
    names = [name.strip() for name in config.camera_ids.split(',')]
    applied = dict(zip(camera_manager._device_ids, camera_manager._logical_ids))
    return [{"device_id": device_id, "camera_id": names[index],
             "label": settings.camera_labels[index] if index < len(settings.camera_labels) else f"Scanner {index + 1}",
             "online": device_id in camera_manager.online_cameras and applied.get(device_id) == names[index]}
            for index, device_id in enumerate(config.camera_device_ids)]

async def generate_frames(camera_index: int, fps: int = 15):
    """
    Generator that captures frames continuously from the specified camera,
    downscales them, and yields them as an MJPEG stream.
    """
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} is not online")

    interval = 1.0 / fps
    loop = asyncio.get_event_loop()

    generation = camera_manager.generation
    while generation == camera_manager.generation:
        coordinator.assert_ready()
        start_time = loop.time()
        try:
            # Capture frame
            async with coordinator.operation():
                capture = await run_blocking(camera_manager._capture_single, camera_index)
            if generation != camera_manager.generation:
                break
            
            # Downscale frame for preview (HD 1280x720 for kiosk clarity)
            downscaled = cv2.resize(capture.frame, (1280, 720))
            
            # Encode as JPEG
            success, buffer = cv2.imencode('.jpg', downscaled, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                logger.warning(f"Failed to encode frame from camera {camera_index}")
                await asyncio.sleep(interval)
                continue

            # Yield multipart chunks
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
            )
        except Exception as exc:
            logger.error(f"Error yielding frame from camera {camera_index}: {exc}")
            # If camera disconnects, we should break and let the stream end appropriately
            break

        # Enforce FPS limit
        elapsed = loop.time() - start_time
        sleep_time = interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            # Quick yield buffer even if we are behind
            await asyncio.sleep(0.001)

@router.get("/preview/{camera_index}")
async def video_feed(camera_index: int, fps: int = 15):
    """
    Returns an MJPEG stream for a specific camera.
    """
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail="Camera not found or offline.")
        
    return StreamingResponse(
        generate_frames(camera_index, fps),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

class CameraMappingUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    operation_id: uuid.UUID
    device_ids: list[StrictInt] = Field(min_length=1, max_length=4)

    @field_validator("device_ids")
    @classmethod
    def valid_mapping(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Camera indices must be distinct and nonnegative")
        return ids

@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate, db: DbSession, admin: AdminUser, request: Request):
    """Persist physical slots atomically, then apply and report actual hardware results."""
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan before remapping cameras")
    async with station_lock:
        previous = await operation_result(db, str(mapping.operation_id))
        if previous:
            if previous.get('actor_id') != str(admin.id) or previous.get('device_ids') != mapping.device_ids or previous.get('kind') != 'calibration':
                raise HTTPException(409, 'Operation ID already used')
            return configuration.config_response(await configuration.get_config(db))
        admin_profile_id = await db.scalar(select(AdminProfile.id).where(AdminProfile.account_id == admin.id))
        config = await configuration.update_config(db, {'camera_device_ids': mapping.device_ids},
            mapping.expected_revision, admin_profile_id)
        db.add(ActivityLog(user_id=admin.id, action='config_changed',
            details=f'Camera mapping saved at revision {config.revision}: {mapping.device_ids}',
            ip_address=get_client_ip(request)))
        await record_operation(db, str(mapping.operation_id), {'kind': 'calibration', 'actor_id': str(admin.id),
            'device_ids': mapping.device_ids, 'status': 'saved'})
        await db.commit()
        await configuration.apply_camera_config(config)
        await configuration.sync_devices(db)
        response = configuration.config_response(config)
        response['results'] = {device_id: device_id in camera_manager.online_cameras for device_id in mapping.device_ids}
        response['message'] = 'Camera mapping saved; see application status for hardware results'
        return response
