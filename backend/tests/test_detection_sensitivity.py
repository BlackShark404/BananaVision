"""Detection retention and review decisions use independent, snapshotted thresholds."""

from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import Settings
from app.models import Scan, SystemConfig
from app.services import configuration, scan_service
from app.services.classification import BananaClassifier
from app.services.fusion_engine import FusionEngine
from tests.test_scan_trigger import scan_station  # noqa: F401
from tests.test_time_and_writes import application  # noqa: F401


class FilteredModel:
    """Filter synthetic model candidates the same way the YOLO conf argument does."""

    def __init__(self, scores):
        self.scores = scores
        self.cutoffs = []
        self.on_predict = None

    def predict(self, _image, **kwargs):
        cutoff = kwargs["conf"]
        self.cutoffs.append(cutoff)
        boxes = [
            SimpleNamespace(
                xyxy=np.array([[index * 20, 1, index * 20 + 10, 80]], dtype=float),
                conf=[score], cls=[0],
            )
            for index, score in enumerate(self.scores) if score >= cutoff
        ]
        if self.on_predict:
            self.on_predict()
        return [SimpleNamespace(boxes=boxes, names={0: "lakatan_ripe"})]


def configure_thresholds(app, monkeypatch, review_threshold, detection_threshold):
    """Change only the disposable fixture row and in-memory settings."""
    settings = Settings(_env_file=None, yolo_confidence_threshold=detection_threshold)
    monkeypatch.setattr(scan_service, "get_settings", lambda: settings)
    monkeypatch.setattr(configuration, "get_settings", lambda: settings)
    with Session(app.engine) as db:
        saved = db.scalar(select(SystemConfig))
        saved.canonical_key = 1
        saved.camera_device_ids = [0, 1, 2, 3]
        saved.confidence_threshold = review_threshold
        db.commit()
    return settings


def use_real_inference(app, monkeypatch, scores):
    model = FilteredModel(scores)
    classifier = BananaClassifier()
    classifier._model = model
    monkeypatch.setattr(scan_service, "banana_classifier", classifier)
    monkeypatch.setattr(scan_service, "fusion_engine", FusionEngine())
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator",
        role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    return model


def test_scan_retains_moderate_boxes_and_persists_low_confidence_review_flag(
    scan_station, monkeypatch,  # noqa: F811
):
    app, _ = scan_station
    configure_thresholds(app, monkeypatch, 85, 0.50)
    model = use_real_inference(app, monkeypatch, [0.92, 0.72, 0.65, 0.42])
    completed = []

    async def record_event(_room, event, data, **_kwargs):
        if event == "scan:completed":
            completed.append(data)

    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", record_event)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200, response.text
    data = response.json()
    assert model.cutoffs == [0.50] * 4
    assert (data["cultivar"], data["ripeness"]) == ("Lakatan", "Ripe")
    assert data["finger_count"] == 3
    assert data["confidence"] == pytest.approx(76.3)
    assert data["flagged"] is True
    assert completed and all(event["flagged"] is True for event in completed)
    with Session(app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert saved.flagged is True
        assert float(saved.original_ai_result.confidence) == pytest.approx(76.3)
        assert len(saved.detections) == 4
        for detection in saved.detections:
            assert detection.finger_count == 3
            assert float(detection.confidence) == pytest.approx(76.3)
            assert [box["conf"] for box in detection.bounding_boxes] == pytest.approx(
                [0.92, 0.72, 0.65],
            )


@pytest.mark.parametrize(
    ("review", "detector", "scores", "expected_cutoff", "confidence"),
    [
        (30, 0.50, [0.40], 0.30, 40),
        (85, 0.90, [0.90, 0.80], 0.85, 90),
        (85, 0.50, [0.85], 0.50, 85),
        (85, 0.50, [0.95], 0.50, 95),
    ],
)
def test_scan_preserves_lower_cutoffs_and_accepts_consensus_at_review_boundary(
    scan_station, monkeypatch, review, detector, scores, expected_cutoff, confidence,  # noqa: F811
):
    app, _ = scan_station
    configure_thresholds(app, monkeypatch, review, detector)
    model = use_real_inference(app, monkeypatch, scores)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200, response.text
    data = response.json()
    assert model.cutoffs == [expected_cutoff] * 4
    assert data["confidence"] == pytest.approx(confidence)
    assert data["flagged"] is False


def test_scan_snapshots_detection_cutoff_before_processing_camera_views(
    scan_station, monkeypatch,  # noqa: F811
):
    app, _ = scan_station
    settings = configure_thresholds(app, monkeypatch, 85, 0.50)
    model = use_real_inference(app, monkeypatch, [0.92, 0.72, 0.65])
    model.on_predict = lambda: setattr(settings, "yolo_confidence_threshold", 0.90)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200, response.text
    assert model.cutoffs == [0.50] * 4
    assert response.json()["finger_count"] == 3


@pytest.mark.parametrize(
    ("review", "detector", "effective_percent"),
    [(85, 0.50, 50), (30, 0.50, 30), (85, 0.90, 85)],
)
def test_config_reports_effective_detection_cutoff_as_read_only(
    application, monkeypatch, review, detector, effective_percent,  # noqa: F811
):
    app = application
    configure_thresholds(app, monkeypatch, review, detector)
    response = app.client.get("/api/v1/config")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["confidence_threshold"] == review
    assert data["detection_confidence_threshold"] == pytest.approx(effective_percent)
    update = app.client.patch("/api/v1/config", json={
        "expected_revision": data["revision"], "detection_confidence_threshold": 25,
    })
    assert update.status_code == 422
    with Session(app.engine) as db:
        saved = db.scalar(select(SystemConfig))
        assert saved.confidence_threshold == review
        assert saved.revision == data["revision"]


@pytest.mark.parametrize("cutoff", [0, -0.1, 1.01, float("nan"), float("inf"), -float("inf")])
def test_detection_setting_rejects_invalid_probabilities(cutoff):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, yolo_confidence_threshold=cutoff)
