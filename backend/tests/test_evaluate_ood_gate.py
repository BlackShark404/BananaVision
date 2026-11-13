"""Evaluation metrics on hand-built frames and model fakes; no weights or dataset."""

import json
from types import SimpleNamespace

import pytest

from app.services.ood_gate import EvidenceBox, GatePolicy
from scripts import evaluate_ood_gate as evaluation
from scripts.evaluate_ood_gate import EvaluationError, Frame

POLICY = GatePolicy()
EVIDENCE = [EvidenceBox(0, 0, 100, 100, 0.9)]
INSIDE = EvidenceBox(40, 40, 20, 20, 1.0)
OUTSIDE = EvidenceBox(400, 400, 20, 20, 1.0)


def frame(group, score, evidence, objects, name="x"):
    return Frame(f"{group}-{score}-{len(objects)}", group, name, score, evidence, objects)


def test_separation_reports_auroc_and_false_positive_rate_at_95_percent_recall():
    perfect = evaluation.separation([0.9, 0.8, 0.7], [0.2, 0.1])
    assert perfect == {
        "auroc": 1.0, "aupr": 1.0, "threshold_at_95_tpr": 0.7, "fpr_at_95_tpr": 0.0,
    }
    # 20 positives: 95 % recall keeps 19, so the threshold is the 19th highest score.
    positives = [1 - index * 0.01 for index in range(19)] + [0.05]
    mixed = evaluation.separation(positives, [0.9, 0.5, 0.1])
    assert mixed["threshold_at_95_tpr"] == pytest.approx(0.82)
    assert mixed["fpr_at_95_tpr"] == pytest.approx(0.3333, abs=1e-4)
    assert evaluation.separation([], [0.1])["auroc"] is None


def test_classification_metrics_count_images_without_a_cultivar_as_missed():
    pairs = [("Lakatan", "Lakatan"), ("Lakatan", None), ("Latundan", "Lakatan"),
             ("Latundan", "Latundan"), ("Cardaba", "Cardaba")]
    metrics = evaluation.classification_metrics(pairs)
    # One correct Lakatan, one Latundan mislabeled as Lakatan, one Lakatan rejected.
    assert metrics["Lakatan"] == {"support": 2, "precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert metrics["Latundan"] == {"support": 2, "precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["Cardaba"]["f1"] == 1.0 and metrics["images_without_cultivar"] == 1
    empty = evaluation.classification_metrics([("Lakatan", None)])
    assert empty["Lakatan"]["precision"] is None and empty["Lakatan"]["f1"] == 0.0
    assert empty["Cardaba"]["f1"] is None


def test_gate_report_separates_frame_gate_from_box_support():
    frames = [
        frame("banana", 0.9, EVIDENCE, [INSIDE, INSIDE]),
        frame("banana", 0.1, [EvidenceBox(0, 0, 100, 100, 0.1)], [INSIDE, OUTSIDE]),
        # A lookalike the gate accepts, with a supported box: still leaks.
        frame("near", 0.6, EVIDENCE, [INSIDE]),
        # Accepted frame whose object lies outside the evidence: rejected after.
        frame("near", 0.5, EVIDENCE, [OUTSIDE]),
        frame("near", 0.0, [], [OUTSIDE]),
        frame("near", 0.0, [], [OUTSIDE]),
        frame("far", 0.0, [], [OUTSIDE, OUTSIDE]),
        # Accepted by the gate, no annotated box: cannot be shown rejected.
        frame("far", 0.7, EVIDENCE, []),
    ]
    report = evaluation.gate_report(frames, POLICY, seed=1, scans=50)
    assert report["images"] == {"banana": 2, "near": 4, "far": 2}
    near = report["frame_gate"]["near"]
    assert near["false_accept_rate_before"] == 0.5 and near["rejection_rate_before"] == 0.5
    assert near["false_cultivar_frame_rate_after"] == 0.25
    assert near["rejection_rate_after"] == 0.75
    far = report["frame_gate"]["far"]
    assert far["false_accept_rate_before"] == 0.5 and far["rejection_rate_after"] == 0.5
    assert report["frame_gate"]["banana"]["accept_rate"] == 0.5
    boxes = report["box_support_filter"]
    assert boxes["banana"] == {"annotated_boxes": 4, "retained_boxes": 3, "retained_rate": 0.75}
    assert boxes["near"]["surviving_rate"] == 0.25 and boxes["far"]["surviving_boxes"] == 0
    mixed = report["simulated_scans"]["banana_plus_three_ood_views"]
    assert mixed["scans"] == 50
    assert mixed["ood_boxes_admitted_after"] < mixed["ood_boxes_admitted_before"]
    assert mixed["accepted_scans_with_ood_box_after"] <= mixed["accepted_scans_with_ood_box_before"]
    assert evaluation.gate_report(frames, POLICY, seed=1, scans=50) == report


def test_pool_loading_refuses_missing_or_escaping_files(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"pools": {"benchmark": [
        {"id": "a", "boxes": []}, {"id": "b", "boxes": []},
    ]}}))
    pool = tmp_path / "pool"
    pool.mkdir()
    with pytest.raises(EvaluationError, match="index.json"):
        evaluation.load_pool(pool, manifest, "benchmark")
    (tmp_path / "outside.jpg").write_bytes(b"x")
    (pool / "ok.jpg").write_bytes(b"x")
    records = [{"pool": "benchmark", "id": "a", "group": "far", "class": "Car",
                "file": "ok.jpg"}]
    (pool / "index.json").write_text(json.dumps({"files": records}))
    [loaded] = evaluation.load_pool(pool, manifest, "benchmark")
    assert loaded["path"] == (pool / "ok.jpg").resolve() and loaded["boxes"] == []
    records.append({"pool": "benchmark", "id": "b", "group": "far", "class": "Car",
                    "file": "../outside.jpg"})
    (pool / "index.json").write_text(json.dumps({"files": records}))
    with pytest.raises(EvaluationError, match="unsafe"):
        evaluation.load_pool(pool, manifest, "benchmark")
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"pools": {"calibration": []}}))
    with pytest.raises(EvaluationError, match="no fetched images"):
        evaluation.load_pool(pool, empty, "calibration")


def fake_detector(by_image):
    """by_image maps an image tag to (banana_detected, evidence boxes)."""
    def detect(image, **_kwargs):
        banana, boxes = by_image[image]
        return SimpleNamespace(
            available=True, banana_detected=banana, boxes=boxes,
            best_confidence=max((box.confidence for box in boxes), default=0.0),
        )
    return SimpleNamespace(detect=detect)


def fake_classifier(calls):
    def predict(image, **kwargs):
        calls.append((image, kwargs))
        # Three fingers without the gate; the gate keeps as many as it has evidence boxes.
        fingers = len(kwargs["banana_evidence"]) if "banana_evidence" in kwargs else 3
        return SimpleNamespace(
            cultivar="Lakatan" if fingers else None, finger_count=fingers,
        )
    return SimpleNamespace(predict=predict)


def test_scan_is_scored_like_the_station_with_each_view_using_its_own_evidence():
    weak = [EvidenceBox(0, 0, 60, 200, 0.21)]
    calls = []
    scored = evaluation.score_scan(
        [("top", "Top"), ("left", "Left"), ("rear", "Rear")],
        # Only Top reaches the acceptance confidence; Left has weak evidence, Rear none.
        fake_detector({"top": (True, EVIDENCE), "left": (False, weak), "rear": (False, [])}),
        fake_classifier(calls), POLICY, 0.5,
    )
    assert [view["has_banana"] for view in scored] == [True, False, False]
    assert all(view["scan_accepted"] for view in scored)
    # The earlier rule kept every box of every view once one view showed a banana.
    assert [view["legacy_gate"] for view in scored] == [("Lakatan", 3)] * 3
    assert [view["no_gate"] for view in scored] == [("Lakatan", 3)] * 3
    # The gate still classifies a view below acceptance, with that view's own evidence.
    assert [view["ood_gate"] for view in scored] == [("Lakatan", 1), ("Lakatan", 1), (None, 0)]
    # The station passes the view; without it the Top paths and filters are skipped.
    assert [(image, kwargs["camera_label"]) for image, kwargs in calls] == [
        ("top", "Top"), ("top", "Top"), ("left", "Left"), ("left", "Left"),
        ("rear", "Rear"), ("rear", "Rear"),
    ]
    assert calls[3][1]["banana_evidence"] == weak


def test_scan_without_enough_banana_views_is_rejected_for_every_view():
    calls = []
    detector = fake_detector({"a": (True, EVIDENCE), "b": (False, [])})
    rejected = evaluation.score_scan(
        [("b", "Top")], detector, fake_classifier(calls), POLICY, 0.5,
    )
    assert rejected == [{
        "has_banana": False, "scan_accepted": False, "no_gate": ("Lakatan", 3),
        "legacy_gate": (None, 0), "ood_gate": (None, 0),
    }]
    # Two views required, one present: the earlier rule passes, the gate does not.
    strict = evaluation.score_scan(
        [("a", "Top"), ("b", "Left")], detector, fake_classifier(calls),
        GatePolicy(min_banana_views=2), 0.5,
    )
    assert [view["legacy_gate"] for view in strict] == [("Lakatan", 3)] * 2
    assert [view["ood_gate"] for view in strict] == [(None, 0)] * 2
    broken = SimpleNamespace(detect=lambda _image, **kwargs: SimpleNamespace(available=False))
    with pytest.raises(EvaluationError):
        evaluation.score_scan([("a", "Top")], broken, fake_classifier(calls), POLICY, 0.5)


def test_top_path_status_requires_every_calibration_condition():
    module = SimpleNamespace(
        TOP_CALIBRATED_CHECKPOINTS={"abc": 640}, TOP_OVERLAP_CONFIDENCE=0.50,
        TOP_OVERLAP_BASE_IOU=0.45,
        settings=SimpleNamespace(yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
                                 yolo_top_rotation_fallback=True),
    )
    classifier = SimpleNamespace(_checkpoint_sha256="abc", _image_size=640)
    assert evaluation.top_paths(classifier, module, 0.50)["active"] is True
    lower = evaluation.top_paths(classifier, module, 0.45)
    assert lower["checkpoint_registered"] is True and lower["confidence_is_calibrated"] is False
    assert lower["active"] is False
    resized = evaluation.top_paths(SimpleNamespace(_checkpoint_sha256="abc", _image_size=800),
                                   module, 0.50)
    assert resized["image_size_matches"] is False and resized["active"] is False
    unknown = evaluation.top_paths(SimpleNamespace(_checkpoint_sha256="zzz", _image_size=640),
                                   module, 0.50)
    assert unknown["checkpoint_registered"] is False and unknown["active"] is False
    module.settings.yolo_top_rotation_fallback = False
    assert evaluation.top_paths(classifier, module, 0.50)["active"] is False


def test_top_paths_report_whether_the_calibrated_iou_can_act():
    module = SimpleNamespace(
        TOP_CALIBRATED_CHECKPOINTS={"abc": 640}, TOP_OVERLAP_CONFIDENCE=0.50,
        TOP_OVERLAP_BASE_IOU=0.45,
        settings=SimpleNamespace(yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
                                 yolo_top_rotation_fallback=True),
    )
    nms = SimpleNamespace(_checkpoint_sha256="abc", _image_size=640,
                          inference_head="one_to_many_nms")
    report = evaluation.top_paths(nms, module, 0.50)
    assert report["inference_head"] == "one_to_many_nms"
    assert report["overlap_refinement_effective"] is True
    # The NMS-free head keeps "active" (the paths run) but the IoU setting cannot act.
    free = SimpleNamespace(_checkpoint_sha256="abc", _image_size=640, inference_head="one_to_one")
    report = evaluation.top_paths(free, module, 0.50)
    assert report["active"] is True and report["overlap_refinement_effective"] is False
    legacy = evaluation.top_paths(SimpleNamespace(_checkpoint_sha256="abc", _image_size=640),
                                  module, 0.50)
    assert legacy["inference_head"] == "unknown"


def test_existing_output_stops_the_run_before_any_evaluation(tmp_path, monkeypatch, capsys):
    ran = []
    monkeypatch.setattr(evaluation, "run_gate", lambda args: ran.append("gate") or {})
    monkeypatch.setattr(evaluation, "run_pipeline", lambda args: ran.append("pipeline") or {})
    report = tmp_path / "ood-pipeline-report.json"
    report.write_text("{}")
    for command in (["gate", "--ood", str(tmp_path)],
                    ["pipeline", "--weights", "w.pt", "--ood", str(tmp_path)]):
        with pytest.raises(SystemExit) as stopped:
            evaluation.main([*command, "--output", str(report)])
        assert stopped.value.code == 2
    assert ran == [] and "output already exists" in capsys.readouterr().err
    fresh = tmp_path / "new.json"
    assert evaluation.main(["gate", "--ood", str(tmp_path), "--output", str(fresh)]) == 0
    assert ran == ["gate"] and json.loads(fresh.read_text()) == {}


@pytest.mark.parametrize(("filename", "scan"), [
    ("valid__B4_Latundan1_NoneChemical_02570_top_jpg.rf.995e.jpg",
     "valid__B4_Latundan1_NoneChemical_02570"),
    ("valid__B4_Latundan1_NoneChemical_02570_back_jpg.rf.b17c.jpg",
     "valid__B4_Latundan1_NoneChemical_02570"),
    ("valid__B4_Latundan1_NoneChemical_02571_left.jpg", "valid__B4_Latundan1_NoneChemical_02571"),
    ("plain.jpg", "plain"),
])
def test_views_of_one_capture_share_a_scan_id(filename, scan):
    assert evaluation.scan_id(filename) == scan


@pytest.mark.parametrize(("filename", "view"), [
    ("valid__B4_Latundan1_NoneChemical_02570_top_jpg.rf.995e92959d649ecc.jpg", "Top"),
    ("test__L2_Lakatan3_00012_left.jpg", "Left"),
    ("train__C1_Cardaba_00007_RIGHT_png.rf.abc.png", "Right"),
    ("valid__B4_Latundan1_00031_back-2-_jpg.rf.abc.jpg", "Rear"),
    ("valid__B4_Latundan1_00031_rear.jpg", "Rear"),
    ("valid__desktop_photo.jpg", None),
    ("valid__topview_of_bananas.jpg", None),
])
def test_camera_view_is_read_from_the_prepared_file_name(filename, view):
    assert evaluation.camera_view(filename) == view


def test_pipeline_reads_views_and_reports_each_one(tmp_path):
    split = tmp_path / "dataset" / "test"
    (split / "images").mkdir(parents=True)
    (split / "labels").mkdir()
    names = [f"{c}_{r}" for c in ("cardaba", "lakatan", "latundan")
             for r in ("overripe", "ripe", "semi_ripe", "unripe")]
    (tmp_path / "dataset" / "data.yaml").write_text(f"nc: 12\nnames: {json.dumps(names)}\n")
    for stem, label in [("a_00001_top_jpg.rf.x", 5), ("a_00001_back_jpg.rf.x", 5),
                        ("plain", 9), ("mixed_00002_left", None)]:
        (split / "images" / f"{stem}.jpg").write_bytes(b"x")
        classes = (5, 1) if label is None else (label,)
        (split / "labels" / f"{stem}.txt").write_text(
            "".join(f"{value} 0.5 0.5 0.2 0.2\n" for value in classes)
        )
    found = {path.name: (truth, view) for path, truth, view in evaluation._id_images(split)}
    assert found == {
        "a_00001_top_jpg.rf.x.jpg": ("Lakatan", "Top"),
        "a_00001_back_jpg.rf.x.jpg": ("Lakatan", "Rear"),
        "plain.jpg": ("Latundan", None),
    }  # the mixed-cultivar image has no single ground truth and is left out
