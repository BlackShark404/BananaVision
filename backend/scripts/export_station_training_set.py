"""Turn a station backup archive into a draft YOLO training set, offline.

Never reads the station database, captures or cameras, never loads a model and never
uses the network. The only input is a backup archive made in the app (Maintenance,
POST /backups), for example one downloaded from a GitHub release. Run from backend/.

The archive is fully validated (app.services.backup_archive.validate_archive) into a
private temporary staging folder that is always removed afterwards; set TMPDIR to a
private disk with room for about three times the archive's expanded size. --output
must be a new or empty directory; it is written in a hidden sibling folder first and
only appears when the export is complete. Nothing is printed from the database except
counts and scan identifiers.

For every scan that has captured images (demo-seeded scans have none), skipping
flagged scans unless --include-flagged and uncorrected scans with --corrected-only,
each Top/Left/Right/Rear view image is copied byte for byte to
  train/images/<scan_id>_<YYYYMMDDHHMMSS>_<view>.jpg
with a YOLO label file train/labels/<same stem>.txt. The digits are the scan's
Asia/Manila capture time. prepare_yolo_dataset.py needs <prefix>_<capture>_<view> file
names, so every view of a scan lands in one group named after the scan id (a plain
<scan_id>__<view> name would be refused there).

Label rows come from the per-view boxes the app stored for the scan (scan_detection:
pixel x, y, w, h from the top-left corner, cls, conf). Box corners are clamped to the
image read from the archive and normalized to class cx cy w h. Class indices follow
prepare_yolo_dataset.EXPECTED_NAMES. When a person corrected the scan's cultivar or
ripeness, its boxes take the corrected value, since one bunch is one cultivar. Boxes
the app dropped (crowns, plate/tray, windows, curtains, outliers) were never stored,
and fingers the model missed have no box: the labels are DRAFTS to review before
training, never ground truth. A view with no box keeps an empty label file to annotate
(prepare_yolo_dataset.py refuses empty label files).

Also written: data.yaml (nc: 12, inline names, train/valid/test layout; valid/ and
test/ stay empty because prepare_yolo_dataset.py takes held-out photos only from an
export's original valid/test), README.txt, counts.csv (one row per exported scan with
the AI and stored finger counts and the per-view AI counts) and, when any exported
scan was corrected by a person, physical/<scan_id>/<View>.jpg with physical/counts.csv
(scan_id,physical_count = the corrected stored count): the physical-mode input of
evaluate_finger_count.py, to use only when those corrections were physical counts.

Example:
  python scripts/export_station_training_set.py --backup station-backup.zip \\
      --output ../station-draft
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.time import TIMEZONE_NAME, as_manila, now_manila  # noqa: E402
from app.services.backup_archive import (  # noqa: E402
    ArchiveError,
    ValidatedBackup,
    validate_archive,
)
from scripts.prepare_yolo_dataset import (  # noqa: E402
    CULTIVARS,
    EXPECTED_NAMES,
    IMAGE_SUFFIXES,
    RIPENESS,
)

VIEWS = ("top", "left", "right", "rear")
VIEW_ALIASES = {"back": "rear"}
WEIGHTS_PLACEHOLDER = "<file named by YOLO_MODEL_PATH>"
COUNT_COLUMNS = (
    "scan_id", "scanned_at", "cultivar", "ripeness", "ai_finger_count",
    "stored_finger_count", "is_overridden", "flagged",
    *(f"{view}_count" for view in VIEWS), "images", "label_boxes",
)

SCAN_NO_IMAGES = "no captured images (demo-seeded scan or images not kept)"
SCAN_FLAGGED = "flagged for review (add --include-flagged to export it)"
SCAN_NOT_CORRECTED = "not corrected by a person (--corrected-only)"
SCAN_NO_USABLE_VIEW = "no usable view image"
IMAGE_NO_DETECTION = "no stored detection for the image's camera"
IMAGE_AMBIGUOUS = "several stored detections for the image's camera"
IMAGE_VIEW = "camera label is not Top/Left/Right/Rear"
IMAGE_DUPLICATE_VIEW = "second image of the same view in one scan"
IMAGE_MISSING = "image file missing from the backup"
IMAGE_TYPE = "unsupported image file type"
IMAGE_UNREADABLE = "unreadable image"
IMAGE_SIZE = "stored image size differs from the file"
BOX_CONFIDENCE = "confidence below --min-confidence"
BOX_GEOMETRY = "invalid, or empty after clamping to the image"
BOX_CLASS = "class is not one of the 12 cultivar/ripeness names"


class ExportError(ValueError):
    """Unusable input or output; nothing is left in the output directory."""


@dataclass
class Totals:
    scans_in_backup: int = 0
    scans: int = 0
    images: int = 0
    images_without_boxes: int = 0
    boxes: int = 0
    clamped: int = 0
    relabelled: int = 0
    physical_scans: int = 0
    skipped_scans: Counter = field(default_factory=Counter)
    skipped_images: Counter = field(default_factory=Counter)
    skipped_boxes: Counter = field(default_factory=Counter)
    class_boxes: Counter = field(default_factory=Counter)


# ── Pure helpers ───────────────────────────────────────────────────────────────


def view_name(label: object) -> str | None:
    """top/left/right/rear from a camera label, case-insensitive; "back" is rear."""
    key = str(label or "").strip().casefold()
    key = VIEW_ALIASES.get(key, key)
    return key if key in VIEWS else None


def _key(text: object) -> str:
    return "_".join(str(text).strip().lower().replace("-", " ").replace("_", " ").split())


def split_class(label: object) -> tuple[str | None, str | None] | None:
    """(cultivar, ripeness) of a stored class label; None when it names neither."""
    key = _key(label)
    for cultivar in CULTIVARS:
        if key == cultivar:
            return cultivar, None
        if key.startswith(cultivar + "_"):
            rest = key[len(cultivar) + 1:]
            return (cultivar, rest) if rest in RIPENESS else None
    return (None, key) if key in RIPENESS else None


def _enum_key(value: object) -> str | None:
    if value is None:
        return None
    return _key(getattr(value, "value", value))


def box_class(
    label: object, *, scan_cultivar: str | None, scan_ripeness: str | None,
    corrected_cultivar: bool, corrected_ripeness: bool,
) -> tuple[int | None, bool]:
    """EXPECTED_NAMES index for a stored box and whether a correction changed it."""
    parsed = split_class(label)
    if parsed is None:
        return None, False
    cultivar, ripeness = parsed
    stored = parsed
    if scan_cultivar and (corrected_cultivar or cultivar is None):
        cultivar = scan_cultivar
    if scan_ripeness and (corrected_ripeness or ripeness is None):
        ripeness = scan_ripeness
    name = f"{cultivar}_{ripeness}"
    if name not in EXPECTED_NAMES:
        return None, False
    return EXPECTED_NAMES.index(name), None not in stored and (cultivar, ripeness) != stored


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def yolo_box(box: object, width: int, height: int) -> tuple[tuple[float, ...], bool] | None:
    """Normalized (cx, cy, w, h) of a top-left pixel box clamped to the image."""
    if not isinstance(box, dict) or width <= 0 or height <= 0:
        return None
    values = [_number(box.get(name)) for name in ("x", "y", "w", "h")]
    if None in values:
        return None
    x, y, w, h = values
    if w <= 0 or h <= 0:
        return None
    corners = (x, y, x + w, y + h)
    x1, x2 = (min(max(value, 0.0), width) for value in (corners[0], corners[2]))
    y1, y2 = (min(max(value, 0.0), height) for value in (corners[1], corners[3]))
    if x2 <= x1 or y2 <= y1:
        return None
    result = ((x1 + x2) / 2 / width, (y1 + y2) / 2 / height, (x2 - x1) / width,
              (y2 - y1) / height)
    if round(result[2], 6) <= 0 or round(result[3], 6) <= 0:
        return None
    return result, (x1, y1, x2, y2) != corners


def box_confidence(box: object) -> float | None:
    if not isinstance(box, dict):
        return None
    return _number(box.get("conf", box.get("confidence")))


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of a fully decodable image, else None."""
    from PIL import Image

    try:
        with Image.open(path) as image:
            image.load()
            return image.size
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


def check_output(output: Path) -> Path:
    """A new or empty real directory; nothing is created here."""
    output = Path(output)
    if output.is_symlink():
        raise ExportError(f"Output is a symbolic link: {output}")
    if output.exists():
        if not output.is_dir():
            raise ExportError(f"Output is not a directory: {output}")
        if any(output.iterdir()):
            raise ExportError(f"Output is not empty; choose a new directory: {output}")
    return output.absolute()


def _manila_text(value: datetime | None) -> str:
    return as_manila(value).isoformat(timespec="seconds") if value is not None else ""


def _flag(value: object) -> str:
    return "true" if value else "false"


# ── Export ─────────────────────────────────────────────────────────────────────


def _tables(validated: ValidatedBackup) -> dict:
    by_scan = {name: defaultdict(list) for name in ("scan_image", "scan_detection")}
    for name, rows in by_scan.items():
        for row in validated.iter_rows(name):
            rows[row["scan_id"]].append(row)
    return {
        "scans": sorted(validated.iter_rows("scan"),
                        key=lambda row: (as_manila(row["date_time"]), str(row["id"]))),
        "classification": {
            row["scan_id"]: row for row in validated.iter_rows("scan_classification")
        },
        "original": {
            row["scan_id"]: row for row in validated.iter_rows("scan_original_ai_result")
        },
        "images": by_scan["scan_image"],
        "detections": by_scan["scan_detection"],
    }


def _label_lines(detection: dict, size: tuple[int, int], scan_class: dict,
                 min_confidence: float, totals: Totals) -> list[str]:
    lines = []
    boxes = detection.get("bounding_boxes")
    for box in boxes if isinstance(boxes, list) else []:
        confidence = box_confidence(box)
        if min_confidence > 0 and (confidence is None or confidence < min_confidence):
            totals.skipped_boxes[BOX_CONFIDENCE] += 1
            continue
        geometry = yolo_box(box, *size)
        if geometry is None:
            totals.skipped_boxes[BOX_GEOMETRY] += 1
            continue
        index, relabelled = box_class(box.get("cls"), **scan_class)
        if index is None:
            totals.skipped_boxes[BOX_CLASS] += 1
            continue
        (cx, cy, w, h), clamped = geometry
        lines.append(f"{index} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        totals.boxes += 1
        totals.clamped += clamped
        totals.relabelled += relabelled
        totals.class_boxes[EXPECTED_NAMES[index]] += 1
    return lines


def _scan_class(classification: dict | None, original: dict | None, overridden: bool) -> dict:
    cultivar = _enum_key(classification and classification["cultivar"])
    ripeness = _enum_key(classification and classification["ripeness"])

    def corrected(name: str, stored: str | None) -> bool:
        # A legacy override without the original AI row cannot say what changed.
        return bool(overridden and stored and (
            original is None or _enum_key(original[name]) != stored
        ))

    return {
        "scan_cultivar": cultivar if cultivar in CULTIVARS else None,
        "scan_ripeness": ripeness if ripeness in RIPENESS else None,
        "corrected_cultivar": corrected("cultivar", cultivar),
        "corrected_ripeness": corrected("ripeness", ripeness),
    }


def _export_scan(scan: dict, tables: dict, validated: ValidatedBackup, root: Path,
                 min_confidence: float, totals: Totals) -> dict | None:
    scan_id = str(scan["id"])
    classification = tables["classification"].get(scan["id"])
    original = tables["original"].get(scan["id"])
    scan_class = _scan_class(classification, original, bool(scan["is_overridden"]))
    detections = defaultdict(list)
    view_counts = {}
    for detection in tables["detections"].get(scan["id"], []):
        detections[detection["camera_id"]].append(detection)
        view = view_name(detection["camera_label"])
        if view is not None and view not in view_counts:
            view_counts[view] = detection["finger_count"]
    stamp = f"{as_manila(scan['date_time']):%Y%m%d%H%M%S}"
    written, boxes = {}, 0
    images = sorted(tables["images"][scan["id"]],
                    key=lambda row: (row["file_path"], str(row["id"])))
    for image in images:
        matches = detections.get(image["camera_id"], [])
        if len(matches) != 1:
            totals.skipped_images[IMAGE_AMBIGUOUS if matches else IMAGE_NO_DETECTION] += 1
            continue
        view = view_name(matches[0]["camera_label"])
        if view is None:
            totals.skipped_images[IMAGE_VIEW] += 1
            continue
        if view in written:
            totals.skipped_images[IMAGE_DUPLICATE_VIEW] += 1
            continue
        reference = image["file_path"]
        source = (validated.evidence.get(reference[len("/captures/"):])
                  if reference.startswith("/captures/") else None)
        if source is None or not source.is_file():
            totals.skipped_images[IMAGE_MISSING] += 1
            continue
        suffix = source.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            totals.skipped_images[IMAGE_TYPE] += 1
            continue
        size = image_size(source)
        if size is None:
            totals.skipped_images[IMAGE_UNREADABLE] += 1
            continue
        stored_size = (image["width"], image["height"])
        if None not in stored_size and tuple(stored_size) != size:
            totals.skipped_images[IMAGE_SIZE] += 1
            continue
        before = totals.boxes
        lines = _label_lines(matches[0], size, scan_class, min_confidence, totals)
        stem = f"{scan_id}_{stamp}_{view}"
        target = root / "train" / "images" / f"{stem}{suffix}"
        shutil.copyfile(source, target)
        (root / "train" / "labels" / f"{stem}.txt").write_text(
            "".join(f"{line}\n" for line in lines), encoding="utf-8"
        )
        totals.images += 1
        totals.images_without_boxes += not lines
        boxes += totals.boxes - before
        written[view] = target
    if not written:
        totals.skipped_scans[SCAN_NO_USABLE_VIEW] += 1
        return None
    totals.scans += 1
    return {
        "scan_id": scan_id,
        "scanned_at": _manila_text(scan["date_time"]),
        "cultivar": classification["cultivar"].value
        if classification and classification["cultivar"] else "",
        "ripeness": classification["ripeness"].value
        if classification and classification["ripeness"] else "",
        "ai_finger_count": (original or classification or {}).get("finger_count", ""),
        "stored_finger_count": classification["finger_count"] if classification else "",
        "is_overridden": _flag(scan["is_overridden"]),
        "flagged": _flag(scan["flagged"]),
        **{f"{view}_count": view_counts.get(view, "") for view in VIEWS},
        "images": len(written),
        "label_boxes": boxes,
        "_views": written,
        "_physical": bool(scan["is_overridden"]) and classification is not None,
    }


def _write_physical(root: Path, rows: list[dict]) -> int:
    corrected = [row for row in rows if row["_physical"]]
    if not corrected:
        return 0
    folder = root / "physical"
    for row in corrected:
        scan_folder = folder / row["scan_id"]
        scan_folder.mkdir(parents=True)
        for view, image in row["_views"].items():
            shutil.copyfile(image, scan_folder / f"{view.capitalize()}{image.suffix}")
    with (folder / "counts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scan_id", "physical_count", "cultivar", "ai_finger_count"])
        for row in corrected:
            writer.writerow([row["scan_id"], row["stored_finger_count"], row["cultivar"],
                             row["ai_finger_count"]])
    return len(corrected)


def next_commands(output: Path, physical: bool) -> list[str]:
    quote = shlex.quote
    commands = [
        "python scripts/prepare_yolo_dataset.py --source <reviewed export with "
        "train/valid/test> --output <new prepared dataset>",
        f"python scripts/train_finger_model.py --data <new prepared dataset> "
        f"--weights {WEIGHTS_PLACEHOLDER} --dry-run",
    ]
    if physical:
        commands.append(
            f"python scripts/evaluate_finger_count.py physical --weights {WEIGHTS_PLACEHOLDER} "
            f"--scans {quote(str(output / 'physical'))} "
            f"--counts {quote(str(output / 'physical' / 'counts.csv'))} --gate "
            "--output finger-count-station-physical.json"
        )
    return commands


REVIEW = (
    "Upload data.yaml with train/images and train/labels (YOLO format, not physical/) to "
    "the Roboflow project and review every image: add the fingers the model missed, delete "
    "any box on a crown, the wooden plate/tray, a window, a dark curtain or other "
    "background, fix wrong classes, and box or delete each image with an empty label file. "
    "Then generate a version with a train/valid/test split and export it in YOLO format."
)


def _readme(summary: dict) -> str:
    backup, totals = summary["backup"], summary
    skipped = "".join(
        f"  - {group}: {reason}: {count}\n"
        for group in ("scans", "images", "boxes")
        for reason, count in summary[group]["skipped"].items()
    ) or "  - nothing\n"
    physical = (
        f"physical/ holds {summary['physical']['scans']} scans that a person corrected, one "
        "photo per view named after it, and physical/counts.csv with physical_count = the "
        "corrected stored finger count. It is the physical-mode input of "
        "evaluate_finger_count.py; use it only if those corrections were physical counts "
        "of the fingers on the tray.\n"
        if summary["physical"]["scans"] else
        "No exported scan was corrected by a person, so physical/ was not written.\n"
    )
    commands = "".join(f"  {command}\n" for command in summary["next_commands"])
    return (
        "BananaVision station training set (DRAFT LABELS)\n"
        "================================================\n\n"
        f"Exported: {summary['exported_at']} ({TIMEZONE_NAME})\n"
        f"Backup: {backup['file']}\n"
        f"Backup SHA-256: {backup['sha256']}\n"
        f"Backup created: {backup['created_at']} ({TIMEZONE_NAME})\n"
        f"Options: min_confidence={summary['options']['min_confidence']}, "
        f"include_flagged={summary['options']['include_flagged']}, "
        f"corrected_only={summary['options']['corrected_only']}\n\n"
        f"Scans: {totals['scans']['exported']} exported of {totals['scans']['in_backup']}\n"
        f"Images: {totals['images']['exported']} "
        f"({totals['images']['without_boxes']} with an empty label file)\n"
        f"Boxes: {totals['boxes']['written']} ({totals['boxes']['clamped']} clamped to the "
        f"image, {totals['boxes']['relabelled_by_correction']} relabelled by a person's "
        "cultivar/ripeness correction)\n"
        f"Skipped:\n{skipped}\n"
        "The labels are DRAFTS, not ground truth. They are the boxes the app stored for "
        "each view after its own filters: boxes it dropped (crowns, plate/tray, windows, "
        "curtains, ripeness outliers) are not here, fingers the model missed have no box, "
        "and a stored box can still be wrong. Review them before training:\n"
        f"  {REVIEW}\n\n"
        "Layout: train/images/<scan_id>_<YYYYMMDDHHMMSS Asia/Manila capture time>_<view>.jpg "
        "with train/labels/<same name>.txt (class cx cy w h, normalized). Class indices "
        "follow data.yaml (the 12 names of prepare_yolo_dataset.py). Every view of a scan "
        "shares one file-name prefix, so prepare_yolo_dataset.py keeps a scan in one "
        "group. valid/ and test/ are empty: prepare_yolo_dataset.py takes held-out photos "
        "only from an export's own valid/test split, so this folder is not a dataset to "
        "prepare or train on by itself; it also refuses empty label files.\n\n"
        "counts.csv: one row per exported scan. ai_finger_count is the model's original "
        "estimate, stored_finger_count the count the app keeps (a person's correction "
        "when is_overridden is true), <view>_count the model's per-view estimate.\n"
        f"{physical}\n"
        f"Next, from backend/, after the review:\n{commands}"
    )


def export_training_set(
    backup: Path, output: Path, *, min_confidence: float = 0.0,
    include_flagged: bool = False, corrected_only: bool = False,
) -> dict:
    output = check_output(output)
    if not 0.0 <= min_confidence <= 1.0:
        raise ExportError("--min-confidence must be between 0 and 1")
    backup = Path(backup).absolute()
    if not backup.is_file():
        raise ExportError(f"Backup archive not found: {backup}")
    with tempfile.TemporaryDirectory(prefix="bananavision-export-") as staging:
        try:
            validated = validate_archive(backup, Path(staging))
        except ArchiveError as exc:
            raise ExportError(f"Backup archive failed validation: {exc}") from exc
        tables = _tables(validated)
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = Path(tempfile.mkdtemp(prefix=f".{output.name}.partial-", dir=output.parent))
        try:
            summary = _write(validated, tables, partial, output, min_confidence=min_confidence,
                             include_flagged=include_flagged, corrected_only=corrected_only,
                             backup=backup)
            if output.exists():
                output.rmdir()  # empty when checked; fails if anything appeared since
            os.rename(partial, output)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
    return summary


def _write(validated: ValidatedBackup, tables: dict, root: Path, output: Path, *,
           min_confidence: float, include_flagged: bool, corrected_only: bool,
           backup: Path) -> dict:
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir()
    totals = Totals(scans_in_backup=len(tables["scans"]))
    rows = []
    for scan in tables["scans"]:
        if not tables["images"].get(scan["id"]):
            totals.skipped_scans[SCAN_NO_IMAGES] += 1
        elif scan["flagged"] and not include_flagged:
            totals.skipped_scans[SCAN_FLAGGED] += 1
        elif corrected_only and not scan["is_overridden"]:
            totals.skipped_scans[SCAN_NOT_CORRECTED] += 1
        elif row := _export_scan(scan, tables, validated, root, min_confidence, totals):
            rows.append(row)
    if not rows:
        raise ExportError(
            "No scan in the backup could be exported: "
            + json.dumps(dict(totals.skipped_scans), sort_keys=True)
        )
    with (root / "counts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COUNT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    totals.physical_scans = _write_physical(root, rows)
    (root / "data.yaml").write_text(
        "train: train/images\nval: valid/images\ntest: test/images\n"
        f"nc: {len(EXPECTED_NAMES)}\nnames: {json.dumps(EXPECTED_NAMES)}\n",
        encoding="utf-8",
    )
    warnings = []
    if totals.images_without_boxes:
        warnings.append(
            f"{totals.images_without_boxes} images have an empty label file: box their "
            "fingers or delete them in the review (prepare_yolo_dataset.py refuses them)"
        )
    if totals.relabelled:
        warnings.append(
            f"{totals.relabelled} boxes took a person's corrected cultivar/ripeness"
        )
    summary = {
        "output": str(output),
        "exported_at": now_manila().isoformat(timespec="seconds"),
        "backup": {
            "file": backup.name,
            "sha256": validated.archive_sha256,
            "format_version": validated.manifest["version"],
            "created_at": _manila_text(datetime.fromisoformat(validated.manifest["created_at"])),
        },
        "options": {"min_confidence": min_confidence, "include_flagged": include_flagged,
                    "corrected_only": corrected_only},
        "scans": {"in_backup": totals.scans_in_backup, "exported": totals.scans,
                  "skipped": dict(sorted(totals.skipped_scans.items()))},
        "images": {"exported": totals.images, "without_boxes": totals.images_without_boxes,
                   "skipped": dict(sorted(totals.skipped_images.items()))},
        "boxes": {"written": totals.boxes, "clamped": totals.clamped,
                  "relabelled_by_correction": totals.relabelled,
                  "per_class": {name: totals.class_boxes[name] for name in EXPECTED_NAMES},
                  "skipped": dict(sorted(totals.skipped_boxes.items()))},
        "physical": {"scans": totals.physical_scans,
                     "folder": str(output / "physical") if totals.physical_scans else None},
        "labels": "DRAFT: review before training",
        "review": REVIEW,
        "warnings": warnings,
        "next_commands": next_commands(output, bool(totals.physical_scans)),
    }
    (root / "README.txt").write_text(_readme(summary), encoding="utf-8")
    return summary


# ── Command line ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backup", type=Path, required=True,
                        help="backup archive (.zip) made by the app's Maintenance page")
    parser.add_argument("--output", type=Path, required=True, help="new or empty directory")
    parser.add_argument("--min-confidence", type=float, default=0.0,
                        help="drop stored boxes below this confidence, 0-1 (default 0.0)")
    parser.add_argument("--include-flagged", action="store_true",
                        help="also export scans flagged for review")
    parser.add_argument("--corrected-only", action="store_true",
                        help="only export scans a person corrected (is_overridden)")
    args = parser.parse_args(argv)
    try:
        summary = export_training_set(
            args.backup, args.output, min_confidence=args.min_confidence,
            include_flagged=args.include_flagged, corrected_only=args.corrected_only,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Export failed: {exc}\nNothing was written to the output.\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
