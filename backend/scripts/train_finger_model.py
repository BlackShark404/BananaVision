"""Fine-tune a YOLO26 finger/cultivar model on CPU from a prepared YOLO dataset.

Never reads the station database, captures or cameras, and never edits app code.
Run from backend/.

--data is a prepare_yolo_dataset.py output, or its prepare_ood_dataset.py
merge-negatives copy: <root>/data.yaml, manifest.json and
{train,valid,test}/{images,labels}. Preflight runs before anything is trained and
refuses a dataset
  - without data.yaml, or without manifest.json (unless --allow-unprepared);
  - whose class names differ from prepare_yolo_dataset.EXPECTED_NAMES, order
    included (fine-tuning keeps the starting checkpoint's class indices);
  - whose data.yaml points somewhere else (a moved copy that was not relocated),
    validates on the test split, or does not train on train/images and validate
    on valid/images;
  - with a missing or empty split, an image without a label file, a label row
    Ultralytics would drop as corrupt (class 0..11, finite normalized x y w h), or
    an image Ultralytics would find but prepare_yolo_dataset never writes (in a
    subfolder of images/, or a format such as .tif or .heic).
It reports images, boxes and background images (empty label files: the negatives
merge-negatives adds to train) per split. The test split stays held out.

--weights starts a new run; --imgsz defaults to 640, not the starting checkpoint's
stored size, and a mismatch is warned. --resume continues an interrupted run from
its last.pt only. A finished or early-stopped run's last.pt has no optimizer state,
and Ultralytics would silently start a new run on its own defaults (hue augmentation
on, outside --project); it is refused, as is a last.pt trained with hue augmentation
or on another dataset than --data (Ultralytics resumes on the dataset stored in
last.pt while that path exists). After training, the arguments Ultralytics actually
used are checked again and recorded.

After training it prints best.pt, its SHA-256, the image size the app will run it
at, and the next evaluation command. A new checkpoint is registered in
TOP_CALIBRATED_CHECKPOINTS (app/services/classification.py) only after that
evaluation; until then the calibrated Top refinement, rotated pass and finger
recovery stay off for it. A JSON run record (arguments, versions, hashes, Manila
time) is written into the run folder. --dry-run prints the preflight and the
training arguments and exits without loading Ultralytics.

Examples (runs/ is not git-ignored; keep weights out of commits):
  python scripts/train_finger_model.py --data <prepared dataset> \\
      --weights <file named by YOLO_MODEL_PATH> --dry-run
  python scripts/train_finger_model.py --data <prepared dataset> \\
      --weights <file named by YOLO_MODEL_PATH> --epochs 30 --time 8
  python scripts/train_finger_model.py --data <prepared dataset> \\
      --resume runs/finger/<run>/weights/last.pt
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import sys
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.time import now_manila  # noqa: E402
from scripts.check_inference_head import CheckError, run_static, sha256  # noqa: E402
from scripts.prepare_yolo_dataset import EXPECTED_NAMES, IMAGE_SUFFIXES, SPLITS  # noqa: E402

FORMAT_VERSION = 1
DEFAULT_PROJECT = BACKEND / "runs" / "finger"
RECORD_NAME = "finger_training_record.json"
# The evaluation report goes next to the run; evaluate_finger_count.py never overwrites one.
EVALUATION_NAME = "finger-count-valid.json"
EVALUATE_SCRIPT = "scripts/evaluate_finger_count.py"
# data.yaml key -> prepared split folder it must name.
YAML_SPLITS = {"train": "train", "val": "valid", "test": "test"}
# Ultralytics 8.4.40 IMG_FORMATS: what it trains on from a split folder, at any depth.
# Hardcoded so --dry-run does not import Ultralytics.
ULTRALYTICS_IMAGE_SUFFIXES = frozenset(
    f".{suffix}"
    for suffix in (
        "avif", "bmp", "dng", "heic", "heif", "jp2", "jpeg", "jpeg2000", "jpg", "mpo", "png",
        "tif", "tiff", "webp",
    )
)


class TrainingError(ValueError):
    """A dataset, checkpoint or argument that must not be trained on."""


@dataclass
class SplitCounts:
    images: int = 0
    labeled: int = 0     # images with at least one box
    background: int = 0  # images with an empty label file (negatives)
    boxes: int = 0
    orphan_labels: int = 0


@dataclass
class Preflight:
    data_root: Path
    data_yaml: Path
    data_yaml_sha256: str
    manifest: dict | None
    splits: dict[str, SplitCounts]
    weights: Path | None
    weights_sha256: str | None
    resume: Path | None
    resume_sha256: str | None
    warnings: list[str] = field(default_factory=list)

    @property
    def negatives(self) -> int:
        """Background images in train; merge-negatives adds them there and only there."""
        return self.splits["train"].background

    def as_dict(self) -> dict:
        return {
            "data_root": str(self.data_root),
            "data_yaml": str(self.data_yaml),
            "data_yaml_sha256": self.data_yaml_sha256,
            "manifest": self.manifest,
            "splits": {name: asdict(counts) for name, counts in self.splits.items()},
            "train_negatives": self.negatives,
            "weights": None if self.weights is None else str(self.weights),
            "weights_sha256": self.weights_sha256,
            "resume": None if self.resume is None else str(self.resume),
            "resume_sha256": self.resume_sha256,
            "warnings": self.warnings,
        }


# ── Preflight ──


def load_data_yaml(root: Path) -> dict:
    import yaml

    path = root / "data.yaml"
    if not path.is_file():
        raise TrainingError(f"No data.yaml in {root}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise TrainingError(f"data.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise TrainingError("data.yaml must be a mapping")
    return data


def check_names(data: dict) -> list[str]:
    """The 12 classes in EXPECTED_NAMES order: the starting weights' indices follow it."""
    names = data.get("names")
    if isinstance(names, dict):
        # Ultralytics also accepts {index: name}; the indices must be 0..n-1.
        if set(names) != set(range(len(names))):
            raise TrainingError("data.yaml names must be indexed 0..11")
        names = [names[index] for index in range(len(names))]
    if names != EXPECTED_NAMES:
        raise TrainingError(
            "data.yaml names must be the 12 classes in prepare_yolo_dataset.EXPECTED_NAMES "
            f"order {EXPECTED_NAMES}; found {names}"
        )
    nc = data.get("nc")
    if nc is not None and nc != len(EXPECTED_NAMES):
        raise TrainingError(f"data.yaml nc must be {len(EXPECTED_NAMES)}; found {nc}")
    return list(names)


def check_split_paths(root: Path, data: dict) -> dict[str, Path]:
    """train/val/test as Ultralytics resolves them: against data.yaml's path: key."""
    root = root.resolve()
    base = data.get("path")
    if base not in (None, ""):
        base_path = Path(str(base))
        # A relative path: is resolved under Ultralytics' own datasets folder.
        if not base_path.is_absolute():
            raise TrainingError("data.yaml path: must be absolute or absent")
        if base_path.resolve() != root:
            raise TrainingError(
                f"data.yaml path: names {base}, not {root}; relocate a moved copy first"
            )
    resolved: dict[str, Path] = {}
    for key in YAML_SPLITS:
        value = data.get(key)
        if value in (None, ""):
            if key == "test":
                continue
            raise TrainingError(f"data.yaml has no {key}:")
        if not isinstance(value, str):
            raise TrainingError(f"data.yaml {key}: must name one folder")
        resolved[key] = (root / value).resolve()
    test_images = (root / "test" / "images").resolve()
    if resolved["val"] in (test_images, resolved.get("test")):
        raise TrainingError(
            "data.yaml val: is the test split; validate on valid/images and keep test held out"
        )
    for key in ("train", "val"):
        expected = (root / YAML_SPLITS[key] / "images").resolve()
        if resolved[key] != expected:
            raise TrainingError(
                f"data.yaml {key}: must be {YAML_SPLITS[key]}/images; found {data[key]}"
            )
    return resolved


def check_manifest(root: Path, *, allow_unprepared: bool) -> dict | None:
    """Provenance of a prepare_yolo_dataset.py output; None for an allowed unprepared set."""
    path = root / "manifest.json"
    if not path.is_file():
        if allow_unprepared:
            return None
        raise TrainingError(
            f"No manifest.json in {root}: not a prepare_yolo_dataset.py output "
            "(pass --allow-unprepared to train on it anyway)"
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrainingError(f"manifest.json is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise TrainingError("manifest.json must be an object")
    names = manifest.get("class_names")
    if names is not None and names != EXPECTED_NAMES:
        raise TrainingError("manifest.json class_names differ from EXPECTED_NAMES order")
    return {
        "sha256": sha256(path),
        "format_version": manifest.get("format_version"),
        "seed": manifest.get("seed"),
    }


def check_label_row(values: list[str]) -> None:
    """prepare_yolo_dataset's row rule; Ultralytics drops the whole image on a bad row."""
    if len(values) != 5:
        raise ValueError("expected five fields")
    cls = int(values[0])
    x, y, width, height = map(float, values[1:])
    if not 0 <= cls < len(EXPECTED_NAMES):
        raise ValueError(f"class must be 0..{len(EXPECTED_NAMES) - 1}")
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        raise ValueError("coordinates must be finite")
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
        raise ValueError("expected normalized coordinates and positive dimensions")


def split_images(images: Path, split: str) -> list[Path]:
    """Every image Ultralytics would train on; refuses any prepare_yolo_dataset never writes."""
    found = []
    for path in sorted(images.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ULTRALYTICS_IMAGE_SUFFIXES:
            continue
        name = path.relative_to(images).as_posix()
        if path.parent != images:
            # Ultralytics globs images/ recursively and would train it as background.
            raise TrainingError(f"Image in a subfolder of {split}/images: {name}")
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise TrainingError(
                f"Image format prepare_yolo_dataset never writes in {split}/images: {name}"
            )
        found.append(path)
    return found


def count_split(root: Path, split: str) -> SplitCounts:
    """Images, boxes and background images of one split; refuses an unusable split."""
    images, labels = root / split / "images", root / split / "labels"
    if not images.is_dir() or not labels.is_dir():
        raise TrainingError(f"Missing {split}/images or {split}/labels in {root}")
    counts, stems = SplitCounts(), set()
    for image in split_images(images, split):
        if image.stem in stems:
            raise TrainingError(f"Multiple images share label stem in {split}: {image.stem}")
        stems.add(image.stem)
        label = labels / f"{image.stem}.txt"
        # Ultralytics would silently train on an unlabeled image as background.
        if not label.is_file():
            raise TrainingError(f"Image without a label file in {split}: {image.name}")
        boxes = 0
        for number, line in enumerate(label.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                check_label_row(line.split())
            except ValueError as exc:
                raise TrainingError(f"Invalid label row {label}:{number}: {exc}") from exc
            boxes += 1
        counts.images += 1
        counts.boxes += boxes
        if boxes:
            counts.labeled += 1
        else:
            counts.background += 1
    counts.orphan_labels = sum(1 for path in labels.glob("*.txt") if path.stem not in stems)
    if counts.images == 0:
        raise TrainingError(f"{split}/images has no images")
    if counts.labeled == 0:
        raise TrainingError(f"{split} has no labeled images")
    return counts


def _negatives_record(root: Path) -> int | None:
    """negatives_added from merge-negatives' ood_negatives.json, if this is such a copy."""
    path = root / "ood_negatives.json"
    if not path.is_file():
        return None
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["negatives_added"])
    except (ValueError, KeyError, TypeError):
        return None


def run_preflight(
    data_root: Path,
    weights: Path | None,
    *,
    resume: Path | None = None,
    allow_unprepared: bool = False,
) -> Preflight:
    """Every check that can fail before training; nothing is written."""
    root = Path(data_root).resolve()
    if not root.is_dir():
        raise TrainingError(f"Dataset folder not found: {data_root}")
    data = load_data_yaml(root)
    check_names(data)
    check_split_paths(root, data)
    manifest = check_manifest(root, allow_unprepared=allow_unprepared)
    splits = {split: count_split(root, split) for split in SPLITS}
    warnings = []
    for split, counts in splits.items():
        if counts.orphan_labels:
            warnings.append(f"{split}: {counts.orphan_labels} label files without an image")
        if split != "train" and counts.background:
            warnings.append(f"{split}: {counts.background} background images in a held-out split")
    recorded = _negatives_record(root)
    if recorded is not None and recorded != splits["train"].background:
        warnings.append(
            f"ood_negatives.json lists {recorded} negatives; train has "
            f"{splits['train'].background} background images"
        )
    if resume is None and weights is None:
        raise TrainingError("Give --weights (starting checkpoint) or --resume (last.pt)")
    if resume is not None and weights is not None:
        # A resumed run continues from last.pt alone; the weights would be recorded, not used.
        raise TrainingError("Give --weights or --resume, not both")
    if weights is not None and not Path(weights).is_file():
        raise TrainingError(f"Starting weights not found: {weights}")
    if resume is not None:
        if not Path(resume).is_file():
            raise TrainingError(f"Resume checkpoint not found: {resume}")
        if Path(resume).name != "last.pt":
            # A mid-run best.pt would rewind the run and overwrite its later epochs.
            raise TrainingError(
                f"--resume takes the last.pt of an interrupted run, not {Path(resume).name}"
            )
    return Preflight(
        data_root=root,
        data_yaml=root / "data.yaml",
        data_yaml_sha256=sha256(root / "data.yaml"),
        manifest=manifest,
        splits=splits,
        weights=None if weights is None else Path(weights).resolve(),
        weights_sha256=None if weights is None else sha256(Path(weights)),
        resume=None if resume is None else Path(resume).resolve(),
        resume_sha256=None if resume is None else sha256(Path(resume)),
        warnings=warnings,
    )


def check_start_names(names) -> str | None:
    """Refuse 12-class weights in another order; a different class count is transfer."""
    values = list(names.values()) if isinstance(names, dict) else list(names or [])
    normalized = [re.sub(r"[\s-]+", "_", str(name).strip().lower()) for name in values]
    if normalized == EXPECTED_NAMES:
        return None
    if len(values) == len(EXPECTED_NAMES):
        # Ultralytics would keep the head and overwrite the names: classes would swap.
        raise TrainingError(
            f"Starting weights' classes {values} are not EXPECTED_NAMES in order"
        )
    return (
        f"starting weights have {len(values)} classes; Ultralytics replaces the class head "
        "(transfer learning, not a fine-tune of the station model)"
    )


def check_resumable(ckpt, data_yaml: Path) -> list[str]:
    """Refuse a checkpoint Ultralytics would not resume as checked; warnings otherwise.

    Ultralytics 8.4.40 Model.train starts a new run on its own defaults from a
    checkpoint without epoch and optimizer state (its run finished or stopped early),
    and check_resume keeps the dataset stored in it while that path exists.
    """
    if not isinstance(ckpt, dict):
        raise TrainingError("Resume checkpoint is not an Ultralytics training checkpoint")
    epoch = ckpt.get("epoch")
    if (
        isinstance(epoch, bool)
        or not isinstance(epoch, int)
        or epoch < 0
        or ckpt.get("optimizer") is None
    ):
        raise TrainingError(
            "Resume checkpoint has no epoch/optimizer state: its run finished or stopped "
            "early, and Ultralytics would start a new run on its own defaults. Start a new "
            "run with --weights instead."
        )
    train_args = ckpt.get("train_args")
    if not isinstance(train_args, dict):
        raise TrainingError("Resume checkpoint has no training arguments")
    if train_args.get("hsv_h") != 0.0:
        raise TrainingError(
            f"Resume checkpoint trains with hue augmentation (hsv_h={train_args.get('hsv_h')}); "
            "start a new run with --weights instead"
        )
    stored = train_args.get("data")
    if not isinstance(stored, str) or not stored:
        raise TrainingError("Resume checkpoint names no dataset file to check against --data")
    if not Path(stored).exists():
        return [
            f"the dataset stored in the resume checkpoint ({stored}) no longer exists; "
            f"Ultralytics resumes on --data {data_yaml}"
        ]
    if Path(stored).resolve() != data_yaml.resolve():
        raise TrainingError(
            f"Resume checkpoint trains on {stored}; Ultralytics ignores --data while that "
            f"file exists. Pass --data {Path(stored).resolve().parent}"
        )
    return []


def check_trainer_args(effective: dict, data_yaml: Path, *, resume: bool) -> list[str]:
    """What Ultralytics actually trained with that differs from what was checked."""
    problems = []
    if effective.get("hsv_h") != 0.0:
        problems.append(f"hue augmentation (hsv_h={effective.get('hsv_h')})")
    if resume and not effective.get("resume"):
        problems.append("a new run instead of resuming")
    data = effective.get("data")
    if not isinstance(data, str) or Path(data).resolve() != data_yaml.resolve():
        problems.append(f"dataset {data}, not {data_yaml}")
    return problems


# ── Training arguments ──


def validate_args(args: argparse.Namespace) -> None:
    positive = {"epochs": args.epochs, "imgsz": args.imgsz, "batch": args.batch}
    for name, value in positive.items():
        if value < 1:
            raise TrainingError(f"--{name} must be positive")
    if args.imgsz % 32:
        # Ultralytics would round it up; the stored size must be the one asked for.
        raise TrainingError("--imgsz must be a multiple of 32")
    for name in ("workers", "patience"):
        if getattr(args, name) < 0:
            raise TrainingError(f"--{name} must not be negative")
    if args.freeze is not None and args.freeze < 0:
        raise TrainingError("--freeze must not be negative")
    if not 0 < args.fraction <= 1:
        raise TrainingError("--fraction must be in (0, 1]")
    if args.time is not None and args.time <= 0:
        raise TrainingError("--time must be positive (hours)")


def build_train_kwargs(
    data_yaml: Path,
    *,
    project: Path,
    name: str,
    epochs: int = 30,
    imgsz: int = 640,
    batch: int = 8,
    workers: int = 2,
    patience: int = 10,
    device: str = "cpu",
    seed: int = 0,
    freeze: int | None = None,
    fraction: float = 1.0,
    time: float | None = None,
    resume: bool = False,
) -> dict:
    """Keyword arguments for ultralytics YOLO(...).train()."""
    if resume:
        # Resume restores every training setting from last.pt. Only these may change:
        # where to run and how much to load at once. imgsz, batch, freeze, epochs and
        # augmentation must not change mid-run, so they are not passed.
        kwargs = {
            "resume": True,
            # Used only when the dataset path stored in last.pt no longer exists.
            "data": str(data_yaml),
            "device": device,
            "workers": workers,
            "cache": False,
            "plots": False,
        }
        if time is not None:
            kwargs["time"] = time  # a fresh wall-clock budget for the remaining epochs
        return kwargs
    kwargs = {
        "data": str(data_yaml),
        # A short fine-tune from an already trained checkpoint, not training from scratch.
        "epochs": epochs,
        # Stored in best.pt; the app predicts at this size and TOP_CALIBRATED_CHECKPOINTS
        # registers it next to the SHA-256.
        "imgsz": imgsz,
        # A fixed batch: AutoBatch (-1) measures GPU memory and does not apply on CPU.
        "batch": batch,
        # Few loader workers: on a CPU machine they compete with the training threads.
        "workers": workers,
        # Stop when validation fitness stalls; a CPU epoch is expensive.
        "patience": patience,
        "device": device,
        # Reproducible runs: same seed, deterministic ops (pinned, not left to defaults).
        "seed": seed,
        "deterministic": True,
        # Ripeness is colour: hue shifts would turn green fingers yellow. Hue augmentation
        # is off, as in the audited runs.
        "hsv_h": 0.0,
        # RAM caching can exhaust a station-class machine and is not deterministic.
        "cache": False,
        # Skip plot rendering on CPU; metrics still go to results.csv.
        "plots": False,
        # Absolute: Ultralytics nests a relative project under its own runs folder.
        "project": str(project),
        "name": name,
        # Never overwrite an earlier run; Ultralytics picks <name>2, <name>3, ...
        "exist_ok": False,
        # 1.0 trains on every train image; less is only for a quick smoke run.
        "fraction": fraction,
    }
    if freeze is not None:
        # Freeze the first N layers (backbone) to fine-tune faster on little data.
        kwargs["freeze"] = freeze
    if time is not None:
        # Hours; Ultralytics then recomputes epochs to fit the budget.
        kwargs["time"] = time
    return kwargs


def default_run_name() -> str:
    return f"finger-{now_manila():%Y%m%d-%H%M%S}"


# ── After training ──


def _quote(value: str) -> str:
    return f'"{value}"' if any(char.isspace() for char in value) else value


def next_command(best: Path, data_root: Path, report: Path) -> str:
    """Evaluate on the valid split first; test stays held out for the final comparison."""
    return " ".join([
        "python", EVALUATE_SCRIPT, "visible",
        "--weights", _quote(str(best)),
        "--split", _quote(str(data_root / "valid")),
        "--configs", "baseline", "head=one_to_one",
        "--output", _quote(str(report)),
    ])


def _pinned_version(package: str) -> str | None:
    requirements = BACKEND / "requirements.txt"
    if not requirements.is_file():
        return None
    match = re.search(
        rf"^{re.escape(package)}==(\S+)", requirements.read_text(encoding="utf-8"), re.MULTILINE
    )
    return match[1] if match else None


def versions() -> dict:
    """Installed versions without importing the packages."""
    found: dict = {"python": platform.python_version()}
    for package in ("ultralytics", "torch", "numpy"):
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = None
    found["ultralytics_pinned"] = _pinned_version("ultralytics")
    return found


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, str | bool | int | float):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def build_run_record(
    *,
    argv: list[str],
    args: argparse.Namespace,
    preflight: Preflight,
    train_kwargs: dict,
    result: dict,
    found_versions: dict,
) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "created_at": now_manila().isoformat(),
        "command": ["python", "scripts/train_finger_model.py", *argv],
        "args": _jsonable(vars(args)),
        "versions": found_versions,
        "preflight": preflight.as_dict(),
        "train_kwargs": _jsonable(train_kwargs),
        **_jsonable(result),
        "registered": False,
        "registration": "Add best_sha256: image_size to TOP_CALIBRATED_CHECKPOINTS only "
        "after the evaluation; this script never edits app code.",
    }


def write_record(save_dir: Path, record: dict) -> Path:
    """The run record next to the run; a resumed run keeps the earlier record."""
    path = save_dir / RECORD_NAME
    if path.exists():
        path = save_dir / f"finger_training_record-{now_manila():%Y%m%d-%H%M%S}.json"
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2) + "\n")
    return path


def train(
    args: argparse.Namespace,
    preflight: Preflight,
    kwargs: dict,
    *,
    yolo_cls=None,
    argv: list[str] | None = None,
) -> dict:
    """Run Ultralytics training and return the run record (already written)."""
    if yolo_cls is None:
        from ultralytics import YOLO

        yolo_cls = YOLO
    found_versions = versions()
    pinned = found_versions["ultralytics_pinned"]
    if pinned and found_versions["ultralytics"] not in (None, pinned):
        preflight.warnings.append(
            f"ultralytics {found_versions['ultralytics']} is installed; the station pins {pinned}"
        )
    model = yolo_cls(str(preflight.resume or preflight.weights))
    if preflight.resume is not None:
        preflight.warnings.extend(
            check_resumable(getattr(model, "ckpt", None), preflight.data_yaml)
        )
    else:
        if note := check_start_names(getattr(model, "names", None)):
            preflight.warnings.append(note)
        stored_size = (getattr(model, "overrides", None) or {}).get("imgsz")
        if stored_size is not None and stored_size != kwargs["imgsz"]:
            # The new best.pt stores --imgsz, and the app predicts at that size.
            preflight.warnings.append(
                f"starting weights store image size {stored_size}; this run trains at and "
                f"stores {kwargs['imgsz']} (pass --imgsz {stored_size} to keep it)"
            )
    for warning in preflight.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    model.train(**kwargs)
    trainer = model.trainer
    best = Path(trainer.best)
    save_dir = Path(getattr(trainer, "save_dir", None) or best.parent.parent)
    trainer_args = getattr(trainer, "args", None)
    if trainer_args is None:
        raise TrainingError(f"Ultralytics reported no training arguments for {save_dir}")
    effective = dict(vars(trainer_args))
    if problems := check_trainer_args(
        effective, preflight.data_yaml, resume=preflight.resume is not None
    ):
        raise TrainingError(
            f"Ultralytics trained with {'; '.join(problems)}. Output in {save_dir} is not "
            "the checked run: do not evaluate or register it."
        )
    if not best.is_file():
        raise TrainingError(f"Training ended without {best}")
    last = Path(getattr(trainer, "last", None) or best.with_name("last.pt"))
    digest = sha256(best)
    # The app reads the image size the same way: from the loaded checkpoint's overrides.
    image_size = getattr(yolo_cls(str(best)), "overrides", {}).get("imgsz", kwargs.get("imgsz"))
    try:
        head = run_static(best)
    except CheckError as exc:
        head = {"error": str(exc)}
    result = {
        "save_dir": save_dir,
        "best": best,
        "best_sha256": digest,
        "last": last if last.is_file() else None,
        "image_size": image_size,
        "checkpoint_head": head,
        # What Ultralytics actually used; train_kwargs holds what was asked for.
        "trainer_args": effective,
        "metrics": getattr(trainer, "metrics", None),
        "next_command": next_command(best, preflight.data_root, save_dir / EVALUATION_NAME),
    }
    record = build_run_record(
        argv=list(argv or []), args=args, preflight=preflight, train_kwargs=kwargs,
        result=result, found_versions=found_versions,
    )
    record_path = write_record(save_dir, record)
    print(f"best.pt:      {best}")
    print(f"SHA-256:      {digest}")
    print(f"image size:   {image_size}")
    print(f"run record:   {record_path}")
    print("next:")
    print(f"  {record['next_command']}")
    print(
        "Register this checkpoint in TOP_CALIBRATED_CHECKPOINTS "
        f"({digest!r}: {image_size}) only after that evaluation; never before."
    )
    return record


def main(argv: list[str] | None = None, *, yolo_cls=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", type=Path, required=True,
                        help="prepared dataset root (or its merge-negatives copy)")
    start = parser.add_mutually_exclusive_group()
    start.add_argument("--weights", type=Path, help="starting checkpoint (.pt) of a new run")
    start.add_argument("--resume", type=Path, help="last.pt of an interrupted run")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="training and stored image size (default 640, not the starting checkpoint's)",
    )
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--freeze", type=int, help="freeze the first N layers")
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--time", type=float, help="training budget in hours (overrides epochs)")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--name", help="run name (default: finger-<Manila date-time>)")
    parser.add_argument("--allow-unprepared", action="store_true",
                        help="train on a dataset without manifest.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="print preflight and training arguments; do not train")
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(raw)
    try:
        validate_args(args)
        preflight = run_preflight(
            args.data, args.weights, resume=args.resume, allow_unprepared=args.allow_unprepared,
        )
        kwargs = build_train_kwargs(
            preflight.data_yaml,
            project=args.project.resolve(),
            name=args.name or default_run_name(),
            epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, workers=args.workers,
            patience=args.patience, device=args.device, seed=args.seed, freeze=args.freeze,
            fraction=args.fraction, time=args.time, resume=args.resume is not None,
        )
        print(json.dumps(
            {"dry_run": args.dry_run, "preflight": preflight.as_dict(), "train_kwargs": kwargs},
            indent=2,
        ))
        if args.dry_run:
            return 0
        train(args, preflight, kwargs, yolo_cls=yolo_cls, argv=raw)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Training failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
