"""Curate open-source out-of-distribution (OOD) images without modifying source data.

Source: Open Images V7 (images CC BY 2.0, annotations CC BY 4.0). No image is stored
in Git; the committed manifest pins the exact image IDs so every pool is reproducible.

Pools (pairwise disjoint by image ID and by file hash):
  train_negatives  background images for detector retraining
  calibration      threshold calibration for the inference gate
  benchmark        held-out evaluation only; never train or tune on it

Negatives come from the official validation split (train_negatives, calibration) and
the official test split (benchmark). Banana positives are rare there, so they come from
the official train split, divided between calibration and benchmark by image ID.

Groups inside each pool:
  near    other produce and yellow/green/curved lookalikes (hard negatives)
  far     people, rooms, vehicles, printed matter, everyday objects
  banana  generic banana photos; a proxy positive for the banana gate only. They carry
          no cultivar label and may show unsupported varieties.

Commands:
  build-manifest   select image IDs from the Open Images label files (deterministic)
  fetch            download the manifest images with strict validation
  merge-negatives  copy a prepared YOLO dataset and add background images to train
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FORMAT_VERSION = 1
SOURCE_NAME = "Open Images V7"
SOURCE_LICENSE = "Images CC BY 2.0; annotations CC BY 4.0 (Google LLC)"
METADATA_HOST = "storage.googleapis.com"
IMAGE_HOST = "open-images-dataset.s3.amazonaws.com"
METADATA_FILES = {
    "classes": "openimages/v7/oidv7-class-descriptions-boxable.csv",
    "validation_labels": "openimages/v5/validation-annotations-human-imagelabels-boxable.csv",
    "validation_boxes": "openimages/v5/validation-annotations-bbox.csv",
    "test_labels": "openimages/v5/test-annotations-human-imagelabels-boxable.csv",
    "test_boxes": "openimages/v5/test-annotations-bbox.csv",
}
# 2.3 GB: streamed and reduced to its banana rows; the full file is never stored.
TRAIN_BOXES = "openimages/v6/oidv6-train-annotations-bbox.csv"
TRAIN_BANANA_BOXES = "train-banana-bbox.csv"
MAX_METADATA_BYTES = 200 * 1024 * 1024
MAX_STREAM_BYTES = 4 * 1024 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_ID = re.compile(r"[0-9a-f]{16}")
SLUG = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
POOLS = ("train_negatives", "calibration", "benchmark")
NEGATIVE_SPLIT = {
    "train_negatives": "validation", "calibration": "validation", "benchmark": "test",
}
BANANA_SPLIT = "train"
SPLITS = ("train", "validation", "test")
GROUPS = ("near", "far", "banana")
BANANA_CLASS = "Banana"
# A banana smaller than this share of the frame is not a usable gate positive.
MIN_BANANA_AREA = 0.10
MAX_BOXES_PER_IMAGE = 30

NEAR_CLASSES = (
    "Lemon (plant)", "Mango", "Orange (fruit)", "Apple", "Pear", "Grapefruit", "Peach",
    "Pineapple", "Cantaloupe", "Squash (Plant)", "Zucchini", "Cucumber", "Bell pepper",
    "Carrot", "Hot dog", "French fries", "Croissant", "Pasta", "Pumpkin",
    "Common sunflower", "Potato", "Winter melon", "Cheese", "Watermelon",
)
FAR_CLASSES = (
    "Person", "Human hand", "Human face", "Car", "Chair", "Table", "Laptop",
    "Mobile phone", "Book", "Bottle", "Building", "Tree", "Dog", "Cat", "Bicycle",
    "Poster", "Whiteboard", "Couch", "Box", "Coffee cup", "Plastic bag", "Toy",
    "Houseplant", "Television",
)


class OODPreparationError(ValueError):
    """Unsafe input, invalid data or a leakage violation."""


def slug(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not SLUG.fullmatch(value):
        raise OODPreparationError(f"Cannot derive a safe class folder from {name!r}")
    return value


def _rank(seed: int, image_id: str) -> str:
    return hashlib.sha256(f"{seed}:{image_id}".encode()).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def _open(host: str, path: str, limit: int):
    """Open one object on an allowlisted HTTPS host; redirects are refused."""
    if host not in (METADATA_HOST, IMAGE_HOST):
        raise OODPreparationError(f"Host is not allowlisted: {host}")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", path) or ".." in path or path.startswith("/"):
        raise OODPreparationError(f"Unsafe object path: {path!r}")
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    response = opener.open(urllib.request.Request(f"https://{host}/{path}"), timeout=60)
    declared = response.headers.get("Content-Length")
    if response.status != 200 or (declared is not None and int(declared) > limit):
        response.close()
        raise OODPreparationError(f"Refused HTTP {response.status} or oversized object: {path}")
    return response


def _https_get(host: str, path: str, limit: int) -> bytes:
    with _open(host, path, limit) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise OODPreparationError(f"Object exceeds {limit} bytes: {path}")
    return body


def _https_filter_lines(host: str, path: str, needle: bytes, limit: int) -> bytes:
    """Stream a large CSV and keep its header plus the lines containing needle."""
    kept, seen = [], 0
    with _open(host, path, limit) as response:
        for number, line in enumerate(response):
            seen += len(line)
            if seen > limit:
                raise OODPreparationError(f"Object exceeds {limit} bytes: {path}")
            if number == 0 or needle in line:
                kept.append(line)
    return b"".join(kept)


def download_metadata(target: Path) -> dict[str, Path]:
    """Download the Open Images label files once into a local cache directory."""
    target.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, remote in METADATA_FILES.items():
        path = target / Path(remote).name
        if not path.is_file():
            _atomic_write(path, _https_get(METADATA_HOST, remote, MAX_METADATA_BYTES))
        paths[key] = path
    banana = target / TRAIN_BANANA_BOXES
    if not banana.is_file():
        needle = f",{_class_ids(paths['classes'])[BANANA_CLASS]},".encode()
        _atomic_write(
            banana, _https_filter_lines(METADATA_HOST, TRAIN_BOXES, needle, MAX_STREAM_BYTES)
        )
    paths["train_banana_boxes"] = banana
    return paths


def _atomic_write(path: Path, data: bytes) -> None:
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".partial-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _rows(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def _class_ids(path: Path) -> dict[str, str]:
    names = {row["DisplayName"].strip(): row["LabelName"].strip() for row in _rows(path)}
    missing = [name for name in (*NEAR_CLASSES, *FAR_CLASSES, BANANA_CLASS) if name not in names]
    if missing:
        raise OODPreparationError(f"Classes missing from Open Images: {missing}")
    return names


def _negative_candidates(
    labels: Path, boxes: Path, class_ids: dict[str, str]
) -> dict[str, set[str]]:
    """Return banana-free positive image IDs for each near/far class."""
    wanted = {class_ids[name]: name for name in (*NEAR_CLASSES, *FAR_CLASSES)}
    banana_id = class_ids[BANANA_CLASS]
    positives: dict[str, set[str]] = defaultdict(set)
    tainted: set[str] = set()
    for row in _rows(labels):
        image_id, label = row["ImageID"], row["LabelName"]
        if not IMAGE_ID.fullmatch(image_id) or row["Confidence"] != "1":
            continue
        if label == banana_id:
            tainted.add(image_id)
        elif label in wanted:
            positives[wanted[label]].add(image_id)
    tainted.update(row["ImageID"] for row in _rows(boxes) if row["LabelName"] == banana_id)
    return {name: ids - tainted for name, ids in positives.items()}


def _object_boxes(boxes: Path, wanted: dict[str, set[str]]) -> dict[str, list[list[float]]]:
    """Annotated boxes (normalised x1, y1, x2, y2) of each image's own class.

    wanted maps a class label ID to the image IDs selected for that class.
    """
    found: dict[str, list[list[float]]] = defaultdict(list)
    for row in _rows(boxes):
        if row["ImageID"] in wanted.get(row["LabelName"], ()):
            found[row["ImageID"]].append(
                [round(float(row[key]), 4) for key in ("XMin", "YMin", "XMax", "YMax")]
            )
    return found


def _prominent_bananas(boxes: Path, banana_id: str) -> set[str]:
    """Photographed (not drawn) bananas that fill a useful share of the frame."""
    area: dict[str, float] = {}
    depicted: set[str] = set()
    for row in _rows(boxes):
        if row["LabelName"] != banana_id or not IMAGE_ID.fullmatch(row["ImageID"]):
            continue
        if row["IsDepiction"] == "1":
            depicted.add(row["ImageID"])
            continue
        size = (float(row["XMax"]) - float(row["XMin"])) * (
            float(row["YMax"]) - float(row["YMin"])
        )
        area[row["ImageID"]] = max(area.get(row["ImageID"], 0.0), size)
    return {i for i, size in area.items() if size >= MIN_BANANA_AREA and i not in depicted}


def build_manifest(
    metadata: dict[str, Path], *, seed: int, per_class: int, banana_per_pool: int
) -> dict:
    """Select deterministic, pairwise-disjoint pools from the official splits."""
    if per_class < 1 or banana_per_pool < 0:
        raise OODPreparationError("Pool sizes must be positive")
    class_ids = _class_ids(metadata["classes"])
    pools: dict[str, list[dict]] = {pool: [] for pool in POOLS}
    for split in ("validation", "test"):
        positives = _negative_candidates(
            metadata[f"{split}_labels"], metadata[f"{split}_boxes"], class_ids
        )
        # Alternate ranked images so pools sharing a split get an even class mix.
        split_pools = sorted(pool for pool in POOLS if NEGATIVE_SPLIT[pool] == split)
        used: set[str] = set()
        for group, classes in (("near", NEAR_CLASSES), ("far", FAR_CLASSES)):
            for name in classes:
                ranked = sorted(
                    (i for i in positives.get(name, ()) if i not in used),
                    key=lambda image_id: _rank(seed, image_id),
                )
                for index, pool in enumerate(split_pools):
                    chosen = ranked[index::len(split_pools)][:per_class]
                    used.update(chosen)
                    pools[pool].extend(
                        {"id": image_id, "split": split, "group": group, "class": name}
                        for image_id in chosen
                    )
    # Training negatives must never contain a banana.
    bananas = sorted(
        _prominent_bananas(metadata["train_banana_boxes"], class_ids[BANANA_CLASS]),
        key=lambda image_id: _rank(seed, image_id),
    )
    for index, pool in enumerate(("benchmark", "calibration")):
        pools[pool].extend(
            {"id": image_id, "split": BANANA_SPLIT, "group": "banana", "class": BANANA_CLASS}
            for image_id in bananas[index::2][:banana_per_pool]
        )
    # Object boxes let the evaluation ask: would a box on this object survive the gate?
    box_files = {
        "validation": metadata["validation_boxes"], "test": metadata["test_boxes"],
        BANANA_SPLIT: metadata["train_banana_boxes"],
    }
    # Background training images need no boxes.
    evaluated = [item for pool in ("calibration", "benchmark") for item in pools[pool]]
    for split, path in box_files.items():
        wanted: dict[str, set[str]] = defaultdict(set)
        for item in evaluated:
            if item["split"] == split:
                wanted[class_ids[item["class"]]].add(item["id"])
        found = _object_boxes(path, wanted)
        for item in evaluated:
            if item["split"] == split:
                item["boxes"] = found.get(item["id"], [])[:MAX_BOXES_PER_IMAGE]
    manifest = {
        "format_version": FORMAT_VERSION,
        "source": SOURCE_NAME,
        "license": SOURCE_LICENSE,
        "image_url_template": f"https://{IMAGE_HOST}/{{split}}/{{id}}.jpg",
        "seed": seed,
        "per_class": per_class,
        "banana_per_pool": banana_per_pool,
        "min_banana_area": MIN_BANANA_AREA,
        "pools": pools,
    }
    validate_manifest(manifest)
    return manifest


def dump_manifest(manifest: dict) -> str:
    """One image per line keeps the committed manifest small and reviewable."""
    head = {key: value for key, value in manifest.items() if key != "pools"}
    lines = [json.dumps(head, indent=1)[:-2] + ',\n "pools": {']
    for index, pool in enumerate(POOLS):
        rows = ",\n".join(
            "   " + json.dumps(item, separators=(",", ":")) for item in manifest["pools"][pool]
        )
        lines.append(f'  "{pool}": [\n{rows}\n  ]' + ("," if index < len(POOLS) - 1 else ""))
    lines.append(" }\n}\n")
    return "\n".join(lines)


def validate_manifest(manifest: dict) -> dict[str, Counter]:
    """Reject malformed entries and any image shared between pools."""
    if manifest.get("format_version") != FORMAT_VERSION:
        raise OODPreparationError("Unsupported OOD manifest version")
    pools = manifest.get("pools")
    if not isinstance(pools, dict) or set(pools) != set(POOLS):
        raise OODPreparationError(f"Manifest must define exactly these pools: {POOLS}")
    seen: dict[str, str] = {}
    summary: dict[str, Counter] = {}
    for pool in POOLS:
        counts: Counter = Counter()
        for item in pools[pool]:
            image_id, group, name = item.get("id"), item.get("group"), item.get("class")
            if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
                raise OODPreparationError(f"Invalid image ID in {pool}: {image_id!r}")
            if group not in GROUPS or not isinstance(name, str):
                raise OODPreparationError(f"Invalid group or class for {image_id}")
            slug(name)
            expected = BANANA_SPLIT if group == "banana" else NEGATIVE_SPLIT[pool]
            if item.get("split") != expected:
                raise OODPreparationError(f"Unexpected source split for {image_id} in {pool}")
            if group == "banana" and pool == "train_negatives":
                raise OODPreparationError("Training negatives must not contain bananas")
            if image_id in seen:
                raise OODPreparationError(
                    f"Leakage: {image_id} appears in {seen[image_id]} and {pool}"
                )
            seen[image_id] = pool
            counts[group] += 1
        summary[pool] = counts
    return summary


def _verify_jpeg(data: bytes) -> tuple[int, int]:
    """Decode-check the payload; anything other than a bounded JPEG is rejected."""
    import io

    from PIL import Image

    if not data.startswith(b"\xff\xd8\xff"):
        raise OODPreparationError("Payload is not a JPEG")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                raise OODPreparationError("Payload is not a JPEG")
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise OODPreparationError("Image exceeds the pixel limit")
            image.verify()
    except OODPreparationError:
        raise
    except Exception as exc:
        raise OODPreparationError(f"Image failed verification: {exc}") from exc
    return width, height


def image_path(root: Path, pool: str, item: dict) -> Path:
    return root / pool / item["group"] / slug(item["class"]) / f"{item['id']}.jpg"


def fetch_pools(
    manifest: dict, output: Path, *, pools: tuple[str, ...] = POOLS, workers: int = 8,
    downloader=None,
) -> dict:
    """Download the selected pools; existing verified files are kept, never replaced."""
    validate_manifest(manifest)
    unknown = [pool for pool in pools if pool not in POOLS]
    if unknown:
        raise OODPreparationError(f"Unknown pools: {unknown}")
    if not 1 <= workers <= 32:
        raise OODPreparationError("Workers must be between 1 and 32")
    download = downloader or (lambda split, image_id: _https_get(
        IMAGE_HOST, f"{split}/{image_id}.jpg", MAX_IMAGE_BYTES))
    output.mkdir(parents=True, exist_ok=True)
    root = output.resolve()
    jobs = [(pool, item) for pool in pools for item in manifest["pools"][pool]]

    def fetch(job: tuple[str, dict]) -> dict:
        pool, item = job
        path = image_path(root, pool, item)
        if not path.resolve().is_relative_to(root):
            raise OODPreparationError(f"Refusing to write outside the output: {path}")
        record = {"pool": pool, **item, "file": path.relative_to(root).as_posix()}
        try:
            if path.is_file():
                data = path.read_bytes()
            else:
                data = download(item["split"], item["id"])
            width, height = _verify_jpeg(data)
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(path, data)
        except (OODPreparationError, OSError, urllib.error.URLError) as exc:
            return {**record, "error": str(exc)}
        return {
            **record, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "width": width, "height": height,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(executor.map(fetch, jobs))
    files = [record for record in records if "error" not in record]
    failures = [record for record in records if "error" in record]
    # Byte-identical images under different IDs would still leak between pools.
    owners: dict[str, str] = {}
    for record in files:
        owner = owners.setdefault(record["sha256"], record["pool"])
        if owner != record["pool"]:
            raise OODPreparationError(
                f"Leakage: identical image bytes in {owner} and {record['pool']} "
                f"({record['id']})"
            )
    index = {
        "format_version": FORMAT_VERSION, "source": manifest["source"],
        "license": manifest["license"], "files": files, "failures": failures,
        "summary": {
            pool: dict(Counter(r["group"] for r in files if r["pool"] == pool)) for pool in pools
        },
    }
    (root / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def merge_negatives(dataset: Path, ood_root: Path, output: Path, *, ratio: float) -> dict:
    """Copy a prepared YOLO dataset and add unlabeled background images to train only."""
    if not 0 < ratio <= 0.5:
        raise OODPreparationError("Ratio must be in (0, 0.5]")
    if output.exists() or output.is_symlink():
        raise OODPreparationError(f"Output already exists; choose a new directory: {output}")
    dataset, ood_root, output = dataset.resolve(), ood_root.resolve(), output.resolve()
    for a, b in ((dataset, output), (ood_root, output)):
        if a == b or a in b.parents or b in a.parents:
            raise OODPreparationError("Dataset, OOD pool and output must be disjoint directories")
    train_images = dataset / "train" / "images"
    if not (dataset / "data.yaml").is_file() or not train_images.is_dir():
        raise OODPreparationError("Dataset must contain data.yaml and train/images")
    index_path = ood_root / "index.json"
    if not index_path.is_file():
        raise OODPreparationError("OOD pool has no index.json; run the fetch command first")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    held_out = {r["sha256"] for r in index["files"] if r["pool"] != "train_negatives"}
    candidates = sorted(
        (r for r in index["files"] if r["pool"] == "train_negatives"),
        key=lambda record: record["id"],
    )
    if not candidates:
        raise OODPreparationError("No fetched train_negatives images are available")
    existing = sum(1 for path in train_images.iterdir() if path.is_file())
    if existing == 0:
        raise OODPreparationError("Dataset train split has no images")
    wanted = max(1, round(existing * ratio))
    selected = candidates[:wanted]
    sources = []
    for record in selected:
        source = (ood_root / record["file"]).resolve()
        if not source.is_relative_to(ood_root) or not source.is_file():
            raise OODPreparationError(f"Missing or unsafe negative image: {record['file']}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != record["sha256"] or digest in held_out:
            raise OODPreparationError(f"Negative image failed integrity checks: {record['id']}")
        sources.append((record, source))
    # All validation happens before creating any output.
    shutil.copytree(dataset, output, symlinks=False)
    labels = output / "train" / "labels"
    labels.mkdir(exist_ok=True)
    added = []
    for record, source in sources:
        name = f"oodneg__{record['id']}"
        shutil.copy2(source, output / "train" / "images" / f"{name}.jpg")
        # An empty label file marks a background image: every pixel is "no banana".
        (labels / f"{name}.txt").write_text("", encoding="utf-8")
        added.append({"id": record["id"], "group": record["group"], "class": record["class"]})
    yaml_path = output / "data.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    patched = re.sub(
        r"^path:.*$", lambda _: f"path: {json.dumps(output.as_posix())}", text, flags=re.MULTILINE
    )
    yaml_path.write_text(patched, encoding="utf-8")
    report = {
        "format_version": FORMAT_VERSION, "source_dataset": str(dataset),
        "ood_source": index["source"], "license": index["license"], "ratio": ratio,
        "train_images_before": existing, "negatives_requested": wanted,
        "negatives_added": len(added), "by_group": dict(Counter(a["group"] for a in added)),
        "validation_and_test_splits": "unchanged", "added": added,
    }
    (output / "ood_negatives.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-manifest", help="select image IDs")
    build.add_argument("--metadata-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--seed", type=int, default=20261112)
    build.add_argument("--per-class", type=int, default=25)
    build.add_argument("--banana-per-pool", type=int, default=150)
    fetch = commands.add_parser("fetch", help="download manifest images")
    fetch.add_argument("--manifest", type=Path, required=True)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--pools", nargs="+", choices=POOLS, default=list(POOLS))
    fetch.add_argument("--workers", type=int, default=8)
    merge = commands.add_parser("merge-negatives", help="add background images to a copy")
    merge.add_argument("--dataset", type=Path, required=True)
    merge.add_argument("--ood", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--ratio", type=float, default=0.10)
    args = parser.parse_args(argv)
    try:
        if args.command == "build-manifest":
            if args.output.exists():
                raise OODPreparationError(f"Manifest already exists: {args.output}")
            manifest = build_manifest(
                download_metadata(args.metadata_dir), seed=args.seed,
                per_class=args.per_class, banana_per_pool=args.banana_per_pool,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(dump_manifest(manifest), encoding="utf-8")
            result = {pool: dict(c) for pool, c in validate_manifest(manifest).items()}
        elif args.command == "fetch":
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            index = fetch_pools(
                manifest, args.output, pools=tuple(args.pools), workers=args.workers
            )
            result = {"summary": index["summary"], "failures": len(index["failures"])}
        else:
            report = merge_negatives(args.dataset, args.ood, args.output, ratio=args.ratio)
            result = {key: value for key, value in report.items() if key != "added"}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        parser.exit(2, f"OOD preparation failed: {exc}\nNo source files were modified.\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
