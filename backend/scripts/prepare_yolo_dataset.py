"""Prepare a separate, grouped YOLO export without modifying source data.

This utility does not train a model. Filename prefixes are grouping proxies, not
verified physical identities. --aliases can conservatively join related prefixes.
Only original valid/test files are eligible for the new held-out splits; their
unaugmented status follows the supplied export convention, not its .rf. hashes.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import random
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

CULTIVARS = ("cardaba", "lakatan", "latundan")
RIPENESS = ("overripe", "ripe", "semi_ripe", "unripe")
EXPECTED_NAMES = [f"{cultivar}_{stage}" for cultivar in CULTIVARS for stage in RIPENESS]
SPLITS = ("train", "valid", "test")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PREFIX_PATTERN = re.compile(
    r"^(?P<prefix>.+)_(?P<capture>\d+)_(?:top|left|right|back|rear)(?:-\d+-?)?"
    r"(?:_(?:jpg|jpeg|png|bmp|webp))?$",
    re.IGNORECASE,
)
KNOWN_BAD_ROWS = {
    "B4_Latundan1_NoneChemical_02570_top_jpg.rf.995e92959d649ecc59efa0066dfece83.txt": "10 0.5 0.5 0.85 1",
    "B4_Latundan1_NoneChemical_02570_top_jpg.rf.b17c29c829489476c6a031ff4acd8f56.txt": "10 0.5 0.5 0.75 1",
}


class PreparationError(ValueError):
    """Unsafe paths, invalid data or an impossible grouped split."""


@dataclass
class Photo:
    image: Path
    label: Path
    original_split: str
    prefix: str
    capture: str
    group: str
    classes: frozenset[int]
    label_text: str
    correction: dict | None = None


def _identity(filename: str) -> tuple[str, str]:
    stem = Path(filename).stem.split(".rf.", 1)[0]
    match = PREFIX_PATTERN.fullmatch(stem)
    if match is None:
        raise PreparationError(f"Cannot infer bunch prefix from {filename!r}")
    return match["prefix"], f"{match['prefix']}_{match['capture']}"


def infer_prefix(filename: str) -> str:
    return _identity(filename)[0]


def infer_capture(filename: str) -> str:
    return _identity(filename)[1]


def _paths(source: Path, output: Path) -> tuple[Path, Path]:
    if output.exists() or output.is_symlink():
        raise PreparationError(f"Output already exists; choose a new directory: {output}")
    source, output = source.resolve(), output.resolve()
    if not source.is_dir():
        raise PreparationError(f"Source directory does not exist: {source}")
    if source == output or source in output.parents or output in source.parents:
        raise PreparationError("Source and output must be disjoint directories")
    if output.exists():
        raise PreparationError(f"Output already exists; choose a new directory: {output}")
    return source, output


def _names(source: Path) -> list[str]:
    yaml = source / "data.yaml"
    if not yaml.is_file() or not yaml.resolve().is_relative_to(source):
        raise PreparationError("Source must contain its own data.yaml")
    text = yaml.read_text(encoding="utf-8-sig")
    match = re.search(r"^names:\s*(\[.*\])\s*$", text, re.MULTILINE)
    try:
        names = ast.literal_eval(match[1]) if match else None
    except (SyntaxError, ValueError) as exc:
        raise PreparationError("Invalid inline names list in data.yaml") from exc
    if (
        not isinstance(names, list)
        or len(names) != 12
        or not all(isinstance(name, str) for name in names)
        or set(names) != set(EXPECTED_NAMES)
    ):
        raise PreparationError("Expected the 12 cultivar/ripeness names in data.yaml")
    nc = re.search(r"^nc:\s*(\d+)\s*$", text, re.MULTILINE)
    if nc is None or int(nc[1]) != 12:
        raise PreparationError("Expected nc: 12 in data.yaml")
    return names


def _read_label(path: Path, original_split: str) -> tuple[str, frozenset[int], dict | None]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    classes, kept = set(), []
    correction = None
    expected_bad_row = KNOWN_BAD_ROWS.get(path.name) if original_split == "train" else None
    if expected_bad_row and (len(lines) < 7 or lines[6].split() != expected_bad_row.split()):
        raise PreparationError(f"Known defect changed; review {path}:7 before preparing a copy")
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        values = line.split()
        try:
            if len(values) != 5:
                raise ValueError("expected five fields")
            cls = int(values[0])
            x, y, width, height = map(float, values[1:])
            if not 0 <= cls < 12:
                raise ValueError("class must be 0..11")
            if not all(math.isfinite(value) for value in (x, y, width, height)):
                raise ValueError("coordinates must be finite")
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
                raise ValueError("expected normalized coordinates and positive dimensions")
        except ValueError as exc:
            raise PreparationError(f"Invalid label {path}:{number}: {exc}") from exc
        if expected_bad_row and number == 7:
            correction = {"line": 7, "old_row": line, "action": "remove_confirmed_background_box"}
            continue
        kept.append(line)
        classes.add(cls)
    if not kept:
        raise PreparationError(f"Empty labels need explicit background-image review: {path}")
    return "\n".join(kept) + "\n", frozenset(classes), correction


def _photos(source: Path, aliases: dict[str, str], exclude_captures: dict[str, str]):
    photos, exclusions, prefixes, captures = [], [], set(), set()
    for split in SPLITS:
        images, labels = source / split / "images", source / split / "labels"
        if not images.is_dir() or not labels.is_dir():
            raise PreparationError(f"Missing {split}/images or {split}/labels")
        seen = set()
        for image in sorted(images.iterdir()):
            if image.suffix.lower() not in IMAGE_SUFFIXES or not image.is_file():
                continue
            label = labels / f"{image.stem}.txt"
            if image.stem in seen:
                raise PreparationError(f"Multiple images share label stem: {image.stem}")
            if not label.is_file():
                raise PreparationError(f"Missing label for {image}")
            if not image.resolve().is_relative_to(source) or not label.resolve().is_relative_to(
                source
            ):
                raise PreparationError(
                    f"Source entry resolves outside the supplied dataset: {image}"
                )
            seen.add(image.stem)
            prefix, capture = _identity(image.name)
            prefixes.add(prefix)
            captures.add(capture)
            if capture in exclude_captures:
                exclusions.append(
                    {
                        "source_image": str(image.relative_to(source)),
                        "source_label": str(label.relative_to(source)),
                        "original_split": split,
                        "inferred_prefix": prefix,
                        "capture": capture,
                        "group": aliases.get(prefix, prefix),
                        "reason": "explicit_capture_quarantine",
                        "explanation": exclude_captures[capture],
                    }
                )
                continue
            label_text, classes, correction = _read_label(label, split)
            photos.append(
                Photo(
                    image,
                    label,
                    split,
                    prefix,
                    capture,
                    aliases.get(prefix, prefix),
                    classes,
                    label_text,
                    correction,
                )
            )
        orphaned = sorted(path.name for path in labels.glob("*.txt") if path.stem not in seen)
        if orphaned:
            raise PreparationError(f"Labels without images in {split}: {orphaned[:5]}")
    if not photos:
        raise PreparationError("No supported images found")
    if unknown := set(aliases) - prefixes:
        raise PreparationError(f"Alias keys do not match inferred prefixes: {sorted(unknown)}")
    if unknown := set(exclude_captures) - captures:
        raise PreparationError(f"Quarantine keys do not match captures: {sorted(unknown)}")
    return photos, exclusions


def _sizes(count: int) -> dict[str, int]:
    if count < 3:
        raise PreparationError("Each cultivar needs at least three groups for train/valid/test")
    # Nearest integer allocation to 70/15/15, keeping at least one group per split.
    candidates = []
    for valid in range(1, count - 1):
        for test in range(1, count - valid):
            train = count - valid - test
            error = (
                (train - count * 0.70) ** 2
                + (valid - count * 0.15) ** 2
                + (test - count * 0.15) ** 2
            )
            candidates.append((error, abs(valid - test), -train, valid, test))
    _, _, negative_train, valid, test = min(candidates)
    return dict(train=-negative_train, valid=valid, test=test)


def _allocate(photos: list[Photo], names: list[str], seed: int, attempts: int) -> dict[str, str]:
    groups = defaultdict(list)
    for photo in photos:
        groups[photo.group].append(photo)
    by_cultivar = defaultdict(list)
    all_classes, heldout_classes = {}, {}
    for group, members in sorted(groups.items()):
        all_classes[group] = set().union(*(photo.classes for photo in members))
        heldout_classes[group] = set().union(
            *(photo.classes for photo in members if photo.original_split != "train")
        )
        cultivars = {names[cls].split("_", 1)[0] for cls in all_classes[group]}
        if len(cultivars) != 1:
            raise PreparationError(
                f"Group {group!r} contains mixed cultivar labels: {sorted(cultivars)}"
            )
        by_cultivar[next(iter(cultivars))].append(group)
    missing = []
    for cls, name in enumerate(names):
        total = sum(cls in present for present in all_classes.values())
        eligible = sum(cls in present for present in heldout_classes.values())
        if total < 3 or eligible < 2:
            missing.append(
                f"{name}: {total} total groups, {eligible} with original valid/test labels"
            )
    if missing:
        raise PreparationError(
            "Class coverage is impossible; need >=3 total and >=2 held-out-eligible "
            "groups per class:\n" + "\n".join(missing)
        )
    sizes = {cultivar: _sizes(len(ids)) for cultivar, ids in by_cultivar.items()}
    rng = random.Random(seed)
    best_missing = None
    for _ in range(attempts):
        allocation, coverage = {}, {split: set() for split in SPLITS}
        for cultivar, ids in sorted(by_cultivar.items()):
            shuffled = list(ids)
            rng.shuffle(shuffled)
            offset = 0
            for split in SPLITS:
                chosen = shuffled[offset : offset + sizes[cultivar][split]]
                offset += sizes[cultivar][split]
                for group in chosen:
                    allocation[group] = split
                    coverage[split].update(
                        all_classes[group] if split == "train" else heldout_classes[group]
                    )
        absent = {
            split: [name for cls, name in enumerate(names) if cls not in present]
            for split, present in coverage.items()
        }
        if not any(absent.values()):
            return allocation
        if best_missing is None or sum(map(len, absent.values())) < sum(
            map(len, best_missing.values())
        ):
            best_missing = absent
    raise PreparationError(
        f"No complete-class 70/15/15 grouped allocation in {attempts} deterministic attempts. "
        f"Nearest attempt missing: {json.dumps(best_missing)}. Group counts: "
        f"{json.dumps(sizes)}. Review group aliases or obtain more independent held-out groups."
    )


def prepare_dataset(
    source: Path,
    output: Path,
    *,
    seed: int = 42,
    aliases: dict[str, str] | None = None,
    exclude_captures: dict[str, str] | None = None,
    attempts: int = 20000,
) -> dict:
    source, output = _paths(Path(source), Path(output))
    aliases = {} if aliases is None else dict(aliases)
    exclude_captures = {} if exclude_captures is None else dict(exclude_captures)
    for label, mapping in (("Aliases", aliases), ("Capture exclusions", exclude_captures)):
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not key.strip()
            or not value.strip()
            for key, value in mapping.items()
        ):
            raise PreparationError(f"{label} must map nonempty keys to nonempty strings")
    if attempts < 1:
        raise PreparationError("Allocation attempts must be positive")
    names = _names(source)
    photos, quarantined = _photos(source, aliases, exclude_captures)
    allocation = _allocate(photos, names, seed, attempts)
    manifest = {
        "format_version": 1,
        "source": str(source),
        "output": str(output),
        "seed": seed,
        "class_names": names,
        "target_group_ratios": {"train": 0.70, "valid": 0.15, "test": 0.15},
        "grouping_assumption": "Filename prefix before capture number/camera is an unverified "
        "bunch proxy; aliases join proxies but do not establish physical identity. "
        "All sessions/views/augmentations for each resulting group stay together.",
        "heldout_policy": "Only original valid/test files are copied to held-out splits. "
        "Their unaugmented status follows the supplied export convention, not RF hashes. "
        "Original train variants assigned to held-out groups are excluded.",
        "aliases": aliases,
        "exclude_captures": exclude_captures,
        "group_assignments": allocation,
        "files": [],
        "exclusions": quarantined,
        "corrections": [],
        "summary": {},
    }
    # All validation and allocation happens before creating any output.
    output.mkdir(parents=True, exist_ok=False)
    for split in SPLITS:
        (output / split / "images").mkdir(parents=True)
        (output / split / "labels").mkdir()
    counters = {split: Counter() for split in SPLITS}
    for photo in photos:
        split = allocation[photo.group]
        provenance = {
            "source_image": str(photo.image.relative_to(source)),
            "source_label": str(photo.label.relative_to(source)),
            "original_split": photo.original_split,
            "inferred_prefix": photo.prefix,
            "capture": photo.capture,
            "group": photo.group,
            "assigned_split": split,
        }
        included = split == "train" or photo.original_split != "train"
        if photo.correction:
            manifest["corrections"].append(
                {**provenance, **photo.correction, "applied_to_copy": included}
            )
        if not included:
            manifest["exclusions"].append(
                {**provenance, "reason": "original_train_variant_in_heldout_group"}
            )
            continue
        # Prefix source split to avoid filename collisions when old splits merge.
        image_name = f"{photo.original_split}__{photo.image.name}"
        image_target = output / split / "images" / image_name
        label_target = output / split / "labels" / f"{Path(image_name).stem}.txt"
        shutil.copy2(photo.image, image_target)
        label_target.write_text(photo.label_text, encoding="utf-8")
        classes = Counter(int(line.split()[0]) for line in photo.label_text.splitlines())
        counters[split].update(classes)
        manifest["files"].append(
            {
                **provenance,
                "image": str(image_target.relative_to(output)),
                "label": str(label_target.relative_to(output)),
                "boxes": sum(classes.values()),
            }
        )
    for split in SPLITS:
        manifest["summary"][split] = {
            "groups": sum(value == split for value in allocation.values()),
            "images": sum(item["assigned_split"] == split for item in manifest["files"]),
            "boxes": sum(counters[split].values()),
            "class_boxes": {name: counters[split][cls] for cls, name in enumerate(names)},
        }
    yaml = (
        f"path: {json.dumps(output.as_posix())}\ntrain: train/images\nval: valid/images\n"
        f"test: test/images\nnc: 12\nnames: {json.dumps(names)}\n"
    )
    (output / "data.yaml").write_text(yaml, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--aliases", type=Path, help="JSON object mapping inferred prefixes to grouped IDs"
    )
    parser.add_argument(
        "--exclude-captures",
        type=Path,
        help="JSON object mapping capture IDs to quarantine reasons",
    )
    args = parser.parse_args(argv)
    try:
        aliases = json.loads(args.aliases.read_text(encoding="utf-8-sig")) if args.aliases else None
        exclusions = (
            json.loads(args.exclude_captures.read_text(encoding="utf-8-sig"))
            if args.exclude_captures
            else None
        )
        if any(
            value is not None and not isinstance(value, dict) for value in (aliases, exclusions)
        ):
            raise PreparationError("Alias and capture-quarantine JSON must be objects")
        manifest = prepare_dataset(
            args.source, args.output, seed=args.seed, aliases=aliases, exclude_captures=exclusions
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Preparation failed: {exc}\nNo source files were modified.\n")
    print(
        json.dumps(
            {
                "output": manifest["output"],
                "summary": manifest["summary"],
                "excluded": len(manifest["exclusions"]),
                "confirmed_defects_logged": len(manifest["corrections"]),
                "corrections_applied": sum(
                    item["applied_to_copy"] for item in manifest["corrections"]
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
