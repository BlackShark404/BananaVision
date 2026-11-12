"""Synthetic Open Images metadata and a fake downloader; no network or real dataset."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts import prepare_ood_dataset as ood
from scripts.prepare_ood_dataset import OODPreparationError

CLASSES = (*ood.NEAR_CLASSES, *ood.FAR_CLASSES, ood.BANANA_CLASS)
LABEL_IDS = {name: f"/m/{index:04d}" for index, name in enumerate(CLASSES)}
BOX_FIELDS = ["ImageID", "Source", "LabelName", "Confidence", "XMin", "XMax", "YMin", "YMax",
              "IsOccluded", "IsTruncated", "IsGroupOf", "IsDepiction", "IsInside"]


def image_id(number: int) -> str:
    return f"{number:016x}"


def jpeg(seed: int) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 24), (seed % 256, (seed * 7) % 256, (seed * 13) % 256)).save(
        stream, "JPEG"
    )
    return stream.getvalue()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def box_row(image, name, *, area=0.5, depiction="0"):
    return {
        "ImageID": image, "Source": "xclick", "LabelName": LABEL_IDS[name], "Confidence": "1",
        "XMin": "0", "XMax": str(area), "YMin": "0", "YMax": "1", "IsOccluded": "0",
        "IsTruncated": "0", "IsGroupOf": "0", "IsDepiction": depiction, "IsInside": "0",
    }


@pytest.fixture
def metadata(tmp_path):
    """Lemon: six clean validation and three test images. Car: two per split."""
    classes = write_csv(tmp_path / "classes.csv", ["LabelName", "DisplayName"], [
        {"LabelName": label, "DisplayName": name} for name, label in LABEL_IDS.items()
    ])
    files = {"classes": classes}
    plans = {
        "validation": {"Lemon (plant)": range(100, 106), "Car": range(200, 202)},
        "test": {"Lemon (plant)": range(300, 303), "Car": range(400, 402)},
    }
    tainted = {"validation": 150, "test": 350}
    for split, plan in plans.items():
        labels, boxes = [], []
        for name, numbers in plan.items():
            for number in numbers:
                labels.append({"ImageID": image_id(number), "Source": "verification",
                               "LabelName": LABEL_IDS[name], "Confidence": "1"})
                boxes.append(box_row(image_id(number), name))
        # A lemon photo that also shows a banana must never become a negative.
        lemon_with_banana = image_id(tainted[split])
        labels.append({"ImageID": lemon_with_banana, "Source": "verification",
                       "LabelName": LABEL_IDS["Lemon (plant)"], "Confidence": "1"})
        boxes.append(box_row(lemon_with_banana, ood.BANANA_CLASS))
        # Verified absence (Confidence 0) is not a positive label.
        labels.append({"ImageID": image_id(tainted[split] + 1), "Source": "verification",
                       "LabelName": LABEL_IDS["Car"], "Confidence": "0"})
        fields = ["ImageID", "Source", "LabelName", "Confidence"]
        files[f"{split}_labels"] = write_csv(tmp_path / f"{split}-labels.csv", fields, labels)
        files[f"{split}_boxes"] = write_csv(tmp_path / f"{split}-boxes.csv", BOX_FIELDS, boxes)
    files["train_banana_boxes"] = write_csv(tmp_path / "train-banana.csv", BOX_FIELDS, [
        *[box_row(image_id(number), ood.BANANA_CLASS) for number in range(500, 504)],
        box_row(image_id(510), ood.BANANA_CLASS, area=0.05),      # too small
        box_row(image_id(511), ood.BANANA_CLASS, depiction="1"),  # a drawing
    ])
    return files


def ids(manifest, pool, group=None):
    return {i["id"] for i in manifest["pools"][pool] if group in (None, i["group"])}


def test_manifest_pools_are_disjoint_banana_free_and_deterministic(metadata):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    again = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    assert manifest == again
    train, calibration, benchmark = (ids(manifest, pool) for pool in ood.POOLS)
    assert not (train & calibration or train & benchmark or calibration & benchmark)
    # Validation lemons are shared evenly; the held-out pool uses only the test split.
    assert len(ids(manifest, "train_negatives", "near")) == 3
    assert len(ids(manifest, "calibration", "near")) == 3
    assert ids(manifest, "benchmark", "near") == {image_id(n) for n in range(300, 303)}
    everything = train | calibration | benchmark
    assert image_id(150) not in everything and image_id(350) not in everything
    assert image_id(151) not in everything  # verified-absent label
    # Bananas: prominent photographs only, and never among training negatives.
    bananas = ids(manifest, "calibration", "banana") | ids(manifest, "benchmark", "banana")
    assert bananas == {image_id(n) for n in range(500, 504)}
    assert not ids(manifest, "train_negatives", "banana")
    assert all("boxes" not in item for item in manifest["pools"]["train_negatives"])
    assert all(item["boxes"] for item in manifest["pools"]["benchmark"])
    assert json.loads(ood.dump_manifest(manifest)) == manifest
    assert ood.build_manifest(metadata, seed=8, per_class=3, banana_per_pool=2) != manifest


def test_manifest_validation_rejects_leakage_and_unsafe_entries(metadata):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)

    def broken(change, message):
        copy = json.loads(json.dumps(manifest))
        change(copy["pools"])
        with pytest.raises(OODPreparationError, match=message):
            ood.validate_manifest(copy)

    def banana(pools, pool):
        return next(item for item in pools[pool] if item["group"] == "banana")

    # Pools that share an official split are separated only by the image-ID check.
    broken(lambda pools: pools["calibration"].append(dict(pools["train_negatives"][0])),
           "Leakage: .* appears in train_negatives and calibration")
    broken(lambda pools: pools["benchmark"].append(dict(banana(pools, "calibration"))),
           "Leakage: .* appears in calibration and benchmark")
    broken(lambda pools: pools["benchmark"].append(dict(pools["train_negatives"][0])),
           "Unexpected source split")
    broken(lambda pools: pools["benchmark"][0].update(id="../../etc/passwd"), "Invalid image ID")
    broken(lambda pools: pools["benchmark"][0].update({"class": "../.."}), "safe class folder")
    broken(lambda pools: pools["benchmark"][0].update(group="unknown"), "Invalid group")
    broken(lambda pools: pools["calibration"][0].update(split="test"), "Unexpected source split")
    broken(lambda pools: pools["train_negatives"].append(
        {"id": image_id(999), "split": "train", "group": "banana", "class": "Banana"}),
        "Unexpected source split|must not contain bananas")
    with pytest.raises(OODPreparationError, match="Unsupported OOD manifest version"):
        ood.validate_manifest({**manifest, "format_version": 99})
    with pytest.raises(OODPreparationError, match="exactly these pools"):
        ood.validate_manifest({**manifest, "pools": {"benchmark": []}})


def test_inspected_banana_images_never_become_training_negatives(metadata, monkeypatch):
    baseline = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    excluded = baseline["pools"]["train_negatives"][0]
    monkeypatch.setattr(ood, "EXCLUDED_TRAIN_NEGATIVES", {excluded["id"]: "shows a banana"})
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    assert excluded["id"] not in ids(manifest, "train_negatives")
    assert len(ids(manifest, "train_negatives")) == len(ids(baseline, "train_negatives")) - 1
    # Held-out pools keep their selection, so earlier measurements stay comparable.
    for pool in ("calibration", "benchmark"):
        assert manifest["pools"][pool] == baseline["pools"][pool]
    with pytest.raises(OODPreparationError, match="bananas"):
        ood.validate_manifest(baseline)
    # The pinned manifest in the repository honors the same list.
    pinned = json.loads((Path(ood.__file__).parent / "ood" / "open_images_ood_manifest.json")
                        .read_text(encoding="utf-8"))
    monkeypatch.undo()
    ood.validate_manifest(pinned)
    assert not ids(pinned, "train_negatives") & set(ood.EXCLUDED_TRAIN_NEGATIVES)


def test_remote_access_is_limited_to_allowlisted_hosts_and_plain_paths():
    for host, path in [
        ("example.com", "validation/0000000000000001.jpg"),
        (ood.IMAGE_HOST, "../secret"),
        (ood.IMAGE_HOST, "/absolute"),
        (ood.IMAGE_HOST, "validation/a b.jpg"),
        (ood.IMAGE_HOST, "validation/x.jpg?redirect=http://example.com"),
    ]:
        with pytest.raises(OODPreparationError):
            ood._https_get(host, path, 10)


def test_fetch_verifies_images_keeps_existing_files_and_records_failures(metadata, tmp_path):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    not_jpeg = manifest["pools"]["benchmark"][0]["id"]
    calls = []

    def download(split, identifier):
        calls.append((split, identifier))
        if identifier == not_jpeg:
            stream = io.BytesIO()
            Image.new("RGB", (8, 8)).save(stream, "PNG")
            return stream.getvalue()
        return jpeg(int(identifier, 16))

    output = tmp_path / "pool"
    index = ood.fetch_pools(manifest, output, workers=2, downloader=download)
    total = sum(len(items) for items in manifest["pools"].values())
    assert index["failures"][0]["error"] == "Payload is not a JPEG"
    assert len(calls) == total and len(index["files"]) == total - 1
    assert [failure["id"] for failure in index["failures"]] == [not_jpeg]
    assert not list(output.rglob(f"{not_jpeg}.jpg"))
    for record in index["files"]:
        path = output / record["file"]
        assert path.resolve().is_relative_to(output.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        assert (record["width"], record["height"]) == (32, 24)
    assert not list(output.rglob(".partial-*"))
    # Splits follow the manifest: bananas from train, benchmark negatives from test.
    by_id = {identifier: split for split, identifier in calls}
    assert by_id[image_id(500)] == "train" and by_id[image_id(400)] == "test"

    calls.clear()
    again = ood.fetch_pools(manifest, output, workers=2, downloader=download)
    assert calls == [("test", not_jpeg)]  # verified files are reused, not replaced
    assert again["files"] == index["files"]


def test_fetch_stops_on_identical_images_in_two_pools(metadata, tmp_path):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    with pytest.raises(OODPreparationError, match="Leakage"):
        ood.fetch_pools(manifest, tmp_path / "pool", downloader=lambda *_: jpeg(1))


def test_fetching_one_pool_keeps_the_others_in_the_index_and_in_the_leak_check(
    metadata, tmp_path,
):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    output = tmp_path / "pool"

    def download(_, identifier):
        return jpeg(int(identifier, 16))

    ood.fetch_pools(manifest, output, pools=("train_negatives",), downloader=download)
    index = ood.fetch_pools(manifest, output, pools=("benchmark",), downloader=download)
    assert {record["pool"] for record in index["files"]} == {"train_negatives", "benchmark"}
    assert set(index["summary"]) == {"train_negatives", "benchmark"}
    assert json.loads((output / "index.json").read_text()) == index
    # A calibration image identical to an already fetched training negative is caught.
    duplicate = (output / index["files"][0]["file"]).read_bytes()
    with pytest.raises(OODPreparationError, match="Leakage"):
        ood.fetch_pools(manifest, output, pools=("calibration",),
                        downloader=lambda *_: duplicate)


def cut_scan_data() -> bytes:
    """A JPEG whose headers are intact and whose image data stops halfway."""
    import numpy as np

    pixels = np.random.default_rng(3).integers(0, 256, (120, 160, 3), dtype=np.uint8)
    stream = io.BytesIO()
    Image.fromarray(pixels).save(stream, "JPEG", quality=90)
    data = stream.getvalue()
    return data[: len(data) // 2]


def test_jpeg_check_decodes_the_whole_image_and_caps_its_size(monkeypatch):
    data = cut_scan_data()
    # Reading the headers alone accepts this payload; only a full decode exposes it.
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG" and image.size == (160, 120)
    with pytest.raises(OODPreparationError, match="Image failed verification"):
        ood._verify_jpeg(data)
    assert ood._verify_jpeg(jpeg(5)) == (32, 24)
    png = io.BytesIO()
    Image.new("RGB", (8, 8)).save(png, "PNG")
    with pytest.raises(OODPreparationError, match="not a JPEG"):
        ood._verify_jpeg(png.getvalue())
    monkeypatch.setattr(ood, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(OODPreparationError, match="pixel limit"):
        ood._verify_jpeg(jpeg(5))


class StubResponse(io.BytesIO):
    def __init__(self, status=200, length="4", body=b"data"):
        super().__init__(body)
        self.status, self.headers = status, ({} if length is None else {"Content-Length": length})


def test_requests_refuse_redirects_bad_status_and_oversized_objects(monkeypatch):
    seen = {}

    def build_opener(*handlers):
        seen["handlers"] = handlers

        def open_url(request, timeout):
            seen["url"], seen["timeout"] = request.full_url, timeout
            return seen["response"]

        return type("Opener", (), {"open": staticmethod(open_url)})

    monkeypatch.setattr(ood.urllib.request, "build_opener", build_opener)
    path = "validation/0000000000000001.jpg"
    seen["response"] = StubResponse()
    response, declared = ood._open(ood.IMAGE_HOST, path, 10)
    assert (response.read(), declared) == (b"data", 4)
    assert seen["url"] == f"https://{ood.IMAGE_HOST}/{path}" and seen["timeout"] > 0
    # A redirect from an allowlisted host must never be followed to another host.
    assert ood._NoRedirect in seen["handlers"]
    assert ood._NoRedirect().redirect_request(
        None, None, 302, "Found", {}, "https://example.com/elsewhere",
    ) is None
    for refused in (StubResponse(status=206), StubResponse(length="abc"),
                    StubResponse(length="-5"), StubResponse(length="11")):
        seen["response"] = refused
        with pytest.raises(OODPreparationError, match="Refused HTTP"):
            ood._open(ood.IMAGE_HOST, path, 10)
        assert refused.closed
    # No declared length: the body itself is still capped.
    seen["response"] = StubResponse(length=None, body=b"x" * 15)
    with pytest.raises(OODPreparationError, match="exceeds 10 bytes"):
        ood._https_get(ood.IMAGE_HOST, path, 10)
    seen["response"] = StubResponse(length=None, body=b"x" * 10)
    assert ood._https_get(ood.IMAGE_HOST, path, 10) == b"x" * 10


def test_truncated_and_interrupted_downloads_are_recorded_not_stored(metadata, tmp_path):
    import http.client

    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    truncated, interrupted = (item["id"] for item in manifest["pools"]["benchmark"][:2])

    def download(_, identifier):
        if identifier == interrupted:
            raise http.client.IncompleteRead(b"partial")
        return cut_scan_data() if identifier == truncated else jpeg(int(identifier, 16))

    index = ood.fetch_pools(manifest, tmp_path / "pool", downloader=download)
    errors = {failure["id"]: failure["error"] for failure in index["failures"]}
    assert set(errors) == {truncated, interrupted}
    assert "Image failed verification" in errors[truncated] and errors[interrupted]
    stored = {path.stem for path in (tmp_path / "pool").rglob("*.jpg")}
    assert not stored & {truncated, interrupted}


@pytest.fixture
def prepared(metadata, tmp_path):
    manifest = ood.build_manifest(metadata, seed=7, per_class=3, banana_per_pool=2)
    pool = tmp_path / "pool"
    ood.fetch_pools(manifest, pool, downloader=lambda _, identifier: jpeg(int(identifier, 16)))
    dataset = tmp_path / "dataset"
    for split in ("train", "valid"):
        (dataset / split / "images").mkdir(parents=True)
        (dataset / split / "labels").mkdir()
    for number in range(20):
        (dataset / "train" / "images" / f"hand_{number}.jpg").write_bytes(jpeg(1000 + number))
        (dataset / "train" / "labels" / f"hand_{number}.txt").write_text("5 0.5 0.5 0.2 0.6\n")
    (dataset / "valid" / "images" / "held.jpg").write_bytes(jpeg(2000))
    (dataset / "valid" / "labels" / "held.txt").write_text("1 0.5 0.5 0.2 0.6\n")
    (dataset / "data.yaml").write_text("path: /old/location\ntrain: train/images\nnc: 12\n")
    return dataset, pool


def snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_merge_adds_background_images_to_a_copy_of_train_only(prepared, tmp_path):
    dataset, pool = prepared
    before_dataset, before_pool = snapshot(dataset), snapshot(pool)
    output = tmp_path / "with-negatives"
    report = ood.merge_negatives(dataset, pool, output, ratio=0.10)
    assert snapshot(dataset) == before_dataset and snapshot(pool) == before_pool
    assert report["train_images_before"] == 20 and report["negatives_added"] == 2
    added = sorted((output / "train" / "images").glob("oodneg__*.jpg"))
    assert len(added) == 2 and len(list((output / "train" / "images").iterdir())) == 22
    for image in added:
        # An empty label file marks the whole image as background.
        assert (output / "train" / "labels" / f"{image.stem}.txt").read_text() == ""
    assert snapshot(output / "valid") == snapshot(dataset / "valid")
    assert (output / "train" / "labels" / "hand_0.txt").read_text() == "5 0.5 0.5 0.2 0.6\n"
    yaml = (output / "data.yaml").read_text()
    assert json.dumps(output.resolve().as_posix()) in yaml and "/old/location" not in yaml
    # Only the training-negatives pool is used; held-out images stay held out.
    index = json.loads((pool / "index.json").read_text())
    held_out = {r["id"] for r in index["files"] if r["pool"] != "train_negatives"}
    assert not {item["id"] for item in report["added"]} & held_out
    assert json.loads((output / "ood_negatives.json").read_text()) == report


def test_merge_refuses_unsafe_targets_and_tampered_negatives(prepared, tmp_path):
    dataset, pool = prepared
    for target, ratio in [(dataset / "inside", 0.1), (pool / "inside", 0.1),
                          (tmp_path / "fresh", 0), (tmp_path / "fresh", 0.6)]:
        with pytest.raises(OODPreparationError):
            ood.merge_negatives(dataset, pool, target, ratio=ratio)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(OODPreparationError, match="already exists"):
        ood.merge_negatives(dataset, pool, existing, ratio=0.1)

    index = json.loads((pool / "index.json").read_text())
    first = min((r for r in index["files"] if r["pool"] == "train_negatives"),
                key=lambda record: record["id"])
    original = (pool / first["file"]).read_bytes()
    (pool / first["file"]).write_bytes(jpeg(4242))
    with pytest.raises(OODPreparationError, match="integrity"):
        ood.merge_negatives(dataset, pool, tmp_path / "tampered", ratio=0.1)
    (pool / first["file"]).write_bytes(original)
    # An index entry cannot smuggle a path into the copied file name.
    first["id"] = "../../escape"
    (pool / "index.json").write_text(json.dumps(index))
    with pytest.raises(OODPreparationError, match="Invalid image ID"):
        ood.merge_negatives(dataset, pool, tmp_path / "tampered", ratio=0.1)
    assert not (tmp_path / "tampered").exists() and not (tmp_path / "fresh").exists()


def test_merge_skips_negatives_excluded_after_they_were_fetched(prepared, tmp_path, monkeypatch):
    dataset, pool = prepared
    index = json.loads((pool / "index.json").read_text())
    fetched = sorted(r["id"] for r in index["files"] if r["pool"] == "train_negatives")
    monkeypatch.setattr(ood, "EXCLUDED_TRAIN_NEGATIVES", {fetched[0]: "shows a banana"})
    report = ood.merge_negatives(dataset, pool, tmp_path / "merged", ratio=0.10)
    assert [item["id"] for item in report["added"]] == fetched[1:3]


@pytest.mark.parametrize("linked", ["train/images", "train/labels", "data.yaml", "valid"])
def test_merge_refuses_a_dataset_with_links_so_writes_cannot_reach_the_source(
    prepared, tmp_path, linked,
):
    dataset, pool = prepared
    # The linked part lives in a shared store outside the dataset.
    store = tmp_path / "store" / Path(linked).name
    store.parent.mkdir()
    (dataset / linked).rename(store)
    try:
        (dataset / linked).symlink_to(store, target_is_directory=store.is_dir())
    except OSError:
        pytest.skip("This platform or account cannot create symbolic links")
    before = snapshot(tmp_path / "store")
    with pytest.raises(OODPreparationError, match="link"):
        ood.merge_negatives(dataset, pool, tmp_path / "merged", ratio=0.10)
    assert snapshot(tmp_path / "store") == before and not (tmp_path / "merged").exists()


@pytest.mark.parametrize(("yaml_text", "error"), [
    ("train: train/images\nnc: 12\n", None),                      # no path key: one is added
    ("path: ../elsewhere\ntrain: train/images\n", None),
    ("path: /src\ntrain: /src/train/images\n", "relative path"),  # would train on the source
    ("path: /src\ntrain: ../other/train/images\n", "relative path"),
    ("path: /src\nnc: 12\n", "relative path"),
    ("train: [a, b\n", "valid YAML"),
])
def test_merged_yaml_always_trains_on_the_copy(prepared, tmp_path, yaml_text, error):
    import yaml

    dataset, pool = prepared
    (dataset / "data.yaml").write_text(yaml_text)
    output = tmp_path / "merged"
    if error:
        with pytest.raises(OODPreparationError, match=error):
            ood.merge_negatives(dataset, pool, output, ratio=0.10)
        assert not output.exists()
        return
    ood.merge_negatives(dataset, pool, output, ratio=0.10)
    merged = yaml.safe_load((output / "data.yaml").read_text())
    assert merged["path"] == output.resolve().as_posix() and merged["train"] == "train/images"
    assert (Path(merged["path"]) / merged["train"]).samefile(output / "train" / "images")
    assert (dataset / "data.yaml").read_text() == yaml_text


class Body(io.BytesIO):
    """Stands in for an HTTP response; counts how much was read at once."""
    largest_read = 0

    def readline(self, size=-1):
        line = super().readline(size)
        Body.largest_read = max(Body.largest_read, len(line))
        return line


def serve(monkeypatch, body: bytes, declared):
    monkeypatch.setattr(ood, "_open", lambda host, path, limit: (Body(body), declared))


def test_short_downloads_are_rejected_and_never_cached(monkeypatch, tmp_path):
    csv_text = b"ImageID,LabelName\n" + b"0000000000000001,/m/09qck\n" * 3
    # The connection closed early: fewer bytes than the server declared.
    serve(monkeypatch, csv_text[:-10], len(csv_text))
    with pytest.raises(OODPreparationError, match="Incomplete download"):
        ood._https_get(ood.METADATA_HOST, "openimages/x.csv", 10_000)
    with pytest.raises(OODPreparationError, match="Incomplete download"):
        ood._https_filter_lines(ood.METADATA_HOST, "openimages/x.csv", b"/m/09qck", 10_000)
    with pytest.raises(OODPreparationError, match="Incomplete download"):
        ood.download_metadata(tmp_path / "cache")
    assert list((tmp_path / "cache").iterdir()) == []
    # Metadata without a declared length cannot be checked, so it is refused.
    serve(monkeypatch, csv_text, None)
    with pytest.raises(OODPreparationError, match="Content-Length"):
        ood._https_get(ood.METADATA_HOST, "openimages/x.csv", 10_000, require_length=True)
    with pytest.raises(OODPreparationError, match="Content-Length"):
        ood._https_filter_lines(ood.METADATA_HOST, "openimages/x.csv", b"/m/09qck", 10_000)
    # A complete body passes, and only the header and matching lines are kept.
    mixed = b"ImageID,LabelName\n0000000000000001,/m/other\n0000000000000002,/m/09qck\n"
    serve(monkeypatch, mixed, len(mixed))
    assert ood._https_get(ood.METADATA_HOST, "openimages/x.csv", 10_000) == mixed
    assert ood._https_filter_lines(
        ood.METADATA_HOST, "openimages/x.csv", b"/m/09qck", 10_000,
    ) == b"ImageID,LabelName\n0000000000000002,/m/09qck\n"


def test_stream_filter_fails_fast_on_a_body_without_line_breaks(monkeypatch):
    huge = b"x" * (ood.MAX_LINE_BYTES * 40)
    serve(monkeypatch, huge, len(huge))
    Body.largest_read = 0
    with pytest.raises(OODPreparationError, match="size limits"):
        ood._https_filter_lines(ood.METADATA_HOST, "openimages/x.csv", b"x", len(huge))
    # The oversized line was never buffered whole.
    assert Body.largest_read <= ood.MAX_LINE_BYTES + 1
    monkeypatch.setattr(ood, "MAX_KEPT_BYTES", 30)
    many = b"header\n" + b"match-line\n" * 10
    serve(monkeypatch, many, len(many))
    with pytest.raises(OODPreparationError, match="Too many matching lines"):
        ood._https_filter_lines(ood.METADATA_HOST, "openimages/x.csv", b"match", len(many))


def test_command_line_reports_errors_without_writing(prepared, tmp_path, capsys):
    dataset, pool = prepared
    with pytest.raises(SystemExit) as stopped:
        ood.main(["merge-negatives", "--dataset", str(dataset), "--ood", str(tmp_path / "none"),
                  "--output", str(tmp_path / "out")])
    assert stopped.value.code == 2
    assert "No source files were modified" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    assert ood.main(["merge-negatives", "--dataset", str(dataset), "--ood", str(pool),
                     "--output", str(tmp_path / "out"), "--ratio", "0.1"]) == 0
    assert json.loads(capsys.readouterr().out)["negatives_added"] == 2
