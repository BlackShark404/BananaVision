"""Measure out-of-distribution (OOD) rejection with the application's own code paths.

Never reads the station database, captures or cameras. Run from backend/.

gate      Banana-vs-OOD gate on a fetched Open Images pool (no cultivar weights needed).
          Reports the frame gate (legacy rule), AUROC/AUPR, FPR at 95% TPR, and the
          box-support filter against annotated object boxes. The annotated boxes act
          as a worst-case stand-in for a closed-set model that boxes every object.

pipeline  Full two-stage pipeline with the trained cultivar weights on a prepared
          YOLO split (in-distribution) and an OOD pool. Reports per-cultivar
          precision/recall/F1 and the false-cultivar rate before and after the gate.
          Prepared files of one capture are scored together as one scan, as on the
          station: the scan passes when enough views show a banana, then every view
          is classified with its own camera label and its own banana evidence. An OOD
          image is a one-camera scan under --ood-view. Use the weights the station
          runs (YOLO_MODEL_PATH); "top_paths" in the report says whether the Top
          refinement, rotated pass and finger recovery were really active.
          Fusion across views is not simulated, and dataset photos are not station
          captures.

Examples (the pool directory and both report names are git-ignored):
  python scripts/evaluate_ood_gate.py gate --ood ood-data --pool benchmark \\
      --output ood-gate-report.json
  python scripts/evaluate_ood_gate.py pipeline --weights <file named by YOLO_MODEL_PATH> \\
      --id-split <prepared dataset>/test --ood ood-data --pool benchmark \\
      --output ood-pipeline-report.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.ood_gate import (  # noqa: E402
    EvidenceBox,
    GatePolicy,
    ViewEvidence,
    decide_scan,
    is_supported,
)

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "ood" / "open_images_ood_manifest.json"
OOD_GROUPS = ("near", "far")
CULTIVARS = ("Cardaba", "Lakatan", "Latundan")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# Prepared files end in the capture view, e.g. "..._02570_top_jpg.rf.<hash>.jpg".
VIEW_SUFFIX = re.compile(
    r"_(top|left|right|back|rear)(?:-\d+-?)?(?:_(?:jpg|jpeg|png|bmp|webp))?$", re.IGNORECASE
)
VIEWS = ("Top", "Left", "Right", "Rear")


class EvaluationError(ValueError):
    """Missing inputs or an unusable pool."""


@dataclass
class Frame:
    """One image with its gate evidence and annotated object boxes (pixels)."""
    image_id: str
    group: str
    name: str
    score: float
    evidence: list[EvidenceBox]
    objects: list[EvidenceBox]


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def load_pool(ood_root: Path, manifest_path: Path, pool: str) -> list[dict]:
    """Join fetched files with the manifest's annotated boxes for one pool."""
    index_path = ood_root / "index.json"
    if not index_path.is_file():
        raise EvaluationError(f"No index.json in {ood_root}; run prepare_ood_dataset.py fetch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    boxes = {item["id"]: item.get("boxes", []) for item in manifest["pools"][pool]}
    root = ood_root.resolve()
    records = []
    for record in json.loads(index_path.read_text(encoding="utf-8"))["files"]:
        if record["pool"] != pool or record["id"] not in boxes:
            continue
        path = (root / record["file"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise EvaluationError(f"Missing or unsafe pool image: {record['file']}")
        records.append({**record, "path": path, "boxes": boxes[record["id"]]})
    if not records:
        raise EvaluationError(f"Pool {pool!r} has no fetched images in {ood_root}")
    return records


def scan_frames(records: list[dict], detector, policy: GatePolicy) -> list[Frame]:
    """Run the application's banana pre-detector once per image."""
    import cv2

    frames = []
    for record in records:
        image = cv2.imread(str(record["path"]))
        if image is None:
            raise EvaluationError(f"Unreadable image: {record['path']}")
        height, width = image.shape[:2]
        result = detector.detect(
            image, accept_confidence=policy.banana_confidence,
            support_confidence=policy.support_confidence,
        )
        if not result.available:
            raise EvaluationError("The banana pre-detector is not loaded")
        frames.append(Frame(
            image_id=record["id"], group=record["group"], name=record["class"],
            score=result.best_confidence, evidence=result.boxes or [],
            objects=[
                EvidenceBox(x1 * width, y1 * height, (x2 - x1) * width, (y2 - y1) * height, 1.0)
                for x1, y1, x2, y2 in record["boxes"]
            ],
        ))
    return frames


def _supported(frame: Frame, policy: GatePolicy) -> int:
    return sum(is_supported(box, frame.evidence, policy.support_margin) for box in frame.objects)


def separation(positive: list[float], negative: list[float]) -> dict:
    """Threshold-free separation of banana frames (positive) from OOD frames."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    if not positive or not negative:
        return {"auroc": None, "aupr": None, "threshold_at_95_tpr": None, "fpr_at_95_tpr": None}
    labels = [1] * len(positive) + [0] * len(negative)
    scores = positive + negative
    # Highest threshold that still accepts at least 95% of banana frames.
    ranked = sorted(positive, reverse=True)
    threshold = ranked[max(0, -(-95 * len(ranked) // 100) - 1)]
    return {
        "auroc": round(float(roc_auc_score(labels, scores)), 4),
        "aupr": round(float(average_precision_score(labels, scores)), 4),
        "threshold_at_95_tpr": round(threshold, 4),
        "fpr_at_95_tpr": _rate(sum(s >= threshold for s in negative), len(negative)),
    }


def gate_report(frames: list[Frame], policy: GatePolicy, *, seed: int, scans: int) -> dict:
    """Frame, box and simulated multi-camera metrics for one pool."""
    by_group = defaultdict(list)
    for frame in frames:
        by_group[frame.group].append(frame)
    bananas = by_group["banana"]
    report: dict = {"images": {group: len(items) for group, items in by_group.items()}}

    frame_gate = {}
    for group in OOD_GROUPS:
        items = by_group[group]
        accepted = sum(f.score >= policy.banana_confidence for f in items)
        # After: the frame yields a cultivar only if an object box also has support.
        # A frame without annotated boxes cannot show that, so it counts as leaking.
        leaking = sum(
            f.score >= policy.banana_confidence
            and (not f.objects or _supported(f, policy) > 0)
            for f in items
        )
        frame_gate[group] = {
            "frames": len(items),
            "false_accept_rate_before": _rate(accepted, len(items)),
            "rejection_rate_before": _rate(len(items) - accepted, len(items)),
            "false_cultivar_frame_rate_after": _rate(leaking, len(items)),
            "rejection_rate_after": _rate(len(items) - leaking, len(items)),
        }
    frame_gate["banana"] = {
        "frames": len(bananas),
        "accept_rate": _rate(
            sum(f.score >= policy.banana_confidence for f in bananas), len(bananas)
        ),
    }
    report["frame_gate"] = frame_gate

    report["separation"] = {
        f"banana_vs_{group}": separation(
            [f.score for f in bananas], [f.score for f in by_group[group]]
        )
        for group in OOD_GROUPS
    }
    report["separation"]["banana_vs_all_ood"] = separation(
        [f.score for f in bananas],
        [f.score for group in OOD_GROUPS for f in by_group[group]],
    )

    box_filter = {}
    for group in (*OOD_GROUPS, "banana"):
        total = sum(len(f.objects) for f in by_group[group])
        kept = sum(_supported(f, policy) for f in by_group[group])
        key = "retained" if group == "banana" else "surviving"
        box_filter[group] = {
            "annotated_boxes": total, f"{key}_boxes": kept, f"{key}_rate": _rate(kept, total),
        }
    report["box_support_filter"] = box_filter

    # Simulated four-camera scans. Views are unrelated photos, so this bounds the
    # structural effect of the gate; it is not a station measurement.
    rng = random.Random(seed)
    ood = [f for group in OOD_GROUPS for f in by_group[group]]
    simulated = {}
    if len(ood) >= 4 and bananas:
        cases = (("banana_plus_three_ood_views", True), ("four_ood_views", False))
        for label, with_banana in cases:
            accepted = boxes_before = boxes_after = scans_before = scans_after = 0
            for _ in range(scans):
                views = rng.sample(ood, 3 if with_banana else 4)
                frames_in_scan = ([rng.choice(bananas)] if with_banana else []) + views
                if not any(f.score >= policy.banana_confidence for f in frames_in_scan):
                    continue
                accepted += 1
                # Before: one banana view admitted every box of every view.
                before = sum(len(f.objects) for f in views)
                after = sum(_supported(f, policy) for f in views)
                boxes_before += before
                boxes_after += after
                scans_before += before > 0
                scans_after += after > 0
            simulated[label] = {
                "scans": scans,
                "accepted_by_scan_gate": accepted,
                "ood_boxes_admitted_before": boxes_before,
                "ood_boxes_admitted_after": boxes_after,
                "accepted_scans_with_ood_box_before": scans_before,
                "accepted_scans_with_ood_box_after": scans_after,
            }
    report["simulated_scans"] = simulated
    return report


def run_gate(args: argparse.Namespace) -> dict:
    from app.services.banana_detector import BananaPreDetector

    policy = _policy(args)
    detector = BananaPreDetector()
    detector.load()
    frames = scan_frames(load_pool(args.ood, args.manifest, args.pool), detector, policy)
    return {
        "mode": "gate", "pool": args.pool, "gate_model": detector._COCO_MODEL,
        "policy": asdict(policy), "seed": args.seed,
        **gate_report(frames, policy, seed=args.seed, scans=args.simulated_scans),
    }


def camera_view(filename: str) -> str | None:
    """Camera view encoded in a prepared file name, as the station labels it."""
    match = VIEW_SUFFIX.search(Path(filename).stem.split(".rf.", 1)[0])
    if match is None:
        return None
    view = match[1].lower()
    return "Rear" if view == "back" else view.capitalize()


def scan_id(filename: str) -> str:
    """Files of one capture share everything before the view suffix."""
    stem = Path(filename).stem.split(".rf.", 1)[0]
    match = VIEW_SUFFIX.search(stem)
    return stem[:match.start()] if match else stem


def _id_images(split: Path) -> list[tuple[Path, str, str | None]]:
    """Images of a prepared YOLO split with a single ground-truth cultivar and their view."""
    images, labels = split / "images", split / "labels"
    yaml = split.parent / "data.yaml"
    if not images.is_dir() or not labels.is_dir() or not yaml.is_file():
        raise EvaluationError("Expected <split>/images, <split>/labels and ../data.yaml")
    import yaml as yaml_parser

    names = yaml_parser.safe_load(yaml.read_text(encoding="utf-8"))["names"]
    names = names if isinstance(names, dict) else dict(enumerate(names))
    selected = []
    for image in sorted(images.iterdir()):
        label = labels / f"{image.stem}.txt"
        if image.suffix.lower() not in IMAGE_SUFFIXES or not label.is_file():
            continue
        cultivars = {
            names[int(line.split()[0])].split("_", 1)[0].capitalize()
            for line in label.read_text(encoding="utf-8").splitlines() if line.strip()
        }
        if len(cultivars) == 1 and next(iter(cultivars)) in CULTIVARS:
            selected.append((image, next(iter(cultivars)), camera_view(image.name)))
    if not selected:
        raise EvaluationError(f"No single-cultivar labeled images in {split}")
    return selected


def classification_metrics(pairs: list[tuple[str, str | None]]) -> dict:
    """Per-cultivar precision/recall/F1; an image may end with no cultivar (None)."""
    result = {}
    for cultivar in CULTIVARS:
        tp = sum(truth == cultivar and predicted == cultivar for truth, predicted in pairs)
        fp = sum(truth != cultivar and predicted == cultivar for truth, predicted in pairs)
        fn = sum(truth == cultivar and predicted != cultivar for truth, predicted in pairs)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall else (0.0 if tp + fp + fn else None)
        )
        result[cultivar] = {
            "support": tp + fn,
            "precision": None if precision is None else round(precision, 4),
            "recall": None if recall is None else round(recall, 4),
            "f1": None if f1 is None else round(f1, 4),
        }
    result["images_without_cultivar"] = sum(predicted is None for _, predicted in pairs)
    return result


VARIANTS = ("no_gate", "legacy_gate", "ood_gate")


def score_scan(
    views: list[tuple[object, str | None]], detector, classifier, policy: GatePolicy,
    confidence: float,
) -> list[dict]:
    """Score one scan the way scan_service does, without fusion.

    views: (image, camera_label) per captured view. Returns one entry per view with
    (cultivar, finger_count) for each variant:
      no_gate      the cultivar model alone;
      legacy_gate  the earlier rule: the scan passes when any view shows a banana,
                   then every box of every view is kept;
      ood_gate     the scan passes on the same evidence, then each view keeps only
                   the boxes its own banana evidence covers.
    """
    evidence = []
    for index, (image, label) in enumerate(views):
        pre = detector.detect(
            image, accept_confidence=policy.banana_confidence,
            support_confidence=policy.support_confidence,
        )
        if not pre.available:
            raise EvaluationError("The banana pre-detector is not loaded")
        evidence.append(ViewEvidence(
            camera_id=str(index), camera_label=label or "", evidence=pre.boxes or [],
            banana_score=pre.best_confidence, has_banana=bool(pre.banana_detected),
        ))
    legacy_accepted = any(view.has_banana for view in evidence)
    accepted = decide_scan(evidence, policy).accepted
    scored = []
    for (image, label), view in zip(views, evidence, strict=True):
        # The view selects the Top refinement, the rotated pass and the background filters.
        open_result = classifier.predict(
            image, confidence_threshold=confidence, camera_label=label,
        )
        outcome = (open_result.cultivar, open_result.finger_count)
        gated = classifier.predict(
            image, confidence_threshold=confidence, camera_label=label,
            banana_evidence=view.evidence, support_margin=policy.support_margin,
        ) if accepted else None
        scored.append({
            "has_banana": view.has_banana,
            "scan_accepted": accepted,
            "no_gate": outcome,
            "legacy_gate": outcome if legacy_accepted else (None, 0),
            "ood_gate": (gated.cultivar, gated.finger_count) if gated else (None, 0),
        })
    return scored


def top_paths(classifier, classification, confidence: float) -> dict:
    """Whether the calibrated Top refinement, rotated pass and recovery can run."""
    settings = classification.settings
    expected = classification.TOP_CALIBRATED_CHECKPOINTS.get(classifier._checkpoint_sha256 or "")
    status = {
        "checkpoint_registered": expected is not None,
        "image_size_matches": expected is not None and classifier._image_size == expected,
        "confidence_is_calibrated": confidence == classification.TOP_OVERLAP_CONFIDENCE,
        "iou_is_calibrated": settings.yolo_iou_threshold == classification.TOP_OVERLAP_BASE_IOU,
        "overlap_refinement_setting": bool(settings.yolo_top_overlap_refinement),
        "rotation_fallback_setting": bool(getattr(settings, "yolo_top_rotation_fallback", False)),
    }
    active = all(status.values())
    # The calibrated IoU only acts with NMS; the NMS-free YOLO26 head skips it.
    head = getattr(classifier, "inference_head", "unknown")
    return {
        **status, "active": active, "inference_head": head,
        "overlap_refinement_effective": active and head == "one_to_many_nms",
    }


def run_pipeline(args: argparse.Namespace) -> dict:
    import cv2

    from app.services import classification
    from app.services.banana_detector import BananaPreDetector

    policy = _policy(args)
    detector = BananaPreDetector()
    detector.load()
    if not args.weights.is_file():
        raise EvaluationError(f"Cultivar weights not found: {args.weights}")
    classifier = classification.BananaClassifier()
    # Point the loader at the given weights without changing the shared settings.
    with mock.patch.object(classification.settings, "yolo_model_path", str(args.weights)):
        classifier.load()
    if not classifier.is_loaded:
        raise EvaluationError("The cultivar model failed to load")
    report: dict = {
        "mode": "pipeline", "weights_sha256": classifier._checkpoint_sha256,
        "top_paths": top_paths(classifier, classification, args.confidence),
        "policy": asdict(policy), "detection_confidence": args.confidence,
    }

    def read(path: Path):
        image = cv2.imread(str(path))
        if image is None:
            raise EvaluationError(f"Unreadable image: {path}")
        return image

    if args.id_split:
        scans: dict = defaultdict(list)
        for path, truth, view in _id_images(args.id_split):
            scans[scan_id(path.name)].append((path, truth, view or args.camera_label))
        # Results for all images, and separately for each camera view.
        pairs: dict = defaultdict(lambda: {variant: [] for variant in VARIANTS})
        fingers: dict = defaultdict(Counter)
        below: Counter = Counter()
        accepted_scans = 0
        for members in scans.values():
            scored = score_scan(
                [(read(path), view) for path, _, view in members],
                detector, classifier, policy, args.confidence,
            )
            accepted_scans += scored[0]["scan_accepted"]
            for (_, truth, view), outcome in zip(members, scored, strict=True):
                for scope in ("all", view or "no_view"):
                    below[scope] += not outcome["has_banana"]
                    for variant in VARIANTS:
                        pairs[scope][variant].append((truth, outcome[variant][0]))
                        fingers[scope][variant] += outcome[variant][1]

        def summarize(scope: str) -> dict:
            return {
                "images": len(pairs[scope]["no_gate"]),
                # Views where the verifier alone would not accept; on an accepted
                # scan they are still classified, with their own evidence.
                "frames_below_acceptance": below[scope],
                **{
                    variant: {
                        **classification_metrics(pairs[scope][variant]),
                        "finger_boxes": fingers[scope][variant],
                    }
                    for variant in VARIANTS
                },
            }

        report["in_distribution"] = {
            "scans": len(scans), "scans_accepted": accepted_scans, **summarize("all"),
        }
        report["in_distribution_by_view"] = {
            scope: summarize(scope) for scope in (*VIEWS, "no_view") if scope in pairs
        }
    if args.ood:
        counts: dict = {group: Counter() for group in OOD_GROUPS}
        for record in load_pool(args.ood, args.manifest, args.pool):
            if record["group"] not in OOD_GROUPS:
                continue
            [outcome] = score_scan(
                [(read(record["path"]), args.ood_view)], detector, classifier, policy,
                args.confidence,
            )
            counts[record["group"]]["images"] += 1
            for variant in VARIANTS:
                counts[record["group"]][variant] += outcome[variant][0] is not None
        report["out_of_distribution"] = {
            # Each OOD image is scored as a one-camera scan under this view.
            "view": args.ood_view,
            **{
                group: {
                    "images": tally["images"],
                    **{
                        f"false_cultivar_rate_{variant}": _rate(tally[variant], tally["images"])
                        for variant in VARIANTS
                    },
                }
                for group, tally in counts.items()
            },
        }
    return report


def _policy(args: argparse.Namespace) -> GatePolicy:
    return GatePolicy(
        banana_confidence=args.banana_confidence, support_confidence=args.support_confidence,
        support_margin=args.support_margin,
        min_banana_views=getattr(args, "min_banana_views", 1),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    defaults = GatePolicy()
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    shared.add_argument("--pool", choices=("calibration", "benchmark"), default="benchmark")
    shared.add_argument("--banana-confidence", type=float, default=defaults.banana_confidence)
    shared.add_argument("--support-confidence", type=float, default=defaults.support_confidence)
    shared.add_argument("--support-margin", type=float, default=defaults.support_margin)
    shared.add_argument("--output", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("gate", parents=[shared])
    gate.add_argument("--ood", type=Path, required=True)
    gate.add_argument("--seed", type=int, default=20261112)
    gate.add_argument("--simulated-scans", type=int, default=2000)
    pipeline = commands.add_parser("pipeline", parents=[shared])
    pipeline.add_argument("--weights", type=Path, required=True)
    pipeline.add_argument("--id-split", type=Path)
    pipeline.add_argument("--ood", type=Path)
    pipeline.add_argument("--confidence", type=float, default=0.50)
    pipeline.add_argument(
        "--camera-label", choices=VIEWS,
        help="view for in-distribution files whose name does not end in a view",
    )
    pipeline.add_argument(
        "--ood-view", choices=VIEWS, default="Top",
        help="camera view under which each OOD image is scored (default: Top)",
    )
    pipeline.add_argument("--min-banana-views", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.command == "pipeline" and not (args.id_split or args.ood):
            raise EvaluationError("Give --id-split, --ood, or both")
        # Checked before the run: a long evaluation must not be lost at the end.
        if args.output and args.output.exists():
            raise EvaluationError(f"output already exists: {args.output}")
        report = run_gate(args) if args.command == "gate" else run_pipeline(args)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Evaluation failed: {exc}\n")
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
