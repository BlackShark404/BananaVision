"""
Banana pre-detection gate using base COCO-pretrained YOLOv26n.

Downloads and loads the standard yolo26n.pt model (COCO 80-class) to detect
whether a banana (COCO class 46) is present in the frame BEFORE running the
custom cultivar/ripeness classification model.

This prevents the pipeline from producing nonsensical results on images that
don't contain any bananas at all.

Each result also carries the banana boxes found at the lower support confidence.
The out-of-distribution gate (app.services.ood_gate) uses them to reject cultivar
boxes that no banana evidence covers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

from app.config import get_settings
from app.services.ood_gate import EvidenceBox

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
    # False when the detector could not run; banana_detected is then a legacy
    # pass-through value and the scan pipeline decides whether to fail closed.
    available: bool = True
    # Banana boxes at the support confidence; None when the detector did not run.
    boxes: list[EvidenceBox] | None = None


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

    # Default acceptance confidence; OOD_BANANA_CONFIDENCE overrides it.
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
            model_type = getattr(self._model, "task", None) or "detect"
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

    def detect(
        self, image: np.ndarray, *,
        accept_confidence: float | None = None,
        support_confidence: float | None = None,
    ) -> PreDetectionResult:
        """
        Check if at least one banana is present in the image.

        Args:
            image: BGR numpy array (from OpenCV)
            accept_confidence: Overrides OOD_BANANA_CONFIDENCE (offline evaluation).
            support_confidence: Overrides OOD_SUPPORT_CONFIDENCE (offline evaluation).

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
                banana_detected=True,  # Legacy pass-through; see `available`
                banana_count=0,
                best_confidence=0.0,
                inference_time_ms=0.0,
                available=False,
            )

        settings = get_settings()
        accept_conf = accept_confidence or settings.ood_banana_confidence
        # Weaker boxes are kept only as spatial support for cultivar boxes.
        support_conf = min(accept_conf, support_confidence or settings.ood_support_confidence)

        try:
            results = self._model.predict(
                image,
                conf=support_conf,
                classes=[BANANA_CLASS_ID],  # Only detect bananas
                verbose=False,
            )
        except Exception as exc:
            logger.error(f"Banana pre-detection failed: {exc}")
            return PreDetectionResult(
                banana_detected=True,  # Legacy pass-through; see `available`
                banana_count=0,
                best_confidence=0.0,
                inference_time_ms=(time.time() - start) * 1000,
                available=False,
            )

        elapsed_ms = (time.time() - start) * 1000

        banana_count = 0
        best_conf = 0.0
        boxes: list[EvidenceBox] = []

        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == BANANA_CLASS_ID:
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                        boxes.append(EvidenceBox(
                            x=x1, y=y1, w=x2 - x1, h=y2 - y1, confidence=conf,
                        ))
                        if conf >= accept_conf:
                            banana_count += 1
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
            boxes=boxes,
        )


# Singleton instance
banana_pre_detector = BananaPreDetector()
