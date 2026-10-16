"""Synthetic model outputs exercise classification and camera consensus only."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.classification import (
    BananaClassifier,
    ClassificationResult,
    Detection,
)
from app.services.fusion_engine import FusionEngine


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

