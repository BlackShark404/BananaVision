"""Station backup to draft YOLO labels: synthetic SQLite stations and real archives only.

Every archive is made by the real backup_archive.create_archive from a disposable
in-memory SQLite station with generated JPEG captures; no live database, capture
folder, camera or network is touched.
"""

import asyncio
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import bcrypt
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import Base
from app.core.time import MANILA
from app.schemas.enums import CultivarEnum, RipenessEnum
from app.services import backup_archive
from scripts import export_station_training_set as export
from scripts.evaluate_finger_count import load_counts, load_scans
from scripts.prepare_yolo_dataset import EXPECTED_NAMES, _names, infer_capture, infer_prefix
from tests.test_backup_archive import AsyncDB  # also maps JSONB to JSON on SQLite

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_station_training_set.py"
# 00:30 on 2 October in Manila; still 1 October in UTC and in Los Angeles.
INSTANT = datetime(2026, 10, 1, 16, 30, tzinfo=UTC)
MANILA_STAMP = "20261002003000"
WIDTH, HEIGHT = 200, 100


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    """Any async engine use (the app's PostgreSQL engine) fails the test."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("the export must never open a database connection")

    monkeypatch.setattr(AsyncEngine, "connect", refuse)
    monkeypatch.setattr(AsyncEngine, "begin", refuse)


@pytest.fixture
def private_tmp(tmp_path, monkeypatch):
    """The process temp folder, to prove the validated staging copy is removed."""
    folder = tmp_path / "process-tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def capture(root, scan_id, index, colour):
    folder = root / str(scan_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"camera_{index}.jpg"
    Image.new("RGB", (WIDTH, HEIGHT), colour).save(path, "JPEG")
    return path


def box(x, y, w, h, cls, conf):
    return {"x": x, "y": y, "w": w, "h": h, "cls": cls, "conf": conf}


@pytest.fixture
def station(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    root = tmp_path / "captures"
    ids = {name: uuid4() for name in ("normal", "flagged", "corrected", "demo")}
    with Session(engine) as db:
        db.add(m.UserRole(id=1, name="Admin"))
        db.flush()
        user = m.UserAccount(username="admin", full_name="Admin", role_id=1,
                             password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt(4)).decode())
        db.add(user)
        db.flush()
        operator = m.OperatorProfile(account_id=user.id, pin_hash="pin-hash")
        db.add_all([m.AdminProfile(account_id=user.id), operator])
        db.flush()

        def scan(name, *, cultivar, ripeness, count, original=None, **values):
            scan_id = ids[name]
            db.add(m.Scan(id=scan_id, operator_id=operator.id, date_time=INSTANT, **values))
            db.flush()
            ai_cultivar, ai_ripeness, ai_count = original or (cultivar, ripeness, count)
            db.add_all([
                m.ScanClassification(scan_id=scan_id, cultivar=cultivar, ripeness=ripeness,
                                     confidence=Decimal("90.00"), finger_count=count),
                m.ScanOriginalAiResult(scan_id=scan_id, cultivar=ai_cultivar,
                                       ripeness=ai_ripeness, finger_count=ai_count),
            ])
            return scan_id

        def view(scan_id, index, label, boxes, *, count=None, colour="yellow"):
            camera = f"CAM-00{index + 1}"
            db.add_all([
                m.ScanImage(scan_id=scan_id, camera_id=camera,
                            file_path=str(capture(root, scan_id, index, colour)),
                            width=WIDTH, height=HEIGHT),
                m.ScanDetection(scan_id=scan_id, camera_id=camera, camera_label=label,
                                finger_count=len(boxes) if count is None else count,
                                bounding_boxes=boxes),
            ])

        normal = scan("normal", cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.RIPE,
                      count=3)
        view(normal, 0, "Top", [
            box(20, 10, 40, 20, "lakatan_ripe", 0.9),
            box(180, -10, 40, 30, "Lakatan_Semi Ripe", 0.4),  # leaves the image
            box(300, 10, 10, 10, "lakatan_ripe", 0.8),  # entirely outside
            box(50, 50, 10, 10, "crown", 0.95),  # not a finger class
        ], count=2)
        view(normal, 1, "Left", [], colour="green")
        view(normal, 2, "Scanner 3", [box(1, 1, 5, 5, "lakatan_ripe", 0.9)])

        flagged = scan("flagged", cultivar=CultivarEnum.CARDABA, ripeness=RipenessEnum.UNRIPE,
                       count=1, flagged=True)
        view(flagged, 0, "Top", [box(0, 0, 100, 50, "cardaba_unripe", 0.7)])

        corrected = scan(
            "corrected", cultivar=CultivarEnum.LATUNDAN, ripeness=RipenessEnum.RIPE, count=7,
            original=(CultivarEnum.LAKATAN, RipenessEnum.RIPE, 5), is_overridden=True,
        )
        view(corrected, 0, "top", [box(100, 50, 50, 25, "lakatan_ripe", 0.88)], count=5)
        view(corrected, 3, "Back", [box(0, 0, 200, 100, "latundan_ripe", 0.6)])

        scan("demo", cultivar=CultivarEnum.LATUNDAN, ripeness=RipenessEnum.SEMI_RIPE, count=4)
        db.commit()
        archive = tmp_path / "station-backup.zip"
        asyncio.run(backup_archive.create_archive(AsyncDB(db), root, archive))
    engine.dispose()
    return archive, root, ids


def run(archive, output, *options):
    return export.main(["--backup", str(archive), "--output", str(output), *options])


def stem(scan_id, view):
    return f"{scan_id}_{MANILA_STAMP}_{view}"


def label(output, scan_id, view):
    return (output / "train" / "labels" / f"{stem(scan_id, view)}.txt").read_text(
        encoding="utf-8")


def summary_of(capsys):
    return json.loads(capsys.readouterr().out)


def counts(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["scan_id"]: row for row in csv.DictReader(handle)}


def test_labels_are_the_stored_boxes_normalized_and_clamped(station, tmp_path, capsys,
                                                            private_tmp):
    archive, root, ids = station
    output = tmp_path / "draft"
    assert run(archive, output) == 0
    summary = summary_of(capsys)
    normal, corrected = ids["normal"], ids["corrected"]

    # lakatan_ripe is index 5; the second box is clamped to x 180-200 and y 0-20.
    assert EXPECTED_NAMES.index("lakatan_ripe") == 5
    assert label(output, normal, "top") == (
        "5 0.200000 0.200000 0.200000 0.200000\n"
        "6 0.950000 0.100000 0.100000 0.200000\n"
    )
    assert label(output, normal, "left") == ""  # no stored box: empty draft label
    # The person corrected Lakatan to Latundan: the box follows (latundan_ripe = 9).
    assert label(output, corrected, "top") == "9 0.625000 0.625000 0.250000 0.250000\n"
    assert label(output, corrected, "rear") == "9 0.500000 0.500000 1.000000 1.000000\n"

    images = sorted(path.name for path in (output / "train" / "images").iterdir())
    assert images == sorted([f"{stem(normal, 'left')}.jpg", f"{stem(normal, 'top')}.jpg",
                             f"{stem(corrected, 'rear')}.jpg", f"{stem(corrected, 'top')}.jpg"])
    copied = output / "train" / "images" / f"{stem(normal, 'top')}.jpg"
    assert copied.read_bytes() == (root / str(normal) / "camera_0.jpg").read_bytes()
    # prepare_yolo_dataset.py groups every view of one scan under the scan id.
    for name in images:
        scan_id = name.split("_", 1)[0]
        assert infer_prefix(name) == scan_id
        assert infer_capture(name) == f"{scan_id}_{MANILA_STAMP}"
        assert infer_prefix(f"{Path(name).stem}_jpg.rf.0123abcd.jpg") == scan_id  # Roboflow
    assert _names(output) == EXPECTED_NAMES
    yaml = (output / "data.yaml").read_text(encoding="utf-8")
    assert "nc: 12\n" in yaml and "train: train/images\n" in yaml and "path:" not in yaml
    for split in ("valid", "test"):
        assert not any((output / split / "images").iterdir())
        assert not any((output / split / "labels").iterdir())

    assert summary["scans"] == {"in_backup": 4, "exported": 2, "skipped": {
        export.SCAN_FLAGGED: 1, export.SCAN_NO_IMAGES: 1}}
    assert summary["images"] == {"exported": 4, "without_boxes": 1,
                                 "skipped": {export.IMAGE_VIEW: 1}}
    assert summary["boxes"]["written"] == 4
    assert summary["boxes"]["clamped"] == 1
    assert summary["boxes"]["relabelled_by_correction"] == 1
    assert summary["boxes"]["skipped"] == {export.BOX_CLASS: 1, export.BOX_GEOMETRY: 1}
    assert summary["boxes"]["per_class"]["latundan_ripe"] == 2
    assert summary["labels"].startswith("DRAFT")
    assert any("prepare_yolo_dataset.py" in command for command in summary["next_commands"])
    assert any("train_finger_model.py" in command for command in summary["next_commands"])
    readme = (output / "README.txt").read_text(encoding="utf-8")
    assert "DRAFT" in readme and "crown" in readme and "Roboflow" in readme
    # The validated copy (it holds password hashes) and the partial folder are gone.
    assert not any(private_tmp.iterdir())
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "captures", "draft", "process-tmp", "station-backup.zip"]


def test_min_confidence_drops_weaker_stored_boxes(station, tmp_path, capsys):
    archive, _, ids = station
    output = tmp_path / "draft"
    assert run(archive, output, "--min-confidence", "0.5") == 0
    summary = summary_of(capsys)
    assert label(output, ids["normal"], "top") == "5 0.200000 0.200000 0.200000 0.200000\n"
    assert summary["boxes"]["skipped"][export.BOX_CONFIDENCE] == 1
    assert summary["options"]["min_confidence"] == 0.5


def test_flagged_scans_are_skipped_unless_requested(station, tmp_path, capsys):
    archive, _, ids = station
    flagged = ids["flagged"]
    assert run(archive, tmp_path / "default") == 0
    assert str(flagged) not in json.dumps(summary_of(capsys))
    assert not list((tmp_path / "default").rglob(f"{flagged}*"))

    output = tmp_path / "with-flagged"
    assert run(archive, output, "--include-flagged") == 0
    summary = summary_of(capsys)
    assert export.SCAN_FLAGGED not in summary["scans"]["skipped"]
    assert summary["scans"]["exported"] == 3
    assert label(output, flagged, "top") == "3 0.250000 0.250000 0.500000 0.500000\n"
    assert counts(output / "counts.csv")[str(flagged)]["flagged"] == "true"


def test_counts_csv_keeps_ai_and_corrected_counts_and_physical_input(station, tmp_path, capsys):
    archive, _, ids = station
    output = tmp_path / "draft"
    assert run(archive, output) == 0
    summary = summary_of(capsys)
    rows = counts(output / "counts.csv")
    assert set(rows) == {str(ids["normal"]), str(ids["corrected"])}
    corrected, normal = rows[str(ids["corrected"])], rows[str(ids["normal"])]
    assert corrected["cultivar"] == "Latundan"
    assert (corrected["ai_finger_count"], corrected["stored_finger_count"]) == ("5", "7")
    assert corrected["is_overridden"] == "true"
    assert (corrected["top_count"], corrected["rear_count"], corrected["left_count"]) == (
        "5", "1", "")
    assert corrected["scanned_at"] == "2026-10-02T00:30:00+08:00"
    assert (normal["ai_finger_count"], normal["stored_finger_count"]) == ("3", "3")
    assert (normal["is_overridden"], normal["top_count"], normal["left_count"]) == (
        "false", "2", "0")
    assert (normal["images"], normal["label_boxes"]) == ("2", "2")

    # Only the person-corrected scan is physical-mode input, as evaluate_finger_count reads it.
    physical = output / "physical"
    assert summary["physical"] == {"scans": 1, "folder": str(physical)}
    loaded = load_counts(physical / "counts.csv")
    assert loaded == {str(ids["corrected"]): 7}
    scans, uncounted = load_scans(physical, loaded)
    assert uncounted == []
    assert [view for view, _ in scans[0].views] == ["Top", "Rear"]
    command = next(c for c in summary["next_commands"] if "evaluate_finger_count.py" in c)
    assert f"--counts {physical / 'counts.csv'}" in command


def test_corrected_only_exports_person_corrected_scans(station, tmp_path, capsys):
    archive, _, ids = station
    output = tmp_path / "draft"
    assert run(archive, output, "--corrected-only") == 0
    summary = summary_of(capsys)
    assert list(counts(output / "counts.csv")) == [str(ids["corrected"])]
    assert summary["scans"]["skipped"][export.SCAN_NOT_CORRECTED] == 1


def test_high_min_confidence_keeps_images_with_empty_labels(station, tmp_path, capsys):
    archive, _, _ = station
    output = tmp_path / "draft"
    assert run(archive, output, "--min-confidence", "0.95") == 0
    summary = summary_of(capsys)
    # Corrected boxes are all weaker than 0.95; the scan still exports with empty labels.
    assert summary["physical"]["scans"] == 1
    assert summary["images"]["without_boxes"] == 4
    assert any("empty label file" in warning for warning in summary["warnings"])


def test_non_empty_output_is_refused_and_left_alone(station, tmp_path, capsys):
    archive, _, _ = station
    output = tmp_path / "draft"
    output.mkdir()
    (output / "keep.txt").write_text("user file", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        run(archive, output)
    assert stopped.value.code == 2
    assert "Output is not empty" in capsys.readouterr().err
    assert [path.name for path in output.iterdir()] == ["keep.txt"]

    empty = tmp_path / "empty"
    empty.mkdir()
    assert run(archive, empty) == 0  # an existing empty directory is fine


def tamper(path):
    """Change one stored box without updating the manifest hash."""
    with zipfile.ZipFile(path) as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["tables/scan_detection.jsonl"] = members["tables/scan_detection.jsonl"].replace(
        b'"cls":"lakatan_ripe"', b'"cls":"cardaba_ripe"', 1)
    with zipfile.ZipFile(path, "w") as target:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 2, 0, 30, 0))
            target.writestr(info, data)


@pytest.mark.parametrize("damage", ["tamper", "truncate", "missing"])
def test_archive_that_fails_validation_exits_2(station, tmp_path, capsys, private_tmp, damage):
    archive, _, _ = station
    if damage == "tamper":
        tamper(archive)
    elif damage == "truncate":
        archive.write_bytes(archive.read_bytes()[:200])
    else:
        archive = tmp_path / "absent.zip"
    output = tmp_path / "draft"
    with pytest.raises(SystemExit) as stopped:
        run(archive, output)
    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert error.startswith("Export failed: ")
    assert ("failed validation" in error) or damage == "missing"
    assert "$2b$" not in error and "pin-hash" not in error
    assert not output.exists()
    assert not any(private_tmp.iterdir())
    assert not [path for path in tmp_path.iterdir() if ".partial-" in path.name]


@pytest.fixture
def los_angeles():
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_timestamps_and_file_name_dates_are_asia_manila(station, tmp_path, capsys,
                                                       monkeypatch, los_angeles):
    archive, _, ids = station
    monkeypatch.setattr(export, "now_manila", lambda: INSTANT.astimezone(MANILA))
    output = tmp_path / "draft"
    assert run(archive, output) == 0
    summary = summary_of(capsys)
    assert summary["exported_at"] == "2026-10-02T00:30:00+08:00"
    assert summary["backup"]["created_at"].endswith("+08:00")
    readme = (output / "README.txt").read_text(encoding="utf-8")
    assert "Exported: 2026-10-02T00:30:00+08:00 (Asia/Manila)" in readme
    assert f"Backup created: {summary['backup']['created_at']} (Asia/Manila)" in readme
    assert f"Backup SHA-256: {hashlib.sha256(archive.read_bytes()).hexdigest()}" in readme
    # The scan was captured on 1 October UTC, 2 October in Manila.
    assert (output / "train" / "labels" / f"{stem(ids['normal'], 'top')}.txt").is_file()


def test_unit_helpers():
    assert export.view_name(" Back ") == "rear"
    assert export.view_name("Scanner 1") is None
    assert export.split_class("Latundan_Semi-Ripe") == ("latundan", "semi_ripe")
    assert export.split_class("lakatan") == ("lakatan", None)
    assert export.split_class("lakatan_crown") is None
    assert export.box_class("ripe", scan_cultivar="cardaba", scan_ripeness="unripe",
                            corrected_cultivar=False, corrected_ripeness=False) == (1, False)
    assert export.box_class("lakatan_ripe", scan_cultivar="lakatan", scan_ripeness="unripe",
                            corrected_cultivar=False, corrected_ripeness=True) == (7, True)
    assert export.yolo_box({"x": 0, "y": 0, "w": True, "h": 1}, 10, 10) is None
    assert export.yolo_box({"x": 0, "y": 0, "w": float("nan"), "h": 1}, 10, 10) is None
    assert export.yolo_box({"x": -5, "y": 2, "w": 10, "h": 4}, 10, 10) == (
        (0.25, 0.4, 0.5, 0.4), True)


def test_command_line_runs_offline_from_any_folder(station, tmp_path):
    """A fresh process with an unreachable database URL and no .env still exports."""
    archive, _, _ = station
    output = tmp_path / "draft"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("DATABASE", "BANANAVISION"))}
    env["DATABASE_URL"] = "postgresql+asyncpg://nobody:nothing@127.0.0.1:9/absent"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--backup", str(archive), "--output", str(output)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["images"]["exported"] == 4
    assert "$2b$" not in result.stdout + result.stderr
