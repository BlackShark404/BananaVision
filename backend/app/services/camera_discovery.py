"""Read capture-backend device metadata without opening camera streams."""
from __future__ import annotations

import hashlib
import logging
import sys

import cv2

from app.config import get_settings

logger = logging.getLogger(__name__)


def capture_backend(preference: str) -> tuple[str, int]:
    """Keep device enumeration and VideoCapture in the same index namespace."""
    if preference == "auto":
        preference = "dshow" if sys.platform == "win32" else "auto"
    return preference, {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(
        preference, cv2.CAP_ANY,
    )


def _enumerate_backend(api: int):
    # This library queries native device metadata; it does not create VideoCapture.
    from cv2_enumerate_cameras import enumerate_cameras

    return enumerate_cameras(api)


def discover_camera_devices() -> dict:
    backend, api = capture_backend(get_settings().camera_backend)
    if sys.platform != "win32":
        return {"backend": backend, "devices": [], "error":
                "Camera name discovery is available on Windows. Enter device indices manually."}
    try:
        cameras = _enumerate_backend(api)
        devices = []
        for camera in cameras:
            # Do not use friendly names as identity: identical USB cameras share names.
            path = camera.path or ""
            uid = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12] if path else None
            devices.append({"device_id": camera.index, "name": camera.name,
                            "device_uid": uid})
        return {"backend": backend, "devices": devices, "error": None}
    except ImportError:
        return {"backend": backend, "devices": [], "error":
                "Camera name discovery requires cv2-enumerate-cameras. "
                "Install backend requirements and restart the backend."}
    except Exception:
        logger.warning("Camera device metadata could not be enumerated", exc_info=True)
        return {"backend": backend, "devices": [], "error":
                "Camera device names could not be listed. Retry or enter device indices manually."}
