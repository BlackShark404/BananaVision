"""DHT22 serial accuracy, validation, smoothing, freshness, and continuous exposure tests."""

# Imported pytest fixtures intentionally share names with test parameters.
# ruff: noqa: F811

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import scan_logs as logs_api
from app.core.database import Base, get_db, get_stream_db
from app.core.time import MANILA, as_manila
from app.models import ScanClassification, SensorReading
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum, TreatmentEnum
from app.schemas.scan_logs import ScanLogQuery
from app.services import analytics, dashboard, scan_logs, scan_records, scan_service, sensor_reader
from app.services.sensor_exposure import compute_exposure, load_hourly_sensor_buckets
from app.services.sensor_reader import (
    SensorData,
    SensorReader,
    freshness_window_seconds,
    is_valid_dht22,
    resolve_scan_sensor_reading,
)
from tests.test_analytics import analytics_db  # noqa: F401
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_exports import workbook_table
from tests.test_scan_logs import logs_db  # noqa: F401
from tests.test_time_and_writes import application  # noqa: F401


class FakeSerialPort:
    """In-memory serial stub simulating queued 2s DHT22 lines behind a 5s poll."""

    def __init__(self, queued_lines):
        self._lines = list(queued_lines)
        self.is_open = True

    @property
    def in_waiting(self):
        return sum(len(line) for line in self._lines)

    def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)

    def reset_input_buffer(self):
        self._lines.clear()

    def close(self):
        self.is_open = False


def test_read_once_drains_serial_backlog_to_newest_valid_line():
    reader = SensorReader()
    reader._connected = True
    reader._serial = FakeSerialPort([
        b"TEMP:25.0,HUM:60.0\n",
        b"TEMP:26.1,HUM:62.5\n",
        b"TEMP:27.4,HUM:65.2\n",
        b"TEMP:30.25,HUM:71.45\n",
        b"ERROR: Failed to read from DHT sensor!\n",
    ])
    reading = reader.read_once()
    assert reading is not None
    assert reading.temperature == 30.25
    assert reading.humidity == 71.45
    assert reader._serial.in_waiting == 0


@pytest.mark.parametrize(
    "line",
    [
        "TEMP:nan,HUM:72.0",
        "TEMP:inf,HUM:70.0",
        "TEMP:-inf,HUM:70.0",
        "TEMP:26.0,HUM:999.0",
        "TEMP:26.0,HUM:-0.5",
        "TEMP:-41.0,HUM:50.0",
        "TEMP:81.0,HUM:50.0",
        "ERROR: Sensor timeout",
        "BAD_FORMAT",
    ],
)
def test_parse_line_rejects_malformed_nonfinite_and_out_of_range_dht22_values(line):
    reader = SensorReader()
    assert reader._parse_line(line) is None
    assert reader.latest is None
    assert is_valid_dht22(float("nan"), 50.0) is False
    assert is_valid_dht22(25.0, 105.0) is False
    assert is_valid_dht22(True, 50.0) is False


def test_calibration_offsets_and_humidity_clamping(monkeypatch):
    monkeypatch.setattr(sensor_reader.settings, "sensor_temp_offset", -1.5)
    monkeypatch.setattr(sensor_reader.settings, "sensor_humidity_offset", 5.0)
    reader = SensorReader()
    parsed = reader._parse_line("TEMP:30.0,HUM:97.2")
    assert parsed is not None
    assert parsed.temperature == 28.5
    assert parsed.humidity == 100.0


def test_scan_reading_uses_trimmed_mean_and_rejects_stale_or_disconnected(monkeypatch):
    monkeypatch.setattr(sensor_reader.settings, "sensor_smoothing_window", 5)
    monkeypatch.setattr(sensor_reader.settings, "sensor_smoothing_max_age_s", 30)
    now = datetime(2026, 11, 26, 12, 0, 30, tzinfo=MANILA)
    reader = SensorReader()
    reader._connected = True
    samples = [
        SensorData(28.0, 70.0, now - timedelta(seconds=16)),
        SensorData(28.2, 70.4, now - timedelta(seconds=12)),
        SensorData(42.0, 99.0, now - timedelta(seconds=8)),  # spike
        SensorData(28.1, 70.2, now - timedelta(seconds=4)),
        SensorData(28.3, 70.6, now),
    ]
    reader._recent.extend(samples)
    reader._latest = samples[-1]

    smoothed = resolve_scan_sensor_reading(reader, now=now)
    assert smoothed is not None
    # Trimmed mean drops 28.0 & 42.0 -> averages (28.1, 28.2, 28.3) = 28.2.
    assert smoothed.temperature == 28.2
    # Trimmed mean drops 70.0 & 99.0 -> averages (70.2, 70.4, 70.6) = 70.4.
    assert smoothed.humidity == 70.4

    # Stale reading (> freshness_window_seconds) is rejected.
    stale_time = now + timedelta(seconds=freshness_window_seconds() + 1)
    assert resolve_scan_sensor_reading(reader, now=stale_time) is None

    # Disconnected reader never reuses old cached readings.
    reader._connected = False
    assert resolve_scan_sensor_reading(reader, now=now) is None


def test_serial_disconnect_exception_marks_reader_offline():
    class DisconnectingSerial:
        in_waiting = 0
        is_open = True

        def readline(self):
            raise OSError("Device disconnected")

        def close(self):
            self.is_open = False

    reader = SensorReader()
    reader._connected = True
    reader._serial = DisconnectingSerial()
    assert reader.read_once() is None
    assert reader.is_connected is False


def test_scan_pipeline_rejects_stale_sensor_reading_instead_of_freezing_it(application, monkeypatch):
    app = application
    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=MANILA)
    stale_reader = SensorReader()
    stale_reader._connected = True
    stale_data = SensorData(33.3, 78.8, now - timedelta(minutes=10))
    stale_reader._latest = stale_data
    stale_reader._recent.append(stale_data)

    captures = [
        SimpleNamespace(camera_id="CAM-001", camera_label="Top", frame=None, file_path=None),
    ]

    async def capture_all():
        return captures

    result = SimpleNamespace(
        cultivar="Lakatan", ripeness="Unripe", confidence=95, finger_count=10,
        detections=[], inference_time_ms=1, auto_flagged=False,
        conflict_detected=False, camera_count=1,
    )
    predict_calls = []

    def fake_predict(**kwargs):
        predict_calls.append(kwargs)
        return "7"

    monkeypatch.setattr(scan_service, "now_manila", lambda: now)
    monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(
        online_cameras=[0], capture_all=capture_all, save_captures=lambda f, _: f,
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
    monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(predict=fake_predict))
    monkeypatch.setattr(scan_service, "sensor_reader", stale_reader)
    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", lambda *a, **k: _noop())

    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Op", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(app.ids.intake)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["temperature"] is None
    assert body["humidity"] is None
    assert body["vpd"] is None
    assert predict_calls[0]["temperature"] is None
    assert predict_calls[0]["humidity"] is None


async def _noop():
    return None


def test_latest_sensor_route_ignores_out_of_range_db_rows(application):
    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=MANILA)
    with Session(application.engine) as session:
        session.add(SensorReading(temperature=27.5, humidity=74.0, recorded_at=now - timedelta(seconds=10)))
        session.add(SensorReading(temperature=28.0, humidity=999.0, recorded_at=now - timedelta(seconds=2)))
        session.commit()
    res = application.client.get("/api/v1/sensors/latest")
    assert res.status_code == 200
    assert res.json()["temperature"] == 27.5
    assert res.json()["humidity"] == 74.0


@pytest.mark.asyncio
async def test_continuous_exposure_adjusts_shelf_life_ripeness_alerts_analytics_and_exports(
    logs_db, monkeypatch,
):
    Base.metadata.create_all(logs_db.session.get_bind(), checkfirst=True)
    admin = account(logs_db, role="Admin", name="Station Admin")
    owner = account(logs_db, name="Kiosk Operator")
    scanned_at = NOW - timedelta(days=3)

    # Scan A: Unripe Lakatan scanned 3 days ago at cool 24C / 60% RH with 6.5d baseline.
    # Under continuous 34C / 70% RH storage, Q10 (~2x) ages 3 calendar days -> ~6 biological days,
    # pushing remaining_days from ~3.5 down to <= 0.5 (At-Risk) and advancing ripeness to Overripe.
    hot_scan_id = scan(
        logs_db, owner, at=scanned_at, source="Warm Room", prediction="6.5", confidence=92.0,
    )
    logs_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == hot_scan_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
            temperature=24.0, humidity=60.0, treatment=TreatmentEnum.NATURAL,
        )
    )

    # Scan B: Same conditions, but Sold -> must remain frozen on staff views.
    sold_id = scan(
        logs_db, owner, at=scanned_at, source="Sold Warm", prediction="6.5", confidence=90.0,
        statuses=[(NOW, InventoryStatusEnum.SOLD)],
    )
    logs_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == sold_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
            temperature=24.0, humidity=60.0, treatment=TreatmentEnum.NATURAL,
        )
    )

    # Hourly DHT22 SensorReading rows across all 72 hours at 34.0C / 70.0% RH.
    for hour_idx in range(72):
        logs_db.session.add(SensorReading(
            temperature=34.0,
            humidity=70.0,
            recorded_at=scanned_at + timedelta(hours=hour_idx, minutes=30),
        ))
    logs_db.session.flush()

    monkeypatch.setattr(dashboard, "now_manila", lambda: NOW)
    monkeypatch.setattr(analytics, "now_manila", lambda: NOW)
    monkeypatch.setattr(scan_records, "now_manila", lambda: NOW)

    buckets = await load_hourly_sensor_buckets(logs_db, scanned_at, NOW)
    assert len(buckets) >= 72
    exposure = compute_exposure(
        scanned_at, NOW, ref_temperature=24.0, ref_humidity=60.0, buckets=buckets,
    )
    assert exposure is not None
    assert exposure.biological_elapsed_days > 5.5
    assert exposure.exposure_offset_days >= 3
    assert exposure.avg_temperature == pytest.approx(34.0)
    assert exposure.avg_humidity == pytest.approx(70.0)

    # Matching reference conditions produce exact 1.0x rate and 0 offset.
    same_cond = compute_exposure(
        scanned_at, NOW, ref_temperature=34.0, ref_humidity=70.0, buckets=buckets,
    )
    assert same_cond.exposure_offset_days == 0
    assert same_cond.biological_elapsed_days == pytest.approx(3.0, abs=0.05)

    # Dashboard, Scan Logs, Analytics, Scan Detail, and XLSX export all agree.
    dash_summary = await dashboard.get_summary(logs_db, admin)
    assert dash_summary.expiring_stock_count == 1
    assert dash_summary.fifo_recommendations[0].earliest_remaining_days <= 2.0

    expiring_dash = await dashboard.list_scans(logs_db, admin, view="expiring")
    assert [row.id for row in expiring_dash.items] == [hot_scan_id]

    logs_page = await scan_logs.list_scan_logs(
        logs_db, admin, ScanLogQuery(attention="at-risk", page_size=50),
    )
    assert logs_page.at_risk_count == 1
    assert [row.id for row in logs_page.items] == [hot_scan_id]
    hot_row = logs_page.items[0]
    assert hot_row.remaining_days <= 2.0
    assert hot_row.shelf_life_window.elapsed_days >= 6
    assert hot_row.ripeness_projection.current_ripeness == "Overripe"

    # Sold row stays frozen for staff.
    all_logs = await scan_logs.list_scan_logs(logs_db, admin, ScanLogQuery(page_size=50))
    sold_row = next(r for r in all_logs.items if r.id == sold_id)
    assert sold_row.ripeness_projection.current_ripeness == "Unripe"
    assert sold_row.ripeness_projection.progressed is False

    detail_scan = await scan_records.load_authorized_scan(logs_db, hot_scan_id, admin)
    detail = await scan_records.serialize_detail(logs_db, detail_scan, admin)
    assert detail.storage_exposure is not None
    assert detail.storage_exposure.avg_temperature == pytest.approx(34.0)
    assert detail.ripeness_projection.current_ripeness == "Overripe"

    # Export reflects exposure-adjusted current ripeness and freshness.
    app = FastAPI()
    app.include_router(logs_api.router, prefix="/api/v1")

    async def database():
        yield logs_db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_stream_db] = database
    app.dependency_overrides[get_current_user] = lambda: admin
    monkeypatch.setattr(logs_api.audit, "emit", lambda *a, **k: _noop())

    with TestClient(app) as client:
        xlsx_res = client.get("/api/v1/scan-logs/export", params={"format": "xlsx", "attention": "at-risk"})
        assert xlsx_res.status_code == 200
        _, data = workbook_table(xlsx_res.content)
        assert len(data) == 1
        assert data[0][2] == "Warm Room"
        assert data[0][4:6] == ["Unripe", "Est. Overripe"]


@pytest.mark.asyncio
async def test_continuous_exposure_updates_analytics_at_risk_count(analytics_db, monkeypatch):
    Base.metadata.create_all(analytics_db.session.get_bind(), checkfirst=True)
    admin = account(analytics_db, role="Admin", name="Analytics Admin")
    owner = account(analytics_db, name="Analytics Operator")
    scanned_at = NOW - timedelta(days=3)

    hot_scan_id = scan(
        analytics_db, owner, at=scanned_at, source="Warm Storage", prediction="6.5", confidence=92.0,
    )
    analytics_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == hot_scan_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
            temperature=24.0, humidity=60.0, treatment=TreatmentEnum.NATURAL,
        )
    )
    for hour_idx in range(72):
        analytics_db.session.add(SensorReading(
            temperature=34.0,
            humidity=70.0,
            recorded_at=scanned_at + timedelta(hours=hour_idx, minutes=30),
        ))
    analytics_db.session.flush()
    monkeypatch.setattr(analytics, "now_manila", lambda: NOW)

    summary = await analytics.get_summary(analytics_db, admin, date_range="all")
    assert summary.at_risk_count == 1


@pytest.mark.asyncio
async def test_postgresql_hourly_buckets_and_partial_schema_guard():
    import os
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.database import Base as AppBase

    url = os.environ.get("BANANAVISION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable PostgreSQL required")

    schema = "qa_sensor_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema, "timezone": "Asia/Manila"}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # Empty schema: _sensor_reading_table_available must return False without aborting tx.
        async with sessions() as db:
            now = datetime(2026, 11, 26, 12, 0, tzinfo=MANILA)
            assert await load_hourly_sensor_buckets(db, now - timedelta(hours=2), now) == []
            assert (await db.scalar(text("SELECT 1"))) == 1

        async with engine.begin() as conn:
            await conn.run_sync(AppBase.metadata.create_all)

        async with sessions() as db:
            now = datetime(2026, 11, 26, 12, 0, tzinfo=MANILA)
            start = now - timedelta(hours=3)
            db.add_all([
                SensorReading(temperature=33.0, humidity=70.0, recorded_at=start + timedelta(minutes=10)),
                SensorReading(temperature=35.0, humidity=74.0, recorded_at=start + timedelta(minutes=40)),
                SensorReading(temperature=34.0, humidity=999.0, recorded_at=start + timedelta(minutes=50)),
            ])
            await db.commit()
            buckets = await load_hourly_sensor_buckets(db, start, now)
            assert len(buckets) == 1
            assert buckets[0].avg_temp == pytest.approx(34.0)
            assert buckets[0].avg_humidity == pytest.approx(72.0)
            assert buckets[0].sample_count == 2
            assert buckets[0].last_recorded_at == as_manila(start + timedelta(minutes=40))
    finally:
        await engine.dispose()
        async with control.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await control.dispose()


def test_exposure_ignores_prescan_only_buckets_and_sparse_coverage():
    from app.services.sensor_exposure import HourlySensorBucket

    scanned_at = datetime(2026, 11, 26, 10, 45, tzinfo=MANILA)
    # Single bucket in the scan hour whose latest reading occurred BEFORE scanned_at.
    prescan_bucket = HourlySensorBucket(
        hour_start=datetime(2026, 11, 26, 10, 0, tzinfo=MANILA),
        avg_temp=36.0,
        avg_humidity=85.0,
        sample_count=3,
        last_recorded_at=datetime(2026, 11, 26, 10, 15, tzinfo=MANILA),
    )
    assert compute_exposure(
        scanned_at,
        scanned_at + timedelta(minutes=30),
        ref_temperature=24.0,
        ref_humidity=60.0,
        buckets=[prescan_bucket],
    ) is None

    # A brief 1-hour burst across a 24-hour span (<25% coverage) must not skew full-day baseline.
    brief_post_scan = HourlySensorBucket(
        hour_start=datetime(2026, 11, 26, 11, 0, tzinfo=MANILA),
        avg_temp=36.0,
        avg_humidity=85.0,
        sample_count=6,
        last_recorded_at=datetime(2026, 11, 26, 11, 50, tzinfo=MANILA),
    )
    assert compute_exposure(
        scanned_at,
        scanned_at + timedelta(days=1),
        ref_temperature=24.0,
        ref_humidity=60.0,
        buckets=[brief_post_scan],
    ) is None

    # Continuous coverage across the monitored span (>=25%) remains active.
    assert compute_exposure(
        scanned_at,
        scanned_at + timedelta(hours=2),
        ref_temperature=24.0,
        ref_humidity=60.0,
        buckets=[brief_post_scan],
    ) is not None
