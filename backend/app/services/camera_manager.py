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
        self._logical_ids: list[str] = []

    def set_logical_ids(self, ids: list[str]) -> None:
        self._logical_ids = list(ids)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ── Frame validation thresholds ────────────────────────────────────────
    # USB cameras produce noisy near-black frames with mean ~3-8 and
    # stddev ~2-4 due to sensor dark current.  These thresholds must be
    # high enough to reject those while still accepting dim-but-real scenes.
    _MEAN_THRESHOLD = 15.0     # max channel mean must be above this
    _STDDEV_THRESHOLD = 8.0    # max channel stddev must be above this
    _VALIDATION_FRAMES = 3     # number of consecutive frames to check

    @property
    def online_cameras(self) -> list[int]:
        """Return device IDs whose handles are open.

        NOTE: This does NOT validate frame content — use probe_all() for
        thorough black-screen detection.  Kept lightweight so the MJPEG
        preview stream and scan pipeline can call it without consuming
        frames.
        """
        return [dev_id for dev_id, cap in self._cameras.items() if cap.isOpened()]

    def _is_frame_valid(self, frame: np.ndarray) -> bool:
        """Check a single frame is not solid black, a uniform solid color, or a noisy black screen."""
        mean, stddev = cv2.meanStdDev(frame)
        max_mean = float(np.max(mean))
        max_stddev = float(np.max(stddev))
        
        # Basic check for completely blank or completely uniform solid colors
        if max_mean < self._MEAN_THRESHOLD or max_stddev < self._STDDEV_THRESHOLD:
            return False
            
        # Strict visual validation check for noisy black screens
        # Convert to grayscale to evaluate overall brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # A valid frame must have a reasonable amount of pixels that are distinctly NOT black/dark.
        # Threshold at 30 (out of 255) to filter out dark noise.
        # If less than 1% of pixels are brighter than 30, it's effectively a black screen.
        non_dark_pixels = cv2.countNonZero(cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)[1])
        total_pixels = gray.size
        
        if non_dark_pixels < (total_pixels * 0.01):
            return False
            
        return True

    def _validate_feed(self, device_id: int) -> bool:
        """
        Thread-safe multi-frame validation — reads several consecutive
        frames and checks ALL are non-black / non-blank.

        Returns True only if every sampled frame contains a real image.
        """
        if device_id not in self._cameras:
            return False

        cap = self._cameras[device_id]
        if not cap.isOpened():
            return False

        with self._locks.get(device_id, threading.Lock()):
            try:
                for _ in range(self._VALIDATION_FRAMES):
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        return False
                    if not self._is_frame_valid(frame):
                        return False
                return True
            except Exception:
                return False

    def probe_all(self) -> dict[int, bool]:
        """
        Probe every configured camera. Returns device_id → is_truly_online.

        A camera is only 'online' if its handle is open AND it is
        producing real images (not black / solid-color) across multiple
        consecutive frames.
        """
        results: dict[int, bool] = {}
        for dev_id in self._device_ids:
            if dev_id in self._cameras and self._cameras[dev_id].isOpened():
                results[dev_id] = self._validate_feed(dev_id)
            else:
                results[dev_id] = False
        return results

    def initialize(self) -> dict[int, bool]:
        """
        Open all cameras and set resolution. Called once at boot.

        Each camera must produce multiple consecutive valid (non-black)
        frames to be considered online.

        Returns dict mapping device_id → success boolean.
        """
        results: dict[int, bool] = {}

        for dev_id in self._device_ids:
            try:
                cap = cv2.VideoCapture(dev_id)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.camera_resolution_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.camera_resolution_h)

                if not settings.camera_autofocus:
                    cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                    cap.set(cv2.CAP_PROP_FOCUS, settings.camera_manual_focus_value)
                else:
                    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)

                # Discard warmup frames to stabilize exposure/white-balance
                for _ in range(settings.camera_warmup_frames):
                    cap.read()

                if not cap.isOpened():
                    results[dev_id] = False
                    logger.error(f"Camera {dev_id} failed to open")
                    continue

                # Validate with multiple consecutive frames
                valid = True
                for i in range(self._VALIDATION_FRAMES):
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        logger.error(f"Camera {dev_id} failed to read validation frame {i + 1}")
                        valid = False
                        break
                    if not self._is_frame_valid(frame):
                        mean, stddev = cv2.meanStdDev(frame)
                        logger.error(
                            f"Camera {dev_id} frame {i + 1} failed validation "
                            f"(mean={float(np.max(mean)):.1f}, stddev={float(np.max(stddev)):.1f}) "
                            f"— black or blank feed detected. Discarding."
                        )
                        valid = False
                        break

                if valid:
                    self._cameras[dev_id] = cap
                    self._locks[dev_id] = threading.Lock()
                    results[dev_id] = True
                    logger.info(f"Camera {dev_id} ({self._get_label(dev_id)}) initialized OK")
                else:
                    cap.release()
                    results[dev_id] = False

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
        return self._logical_ids[idx] if idx < len(self._logical_ids) else f"CAM-{idx + 1:03d}"

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
            # Hardware index makes filenames independent of editable display labels.
            filename = f"camera_{capture.camera_index}.jpg"
            file_path = scan_dir / filename
            if not cv2.imwrite(str(file_path), capture.frame):
                raise CameraError(capture.camera_index, "Could not save captured image")
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
