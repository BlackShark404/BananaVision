"""YOLO26 detection head is chosen explicitly at load, before the first prediction.

Ultralytics 8.4.40 runs a YOLO26 checkpoint with its NMS-free one-to-one head unless the
file says otherwise. NMS and every IoU setting are then skipped, and the first prediction
fuses the one-to-many head away for good. The counts were measured with NMS, so the app
now fixes the head right after loading the weights.
"""

import logging
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services import classification
from app.services.classification import BananaClassifier, _apply_inference_head


class Head:
    """Detection head with the 8.4.40 end2end rule: on unless stored off, if one2one exists."""

    def __init__(self, *, one_to_one=True, stored=None):
        self.cv2 = object()  # one-to-many branch
        if one_to_one:
            self.one2one_cv2 = object()
        if stored is not None:
            self._end2end = stored

    @property
    def end2end(self):
        return getattr(self, "_end2end", True) and hasattr(self, "one2one_cv2")

    @end2end.setter
    def end2end(self, value):
        self._end2end = value


class DetectionModel:
    def __init__(self, head):
        self.model = [head]

    @property
    def end2end(self):
        return getattr(self.model[-1], "end2end", False)

    @end2end.setter
    def end2end(self, value):
        self.model[-1].end2end = value


class FakeYOLO:
    """Records the head in use at every prediction; the first one fuses like 8.4.40."""

    instances: list["FakeYOLO"] = []

    def __init__(self, _path, head=None):
        self.model = DetectionModel(head or Head())
        self.overrides = {"imgsz": 640}
        self.calls = []
        self.head_at_call = []
        FakeYOLO.instances.append(self)

    def predict(self, _image, **kwargs):
        if not self.calls and kwargs.get("end2end") is not None:
            self.model.end2end = kwargs["end2end"]  # predictor.setup_model, first call only
        if not self.calls and self.model.end2end:
            self.model.model[-1].cv2 = None  # Detect.fuse() removes the one-to-many head
        self.calls.append(kwargs.copy())
        self.head_at_call.append(self.model.end2end)
        return [SimpleNamespace(boxes=[], names={0: "lakatan_ripe"})]


@pytest.fixture
def fake_ultralytics(monkeypatch):
    FakeYOLO.instances = []
    module = ModuleType("ultralytics")
    module.YOLO = FakeYOLO
    cfg = ModuleType("ultralytics.cfg")
    cfg.DEFAULT_CFG_DICT = {"end2end": None, "iou": 0.7}
    module.cfg = cfg
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    monkeypatch.setitem(sys.modules, "ultralytics.cfg", cfg)
    return module


def load_with(monkeypatch, tmp_path, mode):
    weights = tmp_path / "banana.pt"
    weights.write_bytes(b"weights")
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_model_path=str(weights), yolo_inference_head=mode,
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
    ))
    classifier = BananaClassifier()
    classifier.load()
    classifier.warmup()
    return classifier, FakeYOLO.instances[-1]


def test_measured_nms_head_is_fixed_before_the_first_prediction(fake_ultralytics, monkeypatch,
                                                                tmp_path):
    classifier, model = load_with(monkeypatch, tmp_path, "one_to_many_nms")
    assert classifier.inference_head == "one_to_many_nms"
    classifier.predict(np.zeros((32, 32, 3), np.uint8), confidence_threshold=0.50)
    # Warmup is the call that sets up the predictor; it already runs with NMS.
    assert model.head_at_call == [False, False]
    assert [call.get("end2end") for call in model.calls] == [False, False]
    assert model.model.model[-1].cv2 is not None  # nothing fused away
    assert model.calls[1]["iou"] == 0.45


def test_one_to_one_head_can_be_chosen(fake_ultralytics, monkeypatch, tmp_path):
    classifier, model = load_with(monkeypatch, tmp_path, "one_to_one")
    assert classifier.inference_head == "one_to_one"
    assert model.head_at_call == [True]
    assert model.calls[0]["end2end"] is True


def test_checkpoint_mode_keeps_todays_behaviour(fake_ultralytics, monkeypatch, tmp_path):
    classifier, model = load_with(monkeypatch, tmp_path, "checkpoint")
    # An unrecorded YOLO26 file loads one-to-one in 8.4.40; nothing is changed or sent.
    assert classifier.inference_head == "one_to_one"
    assert "end2end" not in model.calls[0]
    assert model.head_at_call == [True]


def test_checkpoint_that_stores_its_head_off_reports_nms(fake_ultralytics):
    yolo = FakeYOLO("x", head=Head(stored=False))
    assert _apply_inference_head(yolo, "checkpoint") == "one_to_many_nms"


def test_fused_head_cannot_return_to_nms(fake_ultralytics, caplog):
    head = Head()
    head.cv2 = None  # already fused by an earlier prediction
    yolo = FakeYOLO("x", head=head)
    with caplog.at_level(logging.ERROR, logger=classification.logger.name):
        assert _apply_inference_head(yolo, "one_to_many_nms") == "one_to_one"
    assert "one-to-many" in caplog.text


def test_model_without_a_one_to_one_head_stays_on_nms(fake_ultralytics, caplog):
    yolo = FakeYOLO("x", head=Head(one_to_one=False))
    with caplog.at_level(logging.WARNING, logger=classification.logger.name):
        assert _apply_inference_head(yolo, "one_to_one") == "one_to_many_nms"
    assert "one-to-one" in caplog.text


def test_models_without_a_detection_head_are_left_alone():
    assert _apply_inference_head(SimpleNamespace(), "one_to_many_nms") == "unknown"
    assert _apply_inference_head(SimpleNamespace(model=object()), "one_to_one") == "unknown"


def test_test_doubles_without_a_loaded_model_send_no_head_argument():
    classifier = BananaClassifier()
    calls = []
    classifier._model = SimpleNamespace(predict=lambda _img, **kw: calls.append(kw) or [])
    classifier.predict(np.zeros((8, 8, 3), np.uint8), confidence_threshold=0.5)
    assert "end2end" not in calls[0]
    assert classifier.inference_head == "unknown"


def test_registered_top_checkpoint_on_the_nms_free_head_is_reported(
    fake_ultralytics, monkeypatch, tmp_path, caplog,
):
    monkeypatch.setattr(classification, "_checkpoint_digest", lambda _path: next(
        iter(classification.TOP_CALIBRATED_CHECKPOINTS)))
    with caplog.at_level(logging.WARNING, logger=classification.logger.name):
        load_with(monkeypatch, tmp_path, "one_to_one")
    assert "IoU" in caplog.text


def test_settings_default_validate_and_read_the_environment(monkeypatch):
    assert Settings(_env_file=None).yolo_inference_head == "one_to_many_nms"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, yolo_inference_head="nms")
    monkeypatch.setenv("YOLO_INFERENCE_HEAD", "checkpoint")
    assert Settings(_env_file=None).yolo_inference_head == "checkpoint"
