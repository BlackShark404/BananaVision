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
def test_station_notes_a_scan_with_a_ripeness_outlier(station):  # noqa: F811
    # Three ripe Lakatan fingers and one "unripe" object beside them, on banana evidence.
    station.gate = lambda _frame: gate_result(boxes=[EvidenceBox(0, 0, 400, 200, 0.8)])
    fingers = [(10, 20, 50, 180), (70, 20, 110, 180), (130, 20, 170, 180)]
    station.model.rows = [(*f, 0.90, 0) for f in fingers] + [(330, 20, 380, 180, 0.60, 1)]
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["cultivar"], data["ripeness"], data["finger_count"]) == ("Lakatan", "Ripe", 3)
    # Dropped boxes are noted in the activity log; only low confidence flags a scan.
    assert data["flagged"] is False
    with Session(station.app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert all(len(d.bounding_boxes) == 3 for d in saved.detections)
        created = db.scalar(select(ActivityLog.details).where(
            ActivityLog.action == "scan_created",
        ))
    assert created.endswith("; noted: 4 boxes with inconsistent ripeness dropped")


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


# ── Radial-fan geometry, connected stage-straddling pairs, and split-cultivar recovery ──
def test_stacked_horizontal_finger_inside_diagonal_neighbor_box_is_preserved():
    # Two horizontal flank fingers sharing x-span (rel_dx <= 0.08) but separated vertically
    # (rel_dy > 0.50), where the upper diagonal finger's rectangle overlaps the lower one.
    rows = [
        (839, 276, 1262, 693, 0.92, 0),  # upper diagonal finger (w=423, h=417)
        (853, 499, 1268, 700, 0.63, 0),  # lower horizontal finger (w=415, h=201)
    ]
    result = predict(rows, names=LATUNDAN)
    assert result.finger_count == 2 and len(result.detections) == 2


def test_narrow_protruding_second_tier_finger_inside_diagonal_neighbor_is_preserved():
    # A narrow upright inner-tier finger protruding above/below a wide diagonal neighbor
    # (rel_dx <= 0.08, rel_dy > 0.35, smaller.w < 0.50 * larger.w, smaller.h < 0.75 * larger.h).
    rows = [
        (100, 100, 256, 280, 0.92, 0),   # wide diagonal neighbor (w=156, h=180)
        (151, 177, 209, 275, 0.79, 0),   # narrow inner-tier finger (w=58, h=98)
    ]
    result = predict(rows, names=LATUNDAN)
    assert result.finger_count == 2 and len(result.detections) == 2


def test_diagonal_finger_in_radial_fan_is_not_dropped_as_cluster_box():
    # A 45-degree diagonal finger (478x485) whose empty bounding-box corners overlap one
    # horizontal neighbor (415x165) and one vertical neighbor (312x558) is a real finger,
    # not a whole-hand cluster box covering parallel fingers of the same orientation.
    rows = [
        (96, 65, 574, 550, 0.74, UNRIPE),    # diagonal finger (w=478, h=485)
        (7, 305, 422, 470, 0.85, UNRIPE),    # horizontal neighbor (w=415, h=165)
        (107, 31, 467, 355, 0.75, UNRIPE),   # upper diagonal neighbor (w=360, h=324)
        (324, 2, 636, 560, 0.87, UNRIPE),    # vertical neighbor (w=312, h=558)
        (737, 11, 1072, 505, 0.93, UNRIPE),  # right vertical finger (w=335, h=494)
    ]
    result = predict(rows)
    assert result.finger_count == 5 and len(result.detections) == 5


def test_connected_pair_of_stage_straddling_fingers_touching_hand_is_kept():
    # Two adjacent fingers on the flank of an unripe hand whose peel colour straddles
    # Unripe/Ripe (d1 touches near, d2 touches d1): two connected fingers are part of
    # the hand, whereas a single weak box touching the hand is still dropped.
    near_hand = [
        (324, 2, 636, 560, 0.93, UNRIPE),
        (7, 305, 422, 470, 0.85, UNRIPE),
        (49, 405, 567, 604, 0.77, UNRIPE),
    ]
    connected_pair = [
        (17, 552, 526, 701, 0.69, RIPE),   # touches (49, 405, 567, 604)
        (0, 629, 593, 856, 0.66, RIPE),    # touches (17, 552, 526, 701)
    ]
    result = predict([*near_hand, *connected_pair])
    assert result.finger_count == 5 and result.ripeness_outlier_boxes == 0


def test_second_pass_recovers_fingers_when_cultivar_votes_split_across_uniform_ripeness():
    # Foreshortened Rear view where Pass 1 agrees 100% on Unripe but splits cultivar votes
    # across Cardaba, Lakatan, and Latundan (< 60% for any single cultivar).
    names = {0: "cardaba_unripe", 1: "lakatan_unripe", 2: "latundan_unripe"}
    pass1 = [
        (59, 384, 427, 780, 0.65, 0),
        (704, 80, 1244, 493, 0.55, 0),
        (592, 486, 1028, 854, 0.69, 1),
        (43, 0, 335, 454, 0.52, 1),
        (501, 41, 924, 426, 0.59, 2),
    ]
    recovered = [
        (170, 224, 470, 590, 0.56, 1),
        (450, 247, 710, 611, 0.48, 1),
    ]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([pass1, pass1 + recovered], names)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(
        np.zeros((900, 1280, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Rear",
    )
    assert result.finger_count == 7 and len(result.detections) == 7


def test_rotated_top_pass_preserves_parallel_horizontal_finger_with_moderate_iou():
    # Two adjacent horizontal fingers on the right flank of a 10-finger single-tier hand:
    # IoU is ~0.43 (> TOP_ROTATION_DEDUP_IOU 0.40, < TOP_OVERLAP_IOU 0.65), but their
    # vertical centres are separated by ~0.40 * min_h (> 0.30 * min_h).
    img_h, img_w = 260, 420
    pass1 = [
        (30, 40, 100, 220, 0.92, 0),
        (110, 30, 180, 220, 0.91, 0),
        (190, 35, 260, 220, 0.90, 0),
        (252, 103, 407, 225, 0.94, 0),  # 9th horizontal finger (w=155, h=122, cy=164)
    ]
    # 10th horizontal finger below it: canonical (264, 154, 397, 250) -> rotated 180 coords:
    rx1, ry1 = img_w - 397, img_h - 250
    rx2, ry2 = img_w - 264, img_h - 154
    pass2_rot = [
        (rx1, ry1, rx2, ry2, 0.78, 0),
    ]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([pass1, pass2_rot, pass1], LATUNDAN)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(
        np.zeros((img_h, img_w, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Top",
    )
    assert result.finger_count == 5 and len(result.detections) == 5


def test_second_pass_recovers_multi_stage_hand_fingers_matching_voted_labels():
    # Hand ripening across Semi Ripe and Ripe where both stages appear in Pass 1:
    # Pass 3 (augment=True) must recover occluded Semi Ripe fingers even when Ripe has
    # slightly higher Pass 1 weight.
    names = {0: "lakatan_ripe", 1: "lakatan_semi_ripe"}
    pass1 = [
        (40, 40, 140, 220, 0.85, 0),
        (150, 40, 250, 220, 0.82, 0),
        (260, 40, 360, 220, 0.78, 0),
        (50, 140, 160, 240, 0.80, 1),
        (170, 140, 280, 240, 0.76, 1),
        (290, 140, 390, 240, 0.75, 1),
    ]
    recovered = [
        (310, 138, 418, 223, 0.86, 1),
        (388, 121, 467, 220, 0.88, 1),
    ]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([pass1, pass1 + recovered], names)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(
        np.zeros((300, 500, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Left",
    )
    assert result.finger_count == 8 and len(result.detections) == 8


def test_peripheral_filter_preserves_frame_edge_clipped_upper_finger():
    # An upright upper-tier finger clipped by the right frame edge (x2 >= 0.96 * img_w)
    # on a peripheral camera is kept, while an isolated interior door frame is filtered.
    names = {0: "lakatan_ripe"}
    rows = [
        (120, 140, 260, 250, 0.90, 0),  # main tray finger
        (200, 10, 240, 130, 0.75, 0),   # isolated interior door frame (h/w=3.0, dropped)
        (454, 10, 498, 129, 0.80, 0),   # right-edge clipped upper finger (x2=498 >= 0.96*500, kept)
    ]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([rows, rows], names)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(
        np.zeros((300, 500, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Left",
    )
    assert result.finger_count == 2
    assert sorted( int(d.x) for d in result.detections ) == [120, 454]


def test_centered_sub_box_inside_horizontal_parent_deduplicates_both_passes():
    # Reproduces 18-lakatan-ripe-rear / 19-cardaba-unripe-top: portrait/square sub-box
    # (0.50 <= h/H < 0.80) centered horizontally inside a wide horizontal finger parent
    # (W >= 1.6 * H and W >= 2.0 * w) deduplicates in both Pass 1 and Pass 3.
    names = {0: "cardaba_unripe"}
    parent = (40, 200, 440, 410, 0.85, 0)         # w=400, h=210 (ratio 1.90)
    centered_sub = (185, 235, 295, 375, 0.67, 0)   # w=110, h=140 (0.67*H, centered)
    stacked_child = (185, 205, 295, 300, 0.62, 0)  # offset above centerline (rel_dy > 0.08)

    res_pass1 = predict([parent, centered_sub], names=names, camera_label="Rear")
    assert res_pass1.finger_count == 1

    # Pass 3 recovers parent around existing Pass-1 sub-box: both directions dedup.
    anchors = [
        (500, 60, 600, 260, 0.90, 0),
        (620, 60, 720, 260, 0.89, 0),
        (740, 60, 840, 260, 0.88, 0),
    ]
    p1_with_sub = [centered_sub, *anchors]
    clf = BananaClassifier()
    clf._model = SequencePredictor([p1_with_sub, [*p1_with_sub, parent]], names)
    clf._checkpoint_sha256 = VERIFIED_CHECKPOINT
    res_rec = clf.predict(
        np.zeros((500, 900, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Left",
    )
    assert res_rec.finger_count == 4

    # Off-axis stacked neighbor remains distinct.
    assert predict([parent, stacked_child], names=names, camera_label="Rear").finger_count == 2


def test_pass3_drops_far_ripeness_doorway_box_and_recovers_four_box_rear():
    # 1. Reproduces 03-latundan-unripe-left: a 0.38 Ripe doorway candidate (2 stages away
    # from Unripe) grazing an Unripe corner is dropped even in Pass 3, while an Unripe
    # neighbor inside the hand is kept.
    names_lat = {0: "latundan_unripe", 1: "latundan_ripe"}
    p1_lat = [
        (180, 120, 360, 220, 0.90, 0),
        (190, 230, 370, 330, 0.88, 0),
        (200, 340, 380, 440, 0.86, 0),
        (210, 450, 390, 540, 0.84, 0),
        (400, 180, 560, 280, 0.50, 0),
    ]
    doorway_ripe = (515, 0, 595, 195, 0.38, 1)  # 2 stages away + upper-margin peripheral
    inner_unripe = (220, 280, 380, 380, 0.41, 0)
    clf_lat = BananaClassifier()
    clf_lat._model = SequencePredictor([p1_lat, [*p1_lat, doorway_ripe, inner_unripe]], names_lat)
    clf_lat._checkpoint_sha256 = VERIFIED_CHECKPOINT
    res_lat = clf_lat.predict(
        np.zeros((640, 800, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Left",
    )
    assert res_lat.finger_count == 6
    assert all(d.cls == "latundan_unripe" for d in res_lat.detections)

    # 2. Reproduces 22-cardaba-unripe-rear: 4 confident Pass-1 detections trigger Pass 3
    # recovery instead of skipping it below 5 detections.
    names_car = {0: "cardaba_unripe"}
    p1_rear4 = [
        (180, 220, 340, 380, 0.85, 0),
        (350, 220, 510, 380, 0.82, 0),
        (200, 390, 360, 540, 0.78, 0),
        (370, 390, 530, 540, 0.74, 0),
    ]
    rec_fifth = (280, 310, 430, 460, 0.42, 0)
    clf_rear = BananaClassifier()
    clf_rear._model = SequencePredictor([p1_rear4, [*p1_rear4, rec_fifth]], names_car)
    clf_rear._checkpoint_sha256 = VERIFIED_CHECKPOINT
    res_rear = clf_rear.predict(
        np.zeros((640, 800, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Rear",
    )
    assert res_rear.finger_count == 5


def test_side_view_horizontal_hand_recovers_right_flank_and_high_conf_small_tip():
    # Reproduces 17-lakatan-ripe-right: horizontal (not upright) side-view hand recovers
    # a flanking body within 0.75 * med_w outside Pass-1 x-span plus a >=0.50 small end-on
    # tip (0.14 * median_area), while still dropping a <0.50 fragment of that same small area.
    names = {0: "lakatan_ripe"}
    p1_right = [
        (120, 180, 320, 290, 0.90, 0),  # 200x110 (med_w=200, med_h=110, med_area=22000)
        (130, 300, 330, 410, 0.88, 0),
        (330, 180, 530, 290, 0.86, 0),
        (340, 300, 540, 410, 0.85, 0),
        (220, 240, 420, 350, 0.84, 0),
    ]
    right_flank = (560, 290, 740, 400, 0.40, 0)       # center x=650 inside 540 + 0.75*200=690
    high_conf_tip = (380, 250, 442, 300, 0.58, 0)     # 62x50=3100 (~0.141 * med_area)
    low_conf_tiny = (180, 340, 242, 390, 0.35, 0)     # 62x50=3100 (<0.50 conf, <0.22 area)

    clf = BananaClassifier()
    clf._model = SequencePredictor(
        [p1_right, [*p1_right, right_flank, high_conf_tip, low_conf_tiny]], names,
    )
    clf._checkpoint_sha256 = VERIFIED_CHECKPOINT
    res = clf.predict(
        np.zeros((640, 900, 3), np.uint8),
        confidence_threshold=0.50, camera_label="Right",
    )
    assert res.finger_count == 7


def test_top_bottom_left_trim_overhang_duplicate_dropped_but_real_bl_finger_kept():
    # Reproduces 06/14/19/23 bottom-left trim overhang duplicate vs real bottom-left finger.
    img = np.zeros((480, 640, 3), np.uint8)
    img[:, :] = (165, 195, 205)              # pale tan table & front trim outside banana
    img[100:435, 110:500] = (40, 200, 160)   # bright green/yellow banana peel interior
    img[450:480, 0:640] = (15, 20, 15)       # dark shadow gap below trim

    names = {0: "cardaba_unripe"}
    clean_bl = (110, 345, 430, 435, 0.87, 0)
    trim_dup = (10, 345, 430, 475, 0.78, 0)  # overhangs tan left + dark bottom strip

    clf_dup = BananaClassifier()
    clf_dup._model = SequencePredictor([[clean_bl, trim_dup], []], names)
    clf_dup._checkpoint_sha256 = VERIFIED_CHECKPOINT
    assert clf_dup.predict(img, confidence_threshold=0.50, camera_label="Top").finger_count == 1

    # Single genuine bottom-left finger reaching the trim/gap with no clean inner partner survives.
    clf_real = BananaClassifier()
    clf_real._model = SequencePredictor([[trim_dup], []], names)
    clf_real._checkpoint_sha256 = VERIFIED_CHECKPOINT
    assert clf_real.predict(img, confidence_threshold=0.50, camera_label="Top").finger_count == 1
