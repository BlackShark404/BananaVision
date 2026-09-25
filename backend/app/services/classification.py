"""
YOLO classification wrapper.

Loads the trained YOLO model once and provides inference on banana images.
Detects cultivar (Lakatan/Latundan/Cardaba) and ripeness (Unripe/Semi Ripe/Ripe/Overripe).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.schemas.enums import CultivarEnum, RipenessEnum

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
# Roboflow/YOLO class names are all lowercase with underscores, e.g.:
#   "lakatan_ripe", "cardaba_semi_ripe", "latundan_overripe"
# We need case-insensitive lookup to map back to our enum values.

CULTIVAR_CLASSES = {c.value for c in CultivarEnum}
RIPENESS_CLASSES = {r.value for r in RipenessEnum}

# Case-insensitive lookup: lowercase → proper enum value
_CULTIVAR_LOOKUP = {c.value.lower(): c.value for c in CultivarEnum}
_RIPENESS_LOOKUP = {r.value.lower().replace(" ", "_"): r.value for r in RipenessEnum}


def _parse_class_label(label: str) -> tuple[str | None, str | None]:
    """Parse a YOLO class label into (cultivar, ripeness).

    Handles Roboflow-style lowercase labels:
        "lakatan_ripe"       → ("Lakatan", "Ripe")
        "lakatan_semi_ripe"  → ("Lakatan", "Semi Ripe")
        "cardaba_overripe"   → ("Cardaba", "Overripe")
        "lakatan"            → ("Lakatan", None)
        "ripe"               → (None, "Ripe")
    """
    label_lower = label.lower()

    # Handle combined labels like "lakatan_ripe" or "cardaba_semi_ripe"
    if "_" in label_lower:
        parts = label_lower.split("_", 1)
        cultivar = _CULTIVAR_LOOKUP.get(parts[0])

        ripeness = None
        if len(parts) > 1:
            # Ripeness portion may contain underscores (e.g. "semi_ripe")
            ripeness = _RIPENESS_LOOKUP.get(parts[1])

        return cultivar, ripeness

    # Handle single-class labels
    cultivar = _CULTIVAR_LOOKUP.get(label_lower)
    if cultivar:
        return cultivar, None
    ripeness = _RIPENESS_LOOKUP.get(label_lower)
    if ripeness:
        return None, ripeness
    return None, None


def _model_name_from_path(path: str) -> str:
    """Extract a human-readable model name from the weights file path.

    Example: 'app/ml/weights/banana_yolov26n.pt' → 'banana_yolov26n'
    """
    from pathlib import Path
    return Path(path).stem


class BananaClassifier:
    """
    YOLO banana classification model wrapper.

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
        """Load YOLO model from disk. Call once at startup."""
        try:
            from ultralytics import YOLO

            model_path = settings.yolo_model_path
            self._model_name = _model_name_from_path(model_path)
            logger.info(f"Loading {self._model_name} model from {model_path}")
            self._model = YOLO(model_path)
            self._loaded = True

            # Try to read extra info from the loaded model
            model_type = getattr(self._model, "task", None) or "detect"
            logger.info(
                f"{self._model_name} model loaded successfully "
                f"(task={model_type}, banana classifier)"
            )
        except FileNotFoundError:
            logger.error(
                f"Model file not found at {settings.yolo_model_path}. "
                "Inference will be unavailable until a valid model is provided."
            )
            self._model = None
            self._loaded = False
        except Exception as exc:
            logger.error(f"Failed to load YOLO model: {exc}")
            self._model = None
            self._loaded = False

    def warmup(self) -> None:
        """Run a dummy inference to warm up the model (reduces first-call latency)."""
        if self._model is not None:
            try:
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False)
                logger.info(f"{self._model_name} warmup complete")
            except Exception as exc:
                logger.warning(f"{self._model_name} warmup failed: {exc}")

    def predict(self, image: np.ndarray) -> ClassificationResult:
        """
        Run YOLO inference on a single image.

        Args:
            image: BGR numpy array (from OpenCV)

        Returns:
            ClassificationResult with detections, cultivar, ripeness, etc.
        """
        start = time.time()

        model_name = getattr(self, '_model_name', 'YOLO')
        if self._model is None:
            raise ModelInferenceError(
                model_name,
                "Model not loaded. Ensure a valid .pt model file is available.",
            )

        try:
            results = self._model.predict(
                image,
                conf=settings.yolo_confidence_threshold,
                iou=settings.yolo_iou_threshold,
                verbose=False,
            )
        except Exception as exc:
            raise ModelInferenceError(model_name, str(exc))

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




# Singleton instance
banana_classifier = BananaClassifier()
