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


@pytest.mark.parametrize(("banana", "expected"), [
    (True, {"no_gate": ("Lakatan", 3), "legacy_gate": ("Lakatan", 3), "ood_gate": ("Lakatan", 2)}),
    (False, {"no_gate": ("Lakatan", 3), "legacy_gate": (None, 0), "ood_gate": (None, 0)}),
])
def test_pipeline_variants_compare_no_gate_legacy_gate_and_ood_gate(banana, expected):
    calls = []
    detector = SimpleNamespace(detect=lambda _image, **kwargs: SimpleNamespace(
        available=True, banana_detected=banana, boxes=EVIDENCE if banana else [],
    ))

    def predict(_image, **kwargs):
        calls.append(kwargs)
        fingers = 2 if "banana_evidence" in kwargs else 3
        return SimpleNamespace(cultivar="Lakatan", finger_count=fingers)

    outcome = evaluation.predict_variants(
        None, detector, SimpleNamespace(predict=predict), POLICY, 0.5,
    )
    assert outcome == expected
    assert len(calls) == (2 if banana else 1)
    broken = SimpleNamespace(detect=lambda _image, **kwargs: SimpleNamespace(available=False))
    with pytest.raises(EvaluationError):
        evaluation.predict_variants(None, broken, SimpleNamespace(predict=predict), POLICY, 0.5)
