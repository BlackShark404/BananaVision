"""Synthetic model outputs exercise classification and camera consensus only."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.classification import (
    BananaClassifier,
    ClassificationResult,
    Detection,
)
from app.services.fusion_engine import FusionEngine, _count_top_second_tier


def classify(*labels_and_scores: tuple[str, float]) -> ClassificationResult:
    """Use separate boxes so the fixture needs no model weights or cameras."""
    names = dict(enumerate(label for label, _ in labels_and_scores))
    boxes = [
        SimpleNamespace(
            xyxy=np.array([[index * 20, 1, index * 20 + 10, 80]], dtype=float),
            conf=[score],
            cls=[index],
        )
        for index, (_, score) in enumerate(labels_and_scores)
    ]
    model_result = SimpleNamespace(boxes=boxes, names=names)
    classifier = BananaClassifier()
    classifier._model = SimpleNamespace(predict=lambda *args, **kwargs: [model_result])
    return classifier.predict(
        np.zeros((100, 100, 3), dtype=np.uint8), confidence_threshold=0.85,
    )


def camera_result(
    cultivar: str = "Lakatan", ripeness: str = "Ripe", confidence: float = 90,
) -> ClassificationResult:
    label = f"{cultivar}_{ripeness}".lower().replace(" ", "_")
    return ClassificationResult(
        cultivar=cultivar,
        ripeness=ripeness,
        confidence=confidence,
        finger_count=1,
        detections=[Detection(0, 0, 10, 80, label, confidence / 100)],
    )


def views(*results: ClassificationResult):
    return [(f"CAM-{index:03}", f"View {index}", result)
            for index, result in enumerate(results, start=1)]


def test_classifier_keeps_variety_majority_and_selects_an_observed_pair():
    result = classify(
        ("lakatan_ripe", 0.91), ("lakatan_unripe", 0.90),
        ("cardaba_overripe", 0.95), ("latundan_overripe", 0.95),
    )

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(91)
    assert result.finger_count == 4
    assert result.conflict_detected is True


def test_classifier_confidence_uses_only_the_selected_variety_and_ripeness():
    result = classify(
        ("lakatan_ripe", 0.92), ("lakatan_ripe", 0.88),
        ("lakatan_unripe", 0.86),
    )

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(90)
    assert result.conflict_detected is False


def test_fusion_keeps_variety_majority_and_selects_an_observed_camera_pair():
    result = FusionEngine().fuse(views(
        camera_result("Lakatan", "Ripe", 91),
        camera_result("Lakatan", "Unripe", 90),
        camera_result("Cardaba", "Overripe", 95),
        camera_result("Latundan", "Overripe", 95),
    ))

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(91)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


def test_fusion_confidence_uses_only_cameras_with_the_selected_pair():
    result = FusionEngine().fuse(views(
        camera_result("Lakatan", "Ripe", 92),
        camera_result("Lakatan", "Ripe", 88),
        camera_result("Lakatan", "Unripe", 86),
    ))

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(90)
    assert result.auto_flagged is False


@pytest.mark.parametrize(
    ("lakatan_scores", "latundan_scores", "expected_confidence"),
    [((64, 72), (90, 65.8), 77.9), ((51, 51), (99, 99), 99)],
)
def test_split_cultivar_cameras_require_review_despite_a_higher_candidate_score(
    lakatan_scores, latundan_scores, expected_confidence,
):
    result = FusionEngine().fuse(views(
        *(camera_result("Lakatan", "Ripe", score) for score in lakatan_scores),
        *(camera_result("Latundan", "Ripe", score) for score in latundan_scores),
    ))

    assert (result.cultivar, result.ripeness) == ("Latundan", "Ripe")
    assert result.confidence == pytest.approx(expected_confidence)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


@pytest.mark.parametrize(
    ("majority_score", "minority_score", "expected_conflict"),
    [(70, 90, False), (49, 99, True)],
)
def test_camera_cultivar_majority_preserves_the_existing_weighted_conflict_threshold(
    majority_score, minority_score, expected_conflict,
):
    result = FusionEngine().fuse(views(
        *(camera_result("Lakatan", "Ripe", majority_score) for _ in range(3)),
        camera_result("Latundan", "Ripe", minority_score),
    ), review_confidence_threshold=0.30)

    assert result.cultivar == "Lakatan"
    assert result.confidence == pytest.approx(majority_score)
    assert result.conflict_detected is expected_conflict
    assert result.auto_flagged is expected_conflict


def test_high_score_camera_minority_is_flagged_without_replacing_its_candidate():
    result = FusionEngine().fuse(views(
        *(camera_result("Lakatan", "Ripe", 20) for _ in range(3)),
        camera_result("Latundan", "Ripe", 99),
    ))

    assert result.cultivar == "Latundan"
    assert result.confidence == pytest.approx(99)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


def test_repeated_camera_id_cannot_turn_a_cultivar_split_into_a_majority():
    camera_views = views(
        camera_result("Lakatan", "Ripe", 51),
        camera_result("Lakatan", "Ripe", 51),
        camera_result("Latundan", "Ripe", 99),
        camera_result("Latundan", "Ripe", 99),
    )
    camera_views.append(("CAM-003", "Repeated view", camera_result("Latundan", "Ripe", 99)))
    result = FusionEngine().fuse(camera_views, expected_camera_count=4)

    assert result.camera_count == 4
    assert len(result.per_camera) == 4
    assert result.cultivar == "Latundan"
    assert result.confidence == pytest.approx(99)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


@pytest.mark.parametrize("invalid_view", [
    ClassificationResult(cultivar="Lakatan", confidence=99),
    ClassificationResult(ripeness="Ripe", confidence=99),
    *(camera_result("Lakatan", "Ripe", score)
      for score in [float("nan"), float("inf"), float("-inf"), 0, -1, 100.1]),
])
def test_incomplete_or_invalid_camera_summaries_do_not_remove_a_valid_cultivar_majority(
    invalid_view,
):
    result = FusionEngine().fuse(views(
        camera_result("Latundan", "Ripe", 90),
        camera_result("Latundan", "Ripe", 90),
        camera_result("Lakatan", "Ripe", 30),
        invalid_view,
    ))

    assert result.camera_count == 4
    assert result.cultivar == "Latundan"
    assert result.confidence == pytest.approx(90)
    assert result.conflict_detected is False
    assert result.auto_flagged is False


def test_fusion_flags_a_pair_without_sixty_percent_of_total_camera_weight():
    result = FusionEngine().fuse(views(
        camera_result("Lakatan", "Ripe", 90),
        camera_result("Lakatan", "Ripe", 90),
        camera_result("Lakatan", "Unripe", 86),
        camera_result("Cardaba", "Overripe", 86),
    ))

    # Cultivar has 75.6% support and its selected ripeness has 67.7%,
    # but the actual complete pair has only 51.1% of all camera weight.
    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(90)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


def test_matching_camera_summaries_do_not_hide_ambiguous_detections():
    ambiguous = classify(("lakatan_ripe", 0.90), ("cardaba_overripe", 0.89))
    result = FusionEngine().fuse(views(ambiguous, ambiguous, ambiguous, ambiguous))

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(90)
    assert result.conflict_detected is True
    assert result.auto_flagged is True


def test_one_detecting_view_out_of_four_is_flagged_without_inflating_confidence():
    result = FusionEngine().fuse(views(
        camera_result("Latundan", "Overripe", 86),
        ClassificationResult(), ClassificationResult(), ClassificationResult(),
    ))

    assert (result.cultivar, result.ripeness) == ("Latundan", "Overripe")
    assert result.confidence == pytest.approx(86)
    assert result.camera_count == 4
    assert result.auto_flagged is True


def test_two_detecting_views_out_of_four_can_confirm_the_same_pair():
    result = FusionEngine().fuse(views(
        camera_result(), camera_result(), ClassificationResult(), ClassificationResult(),
    ))

    assert result.confidence == pytest.approx(90)
    assert result.camera_count == 4
    assert result.conflict_detected is False
    assert result.auto_flagged is False


def test_all_four_agreeing_views_are_not_flagged():
    result = FusionEngine().fuse(views(*(camera_result() for _ in range(4))))

    assert result.camera_count == 4
    assert result.conflict_detected is False
    assert result.auto_flagged is False


def test_intentionally_configured_single_camera_remains_supported():
    result = FusionEngine().fuse(views(camera_result()), expected_camera_count=1)

    assert result.camera_count == 1
    assert result.conflict_detected is False
    assert result.auto_flagged is False


def test_missing_expected_captures_are_flagged_even_with_two_agreeing_views():
    result = FusionEngine().fuse(
        views(camera_result(), camera_result()), expected_camera_count=4,
    )

    assert result.camera_count == 2
    assert result.confidence == pytest.approx(90)
    assert result.auto_flagged is True


def test_one_successful_capture_from_four_expected_cameras_is_flagged():
    result = FusionEngine().fuse(views(camera_result()), expected_camera_count=4)

    assert result.camera_count == 1
    assert result.confidence == pytest.approx(90)
    assert result.auto_flagged is True


@pytest.mark.parametrize("camera_results", [[], [ClassificationResult()] * 4])
def test_absent_classifications_cannot_produce_a_prediction(camera_results):
    result = FusionEngine().fuse(views(*camera_results), expected_camera_count=4)

    assert (result.cultivar, result.ripeness) == ("Unknown", "Unknown")
    assert result.confidence == 0
    assert result.finger_count == 0
    assert result.camera_count == len(camera_results)
    assert result.auto_flagged is True


def test_classifier_does_not_combine_separate_partial_labels():
    result = classify(("lakatan", 0.99), ("ripe", 0.99))

    assert result.cultivar == "Lakatan"
    assert result.ripeness is None
    assert result.conflict_detected is True


def test_fusion_does_not_combine_separate_partial_camera_labels():
    result = FusionEngine().fuse(views(
        ClassificationResult(cultivar="Lakatan", confidence=99),
        ClassificationResult(ripeness="Ripe", confidence=99),
    ))

    assert (result.cultivar, result.ripeness) == ("Unknown", "Unknown")
    assert result.confidence == 0
    assert result.auto_flagged is True


def test_repeated_camera_id_cannot_establish_two_camera_support():
    result = FusionEngine().fuse([
        ("CAM-001", "Top", camera_result(confidence=90)),
        ("CAM-001", "Top duplicate", camera_result(confidence=99)),
    ], expected_camera_count=2)

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.camera_count == 1
    assert len(result.per_camera) == 1
    assert result.confidence == pytest.approx(90)
    assert result.auto_flagged is True


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf"), 0, -1, 100.1])
def test_invalid_camera_confidence_cannot_change_a_supported_pair(confidence):
    result = FusionEngine().fuse(views(
        camera_result("Lakatan", "Ripe", 92),
        camera_result("Lakatan", "Ripe", 88),
        camera_result("Cardaba", "Overripe", confidence),
    ))

    assert (result.cultivar, result.ripeness) == ("Lakatan", "Ripe")
    assert result.confidence == pytest.approx(90)
    assert result.auto_flagged is False


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf"), 0, -1, 100.1])
def test_invalid_camera_confidence_cannot_establish_a_prediction(confidence):
    result = FusionEngine().fuse(views(camera_result(confidence=confidence)))

    assert (result.cultivar, result.ripeness) == ("Unknown", "Unknown")
    assert result.confidence == 0
    assert result.auto_flagged is True


def _make_det(x: float, y: float, w: float = 20.0, h: float = 80.0, conf: float = 0.90) -> Detection:
    return Detection(x=x, y=y, w=w, h=h, cls="latundan_ripe", confidence=conf)


@pytest.mark.parametrize("legacy_fusion_enabled", [True, False])
@pytest.mark.parametrize("labels", [
    ["Top", "Left", "Right", "Rear"],
    ["Rear", "Right", "Left", "Top"],
    ["View A", "View B", "View C", "View D"],
])
def test_reported_four_view_counts_do_not_invent_unseen_fingers(
    monkeypatch, legacy_fusion_enabled, labels,
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "multi_camera_finger_fusion", legacy_fusion_enabled)
    counts = [7, 9, 10, 13]
    results = [
        (f"CAM-{index}", label, ClassificationResult(
            cultivar="Latundan", ripeness="Ripe", confidence=90,
            finger_count=count,
            detections=[_make_det(x=i * 30, y=0) for i in range(count)],
        ))
        for index, (label, count) in enumerate(zip(labels, counts, strict=True))
    ]

    fused = FusionEngine().fuse(results, expected_camera_count=4)

    # The user reports about 15 physically present. Counts alone cannot recover
    # hidden fingers; 13 is an observed estimate, not a verified physical total.
    assert fused.finger_count == 13
    assert fused.auto_flagged is True
    assert fused.conflict_detected is False
    assert fused.confidence == 90
    assert [camera.finger_count for camera in fused.per_camera] == counts


def test_peripheral_positions_cannot_establish_nineteen_unique_fingers():
    # Synthetic peripheral positions cannot prove that side/rear detections
    # represent fingers absent from the other cameras.
    # Top view: 10 fingers across the center (span x: 100 to 500)
    top_dets = [_make_det(x=100 + i * 40, y=200) for i in range(10)]
    top_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=10, detections=top_dets,
    )

    # Left view: 3 in outer left flank + 10 central
    left_dets = (
        [_make_det(x=50 + i * 40, y=200) for i in range(3)]
        + [_make_det(x=250 + i * 25, y=200) for i in range(10)]
    )
    left_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=13, detections=left_dets,
    )

    # Right view: 10 central + 3 in outer right flank
    right_dets = (
        [_make_det(x=100 + i * 25, y=200) for i in range(10)]
        + [_make_det(x=400 + i * 40, y=200) for i in range(3)]
    )
    right_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=13, detections=right_dets,
    )

    # Rear view: 3 in upper band + 3 in inner concavity underside (rel_y >= 0.55)
    rear_dets = (
        [_make_det(x=200 + i * 50, y=120) for i in range(3)]
        + [_make_det(x=200 + i * 50, y=350) for i in range(3)]
    )
    rear_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=6, detections=rear_dets,
    )

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top_res),
        ("CAM-002", "Left", left_res),
        ("CAM-003", "Right", right_res),
        ("CAM-004", "Rear", rear_res),
    ])

    assert fused.finger_count == 13
    assert fused.auto_flagged is True
    assert fused.cultivar == "Latundan"
    assert fused.ripeness == "Ripe"


def test_multi_camera_finger_fusion_respects_disabled_setting(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "multi_camera_finger_fusion", False)

    top_dets = [_make_det(x=100 + i * 40, y=200) for i in range(10)]
    top_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=10, detections=top_dets,
    )
    left_dets = [_make_det(x=50 + i * 40, y=200) for i in range(3)] + [_make_det(x=250 + i * 25, y=200) for i in range(10)]
    left_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=13, detections=left_dets,
    )

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top_res),
        ("CAM-002", "Left", left_res),
    ])
    # When disabled, falls back to max(finger_counts) = 13
    assert fused.finger_count == 13


def test_multi_camera_finger_fusion_single_top_view():
    top_dets = [_make_det(x=100 + i * 40, y=200) for i in range(10)]
    top_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=10, detections=top_dets,
    )
    fused = FusionEngine().fuse([("CAM-001", "Top", top_res)], expected_camera_count=1)
    assert fused.finger_count == 10


def test_top_count_drop_does_not_change_the_largest_visible_estimate():
    # Top view only detects 9 fingers (1 finger dropped by confidence cutoff)
    top_dets = [_make_det(x=100 + i * 40, y=200) for i in range(9)]
    top_res = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=9, detections=top_dets,
    )

    # Left view: 3 novel flank fingers
    left_dets = [_make_det(x=50 + i * 40, y=200) for i in range(3)] + [_make_det(x=250 + i * 25, y=200) for i in range(10)]
    left_res = ClassificationResult(cultivar="Latundan", ripeness="Ripe", confidence=90, finger_count=13, detections=left_dets)

    # Right view: 3 novel flank fingers
    right_dets = [_make_det(x=100 + i * 25, y=200) for i in range(10)] + [_make_det(x=400 + i * 40, y=200) for i in range(3)]
    right_res = ClassificationResult(cultivar="Latundan", ripeness="Ripe", confidence=90, finger_count=13, detections=right_dets)

    # Rear view: 9 detections (inner tier of 9 fingers, with 3 in concavity)
    rear_dets = [_make_det(x=150 + i * 35, y=120) for i in range(6)] + [_make_det(x=200 + i * 50, y=350) for i in range(3)]
    rear_res = ClassificationResult(cultivar="Latundan", ripeness="Ripe", confidence=90, finger_count=9, detections=rear_dets)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top_res),
        ("CAM-002", "Left", left_res),
        ("CAM-003", "Right", right_res),
        ("CAM-004", "Rear", rear_res),
    ])

    assert fused.finger_count == 13
    assert fused.auto_flagged is True


def test_equal_camera_counts_do_not_double_count_the_same_fingers():
    # The same four physical fingers may appear in both views. Image position
    # alone cannot establish that the Rear boxes are additional fingers.
    dets = [_make_det(x=index * 30, y=0) for index in range(4)]
    result = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90,
        finger_count=4, detections=dets,
    )

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", result), ("CAM-004", "Rear", result),
    ], expected_camera_count=2)

    assert fused.finger_count == 4
    assert fused.auto_flagged is False
    assert fused.conflict_detected is False
    assert fused.confidence == 90
    assert [camera.finger_count for camera in fused.per_camera] == [4, 4]


def test_rear_anchor_does_not_add_its_own_peripheral_fingers_again():
    top = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90, finger_count=7,
        detections=[_make_det(x=index * 30, y=0) for index in range(7)],
    )
    rear = ClassificationResult(
        cultivar="Latundan", ripeness="Ripe", confidence=90, finger_count=10,
        detections=[_make_det(x=index * 30, y=0) for index in range(10)],
    )

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top), ("CAM-004", "Rear", rear),
    ], expected_camera_count=2)

    assert fused.finger_count == 10
    assert fused.auto_flagged is True
    assert fused.conflict_detected is False


@pytest.mark.parametrize(("view_type", "duplicate_index"), [
    ("left", 0), ("right", 3), ("rear", 3),
])
def test_fusion_uses_unique_per_view_counts_not_raw_class_box_totals(
    view_type, duplicate_index,
):
    dets = [
        _make_det(x=0, y=0), _make_det(x=50, y=0),
        _make_det(x=100, y=200), _make_det(x=150, y=200),
    ]
    original = dets[duplicate_index]
    duplicate = Detection(
        original.x, original.y, original.w, original.h, "lakatan_ripe", 0.88,
    )
    raw_detections = [*dets, duplicate]
    result = ClassificationResult(finger_count=4, detections=raw_detections)

    fused = FusionEngine().fuse([("CAM-1", view_type, result)])

    assert fused.finger_count == 4
    assert result.detections == raw_detections
    assert len(result.detections) == 5


@pytest.mark.parametrize("view_type", ["left", "right", "rear"])
def test_duplicate_labels_cannot_increase_the_reported_view_count(view_type):
    dets = [_make_det(x=index * 50, y=index * 50) for index in range(3)]
    original = dets[0]
    dets.append(Detection(
        original.x, original.y, original.w, original.h, "lakatan_ripe", 0.88,
    ))
    result = ClassificationResult(finger_count=3, detections=dets)

    fused = FusionEngine().fuse([("CAM-1", view_type, result)])
    assert fused.finger_count == 3


def test_top_camera_anchor_resolves_two_vs_two_cultivar_split():
    # Top + Right predict Lakatan Ripe; Left + Rear predict Latundan Ripe.
    # Overhead Top anchor establishes Lakatan without triggering a split conflict.
    top = camera_result("Lakatan", "Ripe", 82)
    right = camera_result("Lakatan", "Ripe", 78)
    left = camera_result("Latundan", "Ripe", 88)
    rear = camera_result("Latundan", "Ripe", 85)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    assert fused.cultivar == "Lakatan"
    assert fused.ripeness == "Ripe"
    assert fused.conflict_detected is False
    assert fused.auto_flagged is False
    assert fused.cultivar_conflict is False


def test_top_camera_anchor_resolves_latundan_split():
    # Top + Left predict Latundan Ripe; Right + Rear predict Lakatan Ripe.
    top = camera_result("Latundan", "Ripe", 80)
    left = camera_result("Latundan", "Ripe", 75)
    right = camera_result("Lakatan", "Ripe", 85)
    rear = camera_result("Lakatan", "Ripe", 82)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    assert fused.cultivar == "Latundan"
    assert fused.ripeness == "Ripe"
    assert fused.conflict_detected is False
    assert fused.auto_flagged is False
    assert fused.cultivar_conflict is False


def test_top_camera_minority_against_strict_majority_requires_review():
    # If 3 peripheral cameras all agree against Top (e.g. 3 Latundan vs 1 Lakatan),
    # strict majority rule flags it for operator review.
    top = camera_result("Lakatan", "Ripe", 80)
    left = camera_result("Latundan", "Ripe", 85)
    right = camera_result("Latundan", "Ripe", 85)
    rear = camera_result("Latundan", "Ripe", 85)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    assert fused.conflict_detected is True
    assert fused.auto_flagged is True


def test_conflicted_top_camera_does_not_unilaterally_anchor():
    top = camera_result("Lakatan", "Ripe", 80)
    top.conflict_detected = True
    top.cultivar_conflict = True
    right = camera_result("Lakatan", "Ripe", 78)
    left = camera_result("Latundan", "Ripe", 88)
    rear = camera_result("Latundan", "Ripe", 85)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    # When Top has cultivar conflict, standard split safeguards apply
    assert fused.conflict_detected is True
    assert fused.auto_flagged is True


def test_top_camera_with_duplicate_boxes_still_anchors():
    # If Top has duplicate boxes (conflict_detected=True, cultivar_conflict=False),
    # it still reliably anchors the cultivar because fingers agree on variety.
    top = camera_result("Lakatan", "Ripe", 80)
    top.conflict_detected = True
    top.cultivar_conflict = False
    right = camera_result("Lakatan", "Ripe", 78)
    left = camera_result("Latundan", "Ripe", 88)
    rear = camera_result("Latundan", "Ripe", 85)

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    assert fused.cultivar == "Lakatan"
    assert fused.cultivar_conflict is False
    assert fused.conflict_detected is True
    assert fused.auto_flagged is True


def test_peripheral_background_filter_suppresses_upper_door_frame():
    # Simulate a 1000x1000 frame on the Left camera with:
    # 1. A vertical pillar/door frame touching top edge: x=450..550, y=0..450 (h/w = 4.5)
    # 2. A ceiling fixture: x=100..300, y=10..150 (all y < 220)
    # 3. A real banana finger on the tray: x=200..400, y=400..600
    boxes = [
        SimpleNamespace(
            xyxy=np.array([[450, 0, 550, 450]], dtype=float),
            conf=[0.85],
            cls=[0],
        ),
        SimpleNamespace(
            xyxy=np.array([[100, 10, 300, 150]], dtype=float),
            conf=[0.80],
            cls=[0],
        ),
        SimpleNamespace(
            xyxy=np.array([[200, 400, 400, 600]], dtype=float),
            conf=[0.90],
            cls=[0],
        ),
        # 4. Background door frame starting below top edge (Image 3): x=650..740, y=150..480
        SimpleNamespace(
            xyxy=np.array([[650, 150, 740, 480]], dtype=float),
            conf=[0.72],
            cls=[0],
        ),
    ]
    model_result = SimpleNamespace(boxes=boxes, names={0: "lakatan_ripe"})
    classifier = BananaClassifier()
    classifier._model = SimpleNamespace(predict=lambda *args, **kwargs: [model_result])

    frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    right_result = classifier.predict(frame, confidence_threshold=0.50, camera_label="Right")

    # Only the real banana finger on the tray is retained; door frames and ceiling are filtered
    assert right_result.finger_count == 1
    assert len(right_result.detections) == 1
    assert right_result.detections[0].y >= 400

    # On Top camera, upper frame detections are NOT suppressed
    top_result = classifier.predict(frame, confidence_threshold=0.50, camera_label="Top")
    assert top_result.finger_count == 4


def test_multi_finger_top_anchor_prevails_over_lower_confidence_peripheral_tips():
    top = ClassificationResult(
        cultivar="Cardaba", ripeness="Unripe", confidence=88.3, finger_count=8,
    )
    left = ClassificationResult(
        cultivar="Lakatan", ripeness="Unripe", confidence=78.0, finger_count=7,
    )
    right = ClassificationResult(
        cultivar="Lakatan", ripeness="Unripe", confidence=76.0, finger_count=7,
    )
    rear = ClassificationResult(
        cultivar="Lakatan", ripeness="Unripe", confidence=80.0, finger_count=11,
    )

    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", left),
        ("CAM-003", "Right", right),
        ("CAM-004", "Rear", rear),
    ], expected_camera_count=4)

    assert fused.cultivar == "Cardaba"
    assert fused.ripeness == "Unripe"
    assert fused.cultivar_conflict is False
    assert fused.finger_count == 11


def _two_tier_view(cultivar: str, ripeness: str, conf: float, upper_n: int, lower_n: int) -> ClassificationResult:
    cls_name = f"{cultivar.lower()}_{ripeness.lower().replace(' ', '_')}"
    span = max(upper_n, lower_n, 1) * 110
    u_step = span / max(upper_n, 1)
    l_step = span / max(lower_n, 1)
    dets = [
        *(Detection(40 + i * u_step, 180, 140, 170, cls_name, conf) for i in range(upper_n)),
        *(Detection(40 + i * l_step, 380, 140, 170, cls_name, conf) for i in range(lower_n)),
    ]
    return ClassificationResult(
        cultivar=cultivar,
        ripeness=ripeness,
        confidence=round(conf * 100, 1),
        finger_count=upper_n + lower_n,
        detections=dets,
    )


def _top_fan_view(
    cultivar: str,
    ripeness: str,
    conf: float,
    primary_n: int,
    recovered_n: int = 0,
    short_tip_n: int = 0,
) -> ClassificationResult:
    cls_name = f"{cultivar.lower()}_{ripeness.lower().replace(' ', '_')}"
    dets: list[Detection] = []
    idx = 0
    for _ in range(primary_n):
        dets.append(Detection(20 + idx * 120, 120, 100, 260, cls_name, conf))
        idx += 1
    for _ in range(recovered_n):
        dets.append(Detection(20 + idx * 120, 80, 95, 240, cls_name, 0.42))
        idx += 1
    for _ in range(short_tip_n):
        dets.append(Detection(20 + idx * 120, 90, 60, 110, cls_name, conf))
        idx += 1
    return ClassificationResult(
        cultivar=cultivar,
        ripeness=ripeness,
        confidence=round(conf * 100, 1),
        finger_count=primary_n + recovered_n + short_tip_n,
        detections=dets,
    )


def test_two_tier_hand_fusion_reconstructs_occluded_lower_tier_fingers():
    engine = FusionEngine()

    # 1. Ripe Latundan 14-finger two-tier hand (Top=10 upper, Left=7, Right=9, Rear=9)
    latundan_ripe = engine.fuse([
        ("CAM-001", "Top", _top_fan_view("Latundan", "Ripe", 0.85, 10)),
        ("CAM-002", "Left", _two_tier_view("Latundan", "Ripe", 0.89, 4, 3)),
        ("CAM-003", "Right", _two_tier_view("Latundan", "Ripe", 0.81, 4, 5)),
        ("CAM-004", "Rear", _two_tier_view("Latundan", "Ripe", 0.88, 5, 4)),
    ], expected_camera_count=4)
    assert latundan_ripe.finger_count == 14
    assert latundan_ripe.auto_flagged is True

    # 2. Unripe Cardaba 14-finger two-tier hand (Top=13 with 2 inner/recovered tips, Left=9, Right=11, Rear=11)
    cardaba_unripe = engine.fuse([
        ("CAM-001", "Top", _top_fan_view("Cardaba", "Unripe", 0.81, 11, recovered_n=1, short_tip_n=1)),
        ("CAM-002", "Left", _two_tier_view("Cardaba", "Unripe", 0.80, 6, 3)),
        ("CAM-003", "Right", _two_tier_view("Cardaba", "Unripe", 0.80, 7, 4)),
        ("CAM-004", "Rear", _two_tier_view("Cardaba", "Unripe", 0.81, 8, 3)),
    ], expected_camera_count=4)
    assert cardaba_unripe.finger_count == 14

    # 3. Unripe Latundan 15-finger two-tier hand (Top=12 with 2 recovered tips, Left=7, Right=10, Rear=11)
    latundan_unripe = engine.fuse([
        ("CAM-001", "Top", _top_fan_view("Latundan", "Unripe", 0.85, 10, recovered_n=2)),
        ("CAM-002", "Left", _two_tier_view("Latundan", "Unripe", 0.82, 4, 3)),
        ("CAM-003", "Right", _two_tier_view("Latundan", "Unripe", 0.84, 5, 5)),
        ("CAM-004", "Rear", _two_tier_view("Latundan", "Unripe", 0.85, 4, 7)),
    ], expected_camera_count=4)
    assert latundan_unripe.finger_count == 15

    # 4. Wide Ripe Lakatan 21-finger two-tier hand (Top=10, Left=10, Right=9, Rear=13)
    lakatan_21 = engine.fuse([
        ("CAM-001", "Top", _top_fan_view("Lakatan", "Ripe", 0.86, 10)),
        ("CAM-002", "Left", _two_tier_view("Lakatan", "Ripe", 0.84, 5, 5)),
        ("CAM-003", "Right", _two_tier_view("Lakatan", "Ripe", 0.83, 4, 5)),
        ("CAM-004", "Rear", _two_tier_view("Lakatan", "Ripe", 0.85, 6, 7)),
    ], expected_camera_count=4)
    assert lakatan_21.finger_count == 21


def test_single_tier_hand_fusion_keeps_single_view_maximum():
    # Single-tier 10-finger Lakatan hand (Top=10, Left=7, Right=10, Rear=6):
    # Rear < max(Left, Right) so no second tier is added.
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", _top_fan_view("Lakatan", "Unripe", 0.84, 10)),
        ("CAM-002", "Left", _two_tier_view("Lakatan", "Unripe", 0.82, 5, 2)),
        ("CAM-003", "Right", _two_tier_view("Lakatan", "Unripe", 0.84, 7, 3)),
        ("CAM-004", "Rear", _two_tier_view("Lakatan", "Unripe", 0.83, 6, 0)),
    ], expected_camera_count=4)
    assert fused.finger_count == 10


def _radial_top_fan_detections(cls_name: str) -> list[Detection]:
    """Build a radial overhead hand with splayed horizontal outer wings (w > h)."""
    # 3 left wings (w > h), 4 central vertical fingers (including 0.52 slender primary),
    # and 3 right wings (w > h). Median box area ~= 280*150 = 42000; smallest primary ~= 0.52*med.
    return [
        Detection(10, 480, 290, 155, cls_name, 0.88),
        Detection(40, 320, 280, 160, cls_name, 0.83),
        Detection(80, 180, 250, 150, cls_name, 0.53),
        Detection(290, 20, 150, 280, cls_name, 0.78),
        Detection(420, 40, 115, 200, cls_name, 0.88),  # 23000 ~= 0.52 * 44000
        Detection(510, 20, 155, 285, cls_name, 0.90),
        Detection(610, 100, 165, 270, cls_name, 0.84),
        Detection(640, 200, 280, 160, cls_name, 0.86),
        Detection(660, 360, 290, 155, cls_name, 0.82),
        Detection(640, 520, 260, 145, cls_name, 0.51),
    ]


def test_top_radial_wings_and_slender_primary_fingers_stay_in_primary_tier():
    radial = _radial_top_fan_detections("latundan_unripe")
    assert _count_top_second_tier(radial) == 0

    with_peeking_tips = [
        *radial,
        Detection(210, 10, 75, 170, "lakatan_ripe", 0.59),   # ~0.32 * med_area
        Detection(770, 70, 130, 105, "lakatan_ripe", 0.85),  # ~0.35 * med_area
        Detection(560, 800, 130, 110, "lakatan_ripe", 0.42),  # < TOP_OVERLAP_CONFIDENCE
    ]
    assert _count_top_second_tier(with_peeking_tips) == 3


def test_radial_latundan_ripe_fan_reconstructs_fourteen_not_ten():
    radial_top = _radial_top_fan_detections("latundan_ripe")
    top = ClassificationResult(
        cultivar="Latundan",
        ripeness="Ripe",
        confidence=85.0,
        finger_count=len(radial_top),
        detections=radial_top,
    )
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", _two_tier_view("Latundan", "Ripe", 0.89, 3, 4)),
        ("CAM-003", "Right", _two_tier_view("Latundan", "Ripe", 0.81, 4, 5)),
        ("CAM-004", "Rear", _two_tier_view("Latundan", "Ripe", 0.88, 5, 4)),
    ], expected_camera_count=4)
    assert fused.finger_count == 14


def test_wide_two_tier_hand_with_top_wing_fans_and_inner_tips_avoids_collapse():
    # Reproduces 21-finger Ripe Lakatan geometry: Top=11 (8 full radial fingers + 3 tiny
    # inner/perimeter peeking tips), Left=11 (5u, 6l), Right=9 (4u, 5l), Rear=13 (6u, 7l).
    top_dets = [
        Detection(10, 460, 390, 270, "lakatan_ripe", 0.86),
        Detection(50, 300, 380, 260, "lakatan_ripe", 0.83),
        Detection(80, 150, 320, 240, "lakatan_ripe", 0.53),
        Detection(290, 10, 220, 420, "lakatan_ripe", 0.75),
        Detection(490, 10, 220, 410, "lakatan_ripe", 0.82),
        Detection(510, 310, 370, 270, "lakatan_ripe", 0.83),
        Detection(560, 570, 320, 230, "lakatan_ripe", 0.51),
        Detection(20, 740, 250, 220, "lakatan_ripe", 0.79),
        # Three genuine tiny peeking tips (< 0.42 * med_area ~ 36k)
        Detection(450, 40, 95, 290, "lakatan_ripe", 0.59),
        Detection(610, 220, 200, 140, "lakatan_ripe", 0.85),
        Detection(560, 800, 190, 140, "lakatan_ripe", 0.75),
    ]
    top = ClassificationResult(
        cultivar="Lakatan",
        ripeness="Ripe",
        confidence=76.5,
        finger_count=len(top_dets),
        detections=top_dets,
    )
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", top),
        ("CAM-002", "Left", _two_tier_view("Lakatan", "Ripe", 0.84, 5, 6)),
        ("CAM-003", "Right", _two_tier_view("Lakatan", "Ripe", 0.83, 4, 5)),
        ("CAM-004", "Rear", _two_tier_view("Lakatan", "Ripe", 0.85, 6, 7)),
    ], expected_camera_count=4)
    assert 20 <= fused.finger_count <= 21


def test_rear_capture_collapse_recovers_from_both_stacked_sides():
    # Severe Rear capture failure (2 detections) while both Left and Right establish two
    # stacked vertical rows should recover conservatively without changing single-tier hands.
    fused = FusionEngine().fuse([
        ("CAM-001", "Top", _top_fan_view("Cardaba", "Unripe", 0.81, 11, short_tip_n=1)),
        ("CAM-002", "Left", _two_tier_view("Cardaba", "Unripe", 0.85, 5, 4)),
        ("CAM-003", "Right", _two_tier_view("Cardaba", "Unripe", 0.85, 6, 5)),
        ("CAM-004", "Rear", _two_tier_view("Cardaba", "Unripe", 0.60, 2, 0)),
    ], expected_camera_count=4)
    assert fused.finger_count == 15
