"""Live ripeness projection, RFR monotonicity, scan_logs ripeness_scope, and invariance tests."""

# Imported pytest fixtures intentionally share names with test parameters.
# ruff: noqa: F811

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.deps import get_current_user
from app.api.v1 import scan_logs as logs_api
from app.core.database import Base, get_db, get_stream_db
from app.core.time import MANILA
from app.models.scan_classification import ScanClassification
from app.models.scan_history import ScanEvent
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum, TreatmentEnum
from app.schemas.scan_logs import ScanLogQuery
from app.services import analytics, auth_service, scan_logs, scan_snapshots
from app.services.inventory_policy import ripeness_projection
from app.services.spoilage import SpoilagePredictor
from tests.test_analytics import analytics_db  # noqa: F401
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_exports import extract_pdf_text, workbook_table
from tests.test_scan_logs import logs_db  # noqa: F401


def test_real_rfr_stage_lifetimes_are_monotonic_and_batched_single_thread():
    predictor = SpoilagePredictor()
    predictor.load()
    assert predictor.is_loaded is True
    assert predictor.uses_enhanced_features is True
    assert getattr(predictor._model, "n_jobs", None) == 1

    for temp, hum in ((24.0, 60.0), (28.0, 75.0)):
        for treatment in ("Natural", "Ethephon"):
            for cultivar in ("Lakatan", "Latundan", "Cardaba"):
                u, sr, r, o = predictor.stage_lifetimes(
                    cultivar, temperature=temp, humidity=hum, treatment=treatment,
                )
                assert u > sr > r > o > 0, (temp, hum, treatment, cultivar, (u, sr, r, o))

    # Repeated calls with the same rounded environment hit the LRU cache.
    info_before = predictor._cached_stage_lifetimes.cache_info()
    first = predictor.stage_lifetimes(
        "Lakatan", temperature=24.04, humidity=60.02, treatment="Natural",
    )
    second = predictor.stage_lifetimes(
        "Lakatan", temperature=24.01, humidity=60.04, treatment="Natural",
    )
    info_after = predictor._cached_stage_lifetimes.cache_info()
    assert first == second
    assert info_after.hits >= info_before.hits + 1


def test_fallback_stage_lifetimes_are_strictly_monotonic_without_model():
    predictor = SpoilagePredictor()  # Not loaded -> fallback mode
    assert predictor.is_loaded is False
    for temp in (18.0, 24.0, 32.0):
        for hum in (45.0, 70.0, 90.0):
            for treatment in ("Natural", "Ethephon"):
                for cultivar in ("Lakatan", "Latundan", "Cardaba", None):
                    u, sr, r, o = predictor.stage_lifetimes(
                        cultivar, temperature=temp, humidity=hum, treatment=treatment,
                    )
                    assert u > sr > r > o > 0


def test_ripeness_projection_day0_manila_midnight_override_and_closed_freeze():
    predictor = SpoilagePredictor()
    predictor.load()
    scanned = datetime(2026, 10, 2, 14, 0, tzinfo=MANILA)

    # Unripe Lakatan Natural at 24C/60% RH -> RFR ~ (14.40, 7.88, 5.13, 1.19)
    # Transitions: Semi Ripe day 7, Ripe day 10, Overripe day 14.
    day0 = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        datetime(2026, 10, 2, 23, 59, 59, tzinfo=MANILA),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert day0 is not None
    assert day0["current_ripeness"] == "Unripe" and day0["progressed"] is False
    assert day0["transitions"] == {"Semi Ripe": 7, "Ripe": 10, "Overripe": 14}

    # Manila midnight boundary before vs at Semi Ripe transition (day 6 vs day 7).
    day6_late = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        datetime(2026, 10, 8, 23, 59, 59, tzinfo=MANILA),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    day7_midnight = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        datetime(2026, 10, 9, 0, 0, 0, tzinfo=MANILA),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert day6_late["current_ripeness"] == "Unripe" and day6_late["progressed"] is False
    assert day7_midnight["current_ripeness"] == "Semi Ripe" and day7_midnight["progressed"] is True

    day10 = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        datetime(2026, 10, 12, 0, 0, 0, tzinfo=MANILA),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert day10["current_ripeness"] == "Ripe" and day10["progressed"] is True

    day15 = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        datetime(2026, 10, 17, 12, 0, 0, tzinfo=MANILA),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert day15["current_ripeness"] == "Overripe" and day15["progressed"] is True

    # Admin override with shorter heuristic range ("4-6", midpoint 5.0) must stay anchored on Day 0
    # and scale proportionally rather than jumping straight to Ripe on Day 0.
    override_day0 = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "4-6", scanned, scanned,
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert override_day0["current_ripeness"] == "Unripe" and override_day0["progressed"] is False
    assert override_day0["transitions"]["Semi Ripe"] >= 1
    tr = override_day0["transitions"]
    assert tr["Semi Ripe"] <= tr["Ripe"] <= tr["Overripe"] <= 5

    override_day5 = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "4-6", scanned,
        scanned + timedelta(days=5),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.IN_STOCK, predictor=predictor,
    )
    assert override_day5["current_ripeness"] == "Overripe" and override_day5["progressed"] is True

    # Closed statuses freeze at scanned ripeness; Public QR (respect_closed_status=False) advances.
    closed_statuses = (
        InventoryStatusEnum.SOLD,
        InventoryStatusEnum.FOR_PROCESSING,
        InventoryStatusEnum.SPOILED,
    )
    for status in closed_statuses:
        frozen = ripeness_projection(
            RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
            scanned + timedelta(days=12),
            temperature=24.0, humidity=60.0, treatment="Natural",
            inventory_status=status, predictor=predictor,
        )
        assert frozen["current_ripeness"] == "Unripe"
        assert frozen["progressed"] is False
        assert frozen["transitions"] == {}

    public_view = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "14.4", scanned,
        scanned + timedelta(days=10),
        temperature=24.0, humidity=60.0, treatment="Natural",
        inventory_status=InventoryStatusEnum.SOLD,
        respect_closed_status=False, predictor=predictor,
    )
    assert public_view["current_ripeness"] == "Ripe" and public_view["progressed"] is True

    # Missing ripeness -> None; Overripe -> no transitions; invalid spoilage -> stays at base.
    assert ripeness_projection(None, CultivarEnum.LAKATAN, "5", scanned, scanned) is None
    overripe = ripeness_projection(
        RipenessEnum.OVERRIPE, CultivarEnum.LAKATAN, "1", scanned, scanned + timedelta(days=2),
    )
    assert (
        overripe["current_ripeness"] == "Overripe"
        and overripe["progressed"] is False
        and overripe["transitions"] == {}
    )
    unknown_spoil = ripeness_projection(
        RipenessEnum.UNRIPE, CultivarEnum.LAKATAN, "Unknown", scanned, scanned + timedelta(days=20),
    )
    assert unknown_spoil["current_ripeness"] == "Unripe" and unknown_spoil["progressed"] is False


@pytest.mark.asyncio
async def test_scan_logs_ripeness_scope_current_snapshots_reconcile_pending_and_exports_parity(
    logs_db, monkeypatch,
):
    Base.metadata.create_all(logs_db.session.get_bind(), checkfirst=True)
    admin = account(logs_db, role="Admin", name="Station Admin")
    owner = account(logs_db, name="Kiosk Operator")
    snapshots = {}

    async def lock(_db, user):
        return user

    async def save(_db, user, key, payload):
        stripped = {
            **payload,
            "items": [
                {k: v for k, v in row.items() if k not in scan_snapshots.DERIVED_FIELDS}
                for row in payload["items"]
            ],
        }
        assert all("ripeness_projection" not in row for row in stripped["items"])
        assert all("shelf_life_window" not in row for row in stripped["items"])
        from types import SimpleNamespace
        from uuid import uuid4
        snap = SimpleNamespace(
            id=uuid4(), expires_at=NOW + timedelta(minutes=10), binding=key, payload=stripped,
        )
        snapshots[snap.id] = snap
        return snap

    async def load(_db, _user, token, key, *, lock=True):
        del lock
        snap = snapshots[token]
        assert snap.binding == key
        return snap

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)

    # Scan A: Unripe Lakatan 4 days ago with 6.5d fallback shelf life (midpoints 6.5, 4.0, 3.0, 1.5)
    # -> transitions: Semi Ripe day 3, Ripe day 4, Overripe day 5 -> on day 4 it is Est. Ripe!
    progressed_id = scan(
        logs_db, owner, at=NOW - timedelta(days=4), source="Davao Farm",
        prediction="6.5", confidence=91.0,
    )
    logs_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == progressed_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
            temperature=25.0, humidity=65.0, treatment=TreatmentEnum.NATURAL,
        )
    )

    # Scan B: Ripe Lakatan scanned today -> Ripe on Day 0 (unprogressed).
    fresh_ripe_id = scan(
        logs_db, owner, at=NOW, source="Cebu Farm", prediction="3.0", confidence=88.0,
    )
    logs_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == fresh_ripe_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.RIPE,
            temperature=25.0, humidity=65.0, treatment=TreatmentEnum.NATURAL,
        )
    )

    # Scan C: Unripe Lakatan 4 days ago, but SOLD -> frozen at Unripe (must NOT match current=Ripe).
    sold_id = scan(
        logs_db, owner, at=NOW - timedelta(days=4), source="Sold Farm",
        prediction="6.5", confidence=85.0, statuses=[(NOW, InventoryStatusEnum.SOLD)],
    )
    logs_db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == sold_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
            temperature=25.0, humidity=65.0, treatment=TreatmentEnum.NATURAL,
        )
    )

    # Default scanned filter finds only Scan B.
    scanned_only = await scan_logs.list_scan_logs(
        logs_db, admin, ScanLogQuery(ripeness=RipenessEnum.RIPE),
    )
    assert [row.id for row in scanned_only.items] == [fresh_ripe_id]

    # ripeness_scope=current finds Scan B + progressed Scan A (and excludes Sold Scan C).
    current_page = await scan_logs.list_scan_logs(
        logs_db,
        admin,
        ScanLogQuery(ripeness=RipenessEnum.RIPE, ripeness_scope="current", stable=True),
    )
    assert current_page.total == 2
    assert {row.id for row in current_page.items} == {fresh_ripe_id, progressed_id}
    prog_row = next(r for r in current_page.items if r.id == progressed_id)
    assert prog_row.ripeness == "Unripe"
    assert prog_row.ripeness_projection is not None
    assert prog_row.ripeness_projection.current_ripeness == "Ripe"
    assert prog_row.ripeness_projection.progressed is True

    # Reconcile and pending on the frozen snapshot respect ripeness_scope=current.
    reconciled = await scan_logs.reconcile_scan_logs(
        logs_db,
        admin,
        ScanLogQuery(
            ripeness=RipenessEnum.RIPE,
            ripeness_scope="current",
            snapshot_id=current_page.snapshot_id,
        ),
    )
    assert reconciled.total == 2
    assert {row.id for row in reconciled.items} == {fresh_ripe_id, progressed_id}

    pending = await scan_logs.pending_scan_count(
        logs_db,
        admin,
        ScanLogQuery(
            ripeness=RipenessEnum.RIPE,
            ripeness_scope="current",
            snapshot_id=current_page.snapshot_id,
        ),
    )
    assert pending.new_count == 0

    # Exports (both live and snapshot, XLSX and PDF) honor ripeness_scope=current with exact parity.
    app = FastAPI()
    app.include_router(logs_api.router, prefix="/api/v1")

    async def database():
        yield logs_db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_stream_db] = database
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch("app.api.v1.scan_logs.audit.emit", return_value=None), TestClient(app) as client:
        for extra in ({}, {"snapshot_id": str(current_page.snapshot_id)}):
            xlsx_res = client.get("/api/v1/scan-logs/export", params={
                "format": "xlsx", "ripeness": "Ripe", "ripeness_scope": "current", **extra,
            })
            pdf_res = client.get("/api/v1/scan-logs/export", params={
                "format": "pdf", "ripeness": "Ripe", "ripeness_scope": "current", **extra,
            })
            assert xlsx_res.status_code == 200 and pdf_res.status_code == 200
            headers, data = workbook_table(xlsx_res.content)
            assert headers[4:6] == ["Scanned Ripeness", "Est. Current Ripeness"]
            assert len(data) == 2
            by_src = {r[2]: r for r in data}
            assert by_src["Davao Farm"][4:6] == ["Unripe", "Est. Ripe"]
            assert by_src["Cebu Farm"][4:6] == ["Ripe", "Ripe"]
            _, pdf_text = extract_pdf_text(pdf_res.content)
            assert "Est. Current Ripeness: Ripe" in pdf_text
            assert "Est. Ripe" in pdf_text
            assert "Sold Farm" not in pdf_text


@pytest.mark.asyncio
async def test_analytics_verified_accuracy_remains_anchored_to_scan_time_ripeness(analytics_db):
    db = analytics_db
    admin = account(db, role="Admin")
    op = account(db)

    # Scan 5 days ago as Unripe (now Est. Overripe), confirmed by QC admin.
    aged_id = scan(
        db, op, at=NOW - timedelta(days=5), prediction="6.5", confidence=78.0, flagged=False,
    )
    db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == aged_id).values(
            cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.UNRIPE,
        )
    )
    db.add(
        ScanEvent, scan_id=aged_id, revision=2, kind="flag", timestamp=NOW - timedelta(days=5),
        actor_id=admin.id, actor_name="Admin",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )

    summary = await analytics.get_summary(db, admin, date_range="week")
    assert summary.verified_scan_count == 1
    assert summary.verified_correct_count == 1
    assert summary.human_verified_accuracy == 100.0
    dist = {row.name: row.value for row in summary.ripeness_distribution}
    assert dist["Unripe"] == 1 and dist["Overripe"] == 0
    # Stored database value is completely untouched.
    stored = db.session.scalar(
        select(ScanClassification.ripeness).where(ScanClassification.scan_id == aged_id)
    )
    assert stored == RipenessEnum.UNRIPE


@pytest.mark.asyncio
async def test_real_save_snapshot_strips_and_slice_rebuilds_ripeness_projection(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    stored_objects = []

    class FakeDb:
        async def scalar(self, *_a, **_kw):
            return "gen-1"

        async def execute(self, *_a, **_kw):
            class Res:
                def scalars(self):
                    return self

                def all(self):
                    return []
            return Res()

        def add(self, obj):
            stored_objects.append(obj)

        async def flush(self):
            pass

    user = SimpleNamespace(
        id=uuid4(), token_version=1, role=SimpleNamespace(name="Admin"),
    )

    async def lock(_db, u):
        return u

    monkeypatch.setattr(scan_snapshots, "lock_current_account", lock)
    monkeypatch.setattr(scan_snapshots, "now_manila", lambda: NOW)

    payload = {
        "items": [{
            "id": str(uuid4()),
            "date_time": (NOW - timedelta(days=4)).isoformat(),
            "cultivar": "Lakatan",
            "ripeness": "Unripe",
            "spoilage_days": "6.5",
            "temperature": 25.0,
            "humidity": 65.0,
            "vpd": 1.1,
            "treatment": "Natural",
            "inventory_status": "In Stock",
            "shelf_life_window": {"stale": True},
            "ripeness_projection": {"stale": True},
        }],
        "meta": {"generated_at": NOW.isoformat()},
    }
    snap = await scan_snapshots.save_snapshot(FakeDb(), user, "key-1", payload)
    # Persisted snapshot payload must strip both derived fields.
    assert "shelf_life_window" not in snap.payload["items"][0]
    assert "ripeness_projection" not in snap.payload["items"][0]

    sliced = scan_snapshots.slice_snapshot(snap, 1, 10)
    rebuilt = sliced["items"][0]
    assert rebuilt["shelf_life_window"] is not None
    assert rebuilt["ripeness_projection"] is not None
    assert rebuilt["ripeness_projection"]["base_ripeness"] == "Unripe"
    assert rebuilt["ripeness_projection"]["current_ripeness"] == "Ripe"
    assert rebuilt["ripeness_projection"]["progressed"] is True

