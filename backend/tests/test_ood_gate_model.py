"""The real COCO banana verifier rejects frames that show no banana.

Uses the tracked backend/yolo26n.pt only; skipped where the model or its runtime is
absent. No camera, capture or station data.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.services.banana_detector import BANANA_CLASS_ID, BananaPreDetector
from app.services.ood_gate import GatePolicy

WEIGHTS = Path(__file__).resolve().parents[1] / "yolo26n.pt"
HEIGHT, WIDTH = 480, 640


@pytest.fixture(scope="module")
def detector():
    pytest.importorskip("ultralytics")
    if not WEIGHTS.is_file():
        pytest.skip("backend/yolo26n.pt is not available")
    verifier = BananaPreDetector()
    # Absolute path: tests run from a temporary directory and must not download.
    verifier._COCO_MODEL = str(WEIGHTS)
    verifier.load()
    if not verifier.is_loaded:
        pytest.skip("The COCO verifier could not be loaded in this environment")
    return verifier


def solid(blue, green, red):
    return np.full((HEIGHT, WIDTH, 3), (blue, green, red), dtype=np.uint8)


def frames():
    import cv2

    noise = np.random.default_rng(7).integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    lemon = solid(200, 200, 200)
    cv2.ellipse(lemon, (320, 240), (120, 90), 0, 0, 360, (0, 225, 255), -1)
    cucumber = solid(200, 200, 200)
    cv2.ellipse(cucumber, (320, 240), (230, 45), 0, 0, 360, (60, 150, 50), -1)
    box = solid(90, 90, 90)
    cv2.rectangle(box, (200, 150), (440, 330), (0, 215, 255), -1)
    orange = solid(200, 200, 200)
    cv2.circle(orange, (320, 240), 110, (0, 160, 255), -1)
    return {
        "black": solid(0, 0, 0), "white": solid(255, 255, 255), "gray": solid(128, 128, 128),
        "banana_yellow": solid(0, 220, 255), "unripe_green": solid(60, 160, 60),
        "overripe_brown": solid(40, 70, 110),
        "noise": noise, "blurred_noise": cv2.GaussianBlur(noise, (0, 0), 12),
        "yellow_ellipse": lemon, "green_bar": cucumber, "yellow_box": box,
        "orange_disc": orange,
    }


def test_shipped_verifier_is_the_audited_model_and_can_see_a_banana_shape(detector):
    import cv2

    # Positive control: the checks below would also pass for a model that sees nothing.
    audit = Path(__file__).resolve().parents[2] / "docs/audits/ood-gate-evaluation-2026-11-13.json"
    digest = hashlib.sha256(WEIGHTS.read_bytes()).hexdigest()
    assert digest == json.loads(audit.read_text(encoding="utf-8"))["gate_model"]["sha256"]
    assert detector._model.names[BANANA_CLASS_ID] == "banana"
    crescent = solid(200, 200, 200)
    cv2.ellipse(crescent, (320, 200), (220, 150), 0, 20, 160, (0, 225, 255), 45)
    result = detector.detect(cv2.GaussianBlur(crescent, (0, 0), 25))
    # A blurred banana-shaped crescent is a known lookalike: it yields evidence.
    assert result.available is True and result.boxes
    assert result.best_confidence >= GatePolicy().support_confidence


@pytest.mark.parametrize("name", [
    "black", "white", "gray", "banana_yellow", "unripe_green", "overripe_brown",
    "noise", "blurred_noise", "yellow_ellipse", "green_bar", "yellow_box", "orange_disc",
])
def test_frames_without_a_banana_give_no_evidence_and_reject_the_scan(detector, name):
    result = detector.detect(frames()[name])
    assert result.available is True
    # No acceptance and no weaker evidence either: the scan gate rejects four such
    # views, and no cultivar box in them can be supported.
    assert result.banana_detected is False and result.boxes == []
    assert result.best_confidence == 0.0
