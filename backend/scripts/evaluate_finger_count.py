"""Measure finger-count accuracy with the application's own classifier and fusion.

Never reads the station database, captures or cameras. Run from backend/.

visible   Per-photo counts on a prepared YOLO split (<prepared root>/valid with images/
          and labels/; class names from ../data.yaml, else the 12 prepared names).
          The truth for a photo is its number of label rows: the fingers a person boxed
          in that photo, not the physical number of fingers in the hand. The camera view
          comes from the file name (Top/Left/Right/Rear, else "unknown", or
          --camera-label) and the dominant cultivar from the label rows. Photos without
          a label file are skipped; an empty label file is a photo with no finger.

physical  Fused per-scan counts against hand-counted totals. <scans>/<scan_id>/ holds one
          photo per view, named after it (top.jpg, Left.png, rear.jpg, ...); counts.csv
          has the columns scan_id,physical_count. Every view is classified with its camera
          label and fused by the real FusionEngine with the station's review threshold,
          as scan_service does. A scan without a supported cultivar is rejected, as on
          the station; the report gives metrics over accepted scans and with rejected
          scans counted as zero.

--configs Each entry is evaluated with a fresh classifier loaded from --weights (the
          detection head is fixed at load). "baseline" is the current settings. Any other
          entry is one or more NAME=VALUE overrides joined by "+", for example
          hand_box_split=off+ripeness_outlier=off. The first entry is the reference: every
          later entry is compared with it photo by photo (or scan by scan), with a seeded
          bootstrap 95% interval of the MAE difference (negative means fewer errors).
          Names: head (one_to_many_nms, one_to_one, checkpoint); axis_dedup,
          hand_box_split, ripeness_outlier, recovery_within_hand, side_view_lip, colour_check,
          recovery_adjacent, top_overlap, top_rotation, peripheral_background (on/off);
          iou (0-1).
          Some passes run only for a checkpoint in TOP_CALIBRATED_CHECKPOINTS at its
          image size and detection confidence 0.50: the occluded-finger recovery
          (recovery_*) and, at IoU 0.45 only, the Top overlap refinement and rotated
          pass (top_overlap, top_rotation). Each config records these "calibrated_paths";
          an override whose pass did not run, or an iou that also turns the Top passes
          off, is listed under "warnings" and printed with the table.

--confidence
          Detection confidence; default YOLO_CONFIDENCE_THRESHOLD of the settings.
          physical mode detects at the lower of it and --review-confidence, as the
          station does.

--gate    Adds the banana pre-detector (COCO yolo26n.pt in backend/) and the OOD gate as
          the station runs them: a scan (the photos of one capture) passes when enough
          views show a banana, then each view keeps only the cultivar boxes that its own
          banana evidence covers. A rejected scan counts zero fingers.

The frozen TEST split is for one final measurement, never for choosing settings: a split
under a "test" directory is refused unless --frozen-test is given with exactly one config.

Examples (existing report files are never overwritten):
  python scripts/evaluate_finger_count.py visible --weights <file named by YOLO_MODEL_PATH> \\
      --split <prepared dataset>/valid --configs baseline head=one_to_one \\
      hand_box_split=off --output finger-count-valid.json
  python scripts/evaluate_finger_count.py physical --weights <same file> \\
      --scans <counted scans> --counts <counted scans>/counts.csv --gate \\
      --output finger-count-physical.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.core.time import now_manila  # noqa: E402
from app.services.ood_gate import (  # noqa: E402
    GatePolicy,
    ViewEvidence,
    decide_scan,
    policy_from_settings,
)
from scripts.evaluate_ood_gate import (  # noqa: E402
    IMAGE_SUFFIXES,
    VIEWS,
    EvaluationError,
    _rate,
    camera_view,
    scan_id,
    top_paths,
)
from scripts.prepare_yolo_dataset import EXPECTED_NAMES  # noqa: E402

BASELINE = "baseline"
UNKNOWN_VIEW = "unknown"
HEADS = ("one_to_many_nms", "one_to_one", "checkpoint")
SIZE_BUCKETS = ("0", "1-4", "5-8", "9-12", "13+")
RULE_COUNTERS = (
    "ood_rejected_boxes", "ripeness_outlier_boxes", "hand_box_splits",
    "colour_rejected_boxes",
)
# Station default of the saved review threshold (system_config.confidence_threshold).
DEFAULT_REVIEW_CONFIDENCE = 0.80
# Bootstrap resamples drawn per block; fixed so a seed always gives the same interval.
_BOOTSTRAP_BLOCK = 250
# Only these settings go into the report: the rest can hold secrets.
_REPORTED_PREFIXES = ("yolo_", "ood_")
_REPORTED_EXTRA = ("top_camera_cultivar_anchor",)
NOTES = {
    "visible": (
        "Counts are visible boxes per photo, not physical hand totals: the truth is the "
        "number of label rows, and a finger hidden in that view is in neither the label "
        "nor the prediction. Dataset photos are not station captures."
    ),
    "physical": (
        "The fused count is the largest per-view visible count (views are never added), "
        "compared with hand-counted physical totals. Rejected scans have no station "
        "count; fused_rejected_as_zero counts them as zero."
    ),
}


class ConfigError(EvaluationError):
    """An unknown or invalid --configs entry."""


# ── Configurations ──────────────────────────────────────────────────────────


def _on_off(text: str) -> bool:
    words = {"on": True, "true": True, "yes": True, "1": True,
             "off": False, "false": False, "no": False, "0": False}
    try:
        return words[text.lower()]
    except KeyError:
        raise ConfigError(f"expected on or off, got {text!r}") from None


def _head(text: str) -> str:
    if text.lower() not in HEADS:
        raise ConfigError(f"expected one of {', '.join(HEADS)}, got {text!r}")
    return text.lower()


def _iou(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not 0 < value <= 1:
        raise ConfigError(f"expected a number in (0, 1], got {text!r}")
    return value


# Short --configs name -> (Settings field, value parser).
OVERRIDES: dict[str, tuple[str, Callable[[str], object]]] = {
    "head": ("yolo_inference_head", _head),
    "axis_dedup": ("yolo_axis_aware_rotation_dedup", _on_off),
    "hand_box_split": ("yolo_hand_box_split", _on_off),
    "ripeness_outlier": ("yolo_ripeness_outlier_filter", _on_off),
    "recovery_within_hand": ("yolo_recovery_within_hand", _on_off),
    "side_view_lip": ("yolo_side_view_lip_filter", _on_off),
    "colour_check": ("yolo_colour_check", _on_off),
    "recovery_adjacent": ("yolo_recovery_adjacent_ripeness", _on_off),
    "top_overlap": ("yolo_top_overlap_refinement", _on_off),
    "top_rotation": ("yolo_top_rotation_fallback", _on_off),
    "peripheral_background": ("yolo_peripheral_background_filter", _on_off),
    "iou": ("yolo_iou_threshold", _iou),
}


SHORT_NAMES = {setting: short for short, (setting, _) in OVERRIDES.items()}
# Settings whose rule acts only inside a calibrated pass of the classifier.
_RECOVERY_SETTINGS = ("yolo_recovery_within_hand", "yolo_recovery_adjacent_ripeness")
_TOP_PASS_SETTINGS = ("yolo_top_overlap_refinement", "yolo_top_rotation_fallback")
# Settings that only change the NMS IoU, which the NMS-free one_to_one head skips.
_NMS_SETTINGS = ("yolo_iou_threshold", "yolo_top_overlap_refinement")


@dataclass
class Config:
    """One evaluated configuration: its name and the Settings fields it overrides."""
    name: str
    overrides: dict[str, object] = field(default_factory=dict)


def parse_config(token: str) -> Config:
    """'baseline' or NAME=VALUE[+NAME=VALUE...] with the short names of OVERRIDES."""
    token = token.strip()
    if token.lower() == BASELINE:
        return Config(BASELINE)
    overrides: dict[str, object] = {}
    for part in token.split("+"):
        name, separator, value = part.partition("=")
        name, value = name.strip().lower(), value.strip()
        if not separator or not name or not value:
            raise ConfigError(
                f"config {token!r}: expected 'baseline' or NAME=VALUE, got {part!r}"
            )
        if name not in OVERRIDES:
            raise ConfigError(
                f"config {token!r}: unknown setting {name!r}; "
                f"known settings: {', '.join(OVERRIDES)}"
            )
        setting, parse = OVERRIDES[name]
        if setting in overrides:
            raise ConfigError(f"config {token!r}: {name} is given twice")
        try:
            overrides[setting] = parse(value)
        except ConfigError as exc:
            raise ConfigError(f"config {token!r}: {name}: {exc}") from None
    return Config(token, overrides)


def parse_configs(tokens: Iterable[str] | None) -> list[Config]:
    configs = [parse_config(token) for token in (tokens or [BASELINE])]
    names = [config.name for config in configs]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ConfigError(f"configs listed more than once: {', '.join(repeated)}")
    return configs


def config_settings(base, weights: Path, config: Config):
    """A copy of the settings with the weights and this configuration's overrides."""
    return base.model_copy(update={"yolo_model_path": str(weights), **config.overrides})


def settings_snapshot(settings) -> dict:
    """The model, rule and gate settings in use (never credentials)."""
    values = settings.model_dump()
    return {
        name: values[name] for name in sorted(values)
        if name.startswith(_REPORTED_PREFIXES) or name in _REPORTED_EXTRA
    }


def guard_frozen_test(split: Path, *, frozen_test: bool, config_count: int) -> bool:
    """Refuse to tune on the frozen TEST split; True when the split is that split."""
    parts = (*split.parts, *split.resolve().parts)
    is_test = any(part.lower() == "test" for part in parts)
    if is_test and not (frozen_test and config_count == 1):
        raise EvaluationError(
            f"{split} is under a 'test' directory: the frozen TEST split is measured once, "
            "with --frozen-test and exactly one config. Compare configurations on valid."
        )
    return is_test


# ── Metrics ─────────────────────────────────────────────────────────────────


def size_bucket(count: int) -> str:
    """Ground-truth size group: 0, 1-4, 5-8, 9-12 or 13+ fingers."""
    if count <= 0:
        return "0"
    if count <= 4:
        return "1-4"
    if count <= 8:
        return "5-8"
    if count <= 12:
        return "9-12"
    return "13+"


def count_metrics(pairs: list[tuple[int, int]]) -> dict:
    """Error statistics of (truth, predicted) counts; bias is predicted minus truth."""
    errors = [predicted - truth for truth, predicted in pairs]
    n = len(errors)
    return {
        "n": n,
        "mae": round(sum(abs(error) for error in errors) / n, 4) if n else None,
        "exact_rate": _rate(sum(error == 0 for error in errors), n),
        "within_one_rate": _rate(sum(abs(error) <= 1 for error in errors), n),
        "bias": round(sum(errors) / n, 4) if n else None,
        "undercount": sum(error < 0 for error in errors),
        "overcount": sum(error > 0 for error in errors),
    }


def _ordered(keys: Iterable[str], preferred: Iterable[str]) -> list[str]:
    keys = set(keys)
    first = [key for key in preferred if key in keys]
    return first + sorted(keys - set(first))


def breakdown(rows: list[tuple[str, int, int]], preferred: Iterable[str] = ()) -> dict:
    """count_metrics per group of (group, truth, predicted) rows."""
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for group, truth, predicted in rows:
        groups[group].append((truth, predicted))
    return {group: count_metrics(groups[group]) for group in _ordered(groups, preferred)}


def paired_comparison(
    truth: list[int], reference: list[int], candidate: list[int], *,
    resamples: int, seed: int,
) -> dict:
    """Candidate vs reference on the same items; differences are candidate minus reference.

    improved/worsened compare absolute errors per item. The interval is a percentile
    bootstrap of the mean absolute-error difference; the same seed gives the same draws.
    """
    if not len(truth) == len(reference) == len(candidate):
        raise ValueError("Paired counts must have the same length")
    target = np.asarray(truth, dtype=float)
    differences = (
        np.abs(np.asarray(candidate, dtype=float) - target)
        - np.abs(np.asarray(reference, dtype=float) - target)
    )
    n = len(differences)
    result: dict = {
        "n": n,
        "improved": int((differences < 0).sum()),
        "worsened": int((differences > 0).sum()),
        "tied": int((differences == 0).sum()),
        "mae_difference": round(float(differences.mean()), 4) if n else None,
        "ci95": None,
        "ci_excludes_zero": None,
        "bootstrap_resamples": resamples,
        "seed": seed,
    }
    if resamples > 0 and n:
        rng = np.random.default_rng(seed)
        means = []
        for start in range(0, resamples, _BOOTSTRAP_BLOCK):
            block = min(_BOOTSTRAP_BLOCK, resamples - start)
            means.append(differences[rng.integers(0, n, size=(block, n))].mean(axis=1))
        low, high = np.percentile(np.concatenate(means), [2.5, 97.5])
        result["ci95"] = [round(float(low), 4), round(float(high), 4)]
        result["ci_excludes_zero"] = bool(low > 0 or high < 0)
    return result


def rule_summary(results: Iterable[object]) -> dict:
    """How often each finger-count rule fired: total boxes and images where it fired."""
    results = [result for result in results if result is not None]
    summary = {}
    for name in RULE_COUNTERS:
        values = [int(getattr(result, name, 0) or 0) for result in results]
        summary[name] = {"total": sum(values), "images": sum(value > 0 for value in values)}
    return summary


# ── Models and images ───────────────────────────────────────────────────────


def read_image(path: Path):
    import cv2

    return cv2.imread(str(path))


def _image(reader: Callable[[Path], object], path: Path):
    image = reader(path)
    if image is None:
        raise EvaluationError(f"Unreadable image: {path}")
    return image


@contextmanager
def load_classifier(settings):
    """A fresh BananaClassifier loaded under these settings.

    predict() reads classification.settings at call time, so the module keeps these
    settings until the block ends; the earlier settings are restored afterwards.
    """
    from app.services import classification

    previous = classification.settings
    classification.settings = settings
    try:
        classifier = classification.BananaClassifier()
        classifier.load()
        if not classifier.is_loaded:
            raise EvaluationError(f"The cultivar model failed to load: {settings.yolo_model_path}")
        yield classifier
    finally:
        classification.settings = previous


def load_detector():
    from app.services.banana_detector import BananaPreDetector

    detector = BananaPreDetector()
    detector.load()
    if not detector.is_loaded:
        raise EvaluationError("The banana pre-detector failed to load (yolo26n.pt in backend/)")
    return detector


def weights_digest(weights: Path) -> str:
    if not weights.is_file():
        raise EvaluationError(f"Cultivar weights not found: {weights}")
    from app.services.classification import _checkpoint_digest

    return _checkpoint_digest(str(weights))


def package_versions() -> dict:
    from importlib import metadata

    versions = {"python": platform.python_version()}
    for package in ("ultralytics", "torch", "numpy"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def gate_scan(
    frames: list[tuple[object, str | None]], detector, policy: GatePolicy,
) -> tuple[bool, list[ViewEvidence]]:
    """The station's scan gate: acceptance and each view's banana evidence."""
    views = []
    for index, (image, label) in enumerate(frames):
        pre = detector.detect(
            image, accept_confidence=policy.banana_confidence,
            support_confidence=policy.support_confidence,
        )
        if not getattr(pre, "available", True):
            raise EvaluationError("The banana pre-detector is not loaded")
        boxes = getattr(pre, "boxes", None)
        views.append(ViewEvidence(
            camera_id=str(index), camera_label=label or "",
            evidence=boxes if policy.box_support_filter else None,
            banana_score=float(getattr(pre, "best_confidence", 0.0) or 0.0),
            has_banana=bool(pre.banana_detected),
        ))
    return decide_scan(views, policy).accepted, views


def _gate_arguments(evidence, policy: GatePolicy) -> dict:
    # As scan_service: without evidence (filter off or legacy detector) every box is kept.
    return {} if evidence is None else {
        "banana_evidence": evidence, "support_margin": policy.support_margin,
    }


def detection_confidence(args: argparse.Namespace, base) -> float:
    """--confidence, else YOLO_CONFIDENCE_THRESHOLD of the settings (as the station)."""
    return args.confidence if args.confidence is not None else base.yolo_confidence_threshold


def _report_header(mode: str, args: argparse.Namespace, configs: list[Config],
                   policy: GatePolicy, digest: str, confidence: float) -> dict:
    return {
        "mode": mode,
        "created_at": now_manila().isoformat(),
        "note": NOTES[mode],
        "weights": str(args.weights),
        "weights_sha256": digest,
        "versions": package_versions(),
        "detection_confidence": confidence,
        "gate": {"enabled": bool(args.gate), "policy": asdict(policy) if args.gate else None},
        "baseline": configs[0].name,
        "bootstrap": {"resamples": args.bootstrap, "seed": args.seed},
    }


def calibrated_paths(classifier, settings, confidence: float) -> dict:
    """Whether the classifier's calibrated passes can run (evaluate_ood_gate.top_paths).

    The occluded-finger recovery needs a checkpoint in TOP_CALIBRATED_CHECKPOINTS at its
    image size and confidence 0.50; the Top overlap refinement and rotated Top pass also
    need IoU 0.45. Outside them the recovery_*, top_overlap and top_rotation settings
    change nothing.
    """
    from app.services import classification

    model = SimpleNamespace(
        _checkpoint_sha256=getattr(classifier, "_checkpoint_sha256", None),
        _image_size=getattr(classifier, "_image_size", None),
        inference_head=getattr(classifier, "inference_head", "unknown"),
    )
    # These settings, not whatever the module holds at the moment.
    constants = SimpleNamespace(
        settings=settings,
        TOP_CALIBRATED_CHECKPOINTS=classification.TOP_CALIBRATED_CHECKPOINTS,
        TOP_OVERLAP_CONFIDENCE=classification.TOP_OVERLAP_CONFIDENCE,
        TOP_OVERLAP_BASE_IOU=classification.TOP_OVERLAP_BASE_IOU,
    )
    paths = top_paths(model, constants, confidence)
    recovery = bool(paths["image_size_matches"] and paths["confidence_is_calibrated"])
    return {
        **paths,
        "recovery_active": recovery,
        "top_passes_active": recovery and bool(paths["iou_is_calibrated"]),
    }


def _inactive_reasons(paths: dict, keys: Iterable[str]) -> str:
    reasons = {
        "checkpoint_registered": "the checkpoint is not in TOP_CALIBRATED_CHECKPOINTS",
        "image_size_matches": "the image size is not the calibrated one",
        "confidence_is_calibrated": "the detection confidence is not 0.50",
        "iou_is_calibrated": "the IoU is not 0.45",
    }
    unmet = [key for key in keys if not paths[key]]
    if "checkpoint_registered" in unmet and "image_size_matches" in unmet:
        unmet.remove("image_size_matches")  # an unregistered checkpoint has no size
    return "; ".join(reasons[key] for key in unmet)


def config_warnings(config: Config, settings, paths: dict) -> list[str]:
    """Overrides this run cannot measure: their pass never ran, or iou changes more."""
    warnings = []
    for setting, value in config.overrides.items():
        short = SHORT_NAMES[setting]
        if setting in _RECOVERY_SETTINGS and not paths["recovery_active"]:
            reasons = _inactive_reasons(
                paths, ("checkpoint_registered", "image_size_matches", "confidence_is_calibrated"),
            )
            warnings.append(
                f"{short} has no effect: the occluded-finger recovery did not run ({reasons})"
            )
        elif setting in _TOP_PASS_SETTINGS and not paths["top_passes_active"]:
            reasons = _inactive_reasons(paths, (
                "checkpoint_registered", "image_size_matches", "confidence_is_calibrated",
                "iou_is_calibrated",
            ))
            warnings.append(
                f"{short} has no effect: the calibrated Top passes did not run ({reasons})"
            )
        if setting in _NMS_SETTINGS and paths["inference_head"] == "one_to_one":
            warnings.append(
                f"{short} changes only the NMS IoU, which the NMS-free one_to_one head skips"
            )
        top_settings_on = settings.yolo_top_overlap_refinement or getattr(
            settings, "yolo_top_rotation_fallback", False
        )
        if (
            setting == "yolo_iou_threshold" and not paths["iou_is_calibrated"]
            and paths["recovery_active"] and top_settings_on
        ):
            warnings.append(
                f"iou={value} also turns off the calibrated Top overlap refinement and rotated "
                "pass, which run only at IoU 0.45: the comparison mixes both changes"
            )
    return warnings


def _config_entry(config: Config, settings, classifier, confidence: float) -> dict:
    paths = calibrated_paths(classifier, settings, confidence)
    return {
        "overrides": dict(config.overrides),
        "inference_head": getattr(classifier, "inference_head", "unknown"),
        "settings": settings_snapshot(settings),
        "calibrated_paths": paths,
        "warnings": config_warnings(config, settings, paths),
    }


# ── Visible mode ────────────────────────────────────────────────────────────


@dataclass
class Photo:
    """One labeled photo of a prepared split."""
    path: Path
    truth: int
    view: str
    cultivar: str
    scan: str

    @property
    def camera_label(self) -> str | None:
        return self.view if self.view in VIEWS else None


def class_names(split: Path) -> dict[int, str]:
    """Class names of ../data.yaml, else the 12 prepared names."""
    # Resolved first: the parent of "." is "." itself, not the prepared root.
    path = split.resolve().parent / "data.yaml"
    if not path.is_file():
        return dict(enumerate(EXPECTED_NAMES))
    import yaml

    names = (yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}).get("names")
    if not names:
        raise EvaluationError(f"No class names in {path}")
    return names if isinstance(names, dict) else dict(enumerate(names))


def read_label(path: Path, names: dict[int, str]) -> list[int]:
    """Class ids of a YOLO label file, one per non-empty row."""
    classes = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        values = line.split()
        if not values:
            continue
        try:
            cls = int(values[0])
        except ValueError:
            cls = None
        if cls not in names or len(values) < 5:
            raise EvaluationError(f"Invalid label row {path}:{number}")
        classes.append(cls)
    return classes


def dominant_cultivar(classes: list[int], names: dict[int, str]) -> str:
    """Most frequent cultivar of the rows; "Mixed" on a tie, "None" without rows."""
    ranked = Counter(
        str(names[cls]).split("_", 1)[0].capitalize() for cls in classes
    ).most_common()
    if not ranked:
        return "None"
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "Mixed"
    return ranked[0][0]


def load_split(split: Path, camera_label: str | None = None) -> tuple[list[Photo], int]:
    """Labeled photos of a prepared split and the number of photos without a label file."""
    images, labels = split / "images", split / "labels"
    if not images.is_dir() or not labels.is_dir():
        raise EvaluationError(f"Expected {split}/images and {split}/labels")
    names = class_names(split)
    photos, unlabeled = [], 0
    for image in sorted(images.iterdir()):
        if image.suffix.lower() not in IMAGE_SUFFIXES or not image.is_file():
            continue
        label = labels / f"{image.stem}.txt"
        if not label.is_file():
            unlabeled += 1
            continue
        classes = read_label(label, names)
        photos.append(Photo(
            path=image, truth=len(classes),
            view=camera_view(image.name) or camera_label or UNKNOWN_VIEW,
            cultivar=dominant_cultivar(classes, names), scan=scan_id(image.name),
        ))
    if not photos:
        raise EvaluationError(f"No labeled images in {split}")
    return photos, unlabeled


def visible_gate(photos: list[Photo], reader, detector, policy: GatePolicy) -> list[tuple]:
    """(scan accepted, view evidence) per photo; photos of one capture form one scan."""
    scans: dict[str, list[int]] = defaultdict(list)
    for index, photo in enumerate(photos):
        scans[photo.scan].append(index)
    outcome: list[tuple] = [(True, None)] * len(photos)
    for members in scans.values():
        accepted, views = gate_scan(
            [(_image(reader, photos[i].path), photos[i].camera_label) for i in members],
            detector, policy,
        )
        for index, view in zip(members, views, strict=True):
            outcome[index] = (accepted, view.evidence)
    return outcome


def summarize_visible(
    photos: list[Photo], runs: dict[str, dict], *, resamples: int, seed: int,
) -> dict:
    """Metrics, breakdowns and paired comparisons; runs[name]["counts"] follows photos."""
    truth = [photo.truth for photo in photos]
    reference = next(iter(runs.values()))["counts"] if runs else []
    summary = {}
    for index, (name, run) in enumerate(runs.items()):
        counts = run["counts"]
        summary[name] = {
            "metrics": count_metrics(list(zip(truth, counts, strict=True))),
            "by_view": breakdown(
                [(p.view, p.truth, c) for p, c in zip(photos, counts, strict=True)],
                (*VIEWS, UNKNOWN_VIEW),
            ),
            "by_cultivar": breakdown(
                [(p.cultivar, p.truth, c) for p, c in zip(photos, counts, strict=True)]
            ),
            "by_size": breakdown(
                [(size_bucket(p.truth), p.truth, c) for p, c in zip(photos, counts, strict=True)],
                SIZE_BUCKETS,
            ),
            "comparison_to_baseline": None if index == 0 else paired_comparison(
                truth, reference, counts, resamples=resamples, seed=seed,
            ),
        }
    return summary


def run_visible(
    args: argparse.Namespace, *, reader=read_image, classifier_factory=load_classifier,
    detector_factory=load_detector, base_settings=None,
) -> dict:
    configs = parse_configs(args.configs)
    frozen = guard_frozen_test(args.split, frozen_test=args.frozen_test,
                               config_count=len(configs))
    photos, unlabeled = load_split(args.split, args.camera_label)
    digest = weights_digest(args.weights)
    base = base_settings if base_settings is not None else get_settings()
    confidence = detection_confidence(args, base)
    policy = policy_from_settings(base)
    gate = visible_gate(photos, reader, detector_factory(), policy) if args.gate else None

    runs: dict[str, dict] = {}
    entries: dict[str, dict] = {}
    for config in configs:
        settings = config_settings(base, args.weights, config)
        results: list[object | None] = []
        with classifier_factory(settings) as classifier:
            for index, photo in enumerate(photos):
                accepted, evidence = gate[index] if gate else (True, None)
                if not accepted:
                    results.append(None)  # a rejected scan reports no fingers
                    continue
                results.append(classifier.predict(
                    _image(reader, photo.path), confidence_threshold=confidence,
                    camera_label=photo.camera_label, **_gate_arguments(evidence, policy),
                ))
            entry = _config_entry(config, settings, classifier, confidence)
        runs[config.name] = {
            "counts": [0 if result is None else int(result.finger_count) for result in results],
        }
        entries[config.name] = {
            **entry,
            "rules": rule_summary(results),
            "gate_rejected_images": sum(result is None for result in results) if gate else None,
        }

    summary = summarize_visible(photos, runs, resamples=args.bootstrap, seed=args.seed)
    return {
        **_report_header("visible", args, configs, policy, digest, confidence),
        "split": str(args.split),
        "frozen_test": frozen,
        "camera_label_fallback": args.camera_label,
        "images": len(photos),
        "skipped_unlabeled": unlabeled,
        "configs": {name: {**entries[name], **summary[name]} for name in runs},
        "per_image": [
            {
                "image": photo.path.name, "view": photo.view, "cultivar": photo.cultivar,
                "truth": photo.truth,
                "predicted": {name: run["counts"][index] for name, run in runs.items()},
            }
            for index, photo in enumerate(photos)
        ],
    }


# ── Physical mode ───────────────────────────────────────────────────────────


@dataclass
class Scan:
    """One hand-counted scan: its physical total and one photo per view."""
    scan_id: str
    physical: int
    views: list[tuple[str, Path]]


def view_from_stem(stem: str) -> str | None:
    """Top/Left/Right/Rear from a file stem, case-insensitive; "back" is Rear."""
    key = stem.strip().lower()
    key = "rear" if key == "back" else key
    return key.capitalize() if key.capitalize() in VIEWS else None


def load_counts(path: Path) -> dict[str, int]:
    """scan_id -> physical_count from a CSV file with those two columns."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise EvaluationError(f"{path} is empty")
    header = [cell.strip().lower() for cell in rows[0]]
    if "scan_id" not in header or "physical_count" not in header:
        raise EvaluationError(f"{path} needs the columns scan_id,physical_count")
    scan_column, count_column = header.index("scan_id"), header.index("physical_count")
    counts: dict[str, int] = {}
    for number, row in enumerate(rows[1:], 2):
        if not any(cell.strip() for cell in row):
            continue
        cells = row + [""] * (len(header) - len(row))
        name, text = cells[scan_column].strip(), cells[count_column].strip()
        if not name or name in (".", "..") or Path(name).name != name or "\\" in name:
            raise EvaluationError(f"{path}:{number}: scan_id must be a folder name")
        try:
            count = int(text)
        except ValueError:
            count = -1
        if count < 0:
            raise EvaluationError(f"{path}:{number}: physical_count must be a whole number >= 0")
        if name in counts:
            raise EvaluationError(f"{path}:{number}: scan_id {name!r} is listed twice")
        counts[name] = count
    if not counts:
        raise EvaluationError(f"{path} has no counted scans")
    return counts


def load_scans(root: Path, counts: dict[str, int]) -> tuple[list[Scan], list[str]]:
    """Counted scans in CSV order, and scan folders that counts.csv does not list."""
    if not root.is_dir():
        raise EvaluationError(f"Scan directory not found: {root}")
    resolved = root.resolve()
    scans = []
    for name, physical in counts.items():
        folder = root / name
        if not folder.is_dir() or not folder.resolve().is_relative_to(resolved):
            raise EvaluationError(f"No scan folder for {name!r} in {root}")
        views: dict[str, Path] = {}
        for file in sorted(folder.iterdir()):
            if not file.is_file() or file.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            view = view_from_stem(file.stem)
            if view is None:
                raise EvaluationError(
                    f"{file}: name each photo after its view ({', '.join(VIEWS)})"
                )
            if view in views:
                raise EvaluationError(f"{folder} has two photos of the {view} view")
            views[view] = file
        if not views:
            raise EvaluationError(f"{folder} has no view photos")
        scans.append(Scan(name, physical, [(view, views[view]) for view in VIEWS if view in views]))
    uncounted = sorted(
        entry.name for entry in root.iterdir() if entry.is_dir() and entry.name not in counts
    )
    return scans, uncounted


def score_physical_scan(
    scan: Scan, classifier, reader, engine, *, gate, policy: GatePolicy,
    confidence: float, review_confidence: float, expected_cameras: int,
) -> tuple[dict, list[object]]:
    """One scan as scan_service runs it: gate, per-view classification, fusion, review flag.

    As on the station, only a confidence below the review threshold flags a scan. What else
    fusion noticed, and whether boxes were dropped, is listed under "noted".
    """
    outcome: dict = {
        "scan_id": scan.scan_id, "physical_count": scan.physical, "views": {},
        "fused_count": None, "cultivar": None, "rejected": None, "review_flagged": None,
        "noted": [],
    }
    accepted, evidence = gate if gate is not None else (True, None)
    if not accepted:
        outcome["rejected"] = "no_banana"
        return outcome, []
    results = []
    for index, (view, path) in enumerate(scan.views):
        view_evidence = evidence[index].evidence if evidence is not None else None
        result = classifier.predict(
            _image(reader, path), confidence_threshold=confidence, camera_label=view,
            **_gate_arguments(view_evidence, policy),
        )
        outcome["views"][view] = int(result.finger_count)
        results.append((view, view, result))
    fused = engine.fuse(
        results, expected_camera_count=expected_cameras,
        review_confidence_threshold=review_confidence,
    )
    view_results = [result for _, _, result in results]
    outcome["cultivar"] = fused.cultivar
    if fused.cultivar == "Unknown" or fused.ripeness == "Unknown":
        outcome["rejected"] = "no_target_cultivar"
        return outcome, view_results
    outcome["fused_count"] = int(fused.finger_count)
    outcome["review_flagged"] = bool(fused.auto_flagged)
    outcome["noted"] = [observation.code for observation in getattr(fused, "observations", ())]
    for name in ("ood_rejected_boxes", "ripeness_outlier_boxes", "colour_rejected_boxes"):
        if any(getattr(result, name, 0) for result in view_results):
            outcome["noted"].append(name)
    return outcome, view_results


def summarize_physical(outcomes: list[dict]) -> dict:
    accepted = [item for item in outcomes if item["rejected"] is None]
    reasons = Counter(item["rejected"] for item in outcomes if item["rejected"] is not None)
    flagged = sum(bool(item["review_flagged"]) for item in accepted)
    pairs = [(item["physical_count"], item["fused_count"]) for item in accepted]
    return {
        "fused": count_metrics(pairs),
        "fused_by_size": breakdown(
            [(size_bucket(item["physical_count"]), item["physical_count"], item["fused_count"])
             for item in accepted],
            SIZE_BUCKETS,
        ),
        "fused_rejected_as_zero": count_metrics(
            [(item["physical_count"], item["fused_count"] or 0) for item in outcomes]
        ),
        "rejected": {
            "scans": sum(reasons.values()), "rate": _rate(sum(reasons.values()), len(outcomes)),
            "by_reason": dict(sorted(reasons.items())),
        },
        "review_flagged": flagged,
        "review_flag_rate": _rate(flagged, len(accepted)),
    }


def run_physical(
    args: argparse.Namespace, *, reader=read_image, classifier_factory=load_classifier,
    detector_factory=load_detector, base_settings=None,
) -> dict:
    from app.services.fusion_engine import FusionEngine

    configs = parse_configs(args.configs)
    scans, uncounted = load_scans(args.scans, load_counts(args.counts))
    digest = weights_digest(args.weights)
    base = base_settings if base_settings is not None else get_settings()
    policy = policy_from_settings(base)
    # As scan_service: moderate boxes are kept; the stricter threshold decides review.
    confidence = min(args.review_confidence, detection_confidence(args, base))
    gates: dict[str, tuple] = {}
    if args.gate:
        detector = detector_factory()
        for scan in scans:
            gates[scan.scan_id] = gate_scan(
                [(_image(reader, path), view) for view, path in scan.views], detector, policy,
            )
    engine = FusionEngine()

    report_configs: dict[str, dict] = {}
    reference: list[int] = []
    truth = [scan.physical for scan in scans]
    for index, config in enumerate(configs):
        settings = config_settings(base, args.weights, config)
        outcomes, view_results = [], []
        with classifier_factory(settings) as classifier:
            for scan in scans:
                outcome, results = score_physical_scan(
                    scan, classifier, reader, engine, gate=gates.get(scan.scan_id),
                    policy=policy, confidence=confidence,
                    review_confidence=args.review_confidence,
                    expected_cameras=args.expected_cameras,
                )
                outcomes.append(outcome)
                view_results.extend(results)
            entry = _config_entry(config, settings, classifier, confidence)
        counts = [item["fused_count"] or 0 for item in outcomes]
        if index == 0:
            reference = counts
        report_configs[config.name] = {
            **entry,
            **summarize_physical(outcomes),
            "rules": rule_summary(view_results),
            "comparison_to_baseline": None if index == 0 else {
                "basis": "fused_rejected_as_zero",
                **paired_comparison(truth, reference, counts,
                                    resamples=args.bootstrap, seed=args.seed),
            },
            "scans": outcomes,
        }
    return {
        **_report_header("physical", args, configs, policy, digest, confidence),
        "review_confidence": args.review_confidence,
        "expected_cameras": args.expected_cameras,
        "scans_dir": str(args.scans),
        "counts_file": str(args.counts),
        "scans": len(scans),
        "uncounted_scan_folders": uncounted,
        "configs": report_configs,
    }


# ── Command line ────────────────────────────────────────────────────────────


def _number(value) -> str:
    return "-" if value is None else f"{value:.4f}"


def summary_lines(report: dict) -> list[str]:
    """A short table of the headline metric per config, for the terminal."""
    key = "metrics" if report["mode"] == "visible" else "fused_rejected_as_zero"
    lines = [
        f"{report['mode']} ({key}); report holds breakdowns, rules and per-item counts",
        f"{'config':<44} {'n':>5} {'MAE':>7} {'exact':>7} {'within1':>7} {'bias':>8}  "
        "dMAE vs first [95% CI]",
    ]
    for name, run in report["configs"].items():
        metrics, comparison = run[key], run.get("comparison_to_baseline")
        delta = ""
        if comparison:
            delta = f"{comparison['mae_difference']:+.4f}"
            if comparison["ci95"]:
                low, high = comparison["ci95"]
                delta += f" [{low:+.4f}, {high:+.4f}]"
        lines.append(
            f"{name:<44} {metrics['n']:>5} {_number(metrics['mae']):>7} "
            f"{_number(metrics['exact_rate']):>7} {_number(metrics['within_one_rate']):>7} "
            f"{_number(metrics['bias']):>8}  {delta}"
        )
    for name, run in report["configs"].items():
        lines.extend(f"warning: {name}: {warning}" for warning in run.get("warnings", []))
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--weights", type=Path, required=True, help="cultivar YOLO weights")
    shared.add_argument(
        "--configs", nargs="+", default=[BASELINE], metavar="CONFIG",
        help="'baseline' and NAME=VALUE[+NAME=VALUE] entries; the first is the reference",
    )
    shared.add_argument("--gate", action="store_true",
                        help="run the banana pre-detector and OOD gate as the station does")
    shared.add_argument(
        "--confidence", type=float, default=None,
        help="detection confidence (default: YOLO_CONFIDENCE_THRESHOLD of the settings)",
    )
    shared.add_argument("--bootstrap", type=int, default=2000, help="bootstrap resamples")
    shared.add_argument("--seed", type=int, default=0, help="bootstrap seed")
    shared.add_argument("--output", type=Path, required=True, help="new JSON report file")
    commands = parser.add_subparsers(dest="command", required=True)
    visible = commands.add_parser("visible", parents=[shared],
                                  help="per-photo counts against label rows")
    visible.add_argument("--split", type=Path, required=True,
                         help="prepared split with images/ and labels/, e.g. <root>/valid")
    visible.add_argument("--camera-label", choices=VIEWS,
                         help="view for files whose name does not end in a view")
    visible.add_argument("--frozen-test", action="store_true",
                         help="allow the frozen TEST split (exactly one config)")
    physical = commands.add_parser("physical", parents=[shared],
                                   help="fused per-scan counts against physical totals")
    physical.add_argument("--scans", type=Path, required=True,
                          help="directory of <scan_id>/<view>.jpg")
    physical.add_argument("--counts", type=Path, required=True,
                          help="CSV with the columns scan_id,physical_count")
    physical.add_argument("--review-confidence", type=float, default=DEFAULT_REVIEW_CONFIDENCE,
                          help="saved review threshold of the station (default 0.80)")
    physical.add_argument("--expected-cameras", type=int, default=len(VIEWS),
                          help="configured camera count (default 4)")
    return parser


def _check_arguments(args: argparse.Namespace) -> None:
    if args.confidence is not None and not 0 < args.confidence <= 1:
        raise EvaluationError("--confidence must be in (0, 1]")
    if args.bootstrap < 0:
        raise EvaluationError("--bootstrap must be 0 or more")
    if args.command == "physical":
        if not 0 < args.review_confidence <= 1:
            raise EvaluationError("--review-confidence must be in (0, 1]")
        if not 1 <= args.expected_cameras <= len(VIEWS):
            raise EvaluationError("--expected-cameras must be 1 to 4")
    # Checked before the run: a long evaluation must not be lost at the end.
    if args.output.exists():
        raise EvaluationError(f"output already exists: {args.output}")
    folder = args.output.parent
    if not folder.is_dir():
        raise EvaluationError(f"output folder not found: {folder}")
    if not os.access(folder, os.W_OK):
        raise EvaluationError(f"output folder is not writable: {folder}")


def write_new_file(path: Path, text: str) -> None:
    """Write a file that must not exist yet; never replaces one (exclusive create)."""
    handle = path.open("x", encoding="utf-8")
    try:
        with handle:
            handle.write(text)
    except OSError:
        path.unlink(missing_ok=True)  # only the partial file this call created
        raise


def main(argv: list[str] | None = None, **dependencies) -> int:
    """dependencies (reader, classifier_factory, detector_factory, base_settings) are for tests."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _check_arguments(args)
        run = run_visible if args.command == "visible" else run_physical
        report = run(args, **dependencies)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Evaluation failed: {exc}\n")
    text = json.dumps(report, indent=2) + "\n"
    print("\n".join(summary_lines(report)))
    try:
        write_new_file(args.output, text)
    except OSError as exc:
        # The evaluation is done: print the report rather than lose it.
        print(text, end="")
        parser.exit(2, f"Could not write {args.output} ({exc}); the report is printed above\n")
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
