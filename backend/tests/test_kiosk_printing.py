"""Removed kiosk replay route and isolated live/legacy label compatibility."""

import asyncio
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import scans
from app.config import get_settings
from app.core.exceptions import ModelInferenceError
from app.models import Intake, PrintJob, Scan, ScanClassification
from app.services import print_jobs
from app.services.prediction_label import PredictionData
from app.services.printer_service import PrinterServiceError
from tests.test_printing import station as station
from tests.test_time_and_writes import application as application


@pytest.mark.parametrize("body", [
    {"request_id": str(uuid4())},
    {"request_id": str(uuid4()), "quantity": 10, "confidence": 100},
])
def test_removed_demo_route_cannot_create_or_modify_records(station, body):
    app = station
    assert not any(path.endswith("/kiosk-demo") for path in app.app.openapi()["paths"])
    for scan_id in (app.ids.scan, uuid4()):
        response = app.client.post(f"/api/v1/scans/{scan_id}/kiosk-demo", json=body)
        assert response.status_code == 404, response.text
    assert "commit" not in app.state.events
    app.submit.assert_not_called()
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(Scan)) == 1
        assert db.scalar(select(func.count()).select_from(ScanClassification)) == 1
        assert db.scalar(select(func.count()).select_from(Intake)) == 1
        scan = db.get(Scan, app.ids.scan)
        assert scan.revision == 1 and not scan.flagged
        assert float(scan.classification.confidence) == 90
        assert db.scalar(select(func.count()).select_from(PrintJob)) == 0


@pytest.mark.parametrize("status", ["QUEUED", "FAILED"])
def test_legacy_demo_jobs_keep_immutable_snapshot_and_retry(station, status):
    app = station
    job_id = uuid4()
    with Session(app.engine) as db:
        scan = db.get(Scan, app.ids.scan)
        data = PredictionData.from_scan(scan, demo=True)
        db.add(PrintJob(
            id=job_id, prediction_id=app.ids.scan, owner_id=app.ids.admin,
            printer_name="Fixture Printer", quantity=1, label_data=asdict(data),
            width_mm=40, height_mm=30, status=status, claimed=status == "FAILED",
            attempt_count=1 if status == "FAILED" else 0,
            error_message="OFFLINE" if status == "FAILED" else None,
        ))
        db.get(Scan, app.ids.scan).classification.confidence = 99
        db.commit()
    base = f"/api/v1/scans/{app.ids.scan}/print-jobs/{job_id}"
    assert app.client.get(base).json()["status"] == status
    if status == "FAILED":
        assert app.client.post(base + "/retry", json={"expected_attempt": 1}).status_code == 200
    else:
        asyncio.run(print_jobs.submit_job(job_id))
    printed = app.submit.call_args.args[1]
    assert printed == data and printed.demo and printed.confidence == 90
    assert "TEST=DEMO" in printed.payload() and printed.panel()[-1] == "DEMO"
    result = app.client.get(base).json()
    assert result["status"] == "SUBMITTED"
    assert result["attempt_count"] == (2 if status == "FAILED" else 1)
    # A historical demo request ID cannot become an ordinary production label.
    normal = app.client.post(f"/api/v1/scans/{app.ids.scan}/print", json={
        "request_id": str(job_id),
    })
    assert normal.status_code == 409
    app.submit.assert_called_once()


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
