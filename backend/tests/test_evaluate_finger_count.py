"""Finger-count evaluation on hand-made numbers, tiny files and model fakes; no weights."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import Settings
from app.services import classification
from app.services.classification import ClassificationResult
from app.services.ood_gate import EvidenceBox
from scripts import evaluate_finger_count as evaluation
from scripts.evaluate_finger_count import ConfigError, EvaluationError

NAMES = [
    f"{cultivar}_{stage}"
    for cultivar in ("cardaba", "lakatan", "latundan")
    for stage in ("overripe", "ripe", "semi_ripe", "unripe")
]
LAKATAN, CARDABA, LATUNDAN = 5, 1, 9  # lakatan_ripe, cardaba_ripe, latundan_ripe


def base_settings(**values):
    return Settings(
        _env_file=None, yolo_inference_head="one_to_many_nms", yolo_hand_box_split=True,
        yolo_recovery_adjacent_ripeness=False, **values,
    )


# ── Fakes: a photo file holds "<model count>[ nobanana][ outlier]" ──────────


def fake_reader(path: Path):
    words = path.read_text(encoding="utf-8").split()
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[0, 0, 0] = int(words[0])
    image[0, 0, 1] = 0 if "nobanana" in words else 1
    image[0, 0, 2] = 1 if "outlier" in words else 0
    return image


class FakeClassifier:
    """Counts what the photo says; settings shift the count like the real rules would."""

    # An unregistered checkpoint: the calibrated passes cannot run unless a test says so.
    _checkpoint_sha256 = None
    _image_size = 640

    def __init__(self, settings):
        self.settings = settings
        head = settings.yolo_inference_head
        self.inference_head = "unknown" if head == "checkpoint" else head
        self.calls = []

    def predict(self, image, *, confidence_threshold, camera_label=None,
                banana_evidence=None, support_margin=0.25):
        self.calls.append((camera_label, confidence_threshold, banana_evidence))
        count = int(image[0, 0, 0])
        if banana_evidence is not None and not banana_evidence:
            # The OOD gate drops every box that no banana evidence covers.
            return ClassificationResult(ood_rejected_boxes=count)
        if not self.settings.yolo_hand_box_split:
            count = max(0, count - 1)
        if count and self.settings.yolo_recovery_adjacent_ripeness and camera_label == "Top":
            count += 1
        if not count:
            return ClassificationResult()
        return ClassificationResult(
            cultivar="Lakatan", ripeness="Ripe", confidence=90.0, finger_count=count,
            hand_box_splits=int(count >= 10 and self.settings.yolo_hand_box_split),
            ripeness_outlier_boxes=2 if image[0, 0, 2] else 0,
        )


def fake_factory(created):
    @contextmanager
    def factory(settings):
        classifier = FakeClassifier(settings)
        created.append(classifier)
        yield classifier
    return factory


class FakeDetector:
    def __init__(self):
        self.calls = 0

    def detect(self, image, *, accept_confidence=None, support_confidence=None):
        self.calls += 1
        banana = bool(image[0, 0, 1])
        boxes = [EvidenceBox(0, 0, 4, 4, 0.9)] if banana else []
        return SimpleNamespace(
            available=True, banana_detected=banana, best_confidence=0.9 if banana else 0.0,
            boxes=boxes,
        )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def label_rows(*classes):
    return "".join(f"{cls} 0.5 0.5 0.1 0.2\n" for cls in classes)


@pytest.fixture
def split(tmp_path):
    """valid/ with five labeled photos, one empty label and one unlabeled photo."""
    root = tmp_path / "prepared"
    write(root / "data.yaml", f"nc: 12\nnames: {json.dumps(NAMES)}\n")
    valid = root / "valid"
    photos = {
        # name: (model count, label rows)
        "A_00001_top_jpg.rf.aa.jpg": ("6", [LAKATAN] * 6),
        "A_00001_left_jpg.rf.bb.jpg": ("4 outlier", [LAKATAN] * 3),
        "B_00002_rear.jpg": ("10", [CARDABA] * 13),
        "C_00003.jpg": ("2", [LAKATAN, LATUNDAN]),
        "D_00004_right.jpg": ("1", []),
    }
    for name, (count, rows) in photos.items():
        write(valid / "images" / name, count)
        write(valid / "labels" / f"{Path(name).stem}.txt", label_rows(*rows))
    write(valid / "images" / "E_00005_top.jpg", "3")
    write(valid / "images" / "notes.txt", "not an image")
    return valid


@pytest.fixture
def weights(tmp_path):
    return write(tmp_path / "weights.pt", "fake checkpoint")


def visible_args(split, weights, output, *extra):
    return evaluation.build_parser().parse_args([
        "visible", "--weights", str(weights), "--split", str(split),
        "--output", str(output), *extra,
    ])


# ── Pure helpers ────────────────────────────────────────────────────────────


def test_count_metrics_on_hand_made_numbers():
    metrics = evaluation.count_metrics([(5, 5), (5, 4), (8, 10), (3, 3), (12, 9)])
    # Errors 0, -1, +2, 0, -3.
    assert metrics == {
        "n": 5, "mae": 1.2, "exact_rate": 0.4, "within_one_rate": 0.6, "bias": -0.4,
        "undercount": 2, "overcount": 1,
    }
    assert evaluation.count_metrics([]) == {
        "n": 0, "mae": None, "exact_rate": None, "within_one_rate": None, "bias": None,
        "undercount": 0, "overcount": 0,
    }


@pytest.mark.parametrize(("count", "bucket"), [
    (0, "0"), (1, "1-4"), (4, "1-4"), (5, "5-8"), (8, "5-8"), (9, "9-12"), (12, "9-12"),
    (13, "13+"), (40, "13+"),
])
def test_size_buckets(count, bucket):
    assert evaluation.size_bucket(count) == bucket


def test_breakdown_orders_preferred_groups_first():
    rows = [("unknown", 2, 2), ("Top", 4, 3), ("Rear", 6, 6), ("Top", 2, 2)]
    result = evaluation.breakdown(rows, ("Top", "Left", "Right", "Rear", "unknown"))
    assert list(result) == ["Top", "Rear", "unknown"]
    assert result["Top"]["n"] == 2 and result["Top"]["mae"] == 0.5


def test_views_come_from_prepared_names_and_scan_photo_stems():
    from scripts.evaluate_ood_gate import camera_view

    assert camera_view("B4_Latundan1_NoneChemical_02570_top_jpg.rf.995e.jpg") == "Top"
    assert camera_view("X_00001_back.jpg") == "Rear"
    assert camera_view("X_00001.jpg") is None
    assert [evaluation.view_from_stem(stem) for stem in ("top", "LEFT", "Right", "back")] == [
        "Top", "Left", "Right", "Rear",
    ]
    assert evaluation.view_from_stem("side") is None


def test_dominant_cultivar_and_label_parsing(tmp_path):
    names = dict(enumerate(NAMES))
    assert evaluation.dominant_cultivar([LAKATAN, LAKATAN, CARDABA], names) == "Lakatan"
    assert evaluation.dominant_cultivar([LAKATAN, CARDABA], names) == "Mixed"
    assert evaluation.dominant_cultivar([], names) == "None"
    good = write(tmp_path / "good.txt", label_rows(LAKATAN, CARDABA) + "\n")
    assert evaluation.read_label(good, names) == [LAKATAN, CARDABA]
    for text in ("12 0.5 0.5 0.1 0.1\n", "x 0.5 0.5 0.1 0.1\n", "1 0.5 0.5\n"):
        with pytest.raises(EvaluationError, match="Invalid label row"):
            evaluation.read_label(write(tmp_path / "bad.txt", text), names)


def test_config_parsing_maps_short_names_to_settings_fields():
    configs = evaluation.parse_configs([
        "baseline", "head=one_to_one", "hand_box_split=off+ripeness_outlier=OFF",
        "recovery_adjacent=on", "iou=0.6",
    ])
    assert [config.name for config in configs] == [
        "baseline", "head=one_to_one", "hand_box_split=off+ripeness_outlier=OFF",
        "recovery_adjacent=on", "iou=0.6",
    ]
    assert configs[0].overrides == {}
    assert configs[1].overrides == {"yolo_inference_head": "one_to_one"}
    assert configs[2].overrides == {
        "yolo_hand_box_split": False, "yolo_ripeness_outlier_filter": False,
    }
    assert configs[3].overrides == {"yolo_recovery_adjacent_ripeness": True}
    assert configs[4].overrides == {"yolo_iou_threshold": 0.6}
    assert evaluation.parse_configs(None)[0].name == "baseline"
    # Every short name points at a real Settings field.
    assert {field for field, _ in evaluation.OVERRIDES.values()} <= set(Settings.model_fields)


@pytest.mark.parametrize(("token", "message"), [
    ("hand_split=off", "unknown setting 'hand_split'; known settings: head, axis_dedup"),
    ("hand_box_split", "expected 'baseline' or NAME=VALUE"),
    ("hand_box_split=maybe", "hand_box_split: expected on or off"),
    ("head=nms", "head: expected one of one_to_many_nms, one_to_one, checkpoint"),
    ("iou=1.5", "iou: expected a number in"),
    ("axis_dedup=off+axis_dedup=on", "axis_dedup is given twice"),
])
def test_invalid_configs_give_a_clear_error(token, message):
    with pytest.raises(ConfigError, match=message.replace("(", r"\(")):
        evaluation.parse_config(token)


def test_repeated_configs_are_refused():
    with pytest.raises(ConfigError, match="listed more than once: baseline"):
        evaluation.parse_configs(["baseline", "head=one_to_one", "baseline"])


def test_config_settings_copy_overrides_without_touching_the_base(weights):
    base = base_settings()
    config = evaluation.parse_config("head=one_to_one+side_view_lip=off")
    settings = evaluation.config_settings(base, weights, config)
    assert settings.yolo_model_path == str(weights)
    assert settings.yolo_inference_head == "one_to_one"
    assert settings.yolo_side_view_lip_filter is False
    assert base.yolo_inference_head == "one_to_many_nms" and base.yolo_side_view_lip_filter
    snapshot = evaluation.settings_snapshot(settings)
    assert snapshot["yolo_inference_head"] == "one_to_one"
    assert "ood_support_margin" in snapshot and "top_camera_cultivar_anchor" in snapshot
    assert not any("secret" in name or "database" in name for name in snapshot)


def test_frozen_test_split_is_refused_for_tuning(tmp_path):
    test_split = tmp_path / "prepared" / "test"
    with pytest.raises(EvaluationError, match="frozen TEST split"):
        evaluation.guard_frozen_test(test_split, frozen_test=False, config_count=1)
    with pytest.raises(EvaluationError, match="exactly one config"):
        evaluation.guard_frozen_test(test_split, frozen_test=True, config_count=2)
    assert evaluation.guard_frozen_test(test_split, frozen_test=True, config_count=1) is True
    assert evaluation.guard_frozen_test(
        tmp_path / "TEST" / "images", frozen_test=True, config_count=1,
    ) is True
    for split in (tmp_path / "prepared" / "valid", tmp_path / "contest", tmp_path / "test_set"):
        assert evaluation.guard_frozen_test(split, frozen_test=False, config_count=3) is False


def test_paired_comparison_counts_and_seeded_bootstrap():
    truth = [5, 5, 8, 3, 12, 6]
    reference = [5, 4, 10, 3, 9, 6]   # absolute errors 0 1 2 0 3 0
    candidate = [5, 5, 9, 4, 12, 6]   # absolute errors 0 0 1 1 0 0
    result = evaluation.paired_comparison(truth, reference, candidate, resamples=500, seed=7)
    assert (result["improved"], result["worsened"], result["tied"]) == (3, 1, 2)
    assert result["mae_difference"] == pytest.approx(-0.6667, abs=1e-4)
    low, high = result["ci95"]
    assert low <= result["mae_difference"] <= high
    assert result["bootstrap_resamples"] == 500 and result["seed"] == 7
    # The same seed gives the same interval; another seed draws differently.
    again = evaluation.paired_comparison(truth, reference, candidate, resamples=500, seed=7)
    assert again == result
    rng = np.random.default_rng(1)
    many = rng.integers(0, 15, 60)
    noisy = (many + rng.integers(-3, 4, 60)).tolist()
    many = many.tolist()
    seeded = [
        evaluation.paired_comparison(many, many, noisy, resamples=400, seed=seed)["ci95"]
        for seed in (1, 1, 2)
    ]
    assert seeded[0] == seeded[1] and seeded[0] != seeded[2]
    same = evaluation.paired_comparison(truth, reference, reference, resamples=100, seed=0)
    assert same["ci95"] == [0.0, 0.0] and same["ci_excludes_zero"] is False
    assert same["tied"] == 6
    skipped = evaluation.paired_comparison(truth, reference, candidate, resamples=0, seed=0)
    assert skipped["ci95"] is None and skipped["mae_difference"] == result["mae_difference"]
    with pytest.raises(ValueError, match="same length"):
        evaluation.paired_comparison([1], [1, 2], [1], resamples=0, seed=0)


def test_rule_summary_counts_totals_and_images():
    results = [
        ClassificationResult(hand_box_splits=2),
        ClassificationResult(ripeness_outlier_boxes=1, ood_rejected_boxes=3),
        None,
        ClassificationResult(hand_box_splits=1),
    ]
    assert evaluation.rule_summary(results) == {
        "ood_rejected_boxes": {"total": 3, "images": 1},
        "ripeness_outlier_boxes": {"total": 1, "images": 1},
        "hand_box_splits": {"total": 3, "images": 2},
    }


# ── Visible mode ────────────────────────────────────────────────────────────


def test_visible_mode_end_to_end_with_fakes(split, weights, tmp_path):
    created = []
    args = visible_args(
        split, weights, tmp_path / "report.json",
        "--configs", "baseline", "hand_box_split=off", "head=one_to_one",
        "--bootstrap", "300", "--seed", "3",
    )
    report = evaluation.run_visible(
        args, reader=fake_reader, classifier_factory=fake_factory(created),
        detector_factory=lambda: pytest.fail("no detector without --gate"),
        base_settings=base_settings(),
    )
    assert report["mode"] == "visible" and report["images"] == 5
    assert report["skipped_unlabeled"] == 1 and report["frozen_test"] is False
    assert report["created_at"].endswith("+08:00")
    assert "not physical hand totals" in report["note"]
    assert report["weights_sha256"] == classification._checkpoint_digest(str(weights))
    assert set(report["versions"]) == {"python", "ultralytics", "torch", "numpy"}
    assert report["baseline"] == "baseline" and report["gate"]["enabled"] is False

    # One fresh classifier per config, each loaded with its own settings and weights.
    assert [c.settings.yolo_model_path for c in created] == [str(weights)] * 3
    assert [c.settings.yolo_hand_box_split for c in created] == [True, False, True]
    assert {call[1] for c in created for call in c.calls} == {0.5}
    # The view in the file name becomes the camera label; no view -> None.
    assert [call[0] for call in created[0].calls] == ["Left", "Top", "Rear", None, "Right"]

    baseline = report["configs"]["baseline"]
    # Truth 6 3 13 2 0 vs predicted 6 4 10 2 1: errors 0 +1 -3 0 +1.
    assert baseline["metrics"] == {
        "n": 5, "mae": 1.0, "exact_rate": 0.4, "within_one_rate": 0.8, "bias": -0.2,
        "undercount": 1, "overcount": 2,
    }
    assert list(baseline["by_view"]) == ["Top", "Left", "Right", "Rear", "unknown"]
    assert baseline["by_view"]["Rear"]["mae"] == 3.0
    assert set(baseline["by_cultivar"]) == {"Lakatan", "Cardaba", "Mixed", "None"}
    assert baseline["by_cultivar"]["Lakatan"]["n"] == 2
    assert list(baseline["by_size"]) == ["0", "1-4", "5-8", "13+"]
    assert baseline["by_size"]["13+"] == {
        "n": 1, "mae": 3.0, "exact_rate": 0.0, "within_one_rate": 0.0, "bias": -3.0,
        "undercount": 1, "overcount": 0,
    }
    assert baseline["comparison_to_baseline"] is None
    assert baseline["inference_head"] == "one_to_many_nms" and baseline["overrides"] == {}
    assert baseline["settings"]["yolo_model_path"] == str(weights)
    assert baseline["rules"]["hand_box_splits"] == {"total": 1, "images": 1}
    assert baseline["rules"]["ripeness_outlier_boxes"] == {"total": 2, "images": 1}
    assert baseline["gate_rejected_images"] is None
    assert baseline["calibrated_paths"]["checkpoint_registered"] is False
    assert all(not run["warnings"] for run in report["configs"].values())

    split_off = report["configs"]["hand_box_split=off"]
    # Predicted 5 3 9 1 0: absolute errors 1 0 4 1 0 against baseline 0 1 3 0 1.
    assert split_off["metrics"]["mae"] == 1.2
    comparison = split_off["comparison_to_baseline"]
    assert (comparison["improved"], comparison["worsened"], comparison["tied"]) == (2, 3, 0)
    assert comparison["mae_difference"] == 0.2
    assert comparison["seed"] == 3 and comparison["bootstrap_resamples"] == 300
    assert split_off["overrides"] == {"yolo_hand_box_split": False}
    assert split_off["rules"]["hand_box_splits"]["total"] == 0

    one_to_one = report["configs"]["head=one_to_one"]
    assert one_to_one["inference_head"] == "one_to_one"
    assert one_to_one["comparison_to_baseline"]["tied"] == 5
    assert one_to_one["comparison_to_baseline"]["ci95"] == [0.0, 0.0]

    assert report["per_image"][2] == {
        "image": "B_00002_rear.jpg", "view": "Rear", "cultivar": "Cardaba", "truth": 13,
        "predicted": {"baseline": 10, "hand_box_split=off": 9, "head=one_to_one": 10},
    }
    json.dumps(report)  # the whole report is JSON


def test_visible_mode_with_the_gate_scores_each_capture_as_one_scan(split, weights, tmp_path):
    # Top of capture A shows a banana; its Left view does not. Capture B shows none.
    write(split / "images" / "A_00001_left_jpg.rf.bb.jpg", "4 nobanana")
    write(split / "images" / "B_00002_rear.jpg", "10 nobanana")
    created, detector = [], FakeDetector()
    report = evaluation.run_visible(
        visible_args(split, weights, tmp_path / "report.json", "--gate",
                     "--configs", "baseline", "hand_box_split=off"),
        reader=fake_reader, classifier_factory=fake_factory(created),
        detector_factory=lambda: detector, base_settings=base_settings(),
    )
    assert len(created) == 2
    assert detector.calls == 5  # once per photo, not per config
    assert report["configs"]["hand_box_split=off"]["gate_rejected_images"] == 1
    assert report["gate"]["enabled"] is True
    assert report["gate"]["policy"]["support_margin"] == 0.25
    baseline = report["configs"]["baseline"]
    assert baseline["gate_rejected_images"] == 1
    predicted = [item["predicted"]["baseline"] for item in report["per_image"]]
    # Left keeps no box (no evidence in its own frame); rejected scan B counts zero.
    assert predicted == [0, 6, 0, 2, 1]
    assert baseline["rules"]["ood_rejected_boxes"] == {"total": 4, "images": 1}
    assert len(created[0].calls) == 4  # the rejected scan is never classified


def test_visible_mode_reads_names_without_data_yaml_and_uses_the_camera_label(
    split, weights, tmp_path,
):
    (split.parent / "data.yaml").unlink()
    created = []
    report = evaluation.run_visible(
        visible_args(split, weights, tmp_path / "report.json", "--camera-label", "Top"),
        reader=fake_reader, classifier_factory=fake_factory(created),
        base_settings=base_settings(),
    )
    assert report["per_image"][3]["view"] == "Top"  # C_00003.jpg has no view in its name
    assert report["per_image"][3]["cultivar"] == "Mixed"
    assert report["camera_label_fallback"] == "Top"


def test_visible_mode_reads_data_yaml_of_a_relative_split(split, weights, tmp_path, monkeypatch):
    # A data.yaml whose class order differs from the prepared names: id 1 is Latundan.
    write(split.parent / "data.yaml", f"nc: 12\nnames: {json.dumps(NAMES[::-1])}\n")
    monkeypatch.chdir(split)
    report = evaluation.run_visible(
        visible_args(".", weights, tmp_path / "report.json"),
        reader=fake_reader, classifier_factory=fake_factory([]),
        base_settings=base_settings(),
    )
    assert report["per_image"][2]["image"] == "B_00002_rear.jpg"
    assert report["per_image"][2]["cultivar"] == "Latundan"  # not the fallback's Cardaba
    assert set(report["configs"]["baseline"]["by_cultivar"]) == {
        "Lakatan", "Latundan", "Mixed", "None",
    }


def test_visible_mode_detects_at_the_configured_confidence(split, weights, tmp_path):
    created = []
    report = evaluation.run_visible(
        visible_args(split, weights, tmp_path / "r.json"),
        reader=fake_reader, classifier_factory=fake_factory(created),
        base_settings=base_settings(yolo_confidence_threshold=0.4),
    )
    assert report["detection_confidence"] == 0.4
    assert {call[1] for call in created[0].calls} == {0.4}


def test_reports_warn_when_a_rule_could_not_run(split, weights, tmp_path, monkeypatch):
    sha, size = next(iter(classification.TOP_CALIBRATED_CHECKPOINTS.items()))
    monkeypatch.setattr(FakeClassifier, "_checkpoint_sha256", sha)
    monkeypatch.setattr(FakeClassifier, "_image_size", size)
    configs = ("baseline", "recovery_within_hand=off", "top_rotation=off", "iou=0.6",
               "head=one_to_one+top_overlap=off")

    def run(*extra):
        return evaluation.run_visible(
            visible_args(split, weights, tmp_path / "r.json", "--configs", *configs,
                         "--bootstrap", "0", *extra),
            reader=fake_reader, classifier_factory=fake_factory([]),
            base_settings=base_settings(),
        )["configs"]

    calibrated = run()
    paths = calibrated["baseline"]["calibrated_paths"]
    assert paths["checkpoint_registered"] and paths["image_size_matches"]
    assert paths["recovery_active"] is True and paths["top_passes_active"] is True
    assert calibrated["baseline"]["warnings"] == []
    assert calibrated["recovery_within_hand=off"]["warnings"] == []
    assert calibrated["top_rotation=off"]["warnings"] == []
    # Any other IoU also turns the calibrated Top passes off.
    iou = calibrated["iou=0.6"]
    assert iou["calibrated_paths"]["top_passes_active"] is False
    assert iou["calibrated_paths"]["recovery_active"] is True
    assert iou["warnings"] == [
        "iou=0.6 also turns off the calibrated Top overlap refinement and rotated pass, "
        "which run only at IoU 0.45: the comparison mixes both changes"
    ]
    assert calibrated["head=one_to_one+top_overlap=off"]["warnings"] == [
        "top_overlap changes only the NMS IoU, which the NMS-free one_to_one head skips"
    ]

    # At another confidence the recovery and Top passes never run.
    other = run("--confidence", "0.6")
    assert other["baseline"]["calibrated_paths"]["recovery_active"] is False
    assert other["recovery_within_hand=off"]["warnings"] == [
        "recovery_within_hand has no effect: the occluded-finger recovery did not run "
        "(the detection confidence is not 0.50)"
    ]
    assert other["top_rotation=off"]["warnings"] == [
        "top_rotation has no effect: the calibrated Top passes did not run "
        "(the detection confidence is not 0.50)"
    ]
    assert other["iou=0.6"]["warnings"] == []
    lines = evaluation.summary_lines({"mode": "visible", "configs": other})
    assert (
        "warning: recovery_within_hand=off: recovery_within_hand has no effect: the "
        "occluded-finger recovery did not run (the detection confidence is not 0.50)"
    ) in lines


def test_visible_mode_refuses_a_test_split_before_loading_anything(tmp_path, weights):
    test_split = tmp_path / "prepared" / "test"
    args = visible_args(test_split, weights, tmp_path / "r.json", "--configs", "baseline",
                        "hand_box_split=off", "--frozen-test")
    with pytest.raises(EvaluationError, match="exactly one config"):
        evaluation.run_visible(
            args, reader=fake_reader,
            classifier_factory=lambda settings: pytest.fail("must not load a model"),
        )


def test_default_factory_swaps_and_restores_the_module_settings(monkeypatch, weights):
    seen = []

    class Recorder:
        is_loaded = True
        inference_head = "one_to_one"

        def load(self):
            seen.append(classification.settings.yolo_model_path)

    monkeypatch.setattr(classification, "BananaClassifier", Recorder)
    previous = classification.settings
    settings = evaluation.config_settings(
        base_settings(), weights, evaluation.parse_config("head=one_to_one"),
    )
    with evaluation.load_classifier(settings) as classifier:
        # predict() reads the module settings at call time: they stay swapped here.
        assert classification.settings is settings
        assert classifier.inference_head == "one_to_one"
    assert seen == [str(weights)] and classification.settings is previous

    Recorder.is_loaded = False
    with pytest.raises(EvaluationError, match="failed to load"), \
            evaluation.load_classifier(settings):
        pass
    assert classification.settings is previous


# ── Physical mode ───────────────────────────────────────────────────────────


@pytest.fixture
def scans(tmp_path):
    root = tmp_path / "scans"
    views = {
        "s1": {"top.jpg": "6", "Left.jpg": "5", "RIGHT.jpg": "6", "rear.png": "4"},
        "s2": {"Top.jpg": "8", "left.jpg": "8", "right.jpg": "8", "back.jpg": "8"},
        "s3": {"top.jpg": "0", "left.jpg": "0", "right.jpg": "0", "rear.jpg": "0"},
        "s4": {"top.jpg": "3", "left.jpg": "3 outlier", "right.jpg": "3", "rear.jpg": "3"},
        "extra": {"top.jpg": "3"},
    }
    for scan, files in views.items():
        for name, count in files.items():
            write(root / scan / name, count)
    write(root / "s1" / "notes.txt", "ignored")
    counts = write(
        tmp_path / "counts.csv", "scan_id,physical_count\ns1,7\ns2,8\n\ns3,5\ns4,3\n",
    )
    return root, counts


def physical_args(scans, weights, output, *extra):
    root, counts = scans
    return evaluation.build_parser().parse_args([
        "physical", "--weights", str(weights), "--scans", str(root), "--counts", str(counts),
        "--output", str(output), *extra,
    ])


def test_physical_mode_fuses_views_with_the_real_fusion_engine(scans, weights, tmp_path):
    created = []
    args = physical_args(scans, weights, tmp_path / "report.json",
                         "--configs", "baseline", "recovery_adjacent=on", "--bootstrap", "200")
    report = evaluation.run_physical(
        args, reader=fake_reader, classifier_factory=fake_factory(created),
        base_settings=base_settings(),
    )
    assert report["mode"] == "physical" and report["scans"] == 4
    assert report["uncounted_scan_folders"] == ["extra"]
    assert report["created_at"].endswith("+08:00") and "physical totals" in report["note"]
    # As scan_service: boxes kept at the lower of the two thresholds.
    assert report["detection_confidence"] == 0.5 and report["review_confidence"] == 0.85
    assert report["expected_cameras"] == 4

    baseline = report["configs"]["baseline"]
    s1, s2, s3, s4 = baseline["scans"]
    assert s1["views"] == {"Top": 6, "Left": 5, "Right": 6, "Rear": 4}
    # Fusion keeps the largest view count; differing counts need a person's review.
    # s1 has no outlier or OOD boxes, so only fusion flags it.
    assert (s1["fused_count"], s1["review_flagged"], s1["cultivar"]) == (6, True, "Lakatan")
    assert s1["rejected"] is None
    # Four agreeing views at 90% confidence, no dropped boxes: no review.
    assert s2["fused_count"] == 8 and s2["review_flagged"] is False
    assert s3["rejected"] == "no_target_cultivar" and s3["fused_count"] is None
    assert s3["views"] == {"Top": 0, "Left": 0, "Right": 0, "Rear": 0}
    # Views agree, but Left dropped ripeness outlier boxes: review as on the station.
    assert s4["fused_count"] == 3 and s4["review_flagged"] is True

    # Fused 6 8 3 against 7 8 3: errors -1 0 0.
    assert baseline["fused"] == {
        "n": 3, "mae": 0.3333, "exact_rate": 0.6667, "within_one_rate": 1.0,
        "bias": -0.3333, "undercount": 1, "overcount": 0,
    }
    assert baseline["fused_rejected_as_zero"]["mae"] == 1.5
    assert baseline["fused_rejected_as_zero"]["n"] == 4
    assert baseline["rejected"] == {
        "scans": 1, "rate": 0.25, "by_reason": {"no_target_cultivar": 1},
    }
    assert baseline["review_flagged"] == 2 and baseline["review_flag_rate"] == 0.6667
    assert list(baseline["fused_by_size"]) == ["1-4", "5-8"]
    assert baseline["rules"]["ripeness_outlier_boxes"] == {"total": 2, "images": 1}
    assert baseline["comparison_to_baseline"] is None
    assert baseline["warnings"] == []

    adjacent = report["configs"]["recovery_adjacent=on"]
    # Top gains one finger: s1 fused 7 (exact), s2 9 and s4 4 (over), s3 still rejected.
    assert [item["fused_count"] for item in adjacent["scans"]] == [7, 9, None, 4]
    comparison = adjacent["comparison_to_baseline"]
    assert comparison["basis"] == "fused_rejected_as_zero"
    assert (comparison["improved"], comparison["worsened"], comparison["tied"]) == (1, 2, 1)
    assert comparison["mae_difference"] == 0.25
    # An unregistered checkpoint never runs the recovery pass on the station.
    assert adjacent["calibrated_paths"]["recovery_active"] is False
    assert adjacent["warnings"] == [
        "recovery_adjacent has no effect: the occluded-finger recovery did not run "
        "(the checkpoint is not in TOP_CALIBRATED_CHECKPOINTS)"
    ]
    # Each view was classified with its own camera label.
    assert [call[0] for call in created[0].calls[:4]] == ["Top", "Left", "Right", "Rear"]
    json.dumps(report)


def test_physical_mode_with_the_gate_rejects_a_scan_without_banana(scans, weights, tmp_path):
    root, _ = scans
    for name in ("top.jpg", "left.jpg", "right.jpg", "rear.jpg"):
        write(root / "s3" / name, "2 nobanana")
    write(root / "s2" / "left.jpg", "8 nobanana")
    created, detector = [], FakeDetector()
    report = evaluation.run_physical(
        physical_args(scans, weights, tmp_path / "report.json", "--gate",
                      "--configs", "baseline", "hand_box_split=off"),
        reader=fake_reader, classifier_factory=fake_factory(created),
        detector_factory=lambda: detector, base_settings=base_settings(),
    )
    baseline = report["configs"]["baseline"]
    s1, s2, s3, s4 = baseline["scans"]
    assert s3["rejected"] == "no_banana" and s3["views"] == {}
    # Left of s2 has no evidence of its own: its boxes are dropped and review is required.
    assert s2["views"]["Left"] == 0 and s2["review_flagged"] is True
    assert baseline["rules"]["ood_rejected_boxes"] == {"total": 8, "images": 1}
    assert baseline["rejected"]["by_reason"] == {"no_banana": 1}
    assert report["configs"]["hand_box_split=off"]["rejected"]["by_reason"] == {"no_banana": 1}
    assert len(created) == 2
    assert detector.calls == 16  # once per photo of the 4 scans, not per config


def test_physical_mode_flags_missing_captures_against_the_expected_camera_count(
    tmp_path, weights,
):
    root = tmp_path / "pairs"
    write(root / "p1" / "top.jpg", "5")
    write(root / "p1" / "left.jpg", "5")
    counts = write(tmp_path / "pairs.csv", "scan_id,physical_count\np1,5\n")

    def scan(*extra):
        report = evaluation.run_physical(
            physical_args((root, counts), weights, tmp_path / "r.json", *extra),
            reader=fake_reader, classifier_factory=fake_factory([]),
            base_settings=base_settings(),
        )
        return report["configs"]["baseline"]["scans"][0]

    # Two agreeing views of four configured cameras: the station asks for review.
    four = scan()
    assert four["fused_count"] == 5 and four["review_flagged"] is True
    # With two cameras configured nothing is missing.
    assert scan("--expected-cameras", "2")["review_flagged"] is False


def test_physical_mode_detects_at_the_configured_confidence(scans, weights, tmp_path):
    created = []
    report = evaluation.run_physical(
        physical_args(scans, weights, tmp_path / "r.json"),
        reader=fake_reader, classifier_factory=fake_factory(created),
        base_settings=base_settings(yolo_confidence_threshold=0.4),
    )
    # As scan_service: min(review threshold, YOLO_CONFIDENCE_THRESHOLD).
    assert report["detection_confidence"] == 0.4
    assert {call[1] for call in created[0].calls} == {0.4}
    explicit = evaluation.run_physical(
        physical_args(scans, weights, tmp_path / "r.json", "--confidence", "0.9"),
        reader=fake_reader, classifier_factory=fake_factory([]),
        base_settings=base_settings(yolo_confidence_threshold=0.4),
    )
    assert explicit["detection_confidence"] == 0.85


@pytest.mark.parametrize(("text", "message"), [
    ("scan,count\ns1,3\n", "needs the columns scan_id,physical_count"),
    ("scan_id,physical_count\ns1,-1\n", "whole number"),
    ("scan_id,physical_count\ns1,three\n", "whole number"),
    ("scan_id,physical_count\ns1,3\ns1,4\n", "listed twice"),
    ("scan_id,physical_count\n../s1,3\n", "folder name"),
    ("scan_id,physical_count\n", "no counted scans"),
])
def test_counts_csv_is_validated(tmp_path, text, message):
    with pytest.raises(EvaluationError, match=message):
        evaluation.load_counts(write(tmp_path / "counts.csv", text))


def test_scan_folders_are_validated(tmp_path):
    root = tmp_path / "scans"
    write(root / "s1" / "top.jpg", "3")
    write(root / "s1" / "side.jpg", "3")
    with pytest.raises(EvaluationError, match="name each photo after its view"):
        evaluation.load_scans(root, {"s1": 3})
    (root / "s1" / "side.jpg").unlink()
    write(root / "s1" / "TOP.png", "3")
    with pytest.raises(EvaluationError, match="two photos of the Top view"):
        evaluation.load_scans(root, {"s1": 3})
    with pytest.raises(EvaluationError, match="No scan folder for 'missing'"):
        evaluation.load_scans(root, {"missing": 3})


# ── Command line and report file ────────────────────────────────────────────


def test_main_writes_the_json_report_and_refuses_to_overwrite(
    split, weights, tmp_path, capsys,
):
    output = tmp_path / "report.json"
    argv = ["visible", "--weights", str(weights), "--split", str(split), "--output",
            str(output), "--configs", "baseline", "ripeness_outlier=off", "--bootstrap", "50"]
    dependencies = {
        "reader": fake_reader, "classifier_factory": fake_factory([]),
        "base_settings": base_settings(),
    }
    assert evaluation.main(argv, **dependencies) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert set(report) >= {
        "mode", "created_at", "note", "weights", "weights_sha256", "versions",
        "detection_confidence", "gate", "baseline", "bootstrap", "split", "frozen_test",
        "images", "skipped_unlabeled", "configs", "per_image",
    }
    assert set(report["configs"]["ripeness_outlier=off"]) >= {
        "overrides", "inference_head", "settings", "metrics", "by_view", "by_cultivar",
        "by_size", "rules", "comparison_to_baseline",
    }
    printed = capsys.readouterr().out
    assert "ripeness_outlier=off" in printed and "Report written to" in printed

    with pytest.raises(SystemExit) as exit_info:
        evaluation.main(argv, **dependencies)
    assert exit_info.value.code == 2
    assert "output already exists" in capsys.readouterr().err


def test_main_refuses_a_missing_output_folder_before_loading(split, weights, tmp_path, capsys):
    created = []
    with pytest.raises(SystemExit) as exit_info:
        evaluation.main([
            "visible", "--weights", str(weights), "--split", str(split),
            "--output", str(tmp_path / "reports" / "r.json"),
        ], reader=fake_reader, classifier_factory=fake_factory(created),
            base_settings=base_settings())
    assert exit_info.value.code == 2
    assert "output folder not found" in capsys.readouterr().err
    assert created == []


def test_main_never_overwrites_a_report_written_during_the_run(
    split, weights, tmp_path, capsys,
):
    output = tmp_path / "report.json"
    created = []
    inner = fake_factory(created)

    @contextmanager
    def racing_factory(settings):
        # Another run finishes first and writes the same output file.
        write(output, "other run\n")
        with inner(settings) as classifier:
            yield classifier

    with pytest.raises(SystemExit) as exit_info:
        evaluation.main([
            "visible", "--weights", str(weights), "--split", str(split),
            "--output", str(output), "--bootstrap", "0",
        ], reader=fake_reader, classifier_factory=racing_factory,
            base_settings=base_settings())
    assert exit_info.value.code == 2
    assert output.read_text(encoding="utf-8") == "other run\n"
    captured = capsys.readouterr()
    assert f"Could not write {output}" in captured.err
    # The finished evaluation is printed instead of lost.
    printed = captured.out
    report = json.loads(printed[printed.index("{"):])
    assert report["mode"] == "visible" and report["images"] == 5


def test_main_reports_an_invalid_config_name_clearly(split, weights, tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        evaluation.main([
            "visible", "--weights", str(weights), "--split", str(split),
            "--output", str(tmp_path / "r.json"), "--configs", "baseline", "lip=off",
        ], reader=fake_reader, classifier_factory=fake_factory([]))
    assert exit_info.value.code == 2
    error = capsys.readouterr().err
    assert "Evaluation failed: config 'lip=off': unknown setting 'lip'" in error
    assert not (tmp_path / "r.json").exists()


def test_main_refuses_missing_weights(split, tmp_path, capsys):
    with pytest.raises(SystemExit):
        evaluation.main([
            "visible", "--weights", str(tmp_path / "none.pt"), "--split", str(split),
            "--output", str(tmp_path / "r.json"),
        ], reader=fake_reader, classifier_factory=fake_factory([]))
    assert "Cultivar weights not found" in capsys.readouterr().err
