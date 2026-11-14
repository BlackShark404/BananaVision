"""Boxes over the crown or dark background are not fingers (colour check).

Colours are the HSV profiles measured on the 16 station screenshots of 2026-11-14 after
removing the overlay tint (docs/knowledge/AI Models.md): finger peel hue 28-80 and bright,
the cut crown bluish-grey (hue ~115, saturation ~55, value ~118), the curtain dark
(value ~30). OpenCV units: hue 0-179, saturation and value 0-255.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import cv2
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ActivityLog, Scan
from app.services import classification, scan_service
from app.services.classification import BananaClassifier, _non_banana_fraction
from app.services.ood_gate import EvidenceBox
from tests.test_ood_gate import (
    BoxModel,
    gate_result,
    rejections,
    station,  # noqa: F401, F811 - fixture
)
from tests.test_scan_trigger import scan_station  # noqa: F401 - fixture dependency
from tests.test_time_and_writes import application  # noqa: F401 - fixture dependency
from tests.test_top_view_inference import VERIFIED_CHECKPOINT, SequencePredictor

COLOUR_CHECK = True  # conftest.py turns the check off for placeholder-frame tests
H, W = 480, 900
GREEN, PALE, CYANISH, YELLOW = (60, 80, 190), (45, 50, 160), (90, 60, 170), (28, 90, 200)
DIM_GREEN, BROWN_DARK = (55, 90, 85), (12, 120, 30)
# Shaded fingers under the hand (screenshot 9, all overlay fills removed).
SHADED, SHADED_DEEP = (88, 62, 45), (60, 80, 50)
CROWN, CURTAIN = (115, 55, 118), (100, 70, 30)
NAMES = {0: "lakatan_unripe", 1: "cardaba_overripe"}


def paint(frame, box, hsv, noise=6, seed=0):
    """Fill a box with one HSV colour plus a little noise, like a camera patch."""
    x1, y1, x2, y2 = box
    rng = np.random.default_rng(seed)
    patch = np.empty((y2 - y1, x2 - x1, 3), np.int16)
    patch[...] = hsv
    patch += rng.integers(-noise, noise + 1, patch.shape)
    patch[..., 0] = np.clip(patch[..., 0], 0, 179)
    patch = np.clip(patch, 0, 255).astype(np.uint8)
    frame[y1:y2, x1:x2] = cv2.cvtColor(patch, cv2.COLOR_HSV2BGR)
    return frame


def table():
    # Pink-brown table background, as in the Top screenshots.
    return paint(np.zeros((H, W, 3), np.uint8), (0, 0, W, H), (5, 40, 200))


@pytest.fixture
def rules(monkeypatch):
    def set_rules(**flags):
        monkeypatch.setattr(classification, "settings",
                            classification.settings.model_copy(update=flags))
    return set_rules


def predict(frame, rows, label="Left", names=NAMES):
    classifier = BananaClassifier()
    classifier._model = BoxModel(rows, names)
    return classifier.predict(frame, confidence_threshold=0.50, camera_label=label)


FINGERS = [(100, 60, 180, 400), (200, 60, 280, 400), (300, 60, 380, 400)]
CROWN_BOX, CURTAIN_BOX = (480, 260, 640, 420), (700, 40, 860, 230)


def station_like_frame():
    frame = table()
    for index, box in enumerate(FINGERS):
        paint(frame, box, (GREEN, PALE, YELLOW)[index], seed=index)
    paint(frame, CROWN_BOX, CROWN, seed=7)
    return paint(frame, CURTAIN_BOX, CURTAIN, seed=8)


def test_crown_and_dark_background_boxes_are_dropped(rules):
    rows = [(*box, 0.9, 0) for box in FINGERS] + [(*CROWN_BOX, 0.76, 0),
                                                   (*CURTAIN_BOX, 0.61, 0)]
    result = predict(station_like_frame(), rows, label="Top")
    assert result.finger_count == 3 and result.colour_rejected_boxes == 2
    assert [d.x for d in result.detections] == [100, 200, 300]
    rules(yolo_colour_check=False)
    legacy = predict(station_like_frame(), rows, label="Top")
    assert legacy.finger_count == 5 and legacy.colour_rejected_boxes == 0


@pytest.mark.parametrize("colour", [GREEN, PALE, CYANISH, YELLOW, DIM_GREEN, SHADED,
                                    SHADED_DEEP])
def test_real_peel_colours_are_kept(colour):
    frame = paint(table(), FINGERS[0], colour)
    assert _non_banana_fraction(frame, *FINGERS[0]) < 0.2
    assert predict(frame, [(*FINGERS[0], 0.9, 0)]).finger_count == 1


def test_spotted_finger_and_dark_corners_are_kept():
    # A pale Cardaba finger with dark spots, boxed diagonally so the corners show curtain.
    frame = paint(table(), (90, 40, 400, 420), CURTAIN)
    paint(frame, (150, 110, 340, 350), PALE)
    for spot in [(170, 130, 200, 160), (260, 250, 300, 290), (300, 150, 330, 175)]:
        paint(frame, spot, (15, 150, 25), noise=2)
    result = predict(frame, [(90, 40, 400, 420, 0.9, 0)])
    assert result.finger_count == 1 and result.colour_rejected_boxes == 0


def test_overripe_boxes_are_not_judged_by_colour():
    # Overripe peel really is dark brown.
    frame = paint(table(), FINGERS[0], BROWN_DARK)
    assert _non_banana_fraction(frame, *FINGERS[0]) > 0.9
    assert predict(frame, [(*FINGERS[0], 0.9, 1)]).finger_count == 1


def test_no_frame_means_no_colour_check():
    result = predict(None, [(*CROWN_BOX, 0.76, 0)])
    assert result.finger_count == 1 and result.colour_rejected_boxes == 0


def test_threshold_setting_is_respected(rules):
    # A finger whose centre is about a third dark spots: kept by default (0.55).
    frame = paint(table(), FINGERS[0], PALE)
    paint(frame, (116, 128, 164, 230), (15, 150, 25), noise=2)
    fraction = _non_banana_fraction(frame, *FINGERS[0])
    assert 0.25 < fraction < 0.55
    assert predict(frame, [(*FINGERS[0], 0.9, 0)]).finger_count == 1
    rules(yolo_colour_check_max_non_banana=0.2)
    assert predict(frame, [(*FINGERS[0], 0.9, 0)]).finger_count == 0


def test_second_pass_does_not_add_the_crown():
    frame = table()
    hand = [(60 + 120 * i, 40, 160 + 120 * i, 440, 0.9 - 0.01 * i, 0) for i in range(5)]
    for index, row in enumerate(hand):
        paint(frame, row[:4], GREEN, seed=index)
    crown = (300, 300, 420, 420)
    paint(frame, crown, CROWN, seed=9)
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([hand, [], hand + [(*crown, 0.35, 0)]], NAMES)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(frame, confidence_threshold=0.50, camera_label="Top")
    assert result.finger_count == 5 and result.colour_rejected_boxes == 1


def test_rotated_pass_does_not_add_dark_background():
    frame = table()
    paint(frame, (100, 60, 200, 400), GREEN)
    paint(frame, CURTAIN_BOX, CURTAIN, seed=3)
    x1, y1, x2, y2 = CURTAIN_BOX  # given to the model in rotated coordinates
    rotated = [(W - x2, H - y2, W - x1, H - y1, 0.7, 0)]
    classifier = BananaClassifier()
    classifier._model = SequencePredictor([[(100, 60, 200, 400, 0.9, 0)], rotated], NAMES)
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    result = classifier.predict(frame, confidence_threshold=0.50, camera_label="Top")
    assert result.finger_count == 1 and result.colour_rejected_boxes == 1


def test_station_flags_a_scan_with_a_crown_box(station):  # noqa: F811
    frame = np.zeros((200, 400, 3), np.uint8)
    paint(frame, (0, 0, 400, 200), (5, 40, 200))
    fingers = [(10, 20, 50, 180), (70, 20, 110, 180), (130, 20, 170, 180)]
    for index, box in enumerate(fingers):
        paint(frame, box, GREEN, seed=index)
    crown = (260, 60, 340, 160)
    paint(frame, crown, CROWN, seed=5)
    captures = [SimpleNamespace(camera_id=f"CAM-{i + 1:03}", camera_label=label,
                                frame=frame.copy(), file_path=None)
                for i, label in enumerate(["Top", "Left", "Right", "Rear"])]

    async def capture_all():
        return captures

    scan_service.camera_manager.capture_all = capture_all
    station.gate = lambda _frame: gate_result(boxes=[EvidenceBox(0, 0, 400, 200, 0.8)])
    station.model.rows = [(*f, 0.90, 0) for f in fingers] + [(*crown, 0.76, 0)]
    response = station.trigger()
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["finger_count"] == 3 and data["flagged"] is True
    with Session(station.app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert all(len(d.bounding_boxes) == 3 for d in saved.detections)
        created = db.scalar(select(ActivityLog.details).where(
            ActivityLog.action == "scan_created",
        ))
    assert created.endswith(
        "4 boxes over non-banana colours (crown or dark background) dropped, "
        "flagged for review"
    )


PROFILES = json.loads(
    (Path(__file__).parent / "data" / "station_colour_profiles_2026-11-14.json").read_text()
)


@pytest.mark.parametrize("profile", PROFILES["finger_examples"], ids=lambda p: p["what"])
def test_measured_station_finger_colours_are_kept(profile):
    frame = paint(table(), FINGERS[0], (profile["hue"], profile["saturation"], profile["value"]))
    assert _non_banana_fraction(frame, *FINGERS[0]) < PROFILES["threshold"]["value"]
    assert predict(frame, [(*FINGERS[0], 0.9, 0)]).finger_count == 1


@pytest.mark.parametrize("profile", PROFILES["non_finger_boxes"], ids=lambda p: p["what"])
def test_measured_station_crown_and_curtain_colours_are_dropped(profile):
    frame = paint(table(), CROWN_BOX, (profile["hue"], profile["saturation"], profile["value"]))
    result = predict(frame, [(*CROWN_BOX, 0.7, 0)])
    assert result.finger_count == 0 and result.colour_rejected_boxes == 1


def test_measured_threshold_separates_the_station_boxes():
    threshold = PROFILES["threshold"]["value"]
    assert threshold == classification.settings.yolo_colour_check_max_non_banana
    assert PROFILES["finger_boxes_non_banana"]["highest_real_box"] < threshold
    assert all(box["non_banana"] > threshold for box in PROFILES["non_finger_boxes"])


def test_settings_default_on_and_read_the_environment(monkeypatch):
    settings = Settings(_env_file=None)
    assert settings.yolo_colour_check is True
    assert settings.yolo_colour_check_max_non_banana == 0.55
    monkeypatch.setenv("YOLO_COLOUR_CHECK", "false")
    assert Settings(_env_file=None).yolo_colour_check is False


def test_dark_fragment_of_a_kept_finger_is_skipped_without_flagging():
    # A small same-label box on a dark spot inside a kept finger: pass 1 drops it as a
    # fragment anyway, so the colour check must not count it (no review flag).
    frame = paint(table(), (100, 40, 180, 440), GREEN)
    paint(frame, (104, 60, 176, 140), CURTAIN, seed=4)
    rows = [(100, 40, 180, 440, 0.9, 0), (104, 60, 176, 140, 0.8, 0)]
    result = predict(frame, rows)
    assert result.finger_count == 1 and result.colour_rejected_boxes == 0


def test_station_rejection_note_counts_colour_drops(station):  # noqa: F811
    # Every box is a crown: nothing is left, the scan is rejected and the audit says why.
    frame = paint(np.zeros((200, 400, 3), np.uint8), (0, 0, 400, 200), (5, 40, 200))
    crown = (260, 60, 340, 160)
    paint(frame, crown, CROWN, seed=5)
    captures = [SimpleNamespace(camera_id=f"CAM-{i + 1:03}", camera_label=label,
                                frame=frame.copy(), file_path=None)
                for i, label in enumerate(["Top", "Left", "Right", "Rear"])]

    async def capture_all():
        return captures

    scan_service.camera_manager.capture_all = capture_all
    station.gate = lambda _frame: gate_result(boxes=[EvidenceBox(0, 0, 400, 200, 0.8)])
    station.model.rows = [(*crown, 0.76, 0)]
    response = station.trigger()
    assert response.status_code == 422, response.text
    [note] = rejections(station.app)
    assert "4 boxes over non-banana colours dropped" in note
