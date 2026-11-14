"""Out-of-distribution rejection: gate logic, classifier filtering and the scan contract."""

from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import Settings
from app.models import ActivityLog, Scan
from app.services import classification, ood_gate, scan_service
from app.services.banana_detector import BANANA_CLASS_ID, BananaPreDetector
from app.services.classification import BananaClassifier
from app.services.fusion_engine import FusionEngine
from app.services.ood_gate import EvidenceBox, GatePolicy, ViewEvidence
from tests.test_scan_trigger import scan_station  # noqa: F401 - isolated SQLite fixture
from tests.test_time_and_writes import application  # noqa: F401 - fixture dependency
from tests.test_top_view_inference import VERIFIED_CHECKPOINT, SequencePredictor

NAMES = {0: "lakatan_ripe", 1: "latundan_unripe", 2: "cardaba_overripe"}
# Banana evidence covering the left half of a 400 x 200 frame.
EVIDENCE = [EvidenceBox(x=0, y=0, w=200, h=200, confidence=0.80)]
# Three separate fingers inside the evidence, and one object far outside it.
FINGERS = [(10, 20, 50, 180), (70, 20, 110, 180), (130, 20, 170, 180)]
FOREIGN = (330, 20, 380, 180)


class BoxModel:
    """Model fixture returning fixed (x1, y1, x2, y2, confidence, class) rows."""

    def __init__(self, rows, names=None):
        self.rows = rows
        self.names = names or NAMES
        self.calls = 0

    def predict(self, _image, **kwargs):
        self.calls += 1
        boxes = [
            SimpleNamespace(xyxy=np.array([row[:4]], dtype=float), conf=[row[4]], cls=[row[5]])
            for row in self.rows if row[4] >= kwargs["conf"]
        ]
        return [SimpleNamespace(boxes=boxes, names=self.names)]


def classifier_for(rows):
    classifier = BananaClassifier()
    classifier._model = BoxModel(rows)
    return classifier


def box(x1, y1, x2, y2):
    return SimpleNamespace(x=x1, y=y1, w=x2 - x1, h=y2 - y1)


# ── Pure gate logic ──────────────────────────────────────────────────────────

def test_support_requires_the_box_centre_inside_grown_banana_evidence():
    assert ood_gate.is_supported(box(*FINGERS[0]), EVIDENCE, 0.0)
    assert not ood_gate.is_supported(box(*FOREIGN), EVIDENCE, 0.25)
    # Centre x = 230: outside the evidence, inside its 25 % margin (200 + 50).
    edge = box(210, 20, 250, 180)
    assert not ood_gate.is_supported(edge, EVIDENCE, 0.0)
    assert ood_gate.is_supported(edge, EVIDENCE, 0.25)
    assert not ood_gate.is_supported(box(*FINGERS[0]), [], 0.25)


def test_banana_score_is_the_strongest_evidence_or_zero():
    assert ood_gate.banana_score([]) == 0.0
    assert ood_gate.banana_score([*EVIDENCE, EvidenceBox(0, 0, 1, 1, 0.31)]) == 0.80


@pytest.mark.parametrize("values", [
    {"banana_confidence": 0.30, "support_confidence": 0.40},
    {"support_confidence": 0},
    {"banana_confidence": 1.5},
    {"support_margin": -0.1},
    {"min_banana_views": 0},
])
def test_policy_rejects_inconsistent_thresholds(values):
    with pytest.raises(ValueError):
        GatePolicy(**values)


def test_settings_reject_support_confidence_above_banana_confidence():
    with pytest.raises(ValueError):
        Settings(_env_file=None, ood_banana_confidence=0.2, ood_support_confidence=0.3)
    policy = ood_gate.policy_from_settings(Settings(_env_file=None))
    assert policy == GatePolicy()
    # Legacy settings objects without OOD fields keep the documented defaults.
    assert ood_gate.policy_from_settings(SimpleNamespace()) == GatePolicy()


def view(has_banana):
    return ViewEvidence("CAM", "Top", [], 0.9 if has_banana else 0.0, has_banana)


@pytest.mark.parametrize(("bananas", "required", "accepted"), [
    ([False, False, False, False], 1, False),
    ([False, True, False, False], 1, True),
    ([False, True, False, False], 2, False),
    ([True, True, False, False], 2, True),
    # A one-camera station cannot be asked for two banana views.
    ([True], 2, True),
    ([], 1, False),
])
def test_scan_decision_counts_views_with_banana_evidence(bananas, required, accepted):
    decision = ood_gate.decide_scan(
        [view(value) for value in bananas], GatePolicy(min_banana_views=required),
    )
    assert decision.accepted is accepted
    assert decision.banana_views == sum(bananas)
    assert decision.reason == (None if accepted else ood_gate.REASON_NO_BANANA)


# ── Classifier filtering ─────────────────────────────────────────────────────

@pytest.mark.parametrize(("class_id", "cultivar", "ripeness"), [
    (0, "Lakatan", "Ripe"), (1, "Latundan", "Unripe"), (2, "Cardaba", "Overripe"),
])
def test_supported_cultivar_boxes_are_classified_unchanged(class_id, cultivar, ripeness):
    rows = [(*finger, 0.90, class_id) for finger in FINGERS]
    gated = classifier_for(rows).predict(
        None, confidence_threshold=0.50, banana_evidence=EVIDENCE,
    )
    legacy = classifier_for(rows).predict(None, confidence_threshold=0.50)
    assert (gated.cultivar, gated.ripeness, gated.finger_count) == (cultivar, ripeness, 3)
    assert gated.ood_rejected_boxes == 0
    assert (gated.cultivar, gated.confidence, gated.finger_count) == (
        legacy.cultivar, legacy.confidence, legacy.finger_count,
    )


def test_foreign_object_beside_a_banana_neither_votes_nor_counts():
    # The foreign box is the most confident and names another cultivar.
    rows = [(*finger, 0.80, 0) for finger in FINGERS] + [(*FOREIGN, 0.99, 2)]
    legacy = classifier_for(rows).predict(None, confidence_threshold=0.50)
    assert legacy.finger_count == 4 and legacy.cultivar_conflict is False
    assert "cardaba_overripe" in [d.cls for d in legacy.detections]

    gated = classifier_for(rows).predict(
        None, confidence_threshold=0.50, banana_evidence=EVIDENCE,
    )
    assert (gated.cultivar, gated.ripeness, gated.finger_count) == ("Lakatan", "Ripe", 3)
    assert gated.confidence == 80.0 and gated.ood_rejected_boxes == 1
    assert [d.cls for d in gated.detections] == ["lakatan_ripe"] * 3


def test_frame_without_banana_evidence_yields_no_cultivar():
    rows = [(*finger, 0.95, 1) for finger in FINGERS]
    result = classifier_for(rows).predict(None, confidence_threshold=0.50, banana_evidence=[])
    assert result.cultivar is None and result.ripeness is None
    assert result.finger_count == 0 and result.detections == []
    assert result.ood_rejected_boxes == 3


def summary(result):
    return (
        result.cultivar, result.ripeness, result.confidence, result.finger_count,
        result.conflict_detected, result.cultivar_conflict,
        [(d.x, d.y, d.w, d.h, d.cls, d.confidence) for d in result.detections],
    )


def on_banana(row, evidence, margin=0.25):
    return ood_gate.is_supported(box(*row[:4]), evidence, margin)


def assert_gate_equals_deleting_unsupported_boxes(rows, evidence, margin=0.25):
    """The gate's contract: the team's classifier, minus the boxes off the banana."""
    gated = classifier_for(rows).predict(
        None, confidence_threshold=0.50, banana_evidence=evidence, support_margin=margin,
    )
    kept = [row for row in rows if on_banana(row, evidence, margin)]
    assert summary(gated) == summary(classifier_for(kept).predict(None, confidence_threshold=0.50))
    return gated


def test_gate_result_equals_the_classifier_without_the_unsupported_boxes():
    # Tight evidence over the middle finger; a hand-sized box of another label.
    tight = [EvidenceBox(x=100, y=0, w=100, h=200, confidence=0.6)]
    fingers = [(60, 20, 100, 180), (130, 20, 170, 180), (200, 20, 240, 180)]
    mixed = [(*finger, 0.90, 0) for finger in fingers] + [(55, 15, 245, 185, 0.55, 1)]
    gated = assert_gate_equals_deleting_unsupported_boxes(mixed, tight, margin=0.0)
    assert gated.finger_count == 1 and gated.ood_rejected_boxes == 2

    # A rejected box must not change the cluster rule's size check for the others.
    evidence = [EvidenceBox(210, 88, 270, 190, 0.8)]
    rows = [
        (310, 130, 545, 319, 0.826, 0), (99, 74, 227, 337, 0.655, 0),
        (158, 166, 195, 394, 0.563, 0), (115, 92, 181, 267, 0.531, 1),
    ]
    without = assert_gate_equals_deleting_unsupported_boxes(rows, evidence)
    with_foreign = assert_gate_equals_deleting_unsupported_boxes(
        [*rows, (34, 142, 161, 432, 0.665, 0)], evidence,
    )
    assert summary(with_foreign) == summary(without)
    assert (without.ood_rejected_boxes, with_foreign.ood_rejected_boxes) == (0, 1)


def test_random_frames_obey_the_gate_contract():
    rng = np.random.default_rng(20261113)
    rejected = unchanged = 0
    for _ in range(300):
        rows = []
        for _ in range(int(rng.integers(1, 9))):
            x, y = float(rng.integers(0, 520)), float(rng.integers(0, 300))
            w, h = float(rng.integers(20, 240)), float(rng.integers(40, 300))
            rows.append((x, y, x + w, y + h, round(float(rng.uniform(0.5, 0.99)), 3),
                         int(rng.integers(0, 3))))
        # Nested same-label fragments at the ends of a box: the kind of repeat the
        # team's classifier drops by itself.
        for x1, y1, x2, y2, score, label in list(rows[:2]):
            if rng.random() < 0.5 and score > 0.55:
                rows.append((x1, y1, x2, y1 + (y2 - y1) * 0.2, round(score - 0.04, 3), label))
        evidence = [
            EvidenceBox(float(rng.integers(0, 400)), float(rng.integers(0, 250)),
                        float(rng.integers(40, 300)), float(rng.integers(40, 300)), 0.5)
            for _ in range(int(rng.integers(0, 3)))
        ]
        gated = assert_gate_equals_deleting_unsupported_boxes(rows, evidence)
        unsupported = sum(not on_banana(row, evidence) for row in rows)
        assert gated.ood_rejected_boxes <= unsupported
        if gated.ood_rejected_boxes == 0:
            # No counted intervention means no silent change: the scan is flagged
            # whenever the gate altered what the team's classifier would report.
            assert summary(gated) == summary(
                classifier_for(rows).predict(None, confidence_threshold=0.50)
            )
            unchanged += unsupported > 0
        rejected += gated.ood_rejected_boxes
    # The sample exercises both outcomes.
    assert rejected > 100 and unchanged > 0


def test_random_hands_obey_the_gate_contract():
    # A confident whole-hand box over a row of upright fingers, with mixed ripeness and
    # random evidence: the hand-box split and the ripeness rule must keep the contract.
    rng = np.random.default_rng(20261114)
    rejected = unchanged = splits = 0
    for _ in range(300):
        fingers = int(rng.integers(1, 6))
        x0, y0 = float(rng.integers(0, 200)), float(rng.integers(0, 100))
        width, gap = float(rng.integers(25, 50)), float(rng.integers(5, 40))
        rows = [(x0 - 5, y0 - 5, x0 + fingers * (width + gap), y0 + 170,
                 round(float(rng.uniform(0.9, 0.99)), 3), 0)]
        for index in range(fingers):
            x = x0 + index * (width + gap)
            label = 0 if rng.random() < 0.8 else int(rng.integers(1, 3))
            rows.append((x, y0, x + width, y0 + 160,
                         round(float(rng.uniform(0.5, 0.89)), 3), label))
        evidence = [
            EvidenceBox(float(rng.integers(0, 400)), float(rng.integers(0, 150)),
                        float(rng.integers(40, 300)), float(rng.integers(40, 250)), 0.5)
            for _ in range(int(rng.integers(0, 3)))
        ]
        gated = assert_gate_equals_deleting_unsupported_boxes(rows, evidence)
        ungated = classifier_for(rows).predict(None, confidence_threshold=0.50)
        splits += ungated.hand_box_splits
        if gated.ood_rejected_boxes == 0:
            assert summary(gated) == summary(ungated)
            unchanged += any(not on_banana(row, evidence) for row in rows)
        rejected += gated.ood_rejected_boxes
    assert splits > 50 and rejected > 50 and unchanged > 0


def test_real_banana_view_keeps_its_fingers_when_evidence_is_tight():
    # A confident same-class hand box with its fingers; evidence covers the middle
    # only. The team's classifier keeps the hand box; the gate must not empty the view.
    evidence = [EvidenceBox(x=126.67, y=0, w=46.67, h=200, confidence=0.3)]
    hand = (55, 15, 245, 185, 0.95, 0)
    fingers = [(60, 20, 100, 180, 0.90, 0), (130, 20, 170, 180, 0.88, 0),
               (200, 20, 240, 180, 0.86, 0)]
    legacy = classifier_for([hand, *fingers]).predict(None, confidence_threshold=0.50)
    gated = assert_gate_equals_deleting_unsupported_boxes([hand, *fingers], evidence)
    # Without the gate the hand box gives way to its three fingers. With it, the outer
    # fingers are off the evidence, so the hand box stays: that changes the count, so
    # it counts as two gate interventions and the scan is flagged.
    assert legacy.finger_count == 3 and gated.finger_count == 1
    assert gated.ood_rejected_boxes == 2


def test_hand_box_with_tight_evidence_matches_the_earlier_behaviour_when_split_is_off(
    monkeypatch,
):
    monkeypatch.setattr(classification, "settings", classification.settings.model_copy(
        update={"yolo_hand_box_split": False},
    ))
    evidence = [EvidenceBox(x=126.67, y=0, w=46.67, h=200, confidence=0.3)]
    hand = (55, 15, 245, 185, 0.95, 0)
    fingers = [(60, 20, 100, 180, 0.90, 0), (130, 20, 170, 180, 0.88, 0),
               (200, 20, 240, 180, 0.86, 0)]
    legacy = classifier_for([hand, *fingers]).predict(None, confidence_threshold=0.50)
    gated = assert_gate_equals_deleting_unsupported_boxes([hand, *fingers], evidence)
    assert legacy.finger_count == gated.finger_count == 1
    assert summary(gated) == summary(legacy)
    # The outer fingers only repeat the accepted hand box: no intervention, no flag.
    assert gated.ood_rejected_boxes == 0


def test_tight_evidence_keeps_one_finger_with_its_fragments():
    # One finger with nested fragments whose centres lie outside the evidence.
    evidence = [EvidenceBox(x=90, y=150, w=80, h=100, confidence=0.3)]
    rows = [(100, 50, 160, 350, 0.90, 0), (100, 50, 160, 120, 0.80, 0),
            (100, 280, 160, 350, 0.78, 0)]
    legacy = classifier_for(rows).predict(None, confidence_threshold=0.50)
    gated = assert_gate_equals_deleting_unsupported_boxes(rows, evidence)
    assert summary(gated) == summary(legacy) and gated.finger_count == 1
    assert gated.ood_rejected_boxes == 0


TOP_NAMES = {0: "lakatan_ripe", 1: "lakatan_unripe", 2: "cardaba_ripe"}
FRAME_W, FRAME_H = 640, 480


class TopPasses:
    """Calibrated Top view: fixed rows for the first, rotated and recovery passes.

    With `evidence` the fake deletes unsupported rows itself, which is the reference
    the gate must match. Rotated-frame rows are judged in original coordinates.
    """

    def __init__(self, passes, frame, evidence=None):
        self.passes, self.frame, self.evidence, self.calls = passes, frame, evidence, 0

    def predict(self, image, **_kwargs):
        rows = self.passes[min(self.calls, len(self.passes) - 1)]
        self.calls += 1
        if self.evidence is not None:
            flipped = image is not self.frame

            def original(row):
                x1, y1, x2, y2 = row[:4]
                if not flipped:
                    return row[:4]
                return (FRAME_W - x2, FRAME_H - y2, FRAME_W - x1, FRAME_H - y1)

            rows = [row for row in rows if on_banana(original(row), self.evidence)]
        boxes = [
            SimpleNamespace(xyxy=np.array([row[:4]], dtype=float), conf=[row[4]], cls=[row[5]])
            for row in rows
        ]
        return [SimpleNamespace(boxes=boxes, names=TOP_NAMES)]


def run_top(passes, evidence, mode):
    """mode: 'gated', 'deleted' (reference) or 'ungated'."""
    frame = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    classifier = BananaClassifier()
    classifier._model = TopPasses(passes, frame, evidence if mode == "deleted" else None)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    gate = {"banana_evidence": evidence} if mode == "gated" else {}
    return classifier.predict(frame, confidence_threshold=0.50, camera_label="Top", **gate)


@pytest.fixture
def top_settings(monkeypatch):
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
        yolo_top_rotation_fallback=True,
    ))


def boxes(*xywh):
    return [EvidenceBox(x, y, w, h, 0.5) for x, y, w, h in xywh]


@pytest.mark.parametrize(("first", "rotated", "evidence"), [
    # Unsupported repeats of a kept finger decided which orientation is canonical.
    ([(300, 100, 400, 400, 0.95, 2), (0, 90, 100, 390, 0.55, 0)],
     [(540, 290, 640, 390, 0.97, 0), (540, 190, 640, 290, 0.90, 0),
      (540, 90, 640, 190, 0.90, 0)],
     boxes((340, 230, 20, 40), (40, 220, 20, 40))),
    # An unsupported rotated box was the only report of a label conflict.
    ([(0, 0, 100, 100, 0.90, 0), (100, 0, 200, 100, 0.55, 1)],
     [(470, 380, 610, 480, 0.80, 0)],
     boxes((30, 30, 40, 40), (130, 30, 40, 40))),
    # An unsupported rotated box swallowed a nested fragment before being dropped.
    ([(0, 0, 100, 140, 0.90, 0)],
     [(540, 180, 640, 480, 0.85, 0), (540, 180, 640, 280, 0.80, 0)],
     boxes((0, 40, 100, 60), (0, 220, 100, 60))),
])
def test_rotated_pass_removal_that_changes_the_result_is_always_counted(
    top_settings, first, rotated, evidence,
):
    passes = [first, rotated, []]
    gated = run_top(passes, evidence, "gated")
    assert summary(gated) == summary(run_top(passes, evidence, "deleted"))
    # The gate altered what the classifier would report, so the scan must be flagged.
    assert summary(gated) != summary(run_top(passes, evidence, "ungated"))
    assert gated.ood_rejected_boxes > 0


def test_random_top_views_obey_the_gate_contract(top_settings):
    rng = np.random.default_rng(20261113)

    def finger():
        x, y = float(rng.integers(0, 540)), float(rng.integers(0, 180))
        return (x, y, x + float(rng.integers(40, 100)), y + float(rng.integers(120, 300)))

    def rotate(row):
        x1, y1, x2, y2 = row[:4]
        return (FRAME_W - x2, FRAME_H - y2, FRAME_W - x1, FRAME_H - y1, *row[4:])

    counted = unchanged = altered = 0
    for _ in range(400):
        first = [(*finger(), round(float(rng.uniform(0.5, 0.97)), 3), int(rng.integers(0, 3)))
                 for _ in range(int(rng.integers(1, 7)))]
        # The rotated pass repeats some fingers (shifted or relabeled) and adds new ones.
        rotated = []
        for x1, y1, x2, y2, _score, label in first:
            if rng.random() < 0.6:
                dx = float(rng.integers(-12, 13))
                relabel = int(rng.integers(0, 3)) if rng.random() < 0.3 else label
                rotated.append(rotate((x1 + dx, y1, x2 + dx, y2,
                                       round(float(rng.uniform(0.5, 0.99)), 3), relabel)))
        rotated += [rotate((*finger(), round(float(rng.uniform(0.5, 0.99)), 3),
                            int(rng.integers(0, 3)))) for _ in range(int(rng.integers(0, 4)))]
        evidence = [
            EvidenceBox(float(rng.integers(0, 500)), float(rng.integers(0, 300)),
                        float(rng.integers(30, 320)), float(rng.integers(30, 320)), 0.5)
            for _ in range(int(rng.integers(1, 4)))
        ]
        passes = [first, rotated, first]
        gated = run_top(passes, evidence, "gated")
        # The result is the classifier's own result for the boxes on banana evidence.
        assert summary(gated) == summary(run_top(passes, evidence, "deleted"))
        same = summary(gated) == summary(run_top(passes, evidence, "ungated"))
        if gated.ood_rejected_boxes == 0:
            # Nothing counted means nothing changed: no silent alteration.
            assert same
            unchanged += 1
        else:
            counted += 1
            altered += not same
    assert counted > 100 and unchanged > 10 and altered > 50


def test_shifted_redetection_in_the_rotated_pass_is_counted_but_changes_nothing(top_settings):
    # Grown evidence ends at x = 475. The edge finger (centre 470) is accepted; the
    # rotated pass returns it 8 px to the right (centre 478), outside the evidence.
    evidence = [EvidenceBox(x=100, y=80, w=300, h=320, confidence=0.8)]
    fingers = [(110 + 55 * index, 100, 150 + 55 * index, 380, 0.90, 0) for index in range(5)]
    edge = (440, 100, 500, 380, 0.90, 0)
    rotated_shifted = (640 - 508, 480 - 380, 640 - 448, 480 - 100, 0.88, 0)
    passes = [[*fingers, edge], [rotated_shifted], [*fingers, edge]]
    gated, ungated = run_top(passes, evidence, "gated"), run_top(passes, evidence, "ungated")
    assert summary(gated) == summary(ungated) and gated.finger_count == 6
    # A rotated repeat can steer the orientation and conflict logic, so it is always
    # counted: flagging a scan for nothing is the safe direction.
    assert gated.ood_rejected_boxes == 1


def test_box_without_banana_evidence_cannot_suppress_fingers_on_the_banana():
    # A more confident same-class box spans far beyond the banana; its centre has no
    # evidence. Before the fix it swallowed the fingers as nested fragments and was
    # then dropped itself, leaving a real banana view empty.
    container = (0, 0, 640, 200)
    rows = [(*container, 0.92, 0)] + [
        (*finger, score, 0) for finger, score in zip(FINGERS, (0.80, 0.78, 0.75), strict=True)
    ]
    legacy = classifier_for(rows).predict(None, confidence_threshold=0.50)
    # Without the gate the container gives way to the fingers it hid (hand-box split).
    assert [(d.x, d.w) for d in legacy.detections] == [(10, 40), (70, 40), (130, 40)]

    gated = classifier_for(rows).predict(
        None, confidence_threshold=0.50, banana_evidence=EVIDENCE,
    )
    assert [(d.x, d.y, d.w, d.h) for d in gated.detections] == [
        (10, 20, 40, 160), (70, 20, 40, 160), (130, 20, 40, 160),
    ]
    assert (gated.cultivar, gated.ripeness, gated.finger_count) == ("Lakatan", "Ripe", 3)
    assert gated.ood_rejected_boxes == 1 and gated.confidence == 77.7


def test_vote_of_a_foreign_box_is_withdrawn_even_when_the_cluster_rule_removed_it():
    # Two narrow banana regions; a confident box of another cultivar covers both
    # fingers, so the cluster rule removes it before the gate looks at it.
    evidence = [EvidenceBox(0, 0, 60, 200, 0.7), EvidenceBox(540, 0, 60, 200, 0.7)]
    fingers = [(10, 20, 50, 180), (550, 20, 590, 180)]
    rows = [(0, 10, 600, 190, 0.97, 2)] + [(*finger, 0.55, 0) for finger in fingers]
    legacy = classifier_for(rows).predict(None, confidence_threshold=0.50)
    assert legacy.finger_count == 2 and legacy.cultivar_conflict is True

    gated = classifier_for(rows).predict(
        None, confidence_threshold=0.50, banana_evidence=evidence,
    )
    assert (gated.cultivar, gated.ripeness, gated.finger_count) == ("Lakatan", "Ripe", 2)
    assert gated.cultivar_conflict is False and gated.conflict_detected is False
    # The removed box still counts as a gate intervention, so the scan is flagged.
    assert gated.ood_rejected_boxes == 1


def test_rotated_pass_keeps_a_finger_that_overlaps_a_box_without_banana_evidence(monkeypatch):
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
        yolo_top_rotation_fallback=True,
    ))
    evidence = [EvidenceBox(x=400, y=100, w=100, h=200, confidence=0.8)]
    # Pass 1 box: centre x = 535, outside the grown evidence (375..525).
    off_banana = (430, 110, 640, 300, 0.90, 0)
    # Rotated coordinates of a finger at (420, 120)-(480, 280) in a 640 x 480 frame.
    rotated_finger = (160, 200, 220, 360, 0.85, 0)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def run(**gate):
        classifier = BananaClassifier()
        classifier._model = SequencePredictor([[off_banana], [rotated_finger]], names=NAMES)
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        return classifier.predict(frame, confidence_threshold=0.50, camera_label="Top", **gate)

    # Without the gate the rotated finger is a duplicate of the larger box.
    assert [(d.x, d.w) for d in run().detections] == [(430, 210)]
    gated = run(banana_evidence=evidence)
    assert [(d.x, d.y, d.w, d.h) for d in gated.detections] == [(420, 120, 60, 160)]
    assert (gated.cultivar, gated.finger_count, gated.ood_rejected_boxes) == ("Lakatan", 1, 1)


@pytest.mark.parametrize("within_hand", [False, True])
def test_occluded_finger_recovery_pass_admits_only_boxes_on_banana_evidence(
    monkeypatch, within_hand,
):
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
        yolo_top_rotation_fallback=True, yolo_recovery_within_hand=within_hand,
    ))
    fingers = [(40 + 70 * index, 100, 90 + 70 * index, 380, 0.90, 0) for index in range(5)]
    recovered = (390, 100, 440, 380, 0.35, 0)
    # Same label, lower confidence, on an object beside the hand.
    foreign = (560, 100, 610, 380, 0.40, 0)
    evidence = [EvidenceBox(x=20, y=80, w=430, h=320, confidence=0.8)]
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def run(**gate):
        classifier = BananaClassifier()
        # Call 1 is the normal pass; call 2 is the low-confidence recovery pass.
        classifier._model = SequencePredictor(
            [fingers, [*fingers, recovered, foreign]], names=NAMES,
        )
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        result = classifier.predict(
            frame, confidence_threshold=0.50, camera_label="Front", **gate,
        )
        assert classifier._model.call_count == 2
        return result

    legacy = run()
    gated = run(banana_evidence=evidence)
    assert sorted(d.x for d in gated.detections) == [40, 110, 180, 250, 320, 390]
    assert (gated.cultivar, gated.ripeness) == ("Lakatan", "Ripe")
    if within_hand:
        # The object lies more than one finger beyond the hand, so the recovery pass
        # never admits it; the gate has nothing left to remove.
        assert legacy.finger_count == gated.finger_count == 6
        assert gated.ood_rejected_boxes == 0
    else:
        assert legacy.finger_count == 7 and 560 in [d.x for d in legacy.detections]
        assert gated.finger_count == 6 and gated.ood_rejected_boxes == 1


def test_gate_changes_nothing_when_every_box_is_on_banana_evidence(monkeypatch):
    # The inverted-hand case: the rotated Top pass becomes the canonical result.
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
        yolo_top_rotation_fallback=True,
    ))
    names = {0: "lakatan_unripe", 1: "cardaba_unripe"}
    passes = [
        [(100, 100, 180, 380, 0.91, 0), (220, 100, 300, 380, 0.90, 0),
         (340, 100, 420, 380, 0.89, 0)],
        [(460, 100, 540, 380, 0.95, 1), (340, 100, 420, 380, 0.94, 1),
         (220, 100, 300, 380, 0.94, 1)],
    ]
    whole_frame = [EvidenceBox(x=0, y=0, w=640, h=480, confidence=0.9)]

    def run(**gate):
        classifier = BananaClassifier()
        classifier._model = SequencePredictor(passes, names=names)
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        result = classifier.predict(
            np.zeros((480, 640, 3), dtype=np.uint8),
            confidence_threshold=0.50, camera_label="Top", **gate,
        )
        return (
            result.cultivar, result.ripeness, result.confidence, result.finger_count,
            result.conflict_detected, result.cultivar_conflict,
            [(d.x, d.y, d.w, d.h, d.cls, d.confidence) for d in result.detections],
        )

    legacy = run()
    assert legacy[0] == "Cardaba" and legacy[3] == 3
    assert run(banana_evidence=whole_frame) == legacy


def test_rotated_pass_disagreement_on_a_foreign_object_is_not_a_banana_conflict(monkeypatch):
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
        yolo_top_rotation_fallback=True,
    ))
    names = {0: "lakatan_ripe", 1: "lakatan_semi_ripe"}
    finger, foreign = (50, 50, 150, 200, 0.90, 0), (500, 300, 560, 440, 0.80, 1)
    # Rotated 640 x 480 coordinates that map back onto the foreign box, relabeled.
    relabeled = (80, 40, 140, 180, 0.70, 0)
    evidence = [EvidenceBox(x=0, y=0, w=300, h=480, confidence=0.8)]
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def run(**gate):
        classifier = BananaClassifier()
        classifier._model = SequencePredictor([[finger, foreign], [relabeled]], names=names)
        classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
        return classifier.predict(frame, confidence_threshold=0.50, camera_label="Top", **gate)

    legacy = run()
    assert legacy.finger_count == 2 and legacy.conflict_detected is True
    assert legacy.cultivar_conflict is False  # only ripeness differs between rotations
    gated = run(banana_evidence=evidence)
    assert (gated.cultivar, gated.ripeness, gated.finger_count) == ("Lakatan", "Ripe", 1)
    assert gated.cultivar_conflict is False and gated.conflict_detected is False
    assert gated.ood_rejected_boxes == 1


# ── Banana pre-detector evidence ─────────────────────────────────────────────

class BananaModel:
    def __init__(self, scores, fail=False):
        self.scores, self.fail, self.calls = scores, fail, []

    def predict(self, _image, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("inference failed")
        boxes = [
            SimpleNamespace(xyxy=np.array([[10 * i, 5, 10 * i + 8, 45]], dtype=float),
                            conf=[score], cls=[BANANA_CLASS_ID])
            for i, score in enumerate(self.scores) if score >= kwargs["conf"]
        ]
        return [SimpleNamespace(boxes=boxes)]


def detector_with(model):
    detector = BananaPreDetector()
    detector._model = model
    return detector


def test_pre_detector_separates_acceptance_from_weaker_supporting_evidence():
    model = BananaModel([0.72, 0.29, 0.06, 0.04])
    result = detector_with(model).detect(None)
    assert model.calls[0]["conf"] == 0.05 and model.calls[0]["classes"] == [BANANA_CLASS_ID]
    assert result.available is True and result.banana_detected is True
    assert result.banana_count == 1 and result.best_confidence == 0.72
    assert [box.confidence for box in result.boxes] == [0.72, 0.29, 0.06]
    assert (result.boxes[1].x, result.boxes[1].y, result.boxes[1].w, result.boxes[1].h) == (
        10, 5, 8, 40,
    )
    # Weak evidence alone supports boxes but never accepts the frame.
    weak = detector_with(BananaModel([0.29, 0.06])).detect(None)
    assert weak.banana_detected is False and len(weak.boxes) == 2
    strict = detector_with(BananaModel([0.72, 0.29])).detect(
        None, accept_confidence=0.80, support_confidence=0.50,
    )
    assert strict.banana_detected is False and [b.confidence for b in strict.boxes] == [0.72]


def test_pre_detector_reports_when_it_cannot_run():
    for detector in (BananaPreDetector(), detector_with(BananaModel([], fail=True))):
        result = detector.detect(None)
        assert result.available is False and result.boxes is None


# ── Scan pipeline and API contract ───────────────────────────────────────────

def gate_result(*, banana=True, boxes=EVIDENCE, available=True):
    return SimpleNamespace(
        banana_detected=banana, available=available, boxes=boxes,
        best_confidence=max((b.confidence for b in boxes or []), default=0.0),
    )


@pytest.fixture
def station(scan_station, monkeypatch):  # noqa: F811
    """Real classifier and fusion on fixture frames; the gate result is set per test."""
    app, _ = scan_station
    state = SimpleNamespace(
        app=app, events=[], model=BoxModel([(*finger, 0.90, 0) for finger in FINGERS]),
        gate=lambda _frame: gate_result(), settings={},
    )
    classifier = BananaClassifier()
    classifier._model = state.model
    monkeypatch.setattr(scan_service, "banana_classifier", classifier)
    monkeypatch.setattr(scan_service, "fusion_engine", FusionEngine())
    monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
        detect=lambda frame: state.gate(frame),
    ))
    monkeypatch.setattr(
        scan_service, "get_settings", lambda: Settings(_env_file=None, **state.settings),
    )

    async def record(_room, event, data, **_kwargs):
        state.events.append((event, data))

    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", record)
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator",
        role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    state.trigger = lambda: app.client.post("/api/v1/scans/trigger", json={})
    state.scan_count = lambda: _scan_count(app)
    return state


def _scan_count(app):
    with Session(app.engine) as db:
        return db.scalar(select(func.count()).select_from(Scan))


def failures(state):
    return [data for event, data in state.events if event == "scan:failed"]


def rejections(app):
    with Session(app.engine) as db:
        return list(db.scalars(
            select(ActivityLog.details).where(ActivityLog.action == "scan_rejected")
        ))


def test_supported_banana_scan_is_saved_without_a_review_flag(station):
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["cultivar"], data["ripeness"], data["finger_count"]) == ("Lakatan", "Ripe", 3)
    assert data["flagged"] is False
    assert station.model.calls == 4 and failures(station) == []
    assert station.scan_count() == 2 and rejections(station.app) == []


def test_scan_without_banana_evidence_is_rejected_before_classification(station):
    station.gate = lambda _frame: gate_result(banana=False, boxes=[])
    response = station.trigger()
    assert response.status_code == 422, response.text
    expected = {
        "code": "ood_rejected", "status": "rejected", "is_ood": True, "reason": "no_banana",
    }
    assert response.json() == {"detail": ood_gate.REJECTION_MESSAGE, **expected}
    assert "No Lakatan, Latundan, or Cardaba detected" in response.json()["detail"]
    # The closed-set model never saw the frames and nothing was stored.
    assert station.model.calls == 0 and station.scan_count() == 1
    [failure] = failures(station)
    assert failure["error"] == ood_gate.REJECTION_MESSAGE and failure["stage"] == "pipeline"
    assert {key: failure[key] for key in expected} == expected
    assert not [event for event, _ in station.events if event == "scan:completed"]
    # The rejection leaves an audit row with the per-view banana scores.
    [audit] = rejections(station.app)
    assert audit.startswith("Scan rejected (no_banana): banana evidence in 0 of 4 views")
    assert "Top 0.00" in audit and "Rear 0.00" in audit


def test_cultivar_boxes_outside_banana_evidence_reject_the_scan(station):
    # The gate saw a banana-like region, but every cultivar box lies elsewhere.
    station.model.rows = [(*FOREIGN, 0.97, 2)]
    response = station.trigger()
    assert response.status_code == 422, response.text
    assert response.json()["reason"] == "no_target_cultivar"
    assert response.json()["is_ood"] is True
    assert station.scan_count() == 1
    assert failures(station)[0]["reason"] == "no_target_cultivar"
    [audit] = rejections(station.app)
    assert "4 cultivar boxes had no banana evidence" in audit and "Top 0.80" in audit


def test_foreign_object_beside_the_banana_is_dropped_and_the_scan_flagged(station):
    station.model.rows = [(*finger, 0.90, 0) for finger in FINGERS] + [(*FOREIGN, 0.99, 2)]
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    # Without the gate this scan reports four fingers in every view.
    assert (data["cultivar"], data["ripeness"], data["finger_count"]) == ("Lakatan", "Ripe", 3)
    assert data["confidence"] == 90
    # The gate changed the result, so a person confirms it.
    assert data["flagged"] is True
    with Session(station.app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert saved.flagged is True and len(saved.detections) == 4
        assert all(
            [box["cls"] for box in detection.bounding_boxes] == ["lakatan_ripe"] * 3
            for detection in saved.detections
        )
    [completed] = [d for event, d in station.events if event == "scan:completed"][:1]
    assert completed["flagged"] is True
    # A reviewer can see why the scan was flagged.
    with Session(station.app.engine) as db:
        created = db.scalar(select(ActivityLog.details).where(
            ActivityLog.action == "scan_created",
        ))
    assert created.endswith("4 boxes without banana evidence dropped, flagged for review")


def test_top_view_without_banana_evidence_cannot_pass_unreviewed(station):
    # Top is the cultivar anchor; losing it must not go unnoticed.
    frames = iter([gate_result(banana=False, boxes=[])] + [gate_result()] * 3)
    station.gate = lambda _frame: next(frames)
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["cultivar"], data["finger_count"]) == ("Lakatan", 3)
    # Every view still reached the cultivar model; Top's boxes were dropped.
    assert station.model.calls == 4
    assert data["flagged"] is True


def test_minimum_banana_views_setting_is_enforced(station):
    station.settings = {"ood_min_banana_views": 2}
    frames = iter([gate_result()] + [gate_result(banana=False, boxes=[])] * 3)
    station.gate = lambda _frame: next(frames)
    response = station.trigger()
    assert response.status_code == 422 and response.json()["reason"] == "no_banana"
    assert station.model.calls == 0
    assert "1 of 4 views (2 required)" in rejections(station.app)[0]


def test_unavailable_verifier_fails_closed_unless_configured_open(station):
    station.gate = lambda _frame: gate_result(available=False, boxes=None)
    response = station.trigger()
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "ood_gate_unavailable" and body["is_ood"] is False
    assert body["status"] == "unavailable" and body["detail"] == ood_gate.GATE_UNAVAILABLE_MESSAGE
    assert station.model.calls == 0 and station.scan_count() == 1
    assert failures(station)[0]["code"] == "ood_gate_unavailable"
    # A fault is not an out-of-distribution rejection.
    assert rejections(station.app) == []

    station.settings = {"ood_gate_fail_open": True}
    assert station.trigger().status_code == 200
    assert station.scan_count() == 2


def test_scan_without_any_camera_frame_is_a_fault_not_an_ood_rejection(station, monkeypatch):
    async def no_frames():
        return []

    monkeypatch.setattr(scan_service.camera_manager, "capture_all", no_frames)
    response = station.trigger()
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "capture_unavailable" and body["is_ood"] is False
    assert body["status"] == "unavailable" and "No camera frame" in body["detail"]
    assert "Lakatan" not in body["detail"]
    assert station.model.calls == 0 and station.scan_count() == 1
    assert rejections(station.app) == []
    assert failures(station)[0]["code"] == "capture_unavailable"


def test_box_filter_can_be_disabled(station):
    station.settings = {"ood_box_support_filter": False}
    station.model.rows = [(*FOREIGN, 0.97, 2)]
    response = station.trigger()
    assert response.status_code == 200, response.text
    assert response.json()["cultivar"] == "Cardaba"
