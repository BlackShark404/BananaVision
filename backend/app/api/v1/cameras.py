from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import cv2
import logging

from app.services.camera_manager import camera_manager
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get("")
async def list_cameras():
    """
    List all configured cameras with their device IDs and online status.
    No auth required — used by the kiosk to map cameras to preview streams.
    """
    result = []
    for idx, dev_id in enumerate(settings.camera_device_ids):
        label = settings.camera_labels[idx] if idx < len(settings.camera_labels) else f"CAM-{dev_id}"
        result.append({
            "device_id": dev_id,
            "label": label,
            "online": dev_id in camera_manager.online_cameras,
        })
    return result

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