"""
Banana pre-detection gate using base COCO-pretrained YOLOv26n.

Downloads and loads the standard yolo26n.pt model (COCO 80-class) to detect
whether a banana (COCO class 46) is present in the frame BEFORE running the
custom cultivar/ripeness classification model.

This prevents the pipeline from producing nonsensical results on images that
don't contain any bananas at all.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# COCO class index for "banana"
BANANA_CLASS_ID = 46


@dataclass
class PreDetectionResult:
    """Result of the banana pre-detection check."""
    banana_detected: bool
    banana_count: int = 0
    best_confidence: float = 0.0
    inference_time_ms: float = 0.0


class BananaPreDetector:
    """
    Base COCO YOLOv26n model that checks if a banana is present in the frame.

    On first load, ultralytics will auto-download `yolo26n.pt` (~6 MB) from
    the official repository if it's not already cached.

    Usage:
        detector = BananaPreDetector()
        detector.load()   # once at boot
        result = detector.detect(image_array)
        if result.banana_detected:
            # proceed with custom classification
    """

    # Minimum confidence to consider a banana detection valid
    CONFIDENCE_THRESHOLD = 0.30

    _COCO_MODEL = "yolo26n.pt"

    def __init__(self):
        self._model = None
        self._loaded = False
        self._model_name: str = "YOLO"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Load base COCO YOLO model. Auto-downloads on first run."""
        try:
            from pathlib import Path
            from ultralytics import YOLO

            self._model_name = Path(self._COCO_MODEL).stem  # e.g. "yolo26n"
            logger.info(f"Loading base COCO {self._model_name} model for banana pre-detection...")
            self._model = YOLO(self._COCO_MODEL)
            self._loaded = True

            # Try to read extra info from the loaded model
            model_type = getattr(self._model, "type", None) or "detect"
            logger.info(
                f"Base COCO {self._model_name} loaded successfully "
                f"(task={model_type}, banana pre-detector)"
            )
        except Exception as exc:
            logger.error(f"Failed to load base COCO {self._model_name}: {exc}")
            self._model = None
            self._loaded = False

    def warmup(self) -> None:
        """Run a dummy inference to warm up the model."""
        if self._model is not None:
            try:
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False)
                logger.info("Banana pre-detector warmup complete")
            except Exception as exc:
                logger.warning(f"Banana pre-detector warmup failed: {exc}")

    def detect(self, image: np.ndarray) -> PreDetectionResult:
        """
        Check if at least one banana is present in the image.

        Args:
            image: BGR numpy array (from OpenCV)

        Returns:
            PreDetectionResult indicating whether a banana was found.
        """
        start = time.time()

        if self._model is None:
            # If the pre-detector failed to load, pass through to avoid
            # blocking the pipeline (graceful degradation).
            logger.warning(
                "Banana pre-detector not loaded — skipping pre-detection check"
            )
            return PreDetectionResult(
                banana_detected=True,  # Assume banana present to not block
                banana_count=0,
                best_confidence=0.0,
                inference_time_ms=0.0,
            )

        try:
            results = self._model.predict(
                image,
                conf=self.CONFIDENCE_THRESHOLD,
                classes=[BANANA_CLASS_ID],  # Only detect bananas
                verbose=False,
            )
        except Exception as exc:
            logger.error(f"Banana pre-detection failed: {exc}")
            # Graceful degradation — let the pipeline continue
            return PreDetectionResult(
                banana_detected=True,
                banana_count=0,
                best_confidence=0.0,
                inference_time_ms=(time.time() - start) * 1000,
            )

        elapsed_ms = (time.time() - start) * 1000

        banana_count = 0
        best_conf = 0.0

        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == BANANA_CLASS_ID:
                        banana_count += 1
                        conf = float(box.conf[0])
                        best_conf = max(best_conf, conf)

        detected = banana_count > 0

        if detected:
            logger.info(
                f"Banana pre-detection: {banana_count} banana(s) found "
                f"(best conf: {best_conf:.2f}) in {elapsed_ms:.0f}ms"
            )
        else:
            logger.info(
                f"Banana pre-detection: NO banana detected in {elapsed_ms:.0f}ms"
            )

        return PreDetectionResult(
            banana_detected=detected,
            banana_count=banana_count,
            best_confidence=best_conf,
            inference_time_ms=elapsed_ms,
        )


# Singleton instance
banana_pre_detector = BananaPreDetector()
