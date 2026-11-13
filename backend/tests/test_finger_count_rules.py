"""Finger-count rules: undercounts from hidden fingers and overcounts from non-banana objects.

Each rule has a setting that restores the earlier behaviour, so the tests check both.
Box rows are (x1, y1, x2, y2, confidence, class id).
"""

from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog, Scan
from app.services import classification
from app.services.classification import BananaClassifier, Detection, _is_duplicate_detection
from app.services.ood_gate import EvidenceBox
from tests.test_ood_gate import (
    BoxModel,
    assert_gate_equals_deleting_unsupported_boxes,
    classifier_for,
    gate_result,
    station,  # noqa: F401, F811 - fixture
    summary,
)
from tests.test_scan_trigger import scan_station  # noqa: F401 - fixture dependency
from tests.test_time_and_writes import application  # noqa: F401 - fixture dependency
from tests.test_top_view_inference import VERIFIED_CHECKPOINT, SequencePredictor

CARDABA = {0: "cardaba_unripe", 1: "cardaba_ripe", 2: "cardaba_semi_ripe",
           3: "cardaba_overripe"}
UNRIPE, RIPE, SEMI, OVERRIPE = 0, 1, 2, 3
LATUNDAN = {0: "latundan_ripe"}


@pytest.fixture
def rules(monkeypatch):
    """Switch individual rules off; everything else keeps the shipped defaults."""
    def set_rules(**flags):
        monkeypatch.setattr(classification, "settings",
                            classification.settings.model_copy(update=flags))
    return set_rules


def predict(rows, names=CARDABA, **kwargs):
    classifier = BananaClassifier()
    classifier._model = BoxModel(rows, names)
    return classifier.predict(None, confidence_threshold=0.50, **kwargs)


def det(x1, y1, x2, y2, cls="lakatan_ripe", conf=0.9):
    return Detection(x=x1, y=y1, w=x2 - x1, h=y2 - y1, cls=cls, confidence=conf)


# ── B1: the "same finger column" duplicate rule follows the finger's long axis ──
STACKED = (det(0, 0, 200, 60), det(10, 30, 210, 90))          # two lying fingers, one above
SHIFTED_ALONG = (det(0, 0, 200, 60), det(80, 5, 280, 65))     # one lying finger, re-detected
SHIFTED_UPRIGHT = (det(0, 0, 60, 200), det(5, 80, 65, 280))   # one upright finger, re-detected


def test_stacked_lying_fingers_are_not_merged_as_one_column(rules):
    assert _is_duplicate_detection(*STACKED) is False
    assert _is_duplicate_detection(*SHIFTED_ALONG) is True
    assert _is_duplicate_detection(*SHIFTED_UPRIGHT) is True
    rules(yolo_axis_aware_rotation_dedup=False)
    assert _is_duplicate_detection(*STACKED) is True
    assert _is_duplicate_detection(*SHIFTED_ALONG) is False
    assert _is_duplicate_detection(*SHIFTED_UPRIGHT) is True


def test_rotated_top_pass_keeps_a_stacked_lying_finger(rules):
    # 480 x 640 Top frame; the rotated pass sees the second finger (rows are given in
    # rotated coordinates: x' = 640 - x, y' = 480 - y).
    first = [(100, 100, 300, 160, 0.90, 0)]
    second = (110, 130, 310, 190)
    rotated = [(640 - second[2], 480 - second[3], 640 - second[0], 480 - second[1], 0.85, 0)]

    def run():
        classifier = BananaClassifier()
        classifier._model = SequencePredictor([first, rotated], {0: "lakatan_ripe"})
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        return classifier.predict(np.zeros((480, 640, 3), np.uint8),
                                  confidence_threshold=0.50, camera_label="Top")

    assert run().finger_count == 2
    rules(yolo_axis_aware_rotation_dedup=False)
    assert run().finger_count == 1


# ── B2: a confident whole-hand box no longer hides the fingers beside each other ──
HAND = (55, 15, 245, 185, 0.95, 0)
ROW = [(60, 20, 100, 180, 0.90, 0), (130, 20, 170, 180, 0.88, 0), (200, 20, 240, 180, 0.86, 0)]


def test_hand_box_is_replaced_by_the_fingers_it_hid(rules):
    result = predict([HAND, *ROW], names=LATUNDAN)
    assert result.finger_count == 3 and result.hand_box_splits == 1
    assert [(d.x, d.confidence) for d in result.detections] == [
        (60, 0.90), (130, 0.88), (200, 0.86),
    ]
    # Votes are unchanged: the hand box voted, the restored fingers do not.
    assert (result.cultivar, result.ripeness, result.confidence) == ("Latundan", "Ripe", 95.0)
    rules(yolo_hand_box_split=False)
    legacy = predict([HAND, *ROW], names=LATUNDAN)
    assert legacy.finger_count == 1 and legacy.hand_box_splits == 0


@pytest.mark.parametrize("rows", [
    # Squarish end fragments of one upright finger.
    [(100, 50, 160, 350, 0.90, 0), (100, 50, 160, 120, 0.80, 0), (100, 280, 160, 350, 0.78, 0)],
    # Long fragments of one upright finger, one above the other.
    [(100, 0, 160, 400, 0.90, 0), (100, 0, 160, 190, 0.80, 0), (100, 210, 160, 400, 0.78, 0)],
    # A hand box that hid only one finger.
    [HAND, ROW[1]],
])
def test_fragments_of_one_finger_still_count_once(rows):
    result = predict(rows, names=LATUNDAN)
    assert result.finger_count == 1 and result.hand_box_splits == 0


def test_lying_fingers_hidden_by_a_hand_box_are_restored():
    hand = (10, 50, 190, 260, 0.95, 0)
    lying = [(15, 60, 185, 110, 0.90, 0), (15, 130, 185, 180, 0.88, 0),
             (15, 200, 185, 250, 0.86, 0)]
    assert predict([hand, *lying], names=LATUNDAN).finger_count == 3


# ── C: a box two or more ripeness stages from the rest of the hand is not a finger ──
GREEN = [(100, 40, 160, 190, 0.80, UNRIPE), (170, 40, 230, 190, 0.75, UNRIPE)]
WOOD = (300, 100, 380, 190, 0.64, RIPE)  # beside the hand, touching no finger


def test_wood_read_as_a_ripe_finger_beside_an_unripe_hand_is_dropped(rules):
    result = predict([*GREEN, WOOD])
    assert (result.cultivar, result.ripeness, result.finger_count) == ("Cardaba", "Unripe", 2)
    assert result.ripeness_outlier_boxes == 1
    assert [d.cls for d in result.detections] == ["cardaba_unripe", "cardaba_unripe"]
    assert result.confidence == 77.5  # the wood box's vote is withdrawn too
    rules(yolo_ripeness_outlier_filter=False)
    legacy = predict([*GREEN, WOOD])
    assert legacy.finger_count == 3 and legacy.ripeness_outlier_boxes == 0


def test_outlier_touching_the_hand_is_dropped_only_when_less_confident():
    hand = [*GREEN, (240, 40, 300, 190, 0.78, UNRIPE)]
    touching_weak = (280, 60, 340, 190, 0.70, RIPE)
    touching_strong = (280, 60, 340, 190, 0.85, RIPE)
    assert predict([*hand, touching_weak]).finger_count == 3
    kept = predict([*hand, touching_strong])
    assert kept.finger_count == 4 and kept.ripeness_outlier_boxes == 0


@pytest.mark.parametrize("rows", [
    [*GREEN, (300, 100, 380, 190, 0.64, SEMI)],                 # adjacent stage
    [(100, 40, 160, 190, 0.80, UNRIPE), (300, 40, 360, 190, 0.80, RIPE)],    # 1 + 1
    [*GREEN, (300, 40, 360, 190, 0.80, RIPE), (400, 40, 460, 190, 0.75, RIPE)],  # 2 + 2
    [(100, 40, 160, 190, 0.55, UNRIPE), (170, 40, 230, 190, 0.52, UNRIPE),
     (300, 100, 380, 190, 0.90, RIPE)],                          # weak majority (< 60 %)
])
def test_mixed_ripeness_without_a_clear_majority_is_left_alone(rows):
    result = predict(rows)
    assert result.ripeness_outlier_boxes == 0 and result.finger_count == len(rows)


def test_majority_of_mixed_cultivars_is_not_a_hand():
    # Ripe/overripe boxes of three cultivars do not make one coherent hand to judge by.
    rows = [(0, 0, 50, 150, 0.91, 0), (60, 0, 110, 150, 0.95, 1),
            (120, 0, 170, 150, 0.95, 2), (200, 0, 250, 150, 0.90, 3)]
    names = {0: "lakatan_ripe", 1: "cardaba_overripe", 2: "latundan_overripe",
             3: "lakatan_unripe"}
    assert predict(rows, names=names).ripeness_outlier_boxes == 0


def test_two_labels_on_one_finger_do_not_make_a_majority():
    # One finger boxed as unripe and semi ripe (same box) is one finger, not two.
    rows = [(100, 40, 160, 190, 0.80, UNRIPE), (100, 40, 160, 190, 0.70, SEMI),
            (300, 100, 380, 190, 0.64, RIPE)]
    assert predict(rows).ripeness_outlier_boxes == 0


# ── Second, low-threshold pass: only fingers inside the hand, no platter lip ──
H, W = 517, 900
# Four upright fingers and a lower one reaching the plate, as in the station photo.
FINGERS = [(100 + 110 * i, 120, 200 + 110 * i, 400, 0.90 - 0.01 * i, 0) for i in range(4)]
FINGERS.append((540, 300, 640, 513, 0.86, 0))
WINDOW = (612, 0, 682, 142, 0.29, 0)     # bright window frame above the hand
PLATE = (307, 411, 640, 513, 0.26, 0)    # wooden plate under the hand
HIDDEN = (160, 200, 230, 390, 0.35, 0)   # a partly hidden finger inside the hand
FLANK = (650, 140, 740, 400, 0.33, 0)    # a hidden finger just beside the outermost one


def side_view(label, recovered):
    classifier = BananaClassifier()
    # Top also runs the rotated pass; it finds nothing new here.
    passes = [FINGERS, FINGERS + recovered]
    if label == "Top":
        passes.insert(1, [])
    classifier._model = SequencePredictor(passes, LATUNDAN)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    return classifier.predict(np.zeros((H, W, 3), np.uint8), confidence_threshold=0.50,
                              camera_label=label)


@pytest.mark.parametrize("label", ["Left", "Right", "Rear", "Top"])
def test_second_pass_adds_hidden_fingers_but_not_background(rules, label):
    # The overhead camera sees no platter lip from the side, so it gets no plate box.
    recovered = [WINDOW, HIDDEN] if label == "Top" else [WINDOW, PLATE, HIDDEN]
    result = side_view(label, recovered)
    added = [(d.x, d.y) for d in result.detections[5:]]
    assert added == [(160, 200)] and result.finger_count == 6


def test_second_pass_keeps_a_flank_finger_beside_the_hand():
    result = side_view("Left", [FLANK, WINDOW])
    assert [(d.x, d.y) for d in result.detections[5:]] == [(650, 140)]


@pytest.mark.parametrize(("flags", "count"), [
    ({"yolo_recovery_within_hand": False}, 7),   # the window frame comes back
    ({"yolo_side_view_lip_filter": False}, 7),   # the plate comes back
    ({"yolo_recovery_within_hand": False, "yolo_side_view_lip_filter": False}, 8),
])
def test_second_pass_background_rules_can_be_switched_off(rules, flags, count):
    rules(**flags)
    assert side_view("Left", [WINDOW, PLATE, HIDDEN]).finger_count == count


def count_on(label, rows):
    classifier = BananaClassifier()
    classifier._model = BoxModel(rows, LATUNDAN)
    return classifier.predict(np.zeros((H, W, 3), np.uint8), confidence_threshold=0.50,
                              camera_label=label).finger_count


def test_platter_lip_is_filtered_on_every_side_camera(rules):
    lip = (300, 420, 700, 500, 0.55, 0)
    rows = [*FINGERS[:2], lip]
    assert [count_on(label, rows) for label in ("Left", "Right", "Rear", "Top")] == [2, 2, 2, 3]
    rules(yolo_side_view_lip_filter=False)
    # Earlier behaviour: only the Rear camera filtered the lip.
    assert [count_on(label, rows) for label in ("Left", "Right", "Rear")] == [3, 3, 2]


# ── The station flags a scan whose boxes were dropped for inconsistent ripeness ──
def test_station_flags_a_scan_with_a_ripeness_outlier(station):  # noqa: F811
    # Three ripe Lakatan fingers and one "unripe" object beside them, on banana evidence.
    station.gate = lambda _frame: gate_result(boxes=[EvidenceBox(0, 0, 400, 200, 0.8)])
    fingers = [(10, 20, 50, 180), (70, 20, 110, 180), (130, 20, 170, 180)]
    station.model.rows = [(*f, 0.90, 0) for f in fingers] + [(330, 20, 380, 180, 0.60, 1)]
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["cultivar"], data["ripeness"], data["finger_count"]) == ("Lakatan", "Ripe", 3)
    assert data["flagged"] is True
    with Session(station.app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert all(len(d.bounding_boxes) == 3 for d in saved.detections)
        created = db.scalar(select(ActivityLog.details).where(
            ActivityLog.action == "scan_created",
        ))
    assert created.endswith("4 boxes with inconsistent ripeness dropped, flagged for review")


def test_adjacent_ripeness_recovery_is_off_unless_switched_on(rules):
    names = {0: "latundan_ripe", 1: "latundan_semi_ripe", 2: "latundan_unripe"}
    semi = (*HIDDEN[:4], 0.35, 1)
    unripe = (420, 200, 490, 390, 0.35, 2)

    def run():
        classifier = BananaClassifier()
        classifier._model = SequencePredictor([FINGERS, FINGERS + [semi, unripe]], names)
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        return classifier.predict(np.zeros((H, W, 3), np.uint8), confidence_threshold=0.50,
                                  camera_label="Left")

    assert run().finger_count == 5
    rules(yolo_recovery_adjacent_ripeness=True)
    # One stage away is admitted for measurement; two stages away never is.
    assert [d.cls for d in run().detections[5:]] == ["latundan_semi_ripe"]


# ── Review follow-ups ──
def test_restored_fingers_do_not_double_count_the_rotated_pass():
    # Pass 1: a hand box that hid three fingers. The rotated Top pass finds the two
    # outer fingers again, shifted 35 px along their length.
    hand = (100, 100, 400, 300, 0.95, 0)
    fingers = [(105, 105, 165, 295, 0.90, 0), (220, 105, 280, 295, 0.88, 0),
               (335, 105, 395, 295, 0.86, 0)]
    again = [(102, 140, 170, 300), (330, 140, 398, 300)]
    rotated = [(640 - x2, 480 - y2, 640 - x1, 480 - y1, score, 0)
               for (x1, y1, x2, y2), score in zip(again, (0.89, 0.85), strict=True)]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([[hand, *fingers], rotated], LATUNDAN)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(np.zeros((480, 640, 3), np.uint8), confidence_threshold=0.50,
                                camera_label="Top")
    assert result.hand_box_splits == 1 and result.finger_count == 3


def test_confident_box_beside_the_hand_is_dropped_when_it_touches_no_finger(rules):
    hand = [*GREEN, (240, 40, 300, 190, 0.78, UNRIPE)]
    detached_strong = (500, 100, 580, 190, 0.85, RIPE)
    result = predict([*hand, detached_strong])
    assert result.finger_count == 3 and result.ripeness_outlier_boxes == 1
    rules(yolo_ripeness_outlier_filter=False)
    assert predict([*hand, detached_strong]).finger_count == 4


def test_far_boxes_that_are_as_many_as_the_majority_are_kept():
    # Two strong unripe fingers and two weak ripe ones: no majority by count.
    rows = [(100, 40, 160, 190, 0.90, UNRIPE), (170, 40, 230, 190, 0.90, UNRIPE),
            (300, 40, 360, 190, 0.60, RIPE), (400, 40, 460, 190, 0.60, RIPE)]
    result = predict(rows)
    assert result.ripeness_outlier_boxes == 0 and result.finger_count == 4


def test_hand_ripening_across_stages_keeps_its_ripe_fingers():
    # Unripe, semi ripe and ripe fingers in one hand: transitional, not wood.
    rows = [(100, 40, 160, 190, 0.80, UNRIPE), (170, 40, 230, 190, 0.78, UNRIPE),
            (240, 40, 300, 190, 0.55, SEMI), (310, 40, 370, 190, 0.52, SEMI),
            (380, 40, 440, 190, 0.72, RIPE), (450, 40, 510, 190, 0.70, RIPE)]
    result = predict(rows)
    assert result.ripeness_outlier_boxes == 0 and result.finger_count == 6


def test_second_pass_on_a_lying_hand_stays_within_the_fingers_length():
    # Lying fingers (wider than tall): a hidden one may sit one finger above or below,
    # but nothing beyond the fingers' ends.
    lying = [(100, 100 + 70 * i, 500, 160 + 70 * i, 0.90 - 0.01 * i, 0) for i in range(5)]
    below = (120, 450, 480, 505, 0.33, 0)      # one finger below the stack
    past_end = (560, 230, 880, 290, 0.33, 0)   # beyond the fingers' tips
    classifier = BananaClassifier()
    # Overhead view: pass 1, an empty rotated pass, then the second pass.
    classifier._model = SequencePredictor([lying, [], lying + [below, past_end]], LATUNDAN)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(np.zeros((H, W, 3), np.uint8), confidence_threshold=0.50,
                                camera_label="Top")
    assert [(d.x, d.y) for d in result.detections[5:]] == [(120, 450)]


def test_finger_still_inside_a_box_that_stays_is_not_restored():
    # The hand box splits, but its first finger also sits in a two-finger box that
    # does not split (only one hidden finger): it stays hidden there.
    rows = [HAND, (55, 15, 110, 185, 0.94, 0), *ROW]
    result = predict(rows, names=LATUNDAN)
    assert result.hand_box_splits == 1
    assert sorted(d.x for d in result.detections) == [55, 130, 200]


def gate_contract(rows, evidence):
    """The gate removes only off-evidence boxes; any other change is counted (flagged)."""
    gated = assert_gate_equals_deleting_unsupported_boxes(rows, evidence)
    ungated = classifier_for(rows).predict(None, confidence_threshold=0.50)
    if gated.ood_rejected_boxes == 0:
        assert summary(gated) == summary(ungated)
    return gated, ungated


def test_gate_flags_a_hand_split_that_only_the_off_evidence_fragment_decided():
    # The hand box P also swallowed a large off-evidence fragment G. With G, the median
    # box area keeps P below the cluster size; without it, P splits. The gate changed the
    # count, so it must be counted.
    rows = [(0, 0, 200, 200, 0.95, 0), (0, -25, 200, 101, 0.93, 0),
            (10, 20, 50, 180, 0.90, 0), (150, 20, 190, 180, 0.88, 0),
            (300, 0, 500, 200, 0.94, 0), (520, 0, 720, 200, 0.92, 0)]
    evidence = [EvidenceBox(0, 80, 200, 120, 0.5), EvidenceBox(300, 0, 420, 200, 0.5)]
    gated, ungated = gate_contract(rows, evidence)
    assert gated.finger_count != ungated.finger_count and gated.ood_rejected_boxes >= 1


def test_gate_does_not_flag_a_split_that_ends_the_same_without_it():
    # A fingertip fragment off the evidence: with or without it the hand box gives way to
    # the same three fingers, so nothing changed and the scan is not flagged.
    rows = [(5, 15, 175, 185, 0.95, 0), (10, 20, 50, 180, 0.90, 0),
            (70, 20, 110, 180, 0.88, 0), (130, 20, 170, 180, 0.86, 0),
            (70, 20, 110, 50, 0.85, 0)]
    gated, ungated = gate_contract(rows, [EvidenceBox(0, 80, 200, 120, 0.5)])
    assert gated.finger_count == ungated.finger_count == 3
    assert gated.ood_rejected_boxes == 0
