from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import cv2
import logging
import os
from typing import List
from pydantic import BaseModel

from app.services.camera_manager import camera_manager
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/cameras", tags=["Cameras"])


from app.api.deps import DbSession
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
    device_ids: List[int]

@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate):
    """
    Updates the CAMERA_DEVICE_IDS in .env, clears settings cache, 
    and restarts the camera manager.
    """
    env_path = ".env"
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    
    updated = False
    with open(env_path, "w") as f:
        for line in lines:
            if line.startswith("CAMERA_DEVICE_IDS="):
                f.write(f"CAMERA_DEVICE_IDS={mapping.device_ids}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"\nCAMERA_DEVICE_IDS={mapping.device_ids}\n")
                
    get_settings.cache_clear()
    new_settings = get_settings()
    
    camera_manager.release_all()
    camera_manager._device_ids = new_settings.camera_device_ids
    results = camera_manager.initialize()
    
    return {"message": "Camera mapping updated", "results": results}