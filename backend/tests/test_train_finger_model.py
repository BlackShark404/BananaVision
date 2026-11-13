"""Training preflight, arguments and run record with a fake YOLO; nothing is trained."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.time import MANILA
from scripts import train_finger_model as training
from scripts.prepare_yolo_dataset import EXPECTED_NAMES
from scripts.train_finger_model import SplitCounts, TrainingError

BACKEND = Path(__file__).resolve().parents[1]
# 00:30 on 2 October in Manila; still 1 October in UTC.
INSTANT = datetime(2026, 10, 1, 16, 30, tzinfo=UTC)
BOX = "0 0.5 0.5 0.2 0.4"


def add_image(root, split, stem, rows):
    (root / split / "images" / f"{stem}.jpg").write_bytes(b"synthetic image " + stem.encode())
    (root / split / "labels" / f"{stem}.txt").write_text(
        "".join(f"{row}\n" for row in rows), encoding="utf-8"
    )


def make_dataset(tmp_path, *, names=None, val="valid/images", negatives=0, manifest=True):
    """A prepared layout: data.yaml, manifest.json and three tiny splits."""
    root = tmp_path / "prepared"
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir()
    add_image(root, "train", "a_top", [BOX, "5 0.4 0.4 0.1 0.3"])
    add_image(root, "train", "b_left", [BOX])
    add_image(root, "valid", "c_top", ["11 0.5 0.5 0.3 0.3"])
    add_image(root, "test", "d_top", [BOX])
    for index in range(negatives):
        # merge-negatives: an empty label file marks a background image.
        add_image(root, "train", f"oodneg__{index:04d}", [])
    names = EXPECTED_NAMES if names is None else names
    (root / "data.yaml").write_text(
        f"path: {json.dumps(root.as_posix())}\ntrain: train/images\nval: {val}\n"
        f"test: test/images\nnc: {len(names)}\nnames: {json.dumps(names)}\n",
        encoding="utf-8",
    )
    if manifest:
        (root / "manifest.json").write_text(
            json.dumps({"format_version": 1, "seed": 42, "class_names": EXPECTED_NAMES}),
            encoding="utf-8",
        )
    weights = tmp_path / "start.pt"
    weights.write_bytes(b"starting weights fixture")
    return root, weights


def resume_ckpt(data, *, epoch=4, optimizer=True, hsv_h=0.0):
    """The parts of an Ultralytics last.pt dict the script reads (a stripped one: epoch -1)."""
    return {
        "epoch": epoch,
        "optimizer": {"state": {}} if optimizer else None,
        "train_args": {"data": str(data), "hsv_h": hsv_h, "imgsz": 640, "resume": False},
    }


def fake_yolo(*, names=None, imgsz=640, ckpt=None, drift=None):
    """A YOLO stand-in that records construction and train() and writes best/last.pt.

    Like Ultralytics, a resume keeps the checkpoint's stored arguments and uses the
    given data only when the stored dataset is gone. drift overrides what the trainer
    reports, to stand in for Ultralytics doing something other than what was asked.
    """
    calls = SimpleNamespace(loaded=[], trained=[])

    class FakeYOLO:
        def __init__(self, path):
            calls.loaded.append(path)
            self.names = dict(enumerate(EXPECTED_NAMES if names is None else names))
            self.overrides = {"imgsz": imgsz}
            self.ckpt = ckpt

        def train(self, **kwargs):
            calls.trained.append(kwargs)
            if kwargs.get("resume"):
                save_dir = Path(calls.loaded[0]).parent.parent
                effective = {**self.ckpt["train_args"], "resume": calls.loaded[0]}
                if not Path(effective["data"]).exists():
                    effective["data"] = kwargs["data"]
            else:
                save_dir = Path(kwargs["project"]) / kwargs["name"]
                effective = {**kwargs, "resume": False}
            effective.update(drift or {})
            weights = save_dir / "weights"
            weights.mkdir(parents=True, exist_ok=True)
            (weights / "best.pt").write_bytes(b"trained best checkpoint")
            (weights / "last.pt").write_bytes(b"trained last checkpoint")
            self.trainer = SimpleNamespace(
                save_dir=save_dir, best=weights / "best.pt", last=weights / "last.pt",
                metrics={"metrics/mAP50(B)": 0.91}, args=SimpleNamespace(**effective),
            )

    return FakeYOLO, calls


def interrupted_run(tmp_path, name="last.pt"):
    run = tmp_path / "runs" / "trial"
    (run / "weights").mkdir(parents=True)
    last = run / "weights" / name
    last.write_bytes(b"interrupted last checkpoint")
    return run, last


@pytest.fixture
def manila_clock(monkeypatch):
    monkeypatch.setattr(training, "now_manila", lambda: INSTANT.astimezone(MANILA))


# ── Preflight ──


def test_preflight_counts_images_boxes_and_train_negatives(tmp_path):
    root, weights = make_dataset(tmp_path, negatives=2)
    report = training.run_preflight(root, weights)
    assert report.splits["train"] == SplitCounts(images=4, labeled=2, background=2, boxes=3)
    assert report.splits["valid"] == SplitCounts(images=1, labeled=1, background=0, boxes=1)
    assert report.negatives == 2
    assert report.weights_sha256 == hashlib.sha256(b"starting weights fixture").hexdigest()
    assert report.manifest["seed"] == 42
    assert report.warnings == []
    summary = report.as_dict()
    assert summary["train_negatives"] == 2
    assert summary["splits"]["test"]["images"] == 1


def test_preflight_compares_negatives_with_the_merge_record(tmp_path):
    root, weights = make_dataset(tmp_path, negatives=1)
    (root / "ood_negatives.json").write_text(json.dumps({"negatives_added": 3}), "utf-8")
    report = training.run_preflight(root, weights)
    assert any("3 negatives" in warning for warning in report.warnings)


@pytest.mark.parametrize(
    ("remove", "message"),
    [
        ("data.yaml", "No data.yaml"),
        ("manifest.json", "No manifest.json"),
        ("valid/labels", "Missing valid/images or valid/labels"),
        ("test/images", "Missing test/images or test/labels"),
    ],
)
def test_preflight_refuses_missing_files(tmp_path, remove, message):
    root, weights = make_dataset(tmp_path)
    target = root / remove
    if target.is_dir():
        for child in target.iterdir():
            child.unlink()
        target.rmdir()
    else:
        target.unlink()
    with pytest.raises(TrainingError, match=message):
        training.run_preflight(root, weights)


def test_unprepared_dataset_needs_explicit_permission(tmp_path):
    root, weights = make_dataset(tmp_path, manifest=False)
    with pytest.raises(TrainingError, match="--allow-unprepared"):
        training.run_preflight(root, weights)
    assert training.run_preflight(root, weights, allow_unprepared=True).manifest is None


def test_preflight_refuses_missing_starting_weights(tmp_path):
    root, _ = make_dataset(tmp_path)
    with pytest.raises(TrainingError, match="Starting weights not found"):
        training.run_preflight(root, tmp_path / "missing.pt")
    with pytest.raises(TrainingError, match="--weights"):
        training.run_preflight(root, None)


@pytest.mark.parametrize(
    "names",
    [
        [EXPECTED_NAMES[1], EXPECTED_NAMES[0], *EXPECTED_NAMES[2:]],  # same set, other order
        EXPECTED_NAMES[:11],
        [name.title() for name in EXPECTED_NAMES],
    ],
)
def test_preflight_refuses_class_names_out_of_expected_order(tmp_path, names):
    root, weights = make_dataset(tmp_path, names=names)
    with pytest.raises(TrainingError, match="EXPECTED_NAMES"):
        training.run_preflight(root, weights)


def test_names_may_be_an_index_mapping_but_nc_must_be_twelve():
    assert training.check_names({"names": dict(enumerate(EXPECTED_NAMES))}) == EXPECTED_NAMES
    with pytest.raises(TrainingError, match="indexed"):
        training.check_names({"names": {index + 1: n for index, n in enumerate(EXPECTED_NAMES)}})
    with pytest.raises(TrainingError, match="nc must be 12"):
        training.check_names({"names": EXPECTED_NAMES, "nc": 13})


@pytest.mark.parametrize(
    ("val", "message"),
    [
        ("test/images", "test split"),
        ("../prepared/test/images", "test split"),
        ("train/images", "val: must be valid/images"),
    ],
)
def test_preflight_refuses_validation_outside_valid(tmp_path, val, message):
    root, weights = make_dataset(tmp_path, val=val)
    with pytest.raises(TrainingError, match=message):
        training.run_preflight(root, weights)


def test_preflight_refuses_a_yaml_that_points_at_another_dataset(tmp_path):
    root, weights = make_dataset(tmp_path)
    yaml = root / "data.yaml"
    other = (tmp_path / "original").as_posix()
    yaml.write_text(
        yaml.read_text("utf-8").replace(json.dumps(root.as_posix()), json.dumps(other)), "utf-8"
    )
    with pytest.raises(TrainingError, match="relocate"):
        training.run_preflight(root, weights)
    yaml.write_text(yaml.read_text("utf-8").replace(json.dumps(other), "prepared"), "utf-8")
    with pytest.raises(TrainingError, match="absolute"):
        training.run_preflight(root, weights)


def test_preflight_refuses_empty_or_unlabeled_splits(tmp_path):
    root, weights = make_dataset(tmp_path)
    for path in (root / "valid" / "images").iterdir():
        path.unlink()
    with pytest.raises(TrainingError, match="valid/images has no images"):
        training.run_preflight(root, weights)
    # A split of background images alone has nothing to validate against.
    add_image(root, "valid", "empty_top", [])
    with pytest.raises(TrainingError, match="valid has no labeled images"):
        training.run_preflight(root, weights)


def test_preflight_refuses_images_without_labels_and_bad_rows(tmp_path):
    root, weights = make_dataset(tmp_path)
    (root / "train" / "images" / "lonely_top.jpg").write_bytes(b"no label")
    with pytest.raises(TrainingError, match="without a label file"):
        training.run_preflight(root, weights)
    (root / "train" / "images" / "lonely_top.jpg").unlink()
    add_image(root, "train", "bad_top", ["12 0.5 0.5 0.2 0.2"])
    with pytest.raises(TrainingError, match="Invalid label row"):
        training.run_preflight(root, weights)


@pytest.mark.parametrize(
    "row",
    [
        "0 0.5 0.5 1.5 0.4",       # width over 1
        "0 abc def ghi jkl",       # not numbers
        "1 -0.5 0.5 0.2 0.4",      # negative centre
        "0 nan 0.5 0.2 0.4",       # not finite
        "0 0.5 0.5 0 0.4",         # zero width
        "x 0.5 0.5 0.2 0.4",       # class not an integer
        "0 0.5 0.5 0.2",           # four fields
        "0 0.5 0.5 0.2 0.4 0.1",   # six fields
    ],
)
def test_preflight_refuses_rows_ultralytics_would_drop_as_corrupt(tmp_path, row):
    root, weights = make_dataset(tmp_path)
    add_image(root, "train", "bad_top", [BOX, row])
    with pytest.raises(TrainingError, match=r"Invalid label row .*bad_top\.txt:2"):
        training.run_preflight(root, weights)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("stray.tif", "never writes"),
        ("stray.HEIC", "never writes"),
        ("sub/nested.jpg", "subfolder"),
    ],
)
def test_preflight_refuses_images_ultralytics_finds_but_preflight_would_not(
    tmp_path, path, message
):
    root, weights = make_dataset(tmp_path)
    # Files Ultralytics does not read as images are ignored, as it ignores them.
    (root / "train" / "images" / "notes.txt").write_text("not an image", encoding="utf-8")
    assert training.run_preflight(root, weights).splits["train"].images == 2
    image = root / "train" / "images" / path
    image.parent.mkdir(exist_ok=True)
    image.write_bytes(b"synthetic image")
    with pytest.raises(TrainingError, match=message):
        training.run_preflight(root, weights)


def test_preflight_refuses_weights_with_resume_and_resume_from_another_file(tmp_path):
    root, weights = make_dataset(tmp_path)
    _, last = interrupted_run(tmp_path)
    with pytest.raises(TrainingError, match="not both"):
        training.run_preflight(root, weights, resume=last)
    best = last.with_name("best.pt")
    best.write_bytes(b"mid-run best checkpoint")
    with pytest.raises(TrainingError, match="last.pt of an interrupted run, not best.pt"):
        training.run_preflight(root, None, resume=best)


# ── Training arguments ──


def test_train_kwargs_default_to_cpu_without_hue_augmentation(tmp_path):
    kwargs = training.build_train_kwargs(
        tmp_path / "data.yaml", project=tmp_path / "runs", name="run"
    )
    assert kwargs == {
        "data": str(tmp_path / "data.yaml"), "epochs": 30, "imgsz": 640, "batch": 8,
        "workers": 2, "patience": 10, "device": "cpu", "seed": 0, "deterministic": True,
        "hsv_h": 0.0, "cache": False, "plots": False, "project": str(tmp_path / "runs"),
        "name": "run", "exist_ok": False, "fraction": 1.0,
    }


def test_train_kwargs_pass_freeze_and_time_only_when_given(tmp_path):
    kwargs = training.build_train_kwargs(
        tmp_path / "data.yaml", project=tmp_path, name="run", freeze=10, time=2.5,
        fraction=0.25,
    )
    assert (kwargs["freeze"], kwargs["time"], kwargs["fraction"]) == (10, 2.5, 0.25)


def test_resume_kwargs_keep_the_checkpoint_settings(tmp_path):
    kwargs = training.build_train_kwargs(
        tmp_path / "data.yaml", project=tmp_path, name="run", imgsz=800, epochs=99,
        freeze=5, resume=True,
    )
    assert kwargs == {
        "resume": True, "data": str(tmp_path / "data.yaml"), "device": "cpu",
        "workers": 2, "cache": False, "plots": False,
    }
    assert training.build_train_kwargs(
        tmp_path / "data.yaml", project=tmp_path, name="run", resume=True, time=1.0
    )["time"] == 1.0


@pytest.mark.parametrize(
    "extra", [["--imgsz", "650"], ["--fraction", "0"], ["--time", "0"], ["--epochs", "0"]]
)
def test_cli_refuses_unusable_arguments(tmp_path, extra):
    root, weights = make_dataset(tmp_path)
    yolo, calls = fake_yolo()
    with pytest.raises(SystemExit) as exit_info:
        training.main(["--data", str(root), "--weights", str(weights), *extra], yolo_cls=yolo)
    assert exit_info.value.code == 2
    assert calls.loaded == []


def test_cli_refuses_weights_together_with_resume(tmp_path, capsys):
    root, weights = make_dataset(tmp_path)
    _, last = interrupted_run(tmp_path)
    yolo, calls = fake_yolo(ckpt=resume_ckpt(root / "data.yaml"))
    with pytest.raises(SystemExit) as exit_info:
        training.main(
            ["--data", str(root), "--weights", str(weights), "--resume", str(last)],
            yolo_cls=yolo,
        )
    assert exit_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
    assert calls.loaded == []


# ── Dry run ──


def test_dry_run_prints_preflight_and_kwargs_without_training(
    tmp_path, capsys, manila_clock
):
    root, weights = make_dataset(tmp_path, negatives=1)
    yolo, calls = fake_yolo()
    code = training.main(
        ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "runs"),
         "--freeze", "10", "--dry-run"],
        yolo_cls=yolo,
    )
    assert code == 0
    assert calls.loaded == [] and calls.trained == []
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["preflight"]["train_negatives"] == 1
    kwargs = report["train_kwargs"]
    # Default run name: the Manila date and time.
    assert kwargs["name"] == "finger-20261002-003000"
    assert kwargs["project"] == str((tmp_path / "runs").resolve())
    assert (kwargs["hsv_h"], kwargs["device"], kwargs["freeze"]) == (0.0, "cpu", 10)
    assert not (tmp_path / "runs").exists()


def test_dry_run_does_not_import_ultralytics_or_torch(tmp_path):
    root, weights = make_dataset(tmp_path)
    code = (
        "import sys\n"
        "from scripts import train_finger_model as training\n"
        f"training.main(['--data', {str(root)!r}, '--weights', {str(weights)!r}, '--dry-run'])\n"
        "print('LOADED', [m for m in ('ultralytics', 'torch') if m in sys.modules])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "LOADED []"


# ── Training with a fake YOLO ──


def test_training_prints_best_sha_size_and_next_command_and_writes_a_record(
    tmp_path, capsys, manila_clock
):
    root, weights = make_dataset(tmp_path, negatives=2)
    yolo, calls = fake_yolo(imgsz=800)
    argv = ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "runs"),
            "--name", "trial", "--epochs", "5", "--imgsz", "800", "--time", "1.5"]
    assert training.main(argv, yolo_cls=yolo) == 0

    best = (tmp_path / "runs" / "trial" / "weights" / "best.pt").resolve()
    digest = hashlib.sha256(b"trained best checkpoint").hexdigest()
    assert calls.loaded == [str(weights.resolve()), str(best)]
    [kwargs] = calls.trained
    assert kwargs == training.build_train_kwargs(
        root.resolve() / "data.yaml", project=(tmp_path / "runs").resolve(), name="trial",
        epochs=5, imgsz=800, time=1.5,
    )
    out = capsys.readouterr().out
    assert f"best.pt:      {best}" in out
    assert f"SHA-256:      {digest}" in out
    assert "image size:   800" in out
    report = (tmp_path / "runs" / "trial" / "finger-count-valid.json").resolve()
    command = (
        f"python scripts/evaluate_finger_count.py visible --weights {best} "
        f"--split {root.resolve() / 'valid'} --configs baseline head=one_to_one "
        f"--output {report}"
    )
    assert command in out
    assert "TOP_CALIBRATED_CHECKPOINTS" in out and "only after that evaluation" in out

    record = json.loads(
        (tmp_path / "runs" / "trial" / training.RECORD_NAME).read_text(encoding="utf-8")
    )
    assert record["created_at"] == "2026-10-02T00:30:00+08:00"
    assert record["best_sha256"] == digest
    assert record["best"] == str(best)
    assert record["image_size"] == 800
    assert record["next_command"] == command
    assert record["registered"] is False
    assert record["command"] == ["python", "scripts/train_finger_model.py", *argv]
    assert record["args"]["epochs"] == 5 and record["args"]["data"] == str(root)
    assert record["train_kwargs"]["hsv_h"] == 0.0
    assert record["trainer_args"]["hsv_h"] == 0.0
    assert record["trainer_args"]["data"] == str(root.resolve() / "data.yaml")
    assert record["preflight"]["warnings"] == []
    assert record["preflight"]["train_negatives"] == 2
    assert record["preflight"]["weights_sha256"] == hashlib.sha256(
        b"starting weights fixture"
    ).hexdigest()
    assert record["metrics"] == {"metrics/mAP50(B)": 0.91}
    assert {"python", "ultralytics", "torch", "ultralytics_pinned"} <= set(record["versions"])
    assert "error" in record["checkpoint_head"]  # the fake best.pt is not a torch file


def test_starting_weights_with_classes_in_another_order_are_refused(tmp_path):
    root, weights = make_dataset(tmp_path)
    swapped = [EXPECTED_NAMES[1], EXPECTED_NAMES[0], *EXPECTED_NAMES[2:]]
    yolo, calls = fake_yolo(names=swapped)
    with pytest.raises(SystemExit) as exit_info:
        training.main(
            ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "r")],
            yolo_cls=yolo,
        )
    assert exit_info.value.code == 2
    assert calls.trained == []


def test_other_class_count_trains_as_transfer_with_a_warning(tmp_path, capsys):
    root, weights = make_dataset(tmp_path)
    yolo, calls = fake_yolo(names=[f"coco_{index}" for index in range(80)])
    training.main(
        ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "r"),
         "--name", "coco"],
        yolo_cls=yolo,
    )
    assert len(calls.trained) == 1
    assert "transfer learning" in capsys.readouterr().err
    record = json.loads((tmp_path / "r" / "coco" / training.RECORD_NAME).read_text("utf-8"))
    assert any("80 classes" in warning for warning in record["preflight"]["warnings"])


def test_starting_weights_with_another_image_size_warn(tmp_path, capsys):
    root, weights = make_dataset(tmp_path)
    yolo, calls = fake_yolo(imgsz=800)
    training.main(
        ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "r"),
         "--name", "size"],
        yolo_cls=yolo,
    )
    assert calls.trained[0]["imgsz"] == 640
    assert "store image size 800; this run trains at and stores 640" in capsys.readouterr().err
    record = json.loads((tmp_path / "r" / "size" / training.RECORD_NAME).read_text("utf-8"))
    assert any("--imgsz 800" in warning for warning in record["preflight"]["warnings"])


def test_training_that_ran_otherwise_than_checked_is_not_recorded(tmp_path, capsys):
    root, weights = make_dataset(tmp_path)
    yolo, calls = fake_yolo(drift={"hsv_h": 0.015})
    with pytest.raises(SystemExit) as exit_info:
        training.main(
            ["--data", str(root), "--weights", str(weights), "--project", str(tmp_path / "r"),
             "--name", "drift"],
            yolo_cls=yolo,
        )
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "hue augmentation (hsv_h=0.015)" in captured.err
    assert "do not evaluate or register it" in captured.err
    assert "Register this checkpoint" not in captured.out
    assert not (tmp_path / "r" / "drift" / training.RECORD_NAME).exists()


def test_resume_loads_last_pt_and_keeps_an_earlier_record(tmp_path, manila_clock):
    root, _ = make_dataset(tmp_path)
    run, last = interrupted_run(tmp_path)
    (run / training.RECORD_NAME).write_text("{}\n", encoding="utf-8")
    yolo, calls = fake_yolo(ckpt=resume_ckpt((root / "data.yaml").resolve()))
    assert training.main(["--data", str(root), "--resume", str(last)], yolo_cls=yolo) == 0
    assert calls.loaded[0] == str(last.resolve())
    assert calls.trained[0]["resume"] is True and "epochs" not in calls.trained[0]
    assert (run / training.RECORD_NAME).read_text(encoding="utf-8") == "{}\n"
    record = json.loads(
        (run / "finger_training_record-20261002-003000.json").read_text(encoding="utf-8")
    )
    assert record["preflight"]["resume_sha256"] == hashlib.sha256(
        b"interrupted last checkpoint"
    ).hexdigest()
    assert record["preflight"]["weights"] is None
    assert record["preflight"]["warnings"] == []
    assert record["trainer_args"]["resume"] == str(last.resolve())


@pytest.mark.parametrize(
    ("ckpt", "message"),
    [
        # A finished or early-stopped run: Ultralytics strips last.pt to epoch -1.
        ({"epoch": -1, "optimizer": None}, "no epoch/optimizer state"),
        ({"epoch": 3, "optimizer": None}, "no epoch/optimizer state"),
        ({"epoch": -1, "optimizer": True}, "no epoch/optimizer state"),
        (None, "not an Ultralytics training checkpoint"),
        ({"hsv_h": 0.015}, "hue augmentation"),
    ],
)
def test_resume_refuses_a_checkpoint_ultralytics_would_not_resume_as_checked(
    tmp_path, capsys, ckpt, message
):
    root, _ = make_dataset(tmp_path)
    run, last = interrupted_run(tmp_path)
    if ckpt is not None:
        ckpt = resume_ckpt((root / "data.yaml").resolve(), **ckpt)
    yolo, calls = fake_yolo(ckpt=ckpt)
    with pytest.raises(SystemExit) as exit_info:
        training.main(["--data", str(root), "--resume", str(last)], yolo_cls=yolo)
    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err
    assert calls.loaded == [str(last.resolve())]
    assert calls.trained == []
    assert not any(run.glob("finger_training_record*.json"))


def test_resume_refuses_a_checkpoint_that_trains_on_another_dataset(tmp_path, capsys):
    root, _ = make_dataset(tmp_path)
    other = tmp_path / "original" / "data.yaml"
    other.parent.mkdir()
    other.write_text("names: []\n", encoding="utf-8")
    _, last = interrupted_run(tmp_path)
    yolo, calls = fake_yolo(ckpt=resume_ckpt(other))
    with pytest.raises(SystemExit) as exit_info:
        training.main(["--data", str(root), "--resume", str(last)], yolo_cls=yolo)
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert f"trains on {other}" in err and f"--data {other.parent.resolve()}" in err
    assert calls.trained == []


def test_resume_uses_data_only_when_the_stored_dataset_is_gone(tmp_path, capsys, manila_clock):
    root, _ = make_dataset(tmp_path)
    run, last = interrupted_run(tmp_path)
    gone = tmp_path / "gone" / "data.yaml"
    yolo, calls = fake_yolo(ckpt=resume_ckpt(gone))
    assert training.main(["--data", str(root), "--resume", str(last)], yolo_cls=yolo) == 0
    assert len(calls.trained) == 1
    assert "no longer exists" in capsys.readouterr().err
    record = json.loads((run / training.RECORD_NAME).read_text(encoding="utf-8"))
    assert record["trainer_args"]["data"] == str(root.resolve() / "data.yaml")
    assert any(str(gone) in warning for warning in record["preflight"]["warnings"])


def test_resume_that_ultralytics_turns_into_a_new_run_is_not_recorded(tmp_path, capsys):
    root, _ = make_dataset(tmp_path)
    run, last = interrupted_run(tmp_path)
    yolo, calls = fake_yolo(
        ckpt=resume_ckpt((root / "data.yaml").resolve()), drift={"resume": False}
    )
    with pytest.raises(SystemExit) as exit_info:
        training.main(["--data", str(root), "--resume", str(last)], yolo_cls=yolo)
    assert exit_info.value.code == 2
    assert "a new run instead of resuming" in capsys.readouterr().err
    assert not any(run.glob("finger_training_record*.json"))


def test_next_command_quotes_paths_with_spaces(tmp_path):
    command = training.next_command(
        Path("/runs/my run/weights/best.pt"), Path("/data set"), Path("/runs/my run/r.json")
    )
    assert '--weights "/runs/my run/weights/best.pt"' in command
    assert '--split "/data set/valid"' in command
    assert command.endswith('--output "/runs/my run/r.json"')
