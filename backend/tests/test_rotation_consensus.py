"""Rotating a finger must not turn stage ambiguity into cultivar ambiguity."""

import numpy as np
import pytest

from app.services.classification import BananaClassifier, Detection, _unique_box_detections
from app.services.fusion_engine import FusionEngine
from tests.test_classification_fusion import camera_result
from tests.test_top_view_inference import VERIFIED_CHECKPOINT, SequencePredictor


def rotated_hand(rotated_class):
    primary = [(40 + i * 50, 180, 65 + i * 50, 300, 0.90, 0) for i in range(11)]
    rotated = [
        (900 - x2, 480 - y2, 900 - x1, 480 - y1, 0.85, rotated_class if i == 0 else 0)
        for i, (x1, y1, x2, y2, _, _) in enumerate(primary)
    ]
    recovered = [(65 + i * 50, 180, 90 + i * 50, 300, 0.40, 0) for i in range(3)]
    classifier = BananaClassifier()
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    classifier._model = SequencePredictor(
        [primary, rotated, primary + recovered],
        {0: "lakatan_unripe", 1: "lakatan_semi_ripe", 2: "cardaba_unripe"},
    )
    return classifier.predict(
        np.zeros((480, 900, 3), dtype=np.uint8),
        confidence_threshold=0.50, camera_label="Top",
    )


def test_rotated_stage_disagreement_preserves_cultivar_and_recovers_all_visible_fingers():
    result = rotated_hand(1)

    assert result.cultivar == "Lakatan"
    assert result.cultivar_conflict is False
    assert result.conflict_detected is True  # stage ambiguity still merits review
    assert result.finger_count == 14
    assert len(result.detections) == 14


def test_rotated_stage_disagreement_does_not_disable_top_cultivar_anchor():
    top = rotated_hand(1)
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", camera_result("Cardaba", "Unripe", 88)),
        ("CAM-003", "Right", camera_result("Lakatan", "Unripe", 89)),
        ("CAM-004", "Rear", camera_result("Cardaba", "Unripe", 87)),
    ], expected_camera_count=4)

    assert fused.cultivar == "Lakatan"
    assert fused.cultivar_conflict is False
    assert fused.finger_count == 14


def test_rotated_stage_ambiguity_still_flags_review_when_all_counts_agree():
    top = rotated_hand(1)
    other = camera_result("Lakatan", "Unripe", 90)
    other.finger_count = top.finger_count
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", other),
        ("CAM-003", "Right", other),
        ("CAM-004", "Rear", other),
    ], expected_camera_count=4)

    assert fused.cultivar_conflict is False
    assert fused.conflict_detected is True
    assert fused.auto_flagged is True


@pytest.mark.parametrize("rotated_class", [0, 2])
def test_actual_rotated_cultivar_disagreement_keeps_review_safeguards(rotated_class):
    result = rotated_hand(rotated_class)

    assert result.cultivar_conflict is (rotated_class == 2)
    assert result.finger_count == (11 if rotated_class == 2 else 14)


@pytest.mark.parametrize("second_label", ["latundan_ripe", "latundan_semi_ripe"])
def test_fourteen_neighboring_fingers_count_the_same_across_ripeness_labels(second_label):
    boxes = [Detection(i * 150, 0, 100, 140, "latundan_ripe", 0.95) for i in range(8)]
    for i in range(3):
        boxes.extend([
            Detection(i * 200, 200, 100, 140, "latundan_ripe", 0.90),
            Detection(i * 200 + 15, 200, 100, 140, second_label, 0.85),
        ])

    assert len(_unique_box_detections(boxes)) == 14


@pytest.mark.parametrize("second_label", ["latundan_ripe", "latundan_semi_ripe"])
def test_coincident_or_nested_hypotheses_still_count_once(second_label):
    parent = Detection(0, 0, 100, 140, "latundan_ripe", 0.95)
    duplicate = Detection(0, 0, 100, 140, second_label, 0.90)
    fragment = Detection(35, 35, 30, 70, second_label, 0.85)

    assert len(_unique_box_detections([parent, duplicate, fragment])) == 1
