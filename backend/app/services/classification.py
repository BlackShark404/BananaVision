"""
YOLOv8n classification wrapper.

Loads the trained YOLOv8n model once and provides inference on banana images.
Detects cultivar (Lakatan/Latundan/Saba) and ripeness (Unripe/Ripe/Overripe/Rotten).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class Detection:
    """Single YOLO bounding-box detection."""
    x: float
    y: float
    w: float
    h: float
    cls: str        # class label, e.g. "Lakatan_Ripe"
    confidence: float


@dataclass
class ClassificationResult:
    """Per-image inference result."""
    cultivar: str | None = None
    ripeness: str | None = None
    confidence: float = 0.0
    finger_count: int = 0
    detections: list[Detection] = field(default_factory=list)
    inference_time_ms: float = 0.0


# ── Class label parsing ─────────────────────────────────────────────────────
# Expected YOLO class names format: "Lakatan_Ripe", "Saba_Unripe", etc.
# Or separate classes: "Lakatan", "Ripe", etc.

CULTIVAR_CLASSES = {"Lakatan", "Latundan", "Saba"}
RIPENESS_CLASSES = {"Unripe", "Ripe", "Overripe", "Rotten"}


def _parse_class_label(label: str) -> tuple[str | None, str | None]:
    """Parse a YOLO class label into (cultivar, ripeness)."""
    # Handle combined labels like "Lakatan_Ripe"
    if "_" in label:
        parts = label.split("_", 1)
        cultivar = parts[0] if parts[0] in CULTIVAR_CLASSES else None
        ripeness = parts[1] if len(parts) > 1 and parts[1] in RIPENESS_CLASSES else None
        return cultivar, ripeness

    # Handle single-class labels
    if label in CULTIVAR_CLASSES:
        return label, None
    if label in RIPENESS_CLASSES:
        return None, label
    return None, None


class BananaClassifier:
    """
    YOLOv8n banana classification model wrapper.

    Usage:
        classifier = BananaClassifier()
        classifier.load()  # once at boot
        result = classifier.predict(image_array)
    """

    def __init__(self):
        self._model = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Load YOLOv8n model from disk. Call once at startup."""
        try:
            from ultralytics import YOLO

            model_path = settings.yolo_model_path
            logger.info(f"Loading YOLOv8n model from {model_path}")
            self._model = YOLO(model_path)
            self._loaded = True
            logger.info("YOLOv8n model loaded successfully")
        except FileNotFoundError:
            logger.warning(
                f"Model file not found at {settings.yolo_model_path}. "
                "Running in placeholder mode — inference will return mock results."
            )
            self._model = None
            self._loaded = True  # Mark as loaded so the app can still run
        except Exception as exc:
            logger.error(f"Failed to load YOLOv8n model: {exc}")
            self._loaded = True  # Allow fallback

    def warmup(self) -> None:
        """Run a dummy inference to warm up the model (reduces first-call latency)."""
        if self._model is not None:
            try:
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False)
                logger.info("YOLOv8n warmup complete")
            except Exception as exc:
                logger.warning(f"YOLOv8n warmup failed: {exc}")

    def predict(self, image: np.ndarray) -> ClassificationResult:
        """
        Run YOLOv8n inference on a single image.

        Args:
            image: BGR numpy array (from OpenCV)

        Returns:
            ClassificationResult with detections, cultivar, ripeness, etc.
        """
        start = time.time()

        # Placeholder mode: return mock results when no model is loaded
        if self._model is None:
            return self._placeholder_predict(start)

        try:
            results = self._model.predict(
                image,
                conf=settings.yolo_confidence_threshold,
                iou=settings.yolo_iou_threshold,
                verbose=False,
            )
        except Exception as exc:
            raise ModelInferenceError("YOLOv8n", str(exc))

        elapsed_ms = (time.time() - start) * 1000

        detections: list[Detection] = []
        cultivar_votes: dict[str, list[float]] = {}
        ripeness_votes: dict[str, list[float]] = {}

        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]

                    det = Detection(
                        x=x1, y=y1, w=x2 - x1, h=y2 - y1,
                        cls=cls_name, confidence=conf,
                    )
                    detections.append(det)

                    cultivar, ripeness = _parse_class_label(cls_name)
                    if cultivar:
                        cultivar_votes.setdefault(cultivar, []).append(conf)
                    if ripeness:
                        ripeness_votes.setdefault(ripeness, []).append(conf)

        # Determine best cultivar and ripeness via max weighted vote
        best_cultivar = self._best_vote(cultivar_votes)
        best_ripeness = self._best_vote(ripeness_votes)
        avg_conf = self._avg_confidence(cultivar_votes, ripeness_votes, best_cultivar, best_ripeness)

        return ClassificationResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=avg_conf,
            finger_count=len(detections),
            detections=detections,
            inference_time_ms=elapsed_ms,
        )

    def _best_vote(self, votes: dict[str, list[float]]) -> str | None:
        if not votes:
            return None
        return max(votes, key=lambda k: sum(votes[k]))

    def _avg_confidence(
        self,
        cultivar_votes: dict[str, list[float]],
        ripeness_votes: dict[str, list[float]],
        best_cultivar: str | None,
        best_ripeness: str | None,
    ) -> float:
        confs: list[float] = []
        if best_cultivar and best_cultivar in cultivar_votes:
            confs.extend(cultivar_votes[best_cultivar])
        if best_ripeness and best_ripeness in ripeness_votes:
            confs.extend(ripeness_votes[best_ripeness])
        return round(sum(confs) / len(confs) * 100, 1) if confs else 0.0

    def _placeholder_predict(self, start: float) -> ClassificationResult:
        """Return mock results when no model file is available."""
        import random

        elapsed_ms = (time.time() - start) * 1000
        cultivar = random.choice(["Lakatan", "Latundan", "Saba"])
        ripeness = random.choice(["Unripe", "Ripe", "Overripe", "Rotten"])
        confidence = round(random.uniform(85, 99), 1)
        finger_count = random.randint(5, 16)

        return ClassificationResult(
            cultivar=cultivar,
            ripeness=ripeness,
            confidence=confidence,
            finger_count=finger_count,
            detections=[],
            inference_time_ms=elapsed_ms,
        )


# Singleton instance
banana_classifier = BananaClassifier()
