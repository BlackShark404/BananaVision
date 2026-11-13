"""Real Ultralytics check: the IoU setting only acts when the NMS head runs.

Uses the COCO yolo26n.pt shipped for the banana verifier and the sample photo bundled
with Ultralytics. It proves the mechanism only; banana counts need the banana weights.
"""

from pathlib import Path

import pytest

ultralytics = pytest.importorskip("ultralytics")
WEIGHTS = Path(__file__).resolve().parents[1] / "yolo26n.pt"
PHOTO = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
pytestmark = pytest.mark.skipif(
    not WEIGHTS.is_file() or not PHOTO.is_file(), reason="COCO weights or sample photo missing",
)


def boxes_by_iou(mode):
    from ultralytics import YOLO

    from app.services.classification import _apply_inference_head

    model = YOLO(str(WEIGHTS))
    head = _apply_inference_head(model, mode)
    counts = {
        iou: len(model.predict(str(PHOTO), conf=0.05, iou=iou, verbose=False)[0].boxes)
        for iou in (0.3, 0.95)
    }
    return head, counts


def test_iou_changes_the_boxes_only_with_the_nms_head():
    head, counts = boxes_by_iou("one_to_many_nms")
    assert head == "one_to_many_nms" and counts[0.3] < counts[0.95]
    head, counts = boxes_by_iou("one_to_one")
    assert head == "one_to_one" and counts[0.3] == counts[0.95]
    # This file stores no head choice, so Ultralytics 8.4.40 picks the NMS-free head.
    assert boxes_by_iou("checkpoint")[0] == "one_to_one"


def test_classifier_loads_and_warms_up_on_the_nms_head(monkeypatch):
    from app.services import classification

    monkeypatch.setattr(classification, "settings", classification.settings.model_copy(
        update={"yolo_model_path": str(WEIGHTS), "yolo_inference_head": "one_to_many_nms"},
    ))
    classifier = classification.BananaClassifier()
    classifier.load()
    classifier.warmup()
    assert classifier.inference_head == "one_to_many_nms"
    # Warmup really ran (it swallows errors): Ultralytics set up its predictor with the
    # head argument the classifier sent.
    predictor = classifier._model.predictor
    assert predictor is not None and predictor.args.end2end is False
    assert classifier._model.model.end2end is False
    # The one-to-many head survived the first prediction, so NMS keeps working.
    assert classifier._model.model.model[-1].cv2 is not None
    # A full prediction through the app's code path, with every argument it sends.
    import cv2

    result = classifier.predict(cv2.imread(str(PHOTO)), confidence_threshold=0.50)
    assert result.detections and predictor.args.end2end is False
