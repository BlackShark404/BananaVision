"""Analytics populations, business boundaries and stable filters on real SQL.

Uses the Dashboard database fixture with a local equivalent of PostgreSQL's
timezone function. Production SQL is also compiled against PostgreSQL.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql

from app.api.deps import get_current_user
from app.api.v1.analytics import router
from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.time import as_manila, business_day_bounds
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.supplier import Supplier
from app.models.system_config import SystemConfig
from app.models.user_account import UserAccount
from app.schemas.enums import CultivarEnum, IntakeStatusEnum, InventoryStatusEnum, RipenessEnum
from app.services import analytics
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401


@pytest.fixture
def analytics_db(db, monkeypatch):
    monkeypatch.setattr(analytics, "now_manila", lambda: NOW)
    ScanOriginalAiResult.__table__.create(db.session.get_bind())

    def local_time(zone, value):
        assert zone == "Asia/Manila"
        if value is None:
            return None
        return as_manila(datetime.fromisoformat(value)).replace(tzinfo=None).isoformat(sep=" ")

    db.session.connection().connection.driver_connection.create_function("timezone", 2, local_time)
    return db


@pytest.mark.asyncio
async def test_empty_dataset_has_no_fabricated_confidence_or_accuracy(analytics_db):
    db = analytics_db
    user = account(db)
    result = await analytics.get_summary(db, user)
    assert result.total_scans == result.classification_count == result.confidence_sample_count == 0
    assert result.avg_confidence is None and result.low_confidence_rate is None
    assert result.human_verified_accuracy is None and result.verified_scan_count == 0
    assert result.current_stock_count == result.at_risk_count == result.risk_unknown_count == 0
    assert result.source_options == result.operator_performance == result.hourly_distribution == []
    assert len(result.scan_trend) == 14 and sum(row.count for row in result.scan_trend) == 0
    assert all(row.avgConfidence is None and row.count == 0 for row in result.ripeness_confidence)
    assert result.next_refresh_at == business_day_bounds(date(2026, 10, 2))[1]
    assert result.range_start == business_day_bounds(date(2026, 9, 26))[0]
    assert result.range_end == NOW
    assert "not measured accuracy" in result.metric_definitions["model_confidence"]


@pytest.mark.asyncio
async def test_combined_cultivar_status_filters_scope_every_chart_and_fixed_trend(analytics_db):
    db = analytics_db
    owner, other = account(db), account(db)
    for who, source, cultivar, status in [
        (owner, "Farm A", "Cardaba", InventoryStatusEnum.SOLD),
        (owner, "Farm A", "Lakatan", InventoryStatusEnum.SOLD),
        (owner, "Farm A", "Cardaba", InventoryStatusEnum.IN_STOCK),
        (owner, "Farm B", "Cardaba", InventoryStatusEnum.SOLD),
        (other, "Farm A", "Cardaba", InventoryStatusEnum.SOLD),
    ]:
        scan_id = scan(db, who, source=source, statuses=[(NOW, status)])
        db.session.execute(
            update(ScanClassification)
            .where(ScanClassification.scan_id == scan_id)
            .values(cultivar=cultivar)
        )
    result = await analytics.get_summary(db, owner, date_range="today", source_key="text:Farm A",
        cultivar=CultivarEnum.CARDABA, inventory_status=InventoryStatusEnum.SOLD)
    assert result.total_scans == result.classification_count == result.confidence_sample_count == 1
    assert sum(item.count for item in result.scan_trend) == 1
    assert sum(item.count for item in result.hourly_distribution) == 1
    assert result.current_stock_count == 0
    assert {option.name for option in result.source_options} == {"Farm A", "Farm B"}
    operators = await analytics.get_operator_performance(
        db,
        owner,
        date_range="today",
        source_key="text:Farm A",
        cultivar=CultivarEnum.CARDABA,
        inventory_status=InventoryStatusEnum.SOLD,
    )
    assert operators.items[0].total_scans == 1


@pytest.mark.asyncio
async def test_manila_today_midnight_and_hourly_grouping(analytics_db):
    db = analytics_db
    user = account(db)
    start, end = business_day_bounds(date(2026, 10, 2))
    scan(db, user, at=start - timedelta(microseconds=1))
    scan(db, user, at=start)
    scan(db, user, at=datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc))
    scan(db, user, at=NOW)
    scan(db, user, at=NOW + timedelta(microseconds=1))
    scan(db, user, at=end)
    result = await analytics.get_summary(db, user, date_range="today")
    assert result.total_scans == 3
    assert result.range_start == start
    assert [(r.hour, r.count) for r in result.hourly_distribution] == [("12 AM", 1), ("7 AM", 1), ("12 PM", 1)]
    assert result.scan_trend[-1].date == "Oct 02" and result.scan_trend[-1].count == 3
    assert result.scan_trend[-2].count == 1


@pytest.mark.asyncio
async def test_calendar_ranges_and_fixed_trend_have_explicit_different_populations(analytics_db):
    db = analytics_db
    user = account(db)
    week_start = business_day_bounds(date(2026, 9, 26))[0]
    month_start = business_day_bounds(date(2026, 9, 3))[0]
    for timestamp in (NOW, week_start, week_start - timedelta(microseconds=1), month_start, month_start - timedelta(microseconds=1)):
        scan(db, user, at=timestamp)
    today = await analytics.get_summary(db, user, date_range="today")
    week = await analytics.get_summary(db, user, date_range="week")
    month = await analytics.get_summary(db, user, date_range="month")
    all_time = await analytics.get_summary(db, user, date_range="all")
    assert [today.total_scans, week.total_scans, month.total_scans, all_time.total_scans] == [1, 2, 4, 5]
    assert all_time.range_start is None
    assert today.scan_trend == week.scan_trend == month.scan_trend == all_time.scan_trend
    assert sum(row.count for row in week.scan_trend) == 3
    assert week.trend_start == date(2026, 9, 19) and week.trend_end == date(2026, 10, 2)


@pytest.mark.asyncio
async def test_confidence_excludes_missing_invalid_and_unrecoverable_overrides(analytics_db):
    db = analytics_db
    user = account(db)
    db.add(SystemConfig, confidence_threshold=75, camera_ids="", data_retention_enabled=False)
    scan(db, user, confidence=None)
    scan(db, user, confidence=0)
    scan(db, user, confidence=75)
    scan(db, user, confidence=-1)
    scan(db, user, confidence=101)
    unknown = scan(db, user, confidence=99)
    # Legacy databases may contain unknown labels. SQL must reject these from
    # denominators without trying to decode an unknown ORM enum value.
    db.session.execute(update(ScanClassification).where(ScanClassification.scan_id == unknown).values(cultivar="Unknown"))
    saved = scan(db, user, confidence=100)
    unrecoverable = scan(db, user, confidence=100)
    db.session.execute(update(Scan).where(Scan.id.in_([saved, unrecoverable])).values(is_overridden=True))
    db.add(
        ScanOriginalAiResult, scan_id=saved, cultivar=CultivarEnum.CARDABA,
        ripeness=RipenessEnum.UNRIPE, confidence=60, finger_count=5,
    )
    result = await analytics.get_summary(db, user)
    assert result.total_scans == 8
    assert result.classification_count == 6 and result.incomplete_count == 2
    assert sum(r.value for r in result.ripeness_distribution) == result.classification_count
    assert sum(c.count for c in result.cultivar_counts) == result.classification_count
    assert result.confidence_threshold == 75
    assert result.confidence_sample_count == 3 and result.avg_confidence == 45
    assert result.low_confidence_count == 2 and result.low_confidence_rate == 66.7
    unripe = next(r for r in result.ripeness_confidence if r.ripeness == "Unripe")
    ripe = next(r for r in result.ripeness_confidence if r.ripeness == "Ripe")
    assert (unripe.count, unripe.avgConfidence) == (1, 60)
    assert (ripe.count, ripe.avgConfidence) == (2, 37.5)
    operator = result.operator_performance[0]
    assert operator.confidence_sample_count == 3 and operator.avg_confidence == result.avg_confidence
    assert operator.overridden_scans == 2


@pytest.mark.asyncio
async def test_risk_ages_estimates_and_excludes_removed_stock_and_depleted_intakes(analytics_db):
    db = analytics_db
    user = account(db)
    aged = scan(db, user, at=NOW - timedelta(days=4), prediction="5-7")
    scan(db, user, at=NOW - timedelta(days=2), prediction="1")  # Overdue.
    scan(db, user, prediction="  .5 - 1.5  ")
    scan(db, user, at=NOW - timedelta(days=3), prediction="5-7")  # Three days remain.
    for status in (InventoryStatusEnum.SOLD, InventoryStatusEnum.SPOILED, InventoryStatusEnum.FOR_PROCESSING):
        scan(db, user, prediction="1", statuses=[(NOW, status)])
    scan(db, user, prediction="1", statuses=[(NOW, InventoryStatusEnum.IN_STOCK), (NOW, InventoryStatusEnum.SOLD)])
    scan(db, user, prediction="1", statuses=[(NOW, InventoryStatusEnum.SOLD), (NOW, InventoryStatusEnum.IN_STOCK)])
    intake_id = uuid4()
    db.add(Intake, id=intake_id, source="Farm", intake_date=date(2026, 10, 2), status=IntakeStatusEnum.DEPLETED)
    scan(db, user, prediction="1", intake=intake_id)
    scan(db, user, confidence=None)
    for prediction in ("NaN", "Infinity", "3-1", "-1", "1-2-3"):
        scan(db, user, prediction=prediction)
    result = await analytics.get_summary(db, user)
    assert result.total_scans == 16
    assert result.current_stock_count == 11
    assert result.at_risk_count == 4 and result.risk_unknown_count == 6
    today = await analytics.get_summary(db, user, date_range="today")
    assert today.at_risk_count == 2  # Aged scans outside the selected cohort excluded.
    assert aged is not None


@pytest.mark.asyncio
async def test_stable_source_keys_survive_rename_and_options_do_not_shrink(analytics_db):
    db = analytics_db
    user = account(db)
    supplier_id, intake_id = uuid4(), uuid4()
    db.add(Supplier, id=supplier_id, name="Original supplier")
    db.add(Intake, id=intake_id, supplier_id=supplier_id, source="Intake legacy name", intake_date=date(2026, 10, 2), status=IntakeStatusEnum.ACTIVE)
    scan(db, user, source="Copied old supplier", intake=intake_id)
    scan(db, user, source="Other farm", at=NOW - timedelta(days=60))
    scan(db, user, source=None)
    key = f"supplier:{supplier_id}"
    chosen = await analytics.get_summary(db, user, date_range="today", source_key=key)
    assert chosen.total_scans == 1 and chosen.scans_by_source[0].key == key
    assert {s.key for s in chosen.source_options} == {key, "text:Other farm", "unknown"}
    db.session.execute(update(Supplier).where(Supplier.id == supplier_id).values(name="Renamed supplier"))
    renamed = await analytics.get_summary(db, user, date_range="today", source_key=key)
    assert renamed.total_scans == 1 and renamed.scans_by_source[0].name == "Renamed supplier"
    assert next(s for s in renamed.source_options if s.key == key).name == "Renamed supplier"
    for legacy in ("Copied old supplier", "Intake legacy name", "Renamed supplier"):
        assert (await analytics.get_summary(db, user, source=legacy)).total_scans == 1
    empty = await analytics.get_summary(db, user, date_range="today", source_key="text:Other farm")
    assert empty.total_scans == 0 and empty.source_options == renamed.source_options
    assert (await analytics.get_summary(db, user, source_key="supplier:bad", source="Renamed supplier")).total_scans == 0


@pytest.mark.asyncio
async def test_operator_namesakes_renames_and_role_scope(analytics_db):
    db = analytics_db
    admin, own, other = account(db, role="Admin"), account(db), account(db)
    scan(db, own, confidence=60, flagged=True, source="Mine")
    scan(db, other, confidence=100, source="Theirs")
    result = await analytics.get_summary(db, admin)
    assert len(result.operator_performance) == 2
    assert {r.operator_id for r in result.operator_performance} == {own.operator_id, other.operator_id}
    own_result = await analytics.get_summary(db, own)
    assert own_result.total_scans == 1 and own_result.avg_confidence == 60
    assert own_result.operator_performance[0].flag_rate == 100
    assert [s.key for s in own_result.source_options] == ["text:Mine"]
    assert (await analytics.get_summary(db, own, source_key="text:Theirs")).total_scans == 0
    db.session.execute(update(UserAccount).where(UserAccount.id == own.id).values(full_name="Renamed Operator"))
    operators = await analytics.get_operator_performance(db, own)
    assert operators.items[0].operator_id == own.operator_id
    assert operators.items[0].name == "Renamed Operator"
    denied = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="Observer"))
    with pytest.raises(ForbiddenException):
        await analytics.get_summary(db, denied)


def test_api_contract_validates_filters_and_serializes_manila_offsets(analytics_db):
    db = analytics_db  # noqa: F811 - pytest fixture injection
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        assert client.get("/api/v1/analytics/summary").status_code == 401
        user = account(db)
        app.dependency_overrides[get_current_user] = lambda: user
        scan(db, user)
        result = client.get("/api/v1/analytics/summary", params={"range": "today"})
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["range_start"] == "2026-10-02T00:00:00+08:00"
        assert data["generated_at"].endswith("+08:00")
        assert data["next_refresh_at"] == "2026-10-03T00:00:00+08:00"
        assert data["operator_performance"][0]["operator_id"] == str(user.operator_id)
        assert data["human_verified_accuracy"] is None
        assert data["cultivar_ripeness"][0]["Semi Ripe"] == 0
        for params in ({"range": "year"}, {"confidence_threshold": -1}, {"confidence_threshold": 101}):
            assert client.get("/api/v1/analytics/summary", params=params).status_code == 422
        operator_result = client.get("/api/v1/analytics/operator-performance", params={"range": "today"})
        assert operator_result.json()["items"] == data["operator_performance"]


def test_postgres_queries_keep_stable_scope_elapsed_risk_and_original_model(analytics_db):
    user = account(analytics_db)
    projection = analytics._projection(user, NOW)
    sql = str(select(projection).compile(dialect=postgresql.dialect()))
    assert "operator_profile.account_id" in sql
    assert "scan_original_ai_result" in sql and "model_confidence" in sql
    assert "EXTRACT(epoch" in sql and "split_part" in sql
    assert "scan_status_log.updated_at DESC, scan_status_log.id DESC" in sql
