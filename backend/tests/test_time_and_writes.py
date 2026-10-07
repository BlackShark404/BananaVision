"""Timezone and persistence contracts through real routes without a live database."""

import csv
import io
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import DateTime, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.v1 import activity, config, intakes, quality, scans, suppliers, users
from app.core import database
from app.core.db_types import ManilaDateTime
from app.core.time import MANILA, as_manila, business_day_bounds, input_manila, now_manila
from app.models import (
    ActivityLog, AdminProfile, Intake, OperatorProfile, Scan, ScanClassification,
    ScanNote, ScanStatusLog, Supplier, SystemConfig, UserAccount, UserRole,
)
from app.schemas.enums import (
    ActiveStatusEnum, CultivarEnum, IntakeStatusEnum, InventoryStatusEnum, RipenessEnum,
)
from app.schemas.timestamps import InputTimestamp, Timestamp


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, compiler, **kwargs):
    return "JSON"


class SessionAdapter:
    """Use a real SQLite transaction behind the production async dependency."""

    def __init__(self, engine, state):
        self.session = Session(engine, expire_on_commit=False)
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.session.close()

    def add(self, value):
        self.session.add(value)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def flush(self):
        self.session.flush()

    async def delete(self, value):
        self.session.delete(value)

    async def commit(self):
        self.state.events.append("commit")
        if self.state.fail_commit:
            raise RuntimeError("Simulated database persistence failure")
        self.session.commit()

    async def rollback(self):
        self.state.events.append("rollback")
        self.session.rollback()

    async def close(self):
        self.session.close()


@pytest.fixture
def application(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    database.Base.metadata.create_all(engine)
    state = SimpleNamespace(fail_commit=False, events=[])
    monkeypatch.setattr(database, "async_session_factory", lambda: SessionAdapter(engine, state))
    ids = SimpleNamespace(admin=uuid4(), operator=uuid4(), profile=uuid4(), supplier=uuid4(),
                          intake=uuid4(), scan=uuid4())
    historical = datetime(2025, 1, 1, 16, 30, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add_all([UserRole(id=1, name="Admin"), UserRole(id=2, name="Operator")])
        db.flush()
        db.add_all([
            UserAccount(id=ids.admin, role_id=1, username="admin", full_name="Admin User", password_hash="unused"),
            UserAccount(id=ids.operator, role_id=2, username="operator", full_name="Original Name", password_hash="unused"),
        ])
        db.flush()
        db.add_all([AdminProfile(account_id=ids.admin), OperatorProfile(id=ids.profile, account_id=ids.operator),
                    Supplier(id=ids.supplier, name="Original Supplier")])
        db.flush()
        db.add(Intake(id=ids.intake, supplier_id=ids.supplier, source="Original Supplier",
                      intake_date=date(2025, 1, 2)))
        db.flush()
        db.add(Scan(id=ids.scan, operator_id=ids.profile, intake_id=ids.intake,
                    date_time=historical, flagged=False))
        db.flush()
        db.add_all([
            ScanClassification(scan_id=ids.scan, cultivar=CultivarEnum.LAKATAN,
                               ripeness=RipenessEnum.RIPE, confidence=90, spoilage_days="3", finger_count=5),
            ScanStatusLog(scan_id=ids.scan, inventory_status=InventoryStatusEnum.IN_STOCK,
                          updated_at=historical),
            SystemConfig(confidence_threshold=85, camera_ids="CAM-001, CAM-002, CAM-003, CAM-004", data_retention_enabled=True),
        ])
        db.commit()

    app = FastAPI()
    for router in (scans.router, suppliers.router, users.router, intakes.router,
                   config.router, activity.router, quality.router):
        app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=ids.admin, full_name="Admin User", role=SimpleNamespace(name="Admin"),
    )

    class ResponseObserver:
        async def __call__(self, scope, receive, send):
            async def observe(message):
                if message["type"] == "http.response.start":
                    state.events.append(f"response:{message['status']}")
                await send(message)
            await app(scope, receive, observe)

    with TestClient(ResponseObserver(), raise_server_exceptions=False) as client:
        yield SimpleNamespace(app=app, engine=engine, state=state, client=client, ids=ids,
                              historical=historical)
    engine.dispose()


def test_timezone_preserves_instants_and_input_interpretation():
    original = datetime(2025, 1, 1, 16, 30, tzinfo=timezone.utc)
    normalized = as_manila(original)
    assert normalized == original
    assert normalized.isoformat() == "2025-01-02T00:30:00+08:00"
    assert as_manila(original.replace(tzinfo=None)) == original
    assert input_manila(datetime(2025, 1, 2, 0, 30)) == original
    assert TypeAdapter(Timestamp).validate_python(original).isoformat() == normalized.isoformat()
    assert TypeAdapter(InputTimestamp).validate_python("2025-01-02T00:30:00") == original
    assert now_manila().utcoffset() == timedelta(hours=8)
    start, end = business_day_bounds(date(2025, 1, 2))
    assert start == datetime(2025, 1, 1, 16, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)
    # Every ORM timestamp participates in the centralized conversion.
    timestamp_columns = [column for table in database.Base.metadata.tables.values()
                         for column in table.columns
                         if isinstance(column.type, (DateTime, ManilaDateTime))]
    assert timestamp_columns
    assert all(isinstance(column.type, ManilaDateTime) for column in timestamp_columns)


def test_history_pagination_preserves_old_instants_incomplete_rows_and_csv(application):
    app = application
    with Session(app.engine) as db:
        for index in range(31):
            db.add(Scan(operator_id=app.ids.profile, date_time=app.historical + timedelta(minutes=index)))
        db.commit()
    records = []
    for page in range(1, 5):
        response = app.client.get("/api/v1/scans", params={"page": page, "page_size": 10})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 32 and data["page_size"] == 10 and data["page"] == page
        records.extend(data["items"])
    assert len(records) == len({row["id"] for row in records}) == 32
    assert all(row["date_time"].startswith("2025-01-02T") for row in records)
    assert all(row["date_time"].endswith("+08:00") for row in records)
    ordering = [(row["date_time"], row["id"]) for row in records]
    assert ordering == sorted(ordering, reverse=True)
    incomplete = next(row for row in records if row["id"] != str(app.ids.scan))
    assert incomplete["cultivar"] is incomplete["confidence"] is incomplete["spoilage_days"] is None
    assert incomplete["inventory_status"] == "In Stock"
    detail = app.client.get(f"/api/v1/scans/{incomplete['id']}")
    assert detail.status_code == 200 and detail.json()["date_time"] == incomplete["date_time"]
    exported = app.client.get("/api/v1/config/export")
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 32
    assert all(row["Date Time (UTC+08:00)"].endswith("+08:00") for row in rows)
    assert [(row["Date Time (UTC+08:00)"], row["Scan ID"]) for row in rows] == sorted(ordering)


@pytest.mark.parametrize("vpd", [0, None, 1.25])
def test_trigger_response_preserves_zero_and_missing_vpd(application, monkeypatch, vpd):
    app = application
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )

    async def persisted_scan(**kwargs):
        scan = (await kwargs["db"].execute(select(Scan).where(Scan.id == app.ids.scan))).scalar_one()
        scan.classification.vpd = vpd
        return scan

    monkeypatch.setattr(scans, "execute_scan_pipeline", persisted_scan)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 200, response.text
    assert response.json()["vpd"] == vpd
    detail = app.client.get(f"/api/v1/scans/{app.ids.scan}")
    assert detail.status_code == 200 and detail.json()["vpd"] == vpd


def test_quality_queue_distinguishes_missing_classification_from_zero_confidence(application):
    app = application
    incomplete_id = uuid4()
    with Session(app.engine) as db:
        classified = db.get(Scan, app.ids.scan)
        classified.flagged = True
        classified.classification.confidence = 0
        db.add(Scan(id=incomplete_id, operator_id=app.ids.profile,
                    date_time=app.historical, flagged=True))
        db.commit()

    response = app.client.get("/api/v1/quality/flagged")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2 and payload["page"] == 1 and payload["page_size"] == 20
    rows = {row["id"]: row for row in payload["items"]}
    incomplete = rows[str(incomplete_id)]
    assert incomplete["cultivar"] is incomplete["ripeness"] is incomplete["confidence"] is None
    assert rows[str(app.ids.scan)]["confidence"] == 0
    assert rows[str(app.ids.scan)]["cultivar"] == "Lakatan"
    assert incomplete["scanned_at"].endswith("+08:00")


@pytest.mark.parametrize("operation", [
    "flag", "note", "supplier_create", "supplier_update", "user_update",
    "intake_create", "intake_status", "inventory_status", "bulk_inventory", "settings",
])
@pytest.mark.parametrize("fail_commit", [False, True])
def test_http_write_only_succeeds_after_commit_and_failure_rolls_back(application, operation, fail_commit):
    app, ids = application, application.ids
    endpoint, method, body = {
        "flag": (f"scans/{ids.scan}/flag", "patch", {"flagged": True}),
        "note": (f"scans/{ids.scan}/notes", "post", {"note": "Review note"}),
        "supplier_create": ("suppliers", "post", {"name": "New Supplier"}),
        "supplier_update": (f"suppliers/{ids.supplier}", "patch", {"name": "Renamed Supplier"}),
        "user_update": (f"users/{ids.operator}", "patch", {"full_name": "Renamed User"}),
        "intake_create": ("intakes", "post", {"source": "New Source", "supplier_id": str(ids.supplier)}),
        "intake_status": (f"intakes/{ids.intake}/status", "patch", {"status": "Depleted"}),
        "inventory_status": (f"scans/{ids.scan}/status", "patch", {"inventory_status": "Sold"}),
        "bulk_inventory": (f"intakes/{ids.intake}/bulk-inventory", "patch", {"inventory_status": "Sold"}),
        "settings": ("config", "patch", {"confidence_threshold": 95, "expected_revision": 1}),
    }[operation]
    app.state.fail_commit = fail_commit
    response = getattr(app.client, method)(f"/api/v1/{endpoint}", json=body)
    if fail_commit:
        assert response.status_code == 500, response.text
        assert app.state.events == ["commit", "rollback", "response:500"]
    else:
        assert 200 <= response.status_code < 300, response.text
        assert app.state.events == ["commit", f"response:{response.status_code}"]

    with Session(app.engine) as db:
        saved = not fail_commit
        assert db.get(Scan, ids.scan).flagged == (saved and operation == "flag")
        assert db.scalar(select(func.count()).select_from(ScanNote)) == int(saved and operation == "note")
        assert db.scalar(select(func.count()).select_from(Supplier)) == 1 + int(saved and operation == "supplier_create")
        assert db.get(Supplier, ids.supplier).name == ("Renamed Supplier" if saved and operation == "supplier_update" else "Original Supplier")
        assert db.get(UserAccount, ids.operator).full_name == ("Renamed User" if saved and operation == "user_update" else "Original Name")
        assert db.scalar(select(func.count()).select_from(Intake)) == 1 + int(saved and operation == "intake_create")
        assert db.get(Intake, ids.intake).status == (IntakeStatusEnum.DEPLETED if saved and operation in {"intake_status", "bulk_inventory"} else IntakeStatusEnum.ACTIVE)
        assert db.scalar(select(func.count()).select_from(ScanStatusLog)) == 1 + int(saved and operation in {"inventory_status", "bulk_inventory"})
        assert db.scalar(select(SystemConfig.confidence_threshold)) == (95 if saved and operation == "settings" else 85)
        assert db.get(Scan, ids.scan).date_time == app.historical


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_commit", [False, True])
@pytest.mark.parametrize("detection_values", [(0, 0), (None, None), (50, 1)])
async def test_scan_pipeline_never_announces_completion_before_persistence(application, monkeypatch, fail_commit, detection_values):
    from app.services import scan_service
    from app.ws import events

    app = application
    messages = []

    async def send(room, event, data):
        app.state.events.append(event)
        messages.append((room, event, data))

    capture = SimpleNamespace(camera_id="CAM-001", camera_label="Camera 1", file_path=None, frame=None)

    async def capture_all():
        return [capture]

    result = SimpleNamespace(cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.RIPE,
                             confidence=50, finger_count=5, detections=[], inference_time_ms=1,
                             auto_flagged=True, conflict_detected=False, camera_count=1)
    detection_result = SimpleNamespace(**vars(result))
    detection_result.confidence, detection_result.inference_time_ms = detection_values
    monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(
        online_cameras=[0], capture_all=capture_all, save_captures=lambda captures, _: captures,
    ))
    monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
        detect=lambda _: SimpleNamespace(banana_detected=True),
    ))
    monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(predict=lambda _, **kwargs: detection_result))
    monkeypatch.setattr(scan_service, "fusion_engine", SimpleNamespace(fuse=lambda _: result))
    monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(predict=lambda **_: "1"))
    monkeypatch.setattr(scan_service, "sensor_reader", SimpleNamespace(latest=None))
    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", send)
    app.state.fail_commit = fail_commit
    async with SessionAdapter(app.engine, app.state) as db:
        if fail_commit:
            with pytest.raises(RuntimeError, match="persistence failure"):
                await scan_service.execute_scan_pipeline(db, app.ids.profile, app.ids.operator, "Operator")
            await db.rollback()
            assert events.SCAN_COMPLETED not in app.state.events
            assert events.NOTIFICATION not in app.state.events
            assert events.SCAN_FAILED in app.state.events
        else:
            created = await scan_service.execute_scan_pipeline(db, app.ids.profile, app.ids.operator, "Operator")
            assert app.state.events.index("commit") < app.state.events.index(events.SCAN_COMPLETED)
            completed = next(data for _, event, data in messages if event == events.SCAN_COMPLETED)
            assert completed["date_time"] == created.date_time.isoformat()
            assert completed["date_time"].endswith("+08:00")
            assert completed["status_updated_at"].endswith("+08:00")
            assert completed["detections"][0]["confidence"] == detection_values[0]
            assert completed["detections"][0]["inference_time_ms"] == detection_values[1]
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(Scan)) == (1 if fail_commit else 2)


@pytest.mark.asyncio
async def test_camera_monitor_retries_persistence_failure_before_announcing_status(monkeypatch):
    from app.core import startup

    tasks, events = [], []
    calls = {"sleep": 0, "probe": 0, "commit": 0}

    def capture_task(coroutine):
        tasks.append(coroutine)
        return coroutine

    async def no_sensor(_callback):
        pass

    async def tick(_delay):
        calls["sleep"] += 1
        if calls["sleep"] > 2:
            raise asyncio.CancelledError

    def probe():
        calls["probe"] += 1
        return {0: calls["probe"] > 1}

    class Loop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    class CameraSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def add(self, _device):
            pass

        async def commit(self):
            calls["commit"] += 1
            if calls["commit"] == 1:
                events.append("commit:failed")
                raise RuntimeError("Database temporarily unavailable")
            events.append("commit:saved")

    async def send(room, _event, data):
        assert data["last_seen"].endswith("+08:00")
        events.append(f"ws:{room}")

    monkeypatch.setattr(startup.asyncio, "create_task", capture_task)
    monkeypatch.setattr(startup.asyncio, "sleep", tick)
    monkeypatch.setattr(startup.asyncio, "get_event_loop", lambda: Loop())
    monkeypatch.setattr(startup, "sensor_reader", SimpleNamespace(start_polling=no_sensor))
    monkeypatch.setattr(startup, "camera_manager", SimpleNamespace(probe_all=probe, _get_camera_id=lambda _: "CAM-001"))
    monkeypatch.setattr(startup, "settings", SimpleNamespace(camera_device_ids=[0], camera_labels=["Camera 1"]))
    monkeypatch.setattr(startup, "async_session_factory", CameraSession)
    monkeypatch.setattr(startup.ws_manager, "send_to_room", send)
    await startup.start_background_tasks()
    for task in tasks[:-1]:
        task.close()
    with pytest.raises(asyncio.CancelledError):
        await tasks[-1]
    assert calls["commit"] == 2
    assert events == ["commit:failed", "commit:saved", "ws:devices", "ws:dashboard"]
