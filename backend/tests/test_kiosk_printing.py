"""Kiosk demonstrations never invent predictions or touch cameras/printers."""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import scans
from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.models import Intake, PrintJob, Scan, ScanClassification
from app.services.windows_printer import PrinterServiceError
from tests.test_printing import station as station
from tests.test_time_and_writes import application as application


def test_demo_uses_saved_values_prints_once_and_preserves_records(station):
    app = station
    body = {"request_id": str(uuid4())}
    url = f"/api/v1/scans/{app.ids.scan}/kiosk-demo"
    first = app.client.post(url, json=body)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["scan"]["id"] == str(app.ids.scan)
    assert data["scan"]["confidence"] == 90
    assert data["print_job"]["quantity"] == 1
    assert "TEST=DEMO" in data["label"]["payload"]
    assert "SPOILAGE_DAYS=3" in data["label"]["payload"]
    assert data["label"]["panel"][-1] == "DEMO"
    replay = app.client.post(url, json=body)
    assert replay.json()["print_job"]["status"] == "SUBMITTED"
    assert app.submit.call_count == 1
    assert app.submit.call_args.args[1].demo
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(Scan)) == 1
        assert db.scalar(select(func.count()).select_from(ScanClassification)) == 1
        assert db.scalar(select(func.count()).select_from(Intake)) == 1
        scan = db.get(Scan, app.ids.scan)
        assert scan.revision == 1 and not scan.flagged
        assert float(scan.classification.confidence) == 90
        assert db.scalar(select(func.count()).select_from(PrintJob)) == 1
    # A demo request ID cannot be reused for an ordinary production label.
    normal = app.client.post(f"/api/v1/scans/{app.ids.scan}/print", json=body)
    assert normal.status_code == 409
    app.submit.assert_called_once()


def test_demo_offline_and_retry_keep_demo_snapshot(station):
    app = station
    app.submit.side_effect = PrinterServiceError("OFFLINE")
    response = app.client.post(f"/api/v1/scans/{app.ids.scan}/kiosk-demo",
                               json={"request_id": str(uuid4())})
    job_id = response.json()["print_job"]["id"]
    base = f"/api/v1/scans/{app.ids.scan}/print-jobs/{job_id}"
    assert app.client.get(base).json()["status"] == "FAILED"
    app.submit.side_effect = None
    assert app.client.post(base + "/retry", json={"expected_attempt": 1}).status_code == 200
    assert app.submit.call_args.args[1].demo
    assert "TEST=DEMO" in app.submit.call_args.args[1].payload()
    assert app.client.get(base).json()["attempt_count"] == 2


def test_demo_replay_display_matches_original_label_after_source_change(station):
    app = station
    url = f"/api/v1/scans/{app.ids.scan}/kiosk-demo"
    body = {"request_id": str(uuid4())}
    first = app.client.post(url, json=body).json()
    with Session(app.engine) as db:
        db.get(Scan, app.ids.scan).classification.confidence = 99
        db.commit()
    replay = app.client.post(url, json=body).json()
    assert replay["label"]["payload"] == first["label"]["payload"]
    assert replay["scan"]["confidence"] == 90
    app.submit.assert_called_once()


def test_demo_rejects_missing_unauthorized_and_client_predictions(station):
    app = station
    body = {"request_id": str(uuid4())}
    assert app.client.post(f"/api/v1/scans/{uuid4()}/kiosk-demo", json=body).status_code == 404
    url = f"/api/v1/scans/{app.ids.scan}/kiosk-demo"
    assert app.client.post(url, json={**body, "quantity": 10}).status_code == 422
    assert app.client.post(url, json={**body, "confidence": 100}).status_code == 422
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role=SimpleNamespace(name="Operator"),
    )
    assert app.client.post(url, json=body).status_code == 403
    app.submit.assert_not_called()


def prepare_trigger(app, monkeypatch):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )

    async def completed(**kwargs):
        db = kwargs["db"]
        scan = (await db.execute(select(Scan).where(Scan.id == app.ids.scan))).scalar_one()
        await db.commit()
        return scan

    monkeypatch.setattr(scans, "execute_scan_pipeline", completed)


def test_real_automatic_print_is_opt_in_and_idempotent(station, monkeypatch):
    app = station
    prepare_trigger(app, monkeypatch)
    monkeypatch.setattr(get_settings(), "bananavision_auto_print", False)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200 and response.json()["print_job"] is None
    app.submit.assert_not_called()
    monkeypatch.setattr(get_settings(), "bananavision_auto_print", True)
    first = app.client.post("/api/v1/scans/trigger", json={})
    again = app.client.post("/api/v1/scans/trigger", json={})
    assert first.json()["print_job"]["id"] == again.json()["print_job"]["id"]
    assert again.json()["print_job"]["status"] == "SUBMITTED"
    app.submit.assert_called_once()
    assert not app.submit.call_args.args[1].demo
    assert app.submit.call_args.kwargs["quantity"] == 1


def test_failed_inference_or_prediction_commit_never_prints(station, monkeypatch):
    app = station
    prepare_trigger(app, monkeypatch)
    monkeypatch.setattr(get_settings(), "bananavision_auto_print", True)

    async def failed(**_kwargs):
        raise ModelInferenceError("BananaClassifier", "No banana detected")

    monkeypatch.setattr(scans, "execute_scan_pipeline", failed)
    assert app.client.post("/api/v1/scans/trigger", json={}).status_code == 422
    prepare_trigger(app, monkeypatch)
    app.state.fail_commit = True
    assert app.client.post("/api/v1/scans/trigger", json={}).status_code == 500
    app.state.fail_commit = False
    app.submit.assert_not_called()


def test_queue_failure_returns_saved_prediction_with_actionable_error(station, monkeypatch):
    app = station
    prepare_trigger(app, monkeypatch)
    monkeypatch.setattr(get_settings(), "bananavision_auto_print", True)

    async def unavailable(*_args):
        raise RuntimeError("Print database unavailable")

    monkeypatch.setattr(scans, "queue_automatic_label", unavailable)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200 and response.json()["confidence"] == 90
    assert "Prediction saved" in response.json()["print_error"]
    assert app.client.get(f"/api/v1/scans/{app.ids.scan}").status_code == 200
    app.submit.assert_not_called()


def test_print_failure_preserves_successful_live_prediction(station, monkeypatch):
    app = station
    prepare_trigger(app, monkeypatch)
    monkeypatch.setattr(get_settings(), "bananavision_auto_print", True)
    app.submit.side_effect = PrinterServiceError("OFFLINE")
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200
    job_id = response.json()["print_job"]["id"]
    status = app.client.get(f"/api/v1/scans/{app.ids.scan}/print-jobs/{job_id}").json()
    assert status["status"] == "FAILED"
    assert app.client.get(f"/api/v1/scans/{app.ids.scan}").status_code == 200
