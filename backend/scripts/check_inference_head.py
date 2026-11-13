"""Report which YOLO26 detection head a checkpoint runs, and whether IoU and TTA act on it.

YOLO26 checkpoints carry two detection heads. The one-to-many head needs NMS, so the
``iou`` setting acts on it; the NMS-free one-to-one head ignores ``iou`` and test-time
augmentation. Ultralytics 8.4.40 (the version the station pins) runs the one-to-one head
unless the checkpoint stores the choice, so the same weights can behave differently on
different machines. The app now picks the head explicitly (``YOLO_INFERENCE_HEAD``).

Usage (from backend/):

    python scripts/check_inference_head.py static --weights app/ml/weights/banana.pt
    python scripts/check_inference_head.py runtime --weights yolo26n.pt \\
        [--image photo.jpg] [--output report.json]

``static`` reads the checkpoint's pickle opcodes without executing them, so it is safe on
any file. It reports the Ultralytics version and date that wrote the file, the training
``end2end``/``nms`` arguments, whether the saved head has a one-to-one branch and whether
it stores a head choice.

``runtime`` loads the weights (loading unpickles the file: only use weights you trust),
once per head mode, and predicts one photo (default: the bus photo bundled with
Ultralytics) with IoU 0.3/0.7/0.95 and with augmentation on and off. It shows which head
each mode really runs and whether IoU and augmentation change the boxes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickletools
import sys
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.time import now_manila  # noqa: E402

MODES = ("checkpoint", "one_to_many_nms", "one_to_one")
IOUS = (0.3, 0.7, 0.95)
_STRING_OPS = {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE",
               "SHORT_BINSTRING", "BINSTRING", "STRING"}
_PUT_OPS = {"PUT", "BINPUT", "LONG_BINPUT"}
_GET_OPS = {"GET", "BINGET", "LONG_BINGET"}
_BOOLS = {"NEWTRUE": True, "NEWFALSE": False, "NONE": None}
# torch.save's legacy (non-zip) format starts with this magic number as its own pickle.
_LEGACY_TORCH_MAGIC = 0x1950A86A20F9469CFC6C


class CheckError(Exception):
    """A checkpoint or argument problem that ends the run with a message."""


def sha256(path: Path) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _pickle_bytes(path: Path) -> bytes:
    """The data.pkl member of a torch zip checkpoint, or the file itself if it is a pickle."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.endswith("data.pkl")]
            if not members:
                raise CheckError(f"{path} is a zip without data.pkl; not a torch checkpoint")
            return archive.read(min(members, key=len))
    return path.read_bytes()


def _opcodes(data: bytes):
    try:
        return list(pickletools.genops(data))
    except (ValueError, EOFError) as exc:
        raise CheckError("not a pickle or torch checkpoint") from exc


def scan_pickle(data: bytes) -> dict:
    """Read keys and simple values from pickle opcodes without running any of them.

    Strings are followed through the memo, so a repeated key is still recognised. Only the
    first value seen after each key is kept: the checkpoint's top-level ``version`` and
    ``date``, the head's stored ``_end2end``, and ``end2end``/``nms`` from ``train_args``
    (the model's YAML, pickled earlier, also has an ``end2end`` key and is skipped).
    """
    ops = _opcodes(data)
    first = next((op for op in ops if op[0].name not in ("PROTO", "FRAME")), None)
    if (first is not None and first[0].name in ("LONG1", "LONG4")
            and first[1] == _LEGACY_TORCH_MAGIC):
        raise CheckError("legacy (non-zip) torch format; re-save the weights with a current "
                         "torch, or run the runtime check")
    memo: dict[int, str] = {}
    next_memo = 0
    strings: list[str] = []
    values: dict[str, object] = {}
    previous: str | None = None
    last_string: str | None = None
    in_train_args = False
    for opcode, arg, _pos in ops:
        name = opcode.name
        current: str | None = None
        if name in _STRING_OPS:
            current = arg.decode("latin-1") if isinstance(arg, bytes) else str(arg)
        elif name in _GET_OPS:
            current = memo.get(arg)
        elif name in _PUT_OPS:
            if last_string is not None:
                memo[arg] = last_string
            continue
        elif name == "MEMOIZE":
            if last_string is not None:
                memo[next_memo] = last_string
            next_memo += 1
            continue
        if current is not None:
            strings.append(current)
            in_train_args = in_train_args or current == "train_args"
            if previous in ("version", "date") and previous not in values:
                values[previous] = current
            previous = last_string = current
            continue
        if name in _BOOLS and (
            previous == "_end2end" or (in_train_args and previous in ("end2end", "nms"))
        ):
            values.setdefault(previous, _BOOLS[name])
        previous = last_string = None
    found = set(strings)
    return {
        "ultralytics_version": values.get("version"),
        "date": values.get("date"),
        "train_end2end": values.get("end2end"),
        "train_nms": values.get("nms"),
        "has_one_to_one_branch": "one2one_cv2" in found,
        "stored_head_choice": values.get("_end2end", "absent" if "_end2end" not in found
                                         else "unreadable"),
    }


def run_static(weights: Path) -> dict:
    if not weights.is_file():
        raise CheckError(f"Weights not found: {weights}")
    info = scan_pickle(_pickle_bytes(weights))
    stored = info["stored_head_choice"]
    if not info["has_one_to_one_branch"]:
        expected = "one_to_many_nms (no one-to-one branch)"
    elif stored is False:
        expected = "one_to_many_nms (stored)"
    elif stored is True:
        expected = "one_to_one (stored)"
    else:
        expected = "one_to_one under Ultralytics 8.4.40 (no stored choice)"
    return {**info, "expected_checkpoint_head_8_4_40": expected}


def _boxes(result) -> list[tuple[float, ...]]:
    rows = []
    for box in result.boxes:
        x1, y1, x2, y2 = (round(float(v), 1) for v in box.xyxy[0].tolist())
        rows.append((x1, y1, x2, y2, round(float(box.conf[0]), 3), int(box.cls[0])))
    return sorted(rows)


def run_runtime(weights: Path, image: Path, confidence: float) -> dict:
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise CheckError("ultralytics is not installed in this environment") from exc

    from app.services.classification import _apply_inference_head

    if not weights.is_file():
        raise CheckError(f"Weights not found: {weights}")
    if not image.is_file():
        raise CheckError(f"Photo not found: {image}")
    modes = {}
    for mode in MODES:
        model = YOLO(str(weights))
        head = _apply_inference_head(model, mode)
        by_iou = {}
        for iou in IOUS:
            result = model.predict(str(image), conf=confidence, iou=iou, verbose=False)[0]
            by_iou[str(iou)] = _boxes(result)
        augmented = _boxes(model.predict(
            str(image), conf=confidence, iou=0.7, augment=True, verbose=False,
        )[0])
        modes[mode] = {
            "head": head,
            "head_after_first_prediction": (
                "one_to_one" if model.model.end2end else "one_to_many_nms"
            ),
            "boxes_by_iou": {iou: len(rows) for iou, rows in by_iou.items()},
            "iou_changes_boxes": len({json.dumps(rows) for rows in by_iou.values()}) > 1,
            "augment_changes_boxes": augmented != by_iou["0.7"],
        }

    # A predict argument cannot change the head after the first prediction: Ultralytics
    # sets the predictor up once and the first one-to-one prediction fuses the other head.
    model = YOLO(str(weights))
    model.predict(str(image), conf=confidence, verbose=False)
    first = "one_to_one" if model.model.end2end else "one_to_many_nms"
    model.predict(str(image), conf=confidence, verbose=False, end2end=False)
    late = "one_to_one" if model.model.end2end else "one_to_many_nms"
    return {
        "image": str(image),
        "confidence": confidence,
        "modes": modes,
        "late_predict_argument": {"head_before": first, "head_after_end2end_false": late},
    }


def _versions() -> dict:
    versions = {"python": sys.version.split()[0]}
    for package in ("ultralytics", "torch"):
        try:
            versions[package] = __import__(package).__version__
        except Exception:
            versions[package] = None
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    static = commands.add_parser("static", help="Read the head choice without loading")
    static.add_argument("--weights", type=Path, required=True)
    static.add_argument("--output", type=Path)
    runtime = commands.add_parser("runtime", help="Load trusted weights and compare heads")
    runtime.add_argument("--weights", type=Path, required=True)
    runtime.add_argument("--image", type=Path)
    runtime.add_argument("--confidence", type=float, default=0.05)
    runtime.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "static":
            body = run_static(args.weights)
        else:
            image = args.image
            if image is None:
                import ultralytics

                image = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
            body = run_runtime(args.weights, image, args.confidence)
        report = {
            "created_at": now_manila().isoformat(),
            "command": args.command,
            "weights": str(args.weights),
            "weights_sha256": sha256(args.weights),
            "versions": _versions(),
            **body,
        }
    except CheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
