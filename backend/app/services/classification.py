"""
YOLO classification wrapper.

Loads the trained YOLO model once and provides inference on banana images.
Detects cultivar (Lakatan/Latundan/Cardaba) and ripeness (Unripe/Semi Ripe/Ripe/Overripe).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.schemas.enums import CultivarEnum, RipenessEnum

logger = logging.getLogger(__name__)
settings = get_settings()
VOTE_CONFLICT_THRESHOLD = 0.60
# Calibrated on prepared VALID Top photos; see docs/yolo-dataset-audit-2026-10-16.md.
# A different checkpoint or custom confidence/NMS setting needs its own calibration.
TOP_OVERLAP_CHECKPOINT_SHA256 = (
    "e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89"
)
TOP_OVERLAP_CONFIDENCE = 0.50
TOP_OVERLAP_BASE_IOU = 0.45
TOP_OVERLAP_IOU = 0.65
TOP_ROTATION_DEDUP_IOU = 0.40


def _checkpoint_digest(path: str) -> str:
    """Identify the actual checkpoint once at load; filenames are not model identity."""
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


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
    conflict_detected: bool = False


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


def _box_iou(a: Detection, b: Detection) -> float:
    """Intersection-over-union between two Detection boxes."""
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    inter_w = max(0.0, min(ax2, bx2) - max(a.x, b.x))
    inter_h = max(0.0, min(ay2, by2) - max(a.y, b.y))
    inter = inter_w * inter_h
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


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
        self._checkpoint_sha256: str | None = None
        self._image_size = 640

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Load YOLO model from disk. Call once at startup."""
        self._checkpoint_sha256 = None
        try:
            from ultralytics import YOLO

            model_path = settings.yolo_model_path
            self._model_name = _model_name_from_path(model_path)
            logger.info(f"Loading {self._model_name} model from {model_path}")
            self._model = YOLO(model_path)
            self._loaded = True
            # Preserve the saved resolution of custom checkpoints as well.
            self._image_size = getattr(self._model, "overrides", {}).get("imgsz", 640)
            try:
                self._checkpoint_sha256 = _checkpoint_digest(model_path)
            except OSError:
                logger.warning(
                    "Checkpoint fingerprint unavailable; using standard overlap filtering"
                )

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

    def predict(
        self, image: np.ndarray, *, confidence_threshold: float,
        camera_label: str | None = None,
    ) -> ClassificationResult:
        """
        Run YOLO inference on a single image.

        Args:
            image: BGR numpy array (from OpenCV)
            camera_label: Configured camera view, independent of device/logical ID.

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

        if not 0 < confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be in (0, 1]")

        iou_threshold = settings.yolo_iou_threshold
        is_calibrated_top = (
            (camera_label or "").strip().casefold() == "top"
            and self._checkpoint_sha256 == TOP_OVERLAP_CHECKPOINT_SHA256
            and self._image_size == 640
            and confidence_threshold == TOP_OVERLAP_CONFIDENCE
            and iou_threshold == TOP_OVERLAP_BASE_IOU
        )
        if settings.yolo_top_overlap_refinement and is_calibrated_top:
            iou_threshold = TOP_OVERLAP_IOU

        try:
            results = self._model.predict(
                image,
                conf=confidence_threshold,
                iou=iou_threshold,
                # Ultralytics retains predictor arguments between calls. Set these
                # explicitly so a Top call cannot alter subsequent camera views.
                imgsz=self._image_size,
                augment=False,
                agnostic_nms=False,
                max_det=300,
                verbose=False,
            )
        except Exception as exc:
            raise ModelInferenceError(model_name, str(exc))

        elapsed_ms = (time.time() - start) * 1000

        detections: list[Detection] = []
        cultivar_votes: dict[str, list[float]] = {}
        class_votes: dict[tuple[str | None, str | None], list[float]] = {}

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
                    if cultivar or ripeness:
                        class_votes.setdefault((cultivar, ripeness), []).append(conf)

        # ── Rotation fallback: recover fingers missed in the original orientation ──
        if is_calibrated_top and getattr(settings, "yolo_top_rotation_fallback", False):
            img_h, img_w = image.shape[:2]
            rotated = image[::-1, ::-1].copy()
            try:
                rot_results = self._model.predict(
                    rotated,
                    conf=confidence_threshold,
                    iou=iou_threshold,
                    imgsz=self._image_size,
                    augment=False,
                    agnostic_nms=False,
                    max_det=300,
                    verbose=False,
                )
            except Exception:
                rot_results = None
            if rot_results and len(rot_results) > 0:
                rot_result = rot_results[0]
                if rot_result.boxes is not None:
                    pass1_detections = list(detections)
                    for box in rot_result.boxes:
                        rx1, ry1, rx2, ry2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = rot_result.names[cls_id]
                        # Remap 180-degree-rotated coordinates back to original space
                        ox1, oy1 = img_w - rx2, img_h - ry2
                        ox2, oy2 = img_w - rx1, img_h - ry1
                        candidate = Detection(
                            x=ox1, y=oy1, w=ox2 - ox1, h=oy2 - oy1,
                            cls=cls_name, confidence=conf,
                        )
                        if any(
                            _box_iou(candidate, existing) > TOP_ROTATION_DEDUP_IOU
                            for existing in pass1_detections
                        ):
                            continue
                        detections.append(candidate)
                        cultivar, ripeness = _parse_class_label(cls_name)
                        if cultivar:
                            cultivar_votes.setdefault(cultivar, []).append(conf)
                        if cultivar or ripeness:
                            class_votes.setdefault((cultivar, ripeness), []).append(conf)
            elapsed_ms = (time.time() - start) * 1000

        # Preserve cultivar consensus, then choose ripeness from that cultivar's
        # actual labels. Independent votes can invent a pair YOLO never detected.
        best_cultivar = self._best_vote(cultivar_votes)
        ripeness_votes = {
            ripeness: confs for (cultivar, ripeness), confs in class_votes.items()
            if cultivar == best_cultivar and ripeness
        }
        best_ripeness = self._best_vote(ripeness_votes)
        winning_confs = class_votes.get((best_cultivar, best_ripeness), [])
        avg_conf = (
            round(sum(winning_confs) / len(winning_confs) * 100, 1)
            if winning_confs else 0.0
        )
        total_weight = sum(sum(confs) for confs in class_votes.values())
        conflict_detected = (
            best_cultivar is None or best_ripeness is None
            or sum(winning_confs) < total_weight * VOTE_CONFLICT_THRESHOLD
        )

        return ClassificationResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=avg_conf,
            finger_count=len(detections),
            detections=detections,
            inference_time_ms=elapsed_ms,
            conflict_detected=conflict_detected,
        )

    def _best_vote(self, votes: dict[str, list[float]]) -> str | None:
        if not votes:
            return None
        return max(votes, key=lambda k: sum(votes[k]))

# Singleton instance
banana_classifier = BananaClassifier()
