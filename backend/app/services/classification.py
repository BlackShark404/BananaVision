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
        min_w = min(candidate.w, existing.w)
        if min_w > 0:
            cx_cand = candidate.x + candidate.w / 2
            cx_exist = existing.x + existing.w / 2
            if abs(cx_cand - cx_exist) <= 0.25 * min_w:
                return True

    return False


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
            )
        except Exception as exc:
            raise ModelInferenceError(model_name, str(exc))

        elapsed_ms = (time.time() - start) * 1000

        detections: list[Detection] = []
        cultivar_votes: dict[str, list[float]] = {}
        class_votes: dict[tuple[str | None, str | None], list[float]] = {}
        duplicate_label_conflict = False
        # OOD gate: a cultivar box that no banana evidence covers is treated as if the
        # model had never emitted it. It is skipped in every pass before any other
        # rule sees it, so it cannot vote, count as a finger or influence another box.
        # `off_banana` only counts the distinct boxes the gate actually removed.
        off_banana: list[Detection] = []

        def rejected_by_gate(box: Detection, dropped_anyway) -> bool:
            """dropped_anyway(box, kept): the pass's own rule for repeats of a kept box."""
            if banana_evidence is None or is_supported(box, banana_evidence, support_margin):
                return False
            # Not an intervention when this pass would have dropped the box anyway as
            # a repeat of an accepted detection, or when the object is already counted.
            if not (
                any(dropped_anyway(box, kept) for kept in detections)
                or any(
                    _is_same_class_sub_box(box, seen) or _is_duplicate_detection(box, seen)
                    for seen in off_banana
                )
            ):
                off_banana.append(box)
            return True

        def same_label_rotated_duplicate(box: Detection, kept: Detection) -> bool:
            # A different label on the same finger is a conflict the team code reports;
            # removing that report is an intervention and stays counted.
            return box.cls == kept.cls and _is_duplicate_detection(
                box, kept, TOP_ROTATION_DEDUP_IOU,
            )

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
                    # Suppress table lip / saucer edge false positives on Rear view
                    if (camera_label or "").strip().casefold() == "rear" and image is not None:
                        img_h = image.shape[0]
                        if y1 > 0.55 * img_h and (x2 - x1) > 2.0 * (y2 - y1) and conf < 0.60:
                            continue

                    # Suppress upper background fixtures (door frames, window jambs, ceiling)
                    # on peripheral side and rear cameras. Real banana fingers on the inspection
                    # platter sit in the middle-to-lower portion of the frame.
                    norm_cam = (camera_label or "").strip().casefold()
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

                    if rejected_by_gate(det, _is_same_class_sub_box):
                        continue

                    # Suppress same-class nested duplicate boxes or severe IoU duplicates.
                    if any(_is_same_class_sub_box(det, existing) for existing in detections):
                        continue

                    detections.append(det)

                    cultivar, ripeness = _parse_class_label(cls_name)
                    if cultivar:
                        cultivar_votes.setdefault(cultivar, []).append(conf)
                    if cultivar or ripeness:
                        class_votes.setdefault((cultivar, ripeness), []).append(conf)

        # ── Rotation fallback: recover fingers missed in the original orientation ──
        rot_is_canonical = False
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
                        if rejected_by_gate(candidate, same_label_rotated_duplicate):
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
                            cultivar, ripeness = _parse_class_label(candidate.cls)
                            if cultivar:
                                cultivar_votes.setdefault(cultivar, []).append(candidate.confidence)
                            if cultivar or ripeness:
                                class_votes.setdefault((cultivar, ripeness), []).append(candidate.confidence)
            elapsed_ms = (time.time() - start) * 1000

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
                recovery_frame = rotated if (rot_is_canonical and rotated is not None) else image
                img_h, img_w = image.shape[:2]
                norm_cam = (camera_label or "").strip().casefold()
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
                        if _parse_class_label(cls_name) != (primary_cultivar, primary_ripeness):
                            continue
                        if norm_cam == "rear" and y1 > 0.55 * img_h and det_w > 2.0 * det_h and conf < 0.60:
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
        )

    def _best_vote(self, votes: dict[str, list[float]]) -> str | None:
        if not votes:
            return None
        return max(votes, key=lambda k: sum(votes[k]))

# Singleton instance
banana_classifier = BananaClassifier()
