"""Cross-session mutation events and sensor freshness contracts.

All tests use the isolated SQLite fixture from ``test_time_and_writes``. No
PostgreSQL instance, live station database, camera or sensor hardware is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ActivityLog, Intake, ScanStatusLog, SensorReading
from app.schemas.enums import IntakeStatusEnum, InventoryStatusEnum
from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application_fixture

application = application_fixture


def _actor(application, role: str = "Admin"):
    return SimpleNamespace(
        id=application.ids.admin,
        token_version=1,
        full_name="Admin User",
        role=SimpleNamespace(name=role),
    )


def test_scan_event_is_post_commit_revision_aware_and_safe(application, monkeypatch):
    from app.schemas.scan import ScanFlagRequest
    from app.services import scan_records

    published = []

    async def capture(event, *, owner_account_id=None):
        published.append((list(application.state.events), event, owner_account_id))

    monkeypatch.setattr(scan_records, "publish_scan_event", capture)

    async def check():
        async with SessionAdapter(application.engine, application.state) as db:
            body = ScanFlagRequest(
                request_id=uuid4(), expected_revision=1, flagged=True, reason="QC check"
            )
            saved = await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "flag", body
            )
            assert saved["revision"] == 2
            # Replaying the same request must not publish a second event.
            replay = await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "flag", body
            )
            assert replay["revision"] == 2

    asyncio.run(check())

    assert len(published) == 1
    events, event, owner_account_id = published[0]
    assert events == ["commit"]
    assert owner_account_id == application.ids.operator
    assert event["revision"] == 2
    assert event["changed"] == ["flagged"]
    assert event["deleted"] is False
    assert event["partial"] is False
    scan = event["scan"]
    assert scan["flagged"] is True
    assert scan["operator_id"] == str(application.ids.profile)
    assert scan["source_key"] == f"supplier:{application.ids.supplier}"
    assert scan["source_name"] == "Original Supplier"
    # Restricted evidence and free-text notes are never broadcast.
    assert "images" not in scan
    assert "original_ai_result" not in scan
    assert "QC check" not in json.dumps(event)


def test_scan_event_is_not_published_when_commit_fails_or_change_is_noop(
    application, monkeypatch
):
    from app.schemas.scan import ScanFlagRequest
    from app.services import scan_records

    published = []

    async def capture(event, *, owner_account_id=None):
        published.append(event)

    monkeypatch.setattr(scan_records, "publish_scan_event", capture)
    application.state.fail_commit = True

    async def failing():
        async with SessionAdapter(application.engine, application.state) as db:
            body = ScanFlagRequest(
                request_id=uuid4(), expected_revision=1, flagged=True, reason="Commit fails"
            )
            await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "flag", body
            )

    with pytest.raises(RuntimeError, match="Simulated database persistence failure"):
        asyncio.run(failing())
    assert published == []

    application.state.fail_commit = False

    async def noop():
        async with SessionAdapter(application.engine, application.state) as db:
            body = ScanFlagRequest(
                request_id=uuid4(), expected_revision=1, flagged=False, reason="No change"
            )
            saved = await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "flag", body
            )
            assert saved["flagged"] is False

    asyncio.run(noop())
    assert published == []


def test_event_rooms_scope_scan_edits_to_admin_and_owning_operator(monkeypatch):
    from app.ws import events, mutations

    calls = []

    async def capture(room, event, data, *, account_id=None):
        calls.append((room, event, data, account_id))

    monkeypatch.setattr(mutations.ws_manager, "send_to_room", capture)
    owner = uuid4()
    event = {"event_id": str(uuid4()), "scan_id": str(uuid4())}

    asyncio.run(mutations.publish_scan_event(event, owner_account_id=owner))
    assert [(call[0], call[1]) for call in calls] == [
        (events.ROOM_DASHBOARD, events.SCAN_CHANGED),
        (events.ROOM_KIOSK, events.SCAN_CHANGED),
    ]
    assert calls[0][3] is None
    assert calls[1][3] == owner

    calls.clear()
    asyncio.run(mutations.publish_intake_event(event))
    assert [call[0] for call in calls] == [events.ROOM_DASHBOARD, events.ROOM_KIOSK]
    assert all(call[3] is None for call in calls)

    calls.clear()
    asyncio.run(mutations.publish_supplier_event(event))
    assert [call[0] for call in calls] == [events.ROOM_DASHBOARD, events.ROOM_KIOSK]
    assert all(call[3] is None for call in calls)


def test_intake_and_bulk_events_follow_commit(application, monkeypatch):
    from app.api.v1 import intakes as intake_api

    intake_events = []
    scan_events = []

    async def capture_intake(event):
        intake_events.append((list(application.state.events), event))

    async def capture_scan(event, *, owner_account_id=None):
        scan_events.append((list(application.state.events), event, owner_account_id))

    monkeypatch.setattr(intake_api, "publish_intake_event", capture_intake)
    monkeypatch.setattr(intake_api, "publish_scan_event", capture_scan)

    created = application.client.post(
        "/api/v1/intakes",
        json={
            "supplier_id": str(application.ids.supplier),
            "batch_number": "B-2",
            "source": "Kiosk",
            "treatment": "Natural",
        },
    )
    assert created.status_code == 200, created.text
    intake_id = created.json()["id"]
    assert intake_events[0][0] == ["commit"]
    created_event = intake_events[0][1]
    assert created_event["kind"] == "created"
    assert created_event["intake"]["updated_at"]
    assert "qr_code" not in created_event["intake"]

    status = application.client.patch(
        f"/api/v1/intakes/{intake_id}/status", json={"status": "Depleted"}
    )
    assert status.status_code == 200, status.text
    assert intake_events[1][0][-1] == "commit"
    assert intake_events[1][1]["kind"] == "status"
    assert intake_events[1][1]["intake"]["status"] == "Depleted"
    assert intake_events[1][1]["intake"]["updated_at"]

    bulk = application.client.patch(
        f"/api/v1/intakes/{application.ids.intake}/bulk-inventory",
        json={
            "inventory_status": "Sold",
            "request_id": str(uuid4()),
            "expected_revisions": {str(application.ids.scan): 1},
            "reason": "Dispatched",
        },
    )
    assert bulk.status_code == 200, bulk.text
    assert scan_events and scan_events[0][0][-1] == "commit"
    _, scan_event, owner_account_id = scan_events[0]
    assert owner_account_id == application.ids.operator
    assert scan_event["partial"] is True
    assert scan_event["scan"]["inventory_status"] == "Sold"
    assert scan_event["scan"]["revision"] == 2
    assert "images" not in scan_event["scan"]
    assert intake_events[-1][1]["kind"] == "bulk-inventory"
    assert intake_events[-1][0][-1] == "commit"


def _sold_scan_in_depleted_intake(application):
    with Session(application.engine) as db:
        log = db.scalar(
            select(ScanStatusLog).where(ScanStatusLog.scan_id == application.ids.scan)
        )
        log.inventory_status = InventoryStatusEnum.SOLD
        db.get(Intake, application.ids.intake).status = IntakeStatusEnum.DEPLETED
        db.commit()


def _intake_reopen_count(application):
    with Session(application.engine) as db:
        return db.scalar(
            select(func.count()).select_from(ActivityLog)
            .where(ActivityLog.action == "intake_status_changed")
        )


def test_reopened_intake_event_follows_commit_and_replays_once(application, monkeypatch):
    from app.schemas.scan import ScanStatusUpdate
    from app.services import scan_records

    _sold_scan_in_depleted_intake(application)
    scan_events, intake_events = [], []

    async def capture_scan(event, *, owner_account_id=None):
        scan_events.append((list(application.state.events), event))

    async def capture_intake(event):
        intake_events.append((list(application.state.events), event))

    monkeypatch.setattr(scan_records, "publish_scan_event", capture_scan)
    monkeypatch.setattr(scan_records, "publish_intake_event", capture_intake)

    async def restore():
        async with SessionAdapter(application.engine, application.state) as db:
            body = ScanStatusUpdate(
                request_id=uuid4(), expected_revision=1, inventory_status="In Stock",
                reason="Sold by mistake",
            )
            saved = await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "status", body
            )
            # Replaying the same request returns the receipt; nothing reopens or publishes again.
            replay = await scan_records.mutate_scan(
                db, application.ids.scan, _actor(application), "status", body
            )
            assert replay == saved
            return saved

    saved = asyncio.run(restore())
    assert saved["inventory_eligible"] is True
    assert len(scan_events) == 1 and len(intake_events) == 1
    assert scan_events[0][0] == ["commit"] and intake_events[0][0] == ["commit"]
    assert scan_events[0][1]["scan"]["inventory_status"] == "In Stock"
    assert scan_events[0][1]["scan"]["inventory_eligible"] is True
    event = intake_events[0][1]
    assert event["kind"] == "scan-status"
    assert event["intake_id"] == str(application.ids.intake)
    assert event["actor_id"] == str(application.ids.admin)
    assert event["status"] == "Active"
    assert set(event["intake"]) == {"id", "status", "updated_at"}
    assert event["intake"]["status"] == "Active" and event["intake"]["updated_at"]
    assert _intake_reopen_count(application) == 1


def test_reopen_is_rolled_back_and_unpublished_when_commit_fails(application, monkeypatch):
    from app.models import Scan
    from app.services import scan_records

    _sold_scan_in_depleted_intake(application)
    published = []

    async def capture_scan(event, *, owner_account_id=None):
        published.append(event)

    async def capture_intake(event):
        published.append(event)

    monkeypatch.setattr(scan_records, "publish_scan_event", capture_scan)
    monkeypatch.setattr(scan_records, "publish_intake_event", capture_intake)
    application.state.fail_commit = True
    response = application.client.patch(
        f"/api/v1/scans/{application.ids.scan}/status",
        json={"request_id": str(uuid4()), "expected_revision": 1,
              "inventory_status": "In Stock", "reason": "Sold by mistake"},
    )
    assert response.status_code == 500
    assert application.state.events == ["commit", "rollback", "response:500"]
    assert published == []
    with Session(application.engine) as db:
        assert db.get(Intake, application.ids.intake).status == IntakeStatusEnum.DEPLETED
        assert db.get(Scan, application.ids.scan).revision == 1
    assert _intake_reopen_count(application) == 0


def test_supplier_events_are_post_commit_and_carry_reference_data(application, monkeypatch):
    from app.api.v1 import suppliers as supplier_api

    events = []

    async def capture(event):
        events.append((list(application.state.events), event))

    monkeypatch.setattr(supplier_api, "publish_supplier_event", capture)

    created = application.client.post("/api/v1/suppliers", json={"name": "New Supplier"})
    assert created.status_code == 201, created.text
    supplier_id = created.json()["id"]
    assert events[0][0] == ["commit"]
    assert events[0][1]["kind"] == "created"
    assert events[0][1]["supplier"]["name"] == "New Supplier"
    assert events[0][1]["supplier"]["updated_at"]

    updated = application.client.patch(
        f"/api/v1/suppliers/{supplier_id}", json={"name": "Renamed Supplier"}
    )
    assert updated.status_code == 200, updated.text
    assert events[1][0][-1] == "commit"
    assert events[1][1]["kind"] == "updated"
    assert events[1][1]["supplier"]["name"] == "Renamed Supplier"
    assert events[1][1]["supplier"]["updated_at"]


def test_sensor_latest_reports_server_freshness_metadata(application):
    from app.services.sensor_reader import freshness_window_seconds

    recorded_at = datetime.now().astimezone() - timedelta(seconds=90)
    with Session(application.engine) as db:
        db.add(SensorReading(temperature=26.5, humidity=70.0, recorded_at=recorded_at))
        db.commit()

    response = application.client.get("/api/v1/sensors/latest")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["temperature"] == 26.5
    assert data["stale_after_seconds"] == freshness_window_seconds() >= 15
    server_time = datetime.fromisoformat(data["server_time"])
    reading_time = datetime.fromisoformat(data["recorded_at"])
    assert server_time.utcoffset() is not None
    assert (server_time - reading_time).total_seconds() >= 89


def test_health_exposes_sensor_age_without_running_lifespan(monkeypatch):
    monkeypatch.setattr(
        logging.handlers, "RotatingFileHandler", lambda *a, **k: logging.NullHandler(),
    )
    from app.main import app

    monkeypatch.setattr(app, "middleware_stack", None)
    client = TestClient(app)
    try:
        response = client.get("/health")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["sensor_stale_after_seconds"] >= 15
        assert "sensor_recorded_at" in data
        assert datetime.fromisoformat(data["server_time"]).utcoffset() is not None
    finally:
        client.close()
