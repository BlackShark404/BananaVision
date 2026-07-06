"""
Camera Manager — initializes and manages multi-camera capture pipeline.

Cameras are opened ONCE at boot and kept alive until shutdown to avoid
reinitialization delays (~1-3s per camera).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import get_settings
from app.core.exceptions import CameraError

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class CaptureResult:
    """Result of a single camera capture."""
    camera_index: int
    camera_id: str
    camera_label: str
    frame: np.ndarray
    timestamp: float
    file_path: str | None = None


class CameraManager:
    """
    Manages all USB webcams. Initialized once at boot, keeps handles open.

    Supports both parallel and sequential capture with automatic fallback.
    """

    def __init__(self):
        self._cameras: dict[int, cv2.VideoCapture] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._device_ids: list[int] = settings.camera_device_ids
        self._labels: list[str] = settings.camera_labels
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def online_cameras(self) -> list[int]:
        return [dev_id for dev_id, cap in self._cameras.items() if cap.isOpened()]

    def initialize(self) -> dict[int, bool]:
        """
        Open all cameras and set resolution. Called once at boot.

        Returns dict mapping device_id → success boolean.
        """
        results: dict[int, bool] = {}

        for dev_id in self._device_ids:
            try:
                cap = cv2.VideoCapture(dev_id)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.camera_resolution_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.camera_resolution_h)

                # Discard warmup frames to stabilize exposure/white-balance
                for _ in range(settings.camera_warmup_frames):
                    cap.read()

                if cap.isOpened():
                    self._cameras[dev_id] = cap
                    self._locks[dev_id] = threading.Lock()
                    results[dev_id] = True
                    logger.info(f"Camera {dev_id} ({self._get_label(dev_id)}) initialized OK")
                else:
                    results[dev_id] = False
                    logger.error(f"Camera {dev_id} failed to open")
            except Exception as exc:
                results[dev_id] = False
                logger.error(f"Camera {dev_id} init error: {exc}")

        self._initialized = True
        return results

    def _get_label(self, device_id: int) -> str:
        idx = self._device_ids.index(device_id) if device_id in self._device_ids else 0
        return self._labels[idx] if idx < len(self._labels) else f"CAM-{device_id}"

    def _get_camera_id(self, device_id: int) -> str:
        idx = self._device_ids.index(device_id) if device_id in self._device_ids else 0
        return f"CAM-{idx + 1:03d}"

    def _capture_single(self, device_id: int) -> CaptureResult:
        """Thread-safe single frame capture from one camera."""
        if device_id not in self._cameras:
            raise CameraError(device_id, "Camera not initialized")

        with self._locks[device_id]:
            ret, frame = self._cameras[device_id].read()
            if not ret or frame is None:
                raise CameraError(device_id, "Failed to read frame")

            return CaptureResult(
                camera_index=device_id,
                camera_id=self._get_camera_id(device_id),
                camera_label=self._get_label(device_id),
                frame=frame,
                timestamp=time.time(),
            )

    async def capture_parallel(self) -> list[CaptureResult]:
        """
        Capture from all online cameras simultaneously using thread pool.
        This is the recommended approach for consistent multi-view snapshots.
        """
        online = self.online_cameras
        if not online:
            raise CameraError("all", "No cameras online")

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=len(online)) as pool:
            futures = [
                loop.run_in_executor(pool, self._capture_single, dev_id)
                for dev_id in online
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        captures: list[CaptureResult] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Parallel capture partial failure: {result}")
            else:
                captures.append(result)

        if not captures:
            raise CameraError("all", "All cameras failed during parallel capture")

        return captures

    async def capture_sequential(self) -> list[CaptureResult]:
        """
        Sequential fallback: capture one camera at a time.
        """
        captures: list[CaptureResult] = []
        loop = asyncio.get_event_loop()

        for dev_id in self.online_cameras:
            try:
                result = await loop.run_in_executor(None, self._capture_single, dev_id)
                captures.append(result)
                await asyncio.sleep(0.15)  # Hardware breathing room for USB controller
            except CameraError as exc:
                logger.warning(f"Sequential capture failed for camera {dev_id}: {exc}")

        return captures

    async def capture_all(self) -> list[CaptureResult]:
        """
        Primary: parallel capture. Fallback: sequential on failure.
        """
        try:
            return await self.capture_parallel()
        except CameraError:
            logger.warning("Parallel capture failed, falling back to sequential")
            return await self.capture_sequential()

    def save_captures(
        self, captures: list[CaptureResult], scan_id: str
    ) -> list[CaptureResult]:
        """Save captured frames as JPEG files under captures/{scan_id}/."""
        scan_dir = settings.capture_path / scan_id
        scan_dir.mkdir(parents=True, exist_ok=True)

        for capture in captures:
            filename = f"{capture.camera_id}_{capture.camera_label.lower()}.jpg"
            file_path = scan_dir / filename
            cv2.imwrite(str(file_path), capture.frame)
            capture.file_path = str(file_path)
            logger.info(f"Saved capture: {file_path}")

        return captures

    def release_all(self):
        """Release all camera handles. Called on shutdown."""
        for dev_id, cap in self._cameras.items():
            try:
                cap.release()
                logger.info(f"Camera {dev_id} released")
            except Exception as exc:
                logger.warning(f"Error releasing camera {dev_id}: {exc}")
        self._cameras.clear()
        self._locks.clear()
        self._initialized = False


# Singleton instance
camera_manager = CameraManager()
