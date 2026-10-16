"""Fresh scan responses and auto labels serialize without implicit database loads."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import scans
from app.models import PrintJob, Scan
from app.services import print_jobs, scan_service
from app.services.scan_records import serialize_scan
from tests.test_time_and_writes import application  # noqa: F401


@pytest.fixture
def scan_station(application, monkeypatch):  # noqa: F811 - imported pytest fixture
    app = application
    captures = [
        SimpleNamespace(camera_id=f"CAM-{index + 1:03}", camera_label=label,
                        frame=None, file_path=None)
        for index, label in enumerate(["Top", "Left", "Right", "Rear"])
    ]

    async def capture_all():
        return captures

    result = SimpleNamespace(
        cultivar="Lakatan", ripeness="Ripe", confidence=98, finger_count=7,
        detections=[], inference_time_ms=1, auto_flagged=False,
        conflict_detected=False, camera_count=4,
    )
    monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(
        online_cameras=[0, 1, 3, 2], capture_all=capture_all,
        save_captures=lambda frames, _: frames,
    ))
    monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
        detect=lambda _: SimpleNamespace(banana_detected=True),
    ))
    monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(
        predict=lambda _, **kwargs: result,
    ))
    monkeypatch.setattr(scan_service, "fusion_engine", SimpleNamespace(
        fuse=lambda _, **kwargs: result,
    ))
    monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(
        predict=lambda **_: "3-6",
    ))
    monkeypatch.setattr(scan_service, "sensor_reader", SimpleNamespace(latest=None))

    async def send(*args, **kwargs):
        pass

    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", send)
    monkeypatch.setattr(scans, "get_settings", lambda: SimpleNamespace(
        bananavision_auto_print=True,
    ))
    monkeypatch.setattr(print_jobs, "get_settings", lambda: SimpleNamespace(
        bananavision_printer_name="Fixture Printer", bananavision_label_width_mm=40,
        bananavision_label_height_mm=30,
    ))
    submit = MagicMock(return_value=713)
    monkeypatch.setattr(print_jobs, "print_prediction_label", submit)
    # Disconnect the completed ORM graph to expose implicit loads even on SQLite.
    # A production AsyncSession would fail with MissingGreenlet at the same access.
    async def persisted_scan(**kwargs):
        scan = await scan_service.execute_scan_pipeline(**kwargs)
        kwargs["db"].session.expunge_all()
        return scan

    monkeypatch.setattr(scans, "execute_scan_pipeline", persisted_scan)
    return app, submit


@pytest.mark.parametrize("role", ["Operator", "Admin"])
@pytest.mark.parametrize("linked", [True, False])
def test_trigger_returns_saved_four_camera_result_and_queues_one_label(scan_station, role, linked):
    app, submit = scan_station
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator", role=SimpleNamespace(name=role),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    response = app.client.post("/api/v1/scans/trigger", json={
        "intake_id": str(app.ids.intake) if linked else None, "source_text": "Fixture Supplier",
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cultivar"] == "Lakatan" and data["spoilage_days"] == "3-6"
    assert data["inventory_eligible"] is True and data["has_notes"] is False
    assert data["intake_id"] == (str(app.ids.intake) if linked else None)
    assert data["intake_provenance"] == ("linked" if linked else "unlinked")
    assert data["print_error"] is None and data["print_job"]["status"] == "QUEUED"
    assert submit.call_count == 1
    with Session(app.engine) as db:
        scan_id = UUID(data["id"])
        job = db.scalar(select(PrintJob).where(PrintJob.prediction_id == scan_id))
        assert job.status == "SUBMITTED" and job.windows_job_id == 713
        saved = db.scalar(select(Scan).where(Scan.id == scan_id))
        assert len(saved.detections) == 4
        response_user = SimpleNamespace(role=SimpleNamespace(name=role))
        assert serialize_scan(saved, response_user).id == saved.id


def test_missing_requested_intake_does_not_create_unlinked_scan_or_label(scan_station):
    app, submit = scan_station
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator",
        role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(uuid4())})
    assert response.status_code == 404, response.text
    submit.assert_not_called()
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(Scan)) == 1
        assert db.scalar(select(func.count()).select_from(PrintJob)) == 0


@pytest.mark.parametrize("scenario", ["conflicting_pairs", "sparse_views", "missing_captures"])
def test_real_fusion_passes_observed_pair_to_rfr_and_persists_review_flag(
    scan_station, monkeypatch, scenario,
):
    from app.services.classification import ClassificationResult
    from app.services.fusion_engine import FusionEngine

    app, _ = scan_station
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    agreeing = ClassificationResult(cultivar="Lakatan", ripeness="Ripe", confidence=91)
    if scenario == "conflicting_pairs":
        results = [
            agreeing,
            ClassificationResult(cultivar="Lakatan", ripeness="Unripe", confidence=90),
            ClassificationResult(cultivar="Cardaba", ripeness="Overripe", confidence=95),
            ClassificationResult(cultivar="Latundan", ripeness="Overripe", confidence=95),
        ]
    elif scenario == "sparse_views":
        results = [agreeing, ClassificationResult(), ClassificationResult(), ClassificationResult()]
    else:
        results = [agreeing, agreeing]
        original_capture_all = scan_service.camera_manager.capture_all

        async def partial_capture():
            return (await original_capture_all())[:2]

        monkeypatch.setattr(scan_service.camera_manager, "capture_all", partial_capture)

    predictions = iter(results)
    monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(
        predict=lambda _, **kwargs: next(predictions),
    ))
    monkeypatch.setattr(scan_service, "fusion_engine", FusionEngine())
    rfr_calls = []

    def predict_spoilage(**kwargs):
        rfr_calls.append(kwargs)
        return "3-6"

    monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(
        predict=predict_spoilage,
    ))
    completed = []

    async def capture_event(_room, event, data, **_kwargs):
        if event == "scan:completed":
            completed.append(data)

    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", capture_event)
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(app.ids.intake)})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["cultivar"], data["ripeness"], data["confidence"]) == ("Lakatan", "Ripe", 91)
    assert data["flagged"] is True
    assert len(rfr_calls) == 1
    assert (rfr_calls[0]["cultivar"], rfr_calls[0]["ripeness"]) == ("Lakatan", "Ripe")
    assert completed and all(event["flagged"] is True for event in completed)
    with Session(app.engine) as db:
        saved = db.get(Scan, UUID(data["id"]))
        assert saved.flagged is True
        assert len(saved.detections) == len(results)
        assert saved.original_ai_result.ripeness == "Ripe"
