from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import cv2
import logging
import os
import json
from pathlib import Path
from app.services.runtime_operations import station_lock
from pydantic import BaseModel, Field, StrictInt, field_validator

from app.services.camera_manager import camera_manager
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/cameras", tags=["Cameras"])


from app.api.deps import DbSession, AdminUser
from sqlalchemy.future import select
from app.models.system_config import SystemConfig

@router.get("")
async def list_cameras(db: DbSession):
    """
    List all configured cameras with their device IDs and online status.
    No auth required — used by the kiosk to map cameras to preview streams.
    """
    # Fetch configured camera IDs from system config
    result = await db.execute(select(SystemConfig).limit(1))
    config = result.scalar_one_or_none()
    
    configured_ids = []
    if config and config.camera_ids:
        configured_ids = [s.strip() for s in config.camera_ids.split(",") if s.strip()]

    cameras = []
    for idx, dev_id in enumerate(settings.camera_device_ids):
        label = settings.camera_labels[idx] if idx < len(settings.camera_labels) else f"CAM-{dev_id}"
        
        # Use custom ID from config if available, otherwise fallback
        if idx < len(configured_ids):
            camera_id = configured_ids[idx]
        else:
            camera_id = f"CAM-{idx + 1:03d}"
            
        cameras.append({
            "device_id": dev_id,
            "camera_id": camera_id,
            "label": label,
            "online": dev_id in camera_manager.online_cameras,
        })
    return cameras

async def generate_frames(camera_index: int, fps: int = 15):
    """
    Generator that captures frames continuously from the specified camera,
    downscales them, and yields them as an MJPEG stream.
    """
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} is not online")

    interval = 1.0 / fps
    loop = asyncio.get_event_loop()

    while True:
        start_time = loop.time()
        try:
            # Capture frame
            capture = await loop.run_in_executor(None, camera_manager._capture_single, camera_index)
            
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
    device_ids: list[StrictInt] = Field(min_length=1, max_length=4)

    @field_validator("device_ids")
    @classmethod
    def valid_mapping(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Camera indices must be distinct and nonnegative")
        return ids

@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate, admin: AdminUser):
    """
    Updates the CAMERA_DEVICE_IDS in .env, clears settings cache, 
    and restarts the camera manager.
    """
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan before remapping cameras")
    async with station_lock:
        env_path = Path(".env")
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        replacement = "CAMERA_DEVICE_IDS=" + json.dumps(mapping.device_ids)
        lines = [line for line in lines if not line.strip().startswith("CAMERA_DEVICE_IDS=")]
        lines.append(replacement)
        temporary = env_path.with_name(env_path.name + ".tmp")
        try:
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temporary, env_path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary camera settings file")
            raise HTTPException(503, "Could not persist camera mapping") from exc

        # Update the existing settings object: modules holding it see the same mapping.
        # Recreating the cached object previously left startup and camera listing stale.
        settings.camera_device_ids = list(mapping.device_ids)
        camera_manager.release_all()
        camera_manager._device_ids = list(mapping.device_ids)
        camera_manager._labels = list(settings.camera_labels)
        results = await asyncio.to_thread(camera_manager.initialize)
        return {"message": "Camera mapping updated", "results": results}
