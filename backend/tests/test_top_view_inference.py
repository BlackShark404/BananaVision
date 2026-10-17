"""Top overlap refinement uses verified weights without changing other camera views."""

import hashlib
import sys
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import Scan
from app.services import classification, scan_service
from app.services.classification import BananaClassifier
from tests.test_scan_trigger import scan_station  # noqa: F401 - isolated SQLite fixture
from tests.test_time_and_writes import application  # noqa: F401 - fixture dependency

VERIFIED_CHECKPOINT = "e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89"
CANDIDATE_CHECKPOINT = "6a9ea2913b68465ee33e0991b125af4a598de526758b1cbe8a3591d430868916"


def box_iou(left, right):
    """Intersection over union for two pixel-coordinate rectangles."""
    width = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = width * height
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / (left_area + right_area - intersection)


class OverlappingFingerPredictor:
    """Model fixture with persistent options and real greedy, class-aware NMS."""

    def __init__(self, rows=None, names=None):
        # Two distinct neighboring fingers whose rectangular boxes overlap 54%.
        # The last, low-confidence candidate must remain filtered in both views.
        self.rows = rows if rows is not None else [
            (20, 30, 120, 170, 0.92, 0),
            (50, 30, 150, 170, 0.88, 0),
            (155, 5, 180, 100, 0.49, 0),
        ]
        self.names = names if names is not None else {0: "latundan_ripe"}
        self.options = {
            "iou": 0.45, "imgsz": 320, "augment": True,
            "agnostic_nms": True, "max_det": 1,
        }
        self.calls = []
        self.frames = []

    def predict(self, image, **kwargs):
        self.calls.append(kwargs.copy())
        self.frames.append(image)
        self.options.update(kwargs)
        selected = []
        for row in sorted(self.rows, key=lambda candidate: candidate[4], reverse=True):
            if row[4] < self.options["conf"]:
                continue
            suppress = any(
                (self.options["agnostic_nms"] or prior[5] == row[5])
                and box_iou(prior, row) > self.options["iou"]
                for prior in selected
            )
            if not suppress and len(selected) < self.options["max_det"]:
                selected.append(row)
        boxes = [
            SimpleNamespace(
                xyxy=np.array([row[:4]], dtype=float), conf=[row[4]], cls=[row[5]],
            )
            for row in selected
        ]
        return [SimpleNamespace(boxes=boxes, names=self.names)]


@pytest.fixture
def verified_classifier(monkeypatch):
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_iou_threshold=0.45, yolo_top_overlap_refinement=True,
    ))
    classifier = BananaClassifier()
    classifier._model = OverlappingFingerPredictor()
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT
    return classifier


def test_top_retains_neighbor_fingers_and_rear_resets_persistent_predictor(verified_classifier):
    classifier = verified_classifier
    # Distinct BGR channels expose unintended color conversion or frame alteration.
    frame = np.empty((180, 200, 3), dtype=np.uint8)
    frame[:] = [17, 93, 211]
    original = frame.copy()

    top = classifier.predict(frame, confidence_threshold=0.5, camera_label="  tOp  ")
    rear = classifier.predict(frame, confidence_threshold=0.5, camera_label="Rear")

    assert top.finger_count == len(top.detections) == 2
    assert rear.finger_count == len(rear.detections) == 1
    assert (top.cultivar, top.ripeness, top.confidence) == ("Latundan", "Ripe", 90)
    assert top.conflict_detected is False
    assert [(box.x, box.y, box.w, box.h) for box in top.detections] == [
        (20, 30, 100, 140), (50, 30, 100, 140),
    ]
    assert [box.confidence for box in top.detections] == pytest.approx([0.92, 0.88])
    np.testing.assert_array_equal(frame, original)
    assert all(received is frame for received in classifier._model.frames)
    # Ultralytics retains predictor arguments. Every invocation must set these,
    # so an earlier Top refinement or external prediction cannot leak to Rear.
    for call, expected_iou in zip(classifier._model.calls, [0.65, 0.45], strict=True):
        assert call["iou"] == expected_iou
        assert call["conf"] == 0.5
        assert call["imgsz"] == 640
        assert call["augment"] is False
        assert call["agnostic_nms"] is False
        assert call["max_det"] == 300
        assert call["verbose"] is False


@pytest.mark.parametrize(
    ("label", "fingerprint", "enabled", "confidence", "base_iou"),
    [
        ("Rear", VERIFIED_CHECKPOINT, True, 0.5, 0.45),
        ("Left", VERIFIED_CHECKPOINT, True, 0.5, 0.45),
        ("Right", VERIFIED_CHECKPOINT, True, 0.5, 0.45),
        (None, VERIFIED_CHECKPOINT, True, 0.5, 0.45),
        ("Top", None, True, 0.5, 0.45),
        ("Top", "0" * 64, True, 0.5, 0.45),
        ("Top", CANDIDATE_CHECKPOINT, True, 0.5, 0.45),
        ("Top", VERIFIED_CHECKPOINT, False, 0.5, 0.45),
        ("Top", VERIFIED_CHECKPOINT, True, 0.3, 0.45),
        ("Top", VERIFIED_CHECKPOINT, True, 0.85, 0.45),
        ("Top", VERIFIED_CHECKPOINT, True, 0.5, 0.7),
    ],
)
def test_unvalidated_profiles_keep_configured_overlap(
    verified_classifier, label, fingerprint, enabled, confidence, base_iou,
):
    classifier = verified_classifier
    classifier._checkpoint_sha256 = fingerprint
    classification.settings.yolo_top_overlap_refinement = enabled
    classification.settings.yolo_iou_threshold = base_iou

    classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=confidence, camera_label=label,
    )

    assert classifier._model.calls[-1]["iou"] == base_iou
    assert classifier._model.calls[-1]["conf"] == confidence


def test_top_preserves_class_aware_boxes_and_observed_pair_voting(verified_classifier):
    classifier = verified_classifier
    classifier._model = OverlappingFingerPredictor(
        rows=[
            (20, 30, 120, 170, 0.91, 0), (20, 30, 120, 170, 0.90, 1),
            (20, 30, 120, 170, 0.95, 2), (20, 30, 120, 170, 0.95, 3),
        ],
        names={
            0: "lakatan_ripe", 1: "lakatan_unripe",
            2: "cardaba_overripe", 3: "latundan_overripe",
        },
    )

    result = classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=0.5, camera_label="Top",
    )

    assert result.finger_count == 4
    assert (result.cultivar, result.ripeness, result.confidence) == ("Lakatan", "Ripe", 91)
    assert result.conflict_detected is True


def test_loading_records_file_fingerprint_instead_of_trusting_model_filename(
    tmp_path, monkeypatch,
):
    payload = b"synthetic checkpoint, never deserialized"
    weights = tmp_path / "banana_yolov8n.pt"
    weights.write_bytes(payload)
    model = OverlappingFingerPredictor()
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda _: model))
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_model_path=str(weights), yolo_iou_threshold=0.45,
        yolo_top_overlap_refinement=True,
    ))
    classifier = BananaClassifier()
    assert classifier._checkpoint_sha256 is None

    classifier.load()

    assert classifier.is_loaded
    assert classifier._checkpoint_sha256 == hashlib.sha256(payload).hexdigest()
    classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=0.5, camera_label="Top",
    )
    assert model.calls[-1]["iou"] == 0.45


def test_loading_failure_clears_previous_verified_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(
        YOLO=lambda _: (_ for _ in ()).throw(FileNotFoundError("fixture missing")),
    ))
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_model_path=str(tmp_path / "missing.pt"),
    ))
    classifier = BananaClassifier()
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT

    classifier.load()

    assert classifier.is_loaded is False
    assert classifier._model is None
    assert classifier._checkpoint_sha256 is None


def test_loading_custom_checkpoint_preserves_its_prediction_resolution(tmp_path, monkeypatch):
    weights = tmp_path / "custom-resolution.pt"
    weights.write_bytes(b"synthetic checkpoint with 960-pixel inference")
    model = OverlappingFingerPredictor()
    model.overrides = {"imgsz": 960}
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda _: model))
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_model_path=str(weights), yolo_iou_threshold=0.45,
        yolo_top_overlap_refinement=True,
    ))
    classifier = BananaClassifier()

    classifier.load()
    result = classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=0.5, camera_label="Top",
    )

    assert classifier.is_loaded
    assert result.finger_count == 1
    assert model.calls[-1]["imgsz"] == 960
    assert model.calls[-1]["iou"] == 0.45


def test_verified_checkpoint_with_custom_resolution_bypasses_top_profile(verified_classifier):
    classifier = verified_classifier
    classifier._image_size = 960

    result = classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=0.5, camera_label="Top",
    )

    assert result.finger_count == 1
    assert classifier._model.calls[-1]["imgsz"] == 960
    assert classifier._model.calls[-1]["iou"] == 0.45


def test_fingerprint_read_failure_keeps_loaded_model_available(tmp_path, monkeypatch):
    model = OverlappingFingerPredictor()
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda _: model))
    monkeypatch.setattr(classification, "settings", SimpleNamespace(
        yolo_model_path=str(tmp_path / "loaded-model.pt"), yolo_iou_threshold=0.45,
        yolo_top_overlap_refinement=True,
    ))

    def unreadable_fingerprint(_path):
        raise PermissionError("synthetic checkpoint fingerprint unavailable")

    monkeypatch.setattr(classification, "_checkpoint_digest", unreadable_fingerprint)
    classifier = BananaClassifier()
    classifier._checkpoint_sha256 = VERIFIED_CHECKPOINT

    classifier.load()
    result = classifier.predict(
        np.zeros((180, 200, 3), dtype=np.uint8),
        confidence_threshold=0.5, camera_label="Top",
    )

    assert classifier.is_loaded
    assert classifier._model is model
    assert classifier._checkpoint_sha256 is None
    assert result.finger_count == 1
    assert model.calls[-1]["iou"] == 0.45


def test_overlap_setting_defaults_on_and_can_be_disabled_from_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("YOLO_TOP_OVERLAP_REFINEMENT", raising=False)
    assert Settings(_env_file=None).yolo_top_overlap_refinement is True
    monkeypatch.setenv("YOLO_TOP_OVERLAP_REFINEMENT", "false")
    assert Settings(_env_file=None).yolo_top_overlap_refinement is False


def test_scan_uses_camera_label_when_top_is_not_first_slot(
    scan_station, verified_classifier, monkeypatch,  # noqa: F811 - fixture injection
):
    app, submit = scan_station
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    original_capture_all = scan_service.camera_manager.capture_all
    order = ["Rear", "Left", "Top", "Right"]

    async def reordered_captures():
        captures = await original_capture_all()
        for capture, label in zip(captures, order, strict=True):
            capture.camera_label = label
            capture.frame = np.zeros((180, 200, 3), dtype=np.uint8)
        return captures

    monkeypatch.setattr(scan_service.camera_manager, "capture_all", reordered_captures)
    monkeypatch.setattr(scan_service, "banana_classifier", verified_classifier)
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(app.ids.intake)})

    assert response.status_code == 200, response.text
    assert [call["iou"] for call in verified_classifier._model.calls] == [0.45, 0.45, 0.65, 0.45]
    with Session(app.engine) as db:
        saved = db.get(Scan, UUID(response.json()["id"]))
        counts = {item.camera_label: item.finger_count for item in saved.detections}
        assert counts == {"Rear": 1, "Left": 1, "Top": 2, "Right": 1}
        assert next(item for item in saved.detections if item.camera_label == "Top").camera_id == (
            "CAM-003"
        )
    assert submit.call_count == 1
