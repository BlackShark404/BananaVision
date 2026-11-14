"""
YOLO classification wrapper.

Loads the trained YOLO model once and provides inference on banana images.
Detects cultivar (Lakatan/Latundan/Cardaba) and ripeness (Unripe/Semi Ripe/Ripe/Overripe).
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.schemas.enums import CultivarEnum, RipenessEnum
from app.services.ood_gate import EvidenceBox, is_supported

logger = logging.getLogger(__name__)
settings = get_settings()
VOTE_CONFLICT_THRESHOLD = 0.60
# Calibrated on prepared VALID Top photos; see docs/yolo-dataset-audit-2026-10-16.md.
# A different checkpoint or custom confidence/NMS setting needs its own calibration.
TOP_OVERLAP_CHECKPOINT_SHA256 = (
    "e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89"
)
TOP_CALIBRATED_CHECKPOINTS: dict[str, int] = {
    TOP_OVERLAP_CHECKPOINT_SHA256: 640,
    "96808fa8ed706909237197e8db2510dccabfaeceed85a4d1ab5182cd28c95f7b": 800,   # banana_yolov26n.pt
    "57ae6c0fe5bfe067f50cd8722823168e630fa99d35bc7905cc6a7010c02aaa41": 1024,  # banana_yolov26s.pt
    "dc171845fe353a2147f6c9219b27fa66df88902eb566eb141670cf4ee5d2b204": 640,   # banana_yolovn26V2.pt
    "9e21668e272bae8ea387d836bbc2b087b5fbb3ae90d375353f49105681e2f478": 640,   # banana_yolovsV2.pt
}
TOP_OVERLAP_CONFIDENCE = 0.50
TOP_OVERLAP_BASE_IOU = 0.45
TOP_OVERLAP_IOU = 0.65
TOP_ROTATION_DEDUP_IOU = 0.40
OCCLUDED_FINGER_RECOVERY_CONF = 0.25
OCCLUDED_FINGER_MIN_PRIMARY = 5
OCCLUDED_FINGER_MIN_AREA_RATIO = 0.22
# A box at least this many times longer than wide has a clear long axis (a finger seen
# from the side or from above); squarer boxes are tips, ends or whole hands.
FINGER_MIN_ELONGATION = 2.0
# One hand ripens together: its fingers sit within one stage of each other.
RIPENESS_STAGE = {"Unripe": 0, "Semi Ripe": 1, "Ripe": 2, "Overripe": 3}
# Table/platter lip seen from a side camera: a low, wide, weak box (Resolved Bugs #9).
PLATTER_LIP_TOP = 0.55
PLATTER_LIP_MAX_CONFIDENCE = 0.60
# Colour check (OpenCV HSV units: hue 0-179, saturation/value 0-255). Measured on the
# 16 station screenshots of 2026-11-14 with the overlay tint removed: finger peel had hue
# 28-80; the cut crown was bluish-grey (hue ~115, saturation ~55); the curtain behind the
# Left camera was dark (value ~30). Shaded fingers under the hand reach value ~45-55, so
# only value < 40 counts as dark background.
COLOUR_DARK_MAX_VALUE = 40
COLOUR_BLUE_MIN_HUE = 100
COLOUR_BLUE_MAX_HUE = 165
COLOUR_BLUE_MIN_SATURATION = 25
COLOUR_CENTRE_SHRINK = 0.20
COLOUR_SAMPLE_SIZE = 48


def _detection_head(yolo) -> object | None:
    """The Detect layer of an Ultralytics YOLO object, or None for anything else."""
    inner = getattr(yolo, "model", None)
    layers = getattr(inner, "model", None)
    if inner is None or not hasattr(inner, "end2end") or layers is None:
        return None
    try:
        return layers[-1]
    except (IndexError, KeyError, TypeError):
        return None


def _apply_inference_head(yolo, mode: str) -> str:
    """Fix which YOLO26 head runs, before the first prediction; return the head in use.

    Ultralytics 8.4.40 turns on the NMS-free one-to-one head of a YOLO26 checkpoint unless
    the file stores it off. NMS, `iou` and test-time augmentation are then skipped, and the
    first prediction fuses the one-to-many head away, so the choice cannot wait for a
    predict argument. "checkpoint" leaves the file's own behaviour untouched.
    Returns "one_to_many_nms", "one_to_one" or "unknown" (no Ultralytics detection head).
    """
    head = _detection_head(yolo)
    if head is None:
        return "unknown"
    inner = yolo.model
    if mode == "one_to_many_nms":
        if getattr(head, "cv2", None) is None:
            logger.error(
                "The one-to-many detection head was already fused away; reload the model "
                "to run it with NMS. Continuing with the NMS-free one-to-one head."
            )
        else:
            inner.end2end = False
    elif mode == "one_to_one":
        if getattr(head, "one2one_cv2", None) is None:
            logger.warning(
                "This checkpoint has no one-to-one head; it keeps running with NMS."
            )
        else:
            inner.end2end = True
    return "one_to_one" if bool(getattr(inner, "end2end", False)) else "one_to_many_nms"


def _head_predict_kwargs(head: str, mode: str) -> dict[str, bool]:
    """Repeat the chosen head on every predict call where this Ultralytics accepts it."""
    if mode == "checkpoint" or head == "unknown":
        return {}
    try:
        from ultralytics.cfg import DEFAULT_CFG_DICT
    except Exception:
        return {}
    if "end2end" not in DEFAULT_CFG_DICT:
        return {}
    return {"end2end": head == "one_to_one"}


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
    cultivar_conflict: bool = False
    # Cultivar boxes discarded because no banana evidence covered them.
    ood_rejected_boxes: int = 0
    # Boxes dropped because their ripeness is two or more stages away from the rest of
    # the hand (e.g. brown wood read as a ripe finger beside an unripe hand).
    ripeness_outlier_boxes: int = 0
    # Whole-hand boxes replaced by the side-by-side fingers they had hidden.
    hand_box_splits: int = 0
    # Boxes whose centre was mostly dark background or the bluish-grey cut crown.
    colour_rejected_boxes: int = 0


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


def _box_containment(a: Detection, b: Detection) -> float:
    """Intersection over the smaller box's area (containment ratio in [0, 1])."""
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    inter_w = max(0.0, min(ax2, bx2) - max(a.x, b.x))
    inter_h = max(0.0, min(ay2, by2) - max(a.y, b.y))
    inter = inter_w * inter_h
    min_area = min(a.w * a.h, b.w * b.h)
    return inter / min_area if min_area > 0 else 0.0


def _is_axially_aligned_or_enclosed(
    a: Detection, b: Detection, axis_tol: float = 0.08,
) -> bool:
    """True when two boxes share the same longitudinal axis (not diagonal neighbors)."""
    min_w = min(a.w, b.w)
    min_h = min(a.h, b.h)
    if min_w <= 0 or min_h <= 0:
        return True
    cx_a, cy_a = a.x + a.w / 2.0, a.y + a.h / 2.0
    cx_b, cy_b = b.x + b.w / 2.0, b.y + b.h / 2.0
    rel_dx = abs(cx_a - cx_b) / min_w
    rel_dy = abs(cy_a - cy_b) / min_h
    return min(rel_dx, rel_dy) <= axis_tol


def _unique_box_detections(detections: list[Detection]) -> list[Detection]:
    """Count coincident class hypotheses once, retaining raw boxes for review.

    Prevents coincident or heavily overlapping class hypotheses on the same
    physical finger from double-counting.
    """
    unique: list[Detection] = []
    for detection in detections:
        if not any(
            _is_same_class_sub_box(detection, existing)
            if detection.cls == existing.cls
            else (
                (detection.x == existing.x and detection.y == existing.y
                 and detection.w == existing.w and detection.h == existing.h)
                or _box_iou(detection, existing) >= 0.70
                or (
                    _box_containment(detection, existing) >= 0.85
                    and _is_axially_aligned_or_enclosed(detection, existing)
                )
            )
            for existing in unique
        ):
            unique.append(detection)
    return unique


def _is_same_class_sub_box(det: Detection, existing: Detection) -> bool:
    """Check if det is a nested fragment or severe duplicate of an existing same-class box.

    Distinguishes nested sub-boxes (which are significantly smaller than the parent
    box) and near-identical boxes from separate neighboring fingers of similar size.
    """
    if det.cls != existing.cls:
        return False
    if _box_iou(det, existing) >= 0.80:
        return True
    det_area = det.w * det.h
    exist_area = existing.w * existing.h
    min_area = min(det_area, exist_area)
    max_area = max(det_area, exist_area)
    if max_area > 0 and (min_area / max_area) <= 0.72:
        if (
            _box_containment(det, existing) >= 0.80
            and _is_axially_aligned_or_enclosed(det, existing)
        ):
            return True
    return False


def _is_cluster_box(det: Detection, others: list[Detection]) -> bool:
    """Detect whether det is an encompassing cluster box covering 2+ distinct fingers."""
    det_area = det.w * det.h
    if det_area <= 0 or not others:
        return False
    other_areas = [o.w * o.h for o in others if o.w * o.h > 0]
    if other_areas and det_area < 1.6 * float(np.median(other_areas)):
        return False
    contained = []
    for o in others:
        o_area = o.w * o.h
        if o_area <= 0:
            continue
        if det_area >= 1.6 * o_area and _box_containment(det, o) >= 0.70:
            contained.append(o)
    for i in range(len(contained)):
        for j in range(i + 1, len(contained)):
            if _box_iou(contained[i], contained[j]) < 0.40:
                return True
    return False


def _is_duplicate_detection(
    candidate: Detection,
    existing: Detection,
    iou_thresh: float = TOP_ROTATION_DEDUP_IOU,
) -> bool:
    """Determine whether candidate is a duplicate bounding box of an existing finger.

    Combines standard IoU with containment ratio and longitudinal axis alignment
    to prevent partial, shifted, or nested bounding boxes from double-counting
    elongated banana fingers.
    """
    if _box_iou(candidate, existing) > iou_thresh:
        return True

    cont = _box_containment(candidate, existing)
    if cont >= 0.75 and _is_axially_aligned_or_enclosed(candidate, existing):
        return True

    if cont >= 0.45:
        # "Same finger column": the centres must line up across the finger, i.e. along
        # x for an upright finger. For a finger lying sideways that is y; comparing x
        # there merged a lying finger with the one stacked on it.
        larger = candidate if candidate.w * candidate.h >= existing.w * existing.h else existing
        if (
            getattr(settings, "yolo_axis_aware_rotation_dedup", True)
            and _long_axis(larger) == "horizontal"
        ):
            min_h = min(candidate.h, existing.h)
            cy_cand = candidate.y + candidate.h / 2
            cy_exist = existing.y + existing.h / 2
            return min_h > 0 and abs(cy_cand - cy_exist) <= 0.25 * min_h
        min_w = min(candidate.w, existing.w)
        if min_w > 0:
            cx_cand = candidate.x + candidate.w / 2
            cx_exist = existing.x + existing.w / 2
            if abs(cx_cand - cx_exist) <= 0.25 * min_w:
                return True

    return False


def _long_axis(det: Detection) -> str | None:
    """'vertical' or 'horizontal' for a clearly elongated box, None for a squarish one."""
    if det.w <= 0 or det.h <= 0:
        return None
    if det.h >= FINGER_MIN_ELONGATION * det.w:
        return "vertical"
    if det.w >= FINGER_MIN_ELONGATION * det.h:
        return "horizontal"
    return None


def _side_by_side(a: Detection, b: Detection) -> bool:
    """Two separate fingers lying parallel next to each other (not one finger in pieces)."""
    axis = _long_axis(a)
    if axis is None or axis != _long_axis(b) or _box_iou(a, b) >= 0.40:
        return False
    dx = abs((a.x + a.w / 2) - (b.x + b.w / 2))
    dy = abs((a.y + a.h / 2) - (b.y + b.h / 2))
    return dx > dy if axis == "vertical" else dy > dx


def _hides_fingers(parent: Detection, children: list[Detection], others: list[Detection]) -> bool:
    """A whole-hand box that swallowed two or more side-by-side fingers as 'fragments'."""
    if len(children) < 2:
        return False
    if not any(_side_by_side(a, b) for a, b in combinations(children, 2)):
        return False
    return _is_cluster_box(parent, others + children)


def _is_platter_lip(x1: float, y1: float, x2: float, y2: float, conf: float,
                    img_h: int) -> bool:
    """Low, wide, weak box: the table or platter edge seen from a side camera."""
    return (
        y1 > PLATTER_LIP_TOP * img_h and (x2 - x1) > 2.0 * (y2 - y1)
        and conf < PLATTER_LIP_MAX_CONFIDENCE
    )


def _non_banana_fraction(image: np.ndarray, x1: float, y1: float, x2: float,
                         y2: float) -> float:
    """Share of the box centre that is clearly not banana peel: dark, or bluish/violet.

    Only the central region is read (20 % trimmed from each side), so the background in
    the corners of a diagonal finger's box does not count. Peel of every stage is
    green-to-yellow and bright; the station's dark curtain and the bluish-grey cut end of
    the crown are not.
    """
    import cv2

    if image is None or image.ndim != 3 or image.shape[2] != 3:
        return 0.0
    img_h, img_w = image.shape[:2]
    w, h = x2 - x1, y2 - y1
    cx1 = min(max(0, int(x1 + COLOUR_CENTRE_SHRINK * w)), img_w)
    cy1 = min(max(0, int(y1 + COLOUR_CENTRE_SHRINK * h)), img_h)
    cx2 = min(max(0, int(round(x2 - COLOUR_CENTRE_SHRINK * w))), img_w)
    cy2 = min(max(0, int(round(y2 - COLOUR_CENTRE_SHRINK * h))), img_h)
    crop = image[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return 0.0
    if crop.shape[0] > COLOUR_SAMPLE_SIZE or crop.shape[1] > COLOUR_SAMPLE_SIZE:
        crop = cv2.resize(
            crop, (min(COLOUR_SAMPLE_SIZE, crop.shape[1]), min(COLOUR_SAMPLE_SIZE, crop.shape[0])),
            interpolation=cv2.INTER_AREA,
        )
    hsv = cv2.cvtColor(np.ascontiguousarray(crop, dtype=np.uint8), cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    dark = value < COLOUR_DARK_MAX_VALUE
    bluish = (
        (hue >= COLOUR_BLUE_MIN_HUE) & (hue <= COLOUR_BLUE_MAX_HUE)
        & (saturation >= COLOUR_BLUE_MIN_SATURATION) & ~dark
    )
    return float((dark | bluish).mean())


def _ripeness_stage(det: Detection) -> int | None:
    return RIPENESS_STAGE.get(_parse_class_label(det.cls)[1] or "")


def _ripeness_outliers(detections: list[Detection]) -> list[Detection]:
    """Boxes two or more ripeness stages away from a clear majority of the hand.

    One hand ripens together, so an "unripe" hand with one "ripe" box most likely holds a
    non-banana object (brown wood read as a ripe finger, for example). Acts only when the
    majority is a clear, coherent hand: one stage holds the most confidence, at least two
    separate boxes lie within one stage of it, they outnumber the far boxes, carry at least
    60 % of the confidence, and at least 60 % of their weight names one cultivar. A far
    box is dropped when it is less confident than the best majority box, or when it
    touches none of the majority's boxes, unless the hand also has fingers at the stage in
    between (a hand ripening across stages keeps all of them).
    """
    staged = [(d, stage) for d in detections if (stage := _ripeness_stage(d)) is not None]
    weight: dict[int, float] = defaultdict(float)
    for d, stage in staged:
        weight[stage] += d.confidence
    if not weight:
        return []
    top = max(weight.values())
    anchors = [stage for stage, w in weight.items() if math.isclose(w, top)]
    if len(anchors) != 1:
        return []
    anchor = anchors[0]
    near = [d for d, stage in staged if abs(stage - anchor) <= 1]
    far = [d for d, stage in staged if abs(stage - anchor) >= 2]
    if not far:
        return []
    near_count = len(_unique_box_detections(near))
    if near_count < 2 or near_count <= len(_unique_box_detections(far)):
        return []
    near_weight = sum(d.confidence for d in near)
    if near_weight < VOTE_CONFLICT_THRESHOLD * sum(weight.values()):
        return []
    by_cultivar: dict[str, float] = defaultdict(float)
    for d in near:
        by_cultivar[_parse_class_label(d.cls)[0] or ""] += d.confidence
    if max(by_cultivar.values()) < VOTE_CONFLICT_THRESHOLD * near_weight:
        return []
    best = max(d.confidence for d, stage in staged if stage == anchor)
    present = {stage for _, stage in staged}
    outliers = []
    for d in far:
        stage = _ripeness_stage(d)
        # A hand with fingers at the stage in between is ripening across stages, not
        # holding a foreign object: its far fingers are real.
        between = range(min(stage, anchor) + 1, max(stage, anchor))
        if any(s in present for s in between):
            continue
        if d.confidence < best or not any(_box_iou(d, n) > 0 for n in near):
            outliers.append(d)
    return outliers


def _is_recovery_duplicate(cand: Detection, existing: Detection) -> bool:
    """True when a TTA recovery candidate duplicates an existing detection."""
    if _box_iou(cand, existing) >= TOP_OVERLAP_IOU:
        return True
    if _is_same_class_sub_box(cand, existing) or _is_same_class_sub_box(existing, cand):
        return True
    if _box_containment(cand, existing) >= 0.80:
        min_w, min_h = min(cand.w, existing.w), min(cand.h, existing.h)
        cx_c, cy_c = cand.x + cand.w / 2.0, cand.y + cand.h / 2.0
        cx_e, cy_e = existing.x + existing.w / 2.0, existing.y + existing.h / 2.0
        if abs(cx_c - cx_e) <= 0.25 * min_w and abs(cy_c - cy_e) <= 0.25 * min_h:
            return True
    return False


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
        self._inference_head = "unknown"
        # Sent with every predict call; empty for test doubles and "checkpoint" mode.
        self._head_kwargs: dict[str, bool] = {}

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def inference_head(self) -> str:
        """Detection head in use: one_to_many_nms, one_to_one or unknown."""
        return self._inference_head

    def load(self) -> None:
        """Load YOLO model from disk. Call once at startup."""
        self._checkpoint_sha256 = None
        self._inference_head = "unknown"
        self._head_kwargs = {}
        try:
            from ultralytics import YOLO

            model_path = settings.yolo_model_path
            self._model_name = _model_name_from_path(model_path)
            logger.info(f"Loading {self._model_name} model from {model_path}")
            self._model = YOLO(model_path)
            # Before warmup: the first prediction fixes the head for this model object.
            mode = getattr(settings, "yolo_inference_head", "one_to_many_nms")
            self._inference_head = _apply_inference_head(self._model, mode)
            self._head_kwargs = _head_predict_kwargs(self._inference_head, mode)
            self._loaded = True
            # Preserve the saved resolution of custom checkpoints as well.
            self._image_size = getattr(self._model, "overrides", {}).get("imgsz", 640)
            try:
                self._checkpoint_sha256 = _checkpoint_digest(model_path)
            except OSError:
                logger.warning(
                    "Checkpoint fingerprint unavailable; using standard overlap filtering"
                )
            logger.info(f"{self._model_name} detection head: {self._inference_head}")
            if (
                self._inference_head == "one_to_one"
                and self._checkpoint_sha256 in TOP_CALIBRATED_CHECKPOINTS
            ):
                logger.warning(
                    "Registered checkpoint runs the NMS-free one-to-one head: the calibrated "
                    "IoU settings and the recovery pass's test-time augmentation have no "
                    "effect. Set YOLO_INFERENCE_HEAD=one_to_many_nms to run it as measured."
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
            self._inference_head = "unknown"
            self._head_kwargs = {}
        except Exception as exc:
            logger.error(f"Failed to load YOLO model: {exc}")
            self._model = None
            self._loaded = False
            self._inference_head = "unknown"
            self._head_kwargs = {}

    def warmup(self) -> None:
        """Run a dummy inference to warm up the model (reduces first-call latency)."""
        if self._model is not None:
            try:
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False, **self._head_kwargs)
                logger.info(f"{self._model_name} warmup complete")
            except Exception as exc:
                logger.warning(f"{self._model_name} warmup failed: {exc}")

    def predict(
        self, image: np.ndarray, *, confidence_threshold: float,
        camera_label: str | None = None,
        banana_evidence: list[EvidenceBox] | None = None,
        support_margin: float = 0.25,
    ) -> ClassificationResult:
        """
        Run YOLO inference on a single image.

        Args:
            image: BGR numpy array (from OpenCV)
            camera_label: Configured camera view, independent of device/logical ID.
            banana_evidence: Banana boxes from the general detector for this frame.
                When given, cultivar boxes outside that evidence are rejected as
                out-of-distribution. None keeps every box.
            support_margin: Relative growth of each evidence box before the check.

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

        head_kwargs = getattr(self, "_head_kwargs", {})
        iou_threshold = settings.yolo_iou_threshold
        expected_imgsz = TOP_CALIBRATED_CHECKPOINTS.get(self._checkpoint_sha256 or "")
        is_calibrated_top = (
            (camera_label or "").strip().casefold() == "top"
            and expected_imgsz is not None
            and self._image_size == expected_imgsz
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
                **head_kwargs,
            )
        except Exception as exc:
            raise ModelInferenceError(model_name, str(exc))

        elapsed_ms = (time.time() - start) * 1000

        detections: list[Detection] = []
        cultivar_votes: dict[str, list[float]] = {}
        class_votes: dict[tuple[str | None, str | None], list[float]] = {}
        duplicate_label_conflict = False
        # OOD gate: a cultivar box that no banana evidence covers is treated as if the
        # model had never emitted it. In every pass it is skipped right after the
        # filters that judge a box on its own (position, size, label) and before any
        # rule that compares it with other boxes, so it cannot vote, count as a finger
        # or influence another box.
        # `off_banana` only counts the distinct boxes the gate actually removed.
        off_banana: list[Detection] = []
        norm_cam = (camera_label or "").strip().casefold()
        lip_views = (
            ("left", "right", "rear")
            if getattr(settings, "yolo_side_view_lip_filter", True) else ("rear",)
        )
        hand_split = getattr(settings, "yolo_hand_box_split", True)
        # A minimal settings object without the field keeps the earlier behaviour (off).
        colour_check = getattr(settings, "yolo_colour_check", False) and image is not None
        max_non_banana = getattr(settings, "yolo_colour_check_max_non_banana", 0.55)
        # Distinct boxes dropped because their centre is not banana colour.
        colour_rejected: list[Detection] = []

        def off_colour(box: Detection, dropped_anyway=None) -> bool:
            """A box over the crown or dark background: judged on its own pixels.

            dropped_anyway(box, kept): the pass's own repeat rule. A box the pass would drop
            anyway is skipped without counting, so it cannot flag a scan for nothing (as
            with the OOD gate).
            """
            if not colour_check or _parse_class_label(box.cls)[1] == "Overripe":
                return False  # overripe peel really is dark brown
            fraction = _non_banana_fraction(image, box.x, box.y, box.x + box.w, box.y + box.h)
            if fraction < max_non_banana:
                return False
            if not (
                (dropped_anyway is not None
                 and any(dropped_anyway(box, kept) for kept in detections))
                or any(
                    _is_same_class_sub_box(box, seen) or _is_duplicate_detection(box, seen)
                    for seen in colour_rejected
                )
            ):
                colour_rejected.append(box)
            return True
        # Pass-1 boxes dropped as "fragments" of a kept box, by parent: those on banana
        # evidence (`swallowed`) and those the gate set aside without counting (`exempt`).
        swallowed: dict[int, list[Detection]] = {}
        exempt: dict[int, list[Detection]] = {}

        def count_off_banana(box: Detection) -> None:
            if not any(
                _is_same_class_sub_box(box, seen) or _is_duplicate_detection(box, seen)
                for seen in off_banana
            ):
                off_banana.append(box)

        def rejected_by_gate(box: Detection, dropped_anyway=None) -> bool:
            """dropped_anyway(box, kept): the pass's own rule for repeats of a kept box.

            Without it every skipped box counts. The rotated Top pass needs that: a
            repeat there still feeds the orientation decision and the label-conflict
            check, so skipping it can change the result.
            """
            if banana_evidence is None or is_supported(box, banana_evidence, support_margin):
                return False
            # Not an intervention when this pass would have dropped the box anyway as
            # a repeat of an accepted detection, or when the object is already counted.
            if not (dropped_anyway is not None
                    and any(dropped_anyway(box, kept) for kept in detections)):
                count_off_banana(box)
            return True

        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                raw_boxes = sorted(result.boxes, key=lambda b: float(b.conf[0]), reverse=True)
                for box in raw_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]

                    det = Detection(
                        x=x1, y=y1, w=x2 - x1, h=y2 - y1,
                        cls=cls_name, confidence=conf,
                    )
                    # Suppress the table lip / platter edge seen by the side cameras
                    if (
                        norm_cam in lip_views and image is not None
                        and _is_platter_lip(x1, y1, x2, y2, conf, image.shape[0])
                    ):
                        continue

                    # Suppress upper background fixtures (door frames, window jambs, ceiling)
                    # on peripheral side and rear cameras. Real banana fingers on the inspection
                    # platter sit in the middle-to-lower portion of the frame.
                    if (
                        getattr(settings, "yolo_peripheral_background_filter", True)
                        and norm_cam in ("left", "right", "rear")
                        and image is not None
                    ):
                        img_h = image.shape[0]
                        det_h = y2 - y1
                        det_w = x2 - x1
                        # 1. Boxes entirely in the upper background (sky / ceiling):
                        if y2 < 0.22 * img_h:
                            continue
                        # 2. Slender background pillars or door frames ending in the upper/mid area:
                        if (
                            det_w > 0 and (det_h / det_w) >= 2.2 and y2 <= 0.55 * img_h
                        ) or (
                            y1 < 0.08 * img_h and det_w > 0
                            and (det_h / det_w) >= 2.5 and y2 < 0.65 * img_h
                        ):
                            continue

                    if off_colour(det, _is_same_class_sub_box):
                        continue

                    if rejected_by_gate(det, _is_same_class_sub_box):
                        if hand_split:
                            for parent in detections:
                                if _is_same_class_sub_box(det, parent):
                                    exempt.setdefault(id(parent), []).append(det)
                        continue

                    # Suppress same-class nested duplicate boxes or severe IoU duplicates.
                    parents = [p for p in detections if _is_same_class_sub_box(det, p)]
                    if parents:
                        if hand_split:
                            for parent in parents:
                                swallowed.setdefault(id(parent), []).append(det)
                        continue

                    detections.append(det)

                    cultivar, ripeness = _parse_class_label(cls_name)
                    if cultivar:
                        cultivar_votes.setdefault(cultivar, []).append(conf)
                    if cultivar or ripeness:
                        class_votes.setdefault((cultivar, ripeness), []).append(conf)

        # ── Rotation fallback: recover fingers missed in the original orientation ──
        rot_is_canonical = False
        # Boxes the rotated pass added beside the pass-1 boxes (not a canonical swap).
        rotated_added: set[int] = set()
        rotated: np.ndarray | None = None
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
                    **head_kwargs,
                )
            except Exception:
                rot_results = None
            if rot_results and len(rot_results) > 0:
                rot_result = rot_results[0]
                if rot_result.boxes is not None:
                    rot_boxes = sorted(rot_result.boxes, key=lambda b: float(b.conf[0]), reverse=True)
                    rot_candidates: list[Detection] = []
                    rot_cultivar_votes: dict[str, list[float]] = {}
                    for box in rot_boxes:
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
                        if off_colour(candidate):
                            continue
                        if rejected_by_gate(candidate):
                            continue
                        if any(_is_same_class_sub_box(candidate, existing) for existing in rot_candidates):
                            continue
                        rot_candidates.append(candidate)
                        rot_cult, _ = _parse_class_label(cls_name)
                        if rot_cult:
                            rot_cultivar_votes.setdefault(rot_cult, []).append(conf)

                    # Top-view training images have the crown at the top of the frame.
                    # When a hand is placed with the crown at the bottom (180° inverted),
                    # the rotated pass produces a higher-confidence canonical consensus.
                    orig_best_cult = self._best_vote(cultivar_votes)
                    rot_best_cult = self._best_vote(rot_cultivar_votes)
                    orig_max_conf = max((d.confidence for d in detections), default=0.0)
                    rot_max_conf = max((d.confidence for d in rot_candidates), default=0.0)
                    rot_total_weight = sum(sum(v) for v in rot_cultivar_votes.values())
                    rot_win_weight = sum(rot_cultivar_votes.get(rot_best_cult or "", []))
                    rot_unconflicted = (
                        rot_best_cult is not None
                        and rot_total_weight > 0
                        and rot_win_weight >= rot_total_weight * VOTE_CONFLICT_THRESHOLD
                    )
                    if (
                        len(rot_candidates) >= 3
                        and rot_unconflicted
                        and rot_best_cult != orig_best_cult
                        and rot_max_conf > orig_max_conf
                    ):
                        rot_is_canonical = True
                        orig_detections = detections
                        detections = []
                        cultivar_votes = {}
                        class_votes = {}
                        primary_cls = rot_candidates[0].cls
                        for cand in rot_candidates:
                            detections.append(cand)
                            cultivar, ripeness = _parse_class_label(cand.cls)
                            if cultivar:
                                cultivar_votes.setdefault(cultivar, []).append(cand.confidence)
                            if cultivar or ripeness:
                                class_votes.setdefault((cultivar, ripeness), []).append(cand.confidence)
                        for orig_det in orig_detections:
                            if any(
                                _is_duplicate_detection(orig_det, existing, TOP_ROTATION_DEDUP_IOU)
                                for existing in detections
                            ):
                                continue
                            harmonized = Detection(
                                x=orig_det.x, y=orig_det.y, w=orig_det.w, h=orig_det.h,
                                cls=primary_cls, confidence=orig_det.confidence,
                            )
                            detections.append(harmonized)
                            cultivar, ripeness = _parse_class_label(primary_cls)
                            if cultivar:
                                cultivar_votes.setdefault(cultivar, []).append(harmonized.confidence)
                            if cultivar or ripeness:
                                class_votes.setdefault((cultivar, ripeness), []).append(harmonized.confidence)
                    else:
                        for candidate in rot_candidates:
                            # Check against all accepted detections (pass 1 and newly accepted)
                            # using robust containment and spatial alignment
                            duplicates = [
                                existing for existing in detections
                                if _is_duplicate_detection(
                                    candidate, existing, TOP_ROTATION_DEDUP_IOU,
                                )
                            ]
                            if duplicates:
                                # Suppression must not conceal cultivar/ripeness disagreement
                                # between orientations of the same boxed finger.
                                candidate_label = _parse_class_label(candidate.cls)
                                duplicate_label_conflict = duplicate_label_conflict or any(
                                    candidate_label != _parse_class_label(existing.cls)
                                    for existing in duplicates
                                )
                                continue
                            detections.append(candidate)
                            rotated_added.add(id(candidate))
                            cultivar, ripeness = _parse_class_label(candidate.cls)
                            if cultivar:
                                cultivar_votes.setdefault(cultivar, []).append(candidate.confidence)
                            if cultivar or ripeness:
                                class_votes.setdefault((cultivar, ripeness), []).append(candidate.confidence)
            elapsed_ms = (time.time() - start) * 1000

        # ── Whole-hand box hiding side-by-side fingers ──
        # Pass 1 drops a box inside a more confident same-label box as a fragment. A
        # whole-hand box therefore hid its fingers before the cluster rule could see
        # them. Replace such a box with the fingers it hid (they count, they do not vote).
        restored: list[Detection] = []
        hand_box_splits = 0

        def plan_split(hidden: dict[int, list[Detection]]):
            """Hand boxes to dissolve and the fingers to restore, in confidence order."""
            dissolved = {
                id(parent) for parent in detections
                if _hides_fingers(parent, hidden.get(id(parent), []),
                                  [d for d in detections if d is not parent])
            }
            remaining = [d for d in detections if id(d) not in dissolved]
            kept: list[Detection] = []
            candidates = sorted(
                {id(k): k for pid in dissolved for k in hidden.get(pid, [])}.values(),
                key=lambda d: d.confidence, reverse=True,
            )
            for kid in candidates:
                if any(
                    pid not in dissolved and any(k is kid for k in kids)
                    for pid, kids in hidden.items()
                ):
                    continue  # still inside a box that stays
                if any(_is_same_class_sub_box(kid, d) for d in remaining + kept):
                    continue
                # The rotated Top pass may already hold this finger (checked against
                # the hand box only); use that pass's own repeat rule.
                if any(
                    _is_duplicate_detection(kid, d, TOP_ROTATION_DEDUP_IOU)
                    for d in remaining if id(d) in rotated_added
                ):
                    continue
                kept.append(kid)
            return dissolved, kept

        if hand_split and (swallowed or exempt):
            dissolved, restored = plan_split(swallowed)
            if exempt:
                # Without the gate the off-evidence fragments would have been ordinary
                # fragments. When that changes the split, the gate changed the count:
                # an intervention, so the scan is flagged.
                merged = {
                    pid: swallowed.get(pid, []) + exempt.get(pid, [])
                    for pid in set(swallowed) | set(exempt)
                }
                ungated_dissolved, ungated_restored = plan_split(merged)
                if (ungated_dissolved != dissolved
                        or [id(k) for k in ungated_restored] != [id(k) for k in restored]):
                    gated_kids = [k for kids in exempt.values() for k in kids]
                    changed = [k for k in ungated_restored if any(k is g for g in gated_kids)]
                    for kid in changed or [
                        k for pid in ungated_dissolved ^ dissolved for k in exempt.get(pid, [])
                    ] or gated_kids:
                        count_off_banana(kid)
            if dissolved:
                detections = [d for d in detections if id(d) not in dissolved] + restored
                hand_box_splits = len(dissolved)

        # ── Ripeness outliers: a non-banana object read as a finger of another stage ──
        outliers: list[Detection] = []
        if getattr(settings, "yolo_ripeness_outlier_filter", True):
            outliers = _ripeness_outliers(detections)
            for det in outliers:
                detections = [d for d in detections if d is not det]
                if any(det is r for r in restored):
                    continue  # restored fingers never voted
                cultivar, ripeness = _parse_class_label(det.cls)
                for votes, key in ((cultivar_votes, cultivar), (class_votes, (cultivar, ripeness))):
                    confs = votes.get(key) if (cultivar or ripeness) else None
                    if confs and det.confidence in confs:
                        confs.remove(det.confidence)
                        if not confs:
                            del votes[key]
            if outliers:
                logger.info(
                    "Dropped %s box(es) with inconsistent ripeness on %s: %s",
                    len(outliers), camera_label or "camera",
                    [(d.cls, round(d.confidence, 2)) for d in outliers],
                )

        # ── Occluded flank / second-tier finger recovery for multi-finger bunches ──
        if (
            expected_imgsz is not None
            and self._image_size == expected_imgsz
            and confidence_threshold == TOP_OVERLAP_CONFIDENCE
            and len(detections) >= OCCLUDED_FINGER_MIN_PRIMARY
            and not duplicate_label_conflict
            and image is not None
        ):
            primary_cultivar = self._best_vote(cultivar_votes)
            primary_ripeness_votes = {
                ripeness: confs for (cultivar, ripeness), confs in class_votes.items()
                if cultivar == primary_cultivar and ripeness
            }
            primary_ripeness = self._best_vote(primary_ripeness_votes)
            primary_total_w = sum(sum(v) for v in cultivar_votes.values())
            primary_win_w = sum(cultivar_votes.get(primary_cultivar or "", []))
            if (
                primary_cultivar
                and primary_ripeness
                and primary_total_w > 0
                and primary_win_w >= primary_total_w * VOTE_CONFLICT_THRESHOLD
            ):
                median_area = float(np.median([d.w * d.h for d in detections]))
                # Hidden fingers lie within the hand: along the fingers' length inside the
                # span of the confident fingers, across it at most one finger beside them.
                # (A box above the tips of upright fingers is background, e.g. a window.)
                upright = float(np.median(
                    [d.h / d.w for d in detections if d.w > 0] or [1.0]
                )) >= 1.0
                beside_x = float(np.median([d.w for d in detections])) if upright else 0.0
                beside_y = 0.0 if upright else float(np.median([d.h for d in detections]))
                hand_x1 = min(d.x for d in detections) - beside_x
                hand_y1 = min(d.y for d in detections) - beside_y
                hand_x2 = max(d.x + d.w for d in detections) + beside_x
                hand_y2 = max(d.y + d.h for d in detections) + beside_y
                within_hand = getattr(settings, "yolo_recovery_within_hand", True)
                adjacent = getattr(settings, "yolo_recovery_adjacent_ripeness", False)
                primary_stage = RIPENESS_STAGE.get(primary_ripeness)
                recovery_frame = rotated if (rot_is_canonical and rotated is not None) else image
                img_h, img_w = image.shape[:2]
                try:
                    rec_results = self._model.predict(
                        recovery_frame,
                        conf=OCCLUDED_FINGER_RECOVERY_CONF,
                        iou=0.70,
                        imgsz=self._image_size,
                        augment=True,
                        agnostic_nms=False,
                        max_det=300,
                        verbose=False,
                        **head_kwargs,
                    )
                except Exception:
                    rec_results = None
                if rec_results and len(rec_results) > 0 and rec_results[0].boxes is not None:
                    rec_boxes = sorted(
                        rec_results[0].boxes, key=lambda b: float(b.conf[0]), reverse=True,
                    )
                    for box in rec_boxes:
                        bx1, by1, bx2, by2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = rec_results[0].names[cls_id]
                        if rot_is_canonical:
                            x1, y1 = img_w - bx2, img_h - by2
                            x2, y2 = img_w - bx1, img_h - by1
                        else:
                            x1, y1, x2, y2 = bx1, by1, bx2, by2
                        det_w, det_h = x2 - x1, y2 - y1
                        if det_w * det_h < OCCLUDED_FINGER_MIN_AREA_RATIO * median_area:
                            continue
                        label = _parse_class_label(cls_name)
                        if label != (primary_cultivar, primary_ripeness):
                            stage = RIPENESS_STAGE.get(label[1] or "")
                            if not (
                                adjacent and label[0] == primary_cultivar
                                and stage is not None and primary_stage is not None
                                and abs(stage - primary_stage) == 1
                            ):
                                continue
                        if within_hand and not (
                            hand_x1 <= x1 + det_w / 2 <= hand_x2
                            and hand_y1 <= y1 + det_h / 2 <= hand_y2
                        ):
                            continue
                        if norm_cam in lip_views and _is_platter_lip(x1, y1, x2, y2, conf, img_h):
                            continue
                        if (
                            getattr(settings, "yolo_peripheral_background_filter", True)
                            and norm_cam in ("left", "right", "rear")
                        ):
                            if y2 < 0.22 * img_h:
                                continue
                            if (
                                det_w > 0 and (det_h / det_w) >= 2.2 and y2 <= 0.55 * img_h
                            ) or (
                                y1 < 0.08 * img_h and det_w > 0
                                and (det_h / det_w) >= 2.5 and y2 < 0.65 * img_h
                            ):
                                continue
                        cand = Detection(
                            x=x1, y=y1, w=det_w, h=det_h,
                            cls=cls_name, confidence=conf,
                        )
                        if off_colour(cand, _is_recovery_duplicate):
                            continue
                        if rejected_by_gate(cand, _is_recovery_duplicate):
                            continue
                        if any(_is_recovery_duplicate(cand, existing) for existing in detections):
                            continue
                        detections.append(cand)
                elapsed_ms = (time.time() - start) * 1000

        # Suppress cluster boxes that encompass 2+ distinct individual fingers
        if len(detections) >= 3:
            detections = [
                det for det in detections
                if not _is_cluster_box(det, [o for o in detections if o != det])
            ]

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
        unique_detections = _unique_box_detections(detections)
        conflict_detected = (
            best_cultivar is None or best_ripeness is None
            or sum(winning_confs) < total_weight * VOTE_CONFLICT_THRESHOLD
            or duplicate_label_conflict or len(unique_detections) < len(detections)
        )
        total_cultivar_weight = sum(sum(confs) for confs in cultivar_votes.values())
        winning_cultivar_weight = sum(cultivar_votes.get(best_cultivar, []))
        cultivar_conflict = (
            best_cultivar is None
            or (
                total_cultivar_weight > 0
                and winning_cultivar_weight < total_cultivar_weight * VOTE_CONFLICT_THRESHOLD
            )
            or duplicate_label_conflict
        )

        return ClassificationResult(
            cultivar=best_cultivar,
            ripeness=best_ripeness,
            confidence=avg_conf,
            finger_count=len(unique_detections),
            detections=detections,
            inference_time_ms=elapsed_ms,
            conflict_detected=conflict_detected,
            cultivar_conflict=cultivar_conflict,
            ood_rejected_boxes=len(off_banana),
            ripeness_outlier_boxes=len(_unique_box_detections(outliers)),
            hand_box_splits=hand_box_splits,
            colour_rejected_boxes=len(colour_rejected),
        )

    def _best_vote(self, votes: dict[str, list[float]]) -> str | None:
        if not votes:
            return None
        return max(votes, key=lambda k: sum(votes[k]))

# Singleton instance
banana_classifier = BananaClassifier()
