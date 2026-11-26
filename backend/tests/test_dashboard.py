"""Dashboard contracts against an isolated SQL database, without app startup.

SQLite executes the aggregate/projection statements. PostgreSQL's split_part and
btrim primitives are supplied as SQLite functions; SQLAlchemy supplies each
dialect's regexp/epoch syntax. An async adapter avoids another test dependency.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.v1.dashboard import router
from app.core.database import Base, get_db
from app.core.exceptions import ForbiddenException
from app.models.admin_profile import AdminProfile
from app.models.intake import Intake
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.models.supplier import Supplier
from app.models.system_config import SystemConfig
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.schemas.enums import (
    ActiveStatusEnum,
    CultivarEnum,
    IntakeStatusEnum,
    InventoryStatusEnum,
    RipenessEnum,
)
from app.services import dashboard

NOW = datetime(2026, 10, 2, 4, tzinfo=UTC)  # Noon in Manila.


class Database:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    def add(self, model, **values):
        self.session.execute(insert(model.__table__).values(**values))


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(dashboard, "now_manila", lambda: NOW)
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def string_functions(connection, _):
        def split_part(value, separator, position):
            if value is None:
                return None
            parts = value.split(separator)
            return parts[position - 1] if len(parts) >= position else ""

        connection.create_function("split_part", 3, split_part)
        connection.create_function(
            "btrim", 2, lambda value, chars: None if value is None else value.strip(chars)
        )

    tables = [
        UserRole, UserAccount, AdminProfile, OperatorProfile, Supplier, Intake,
        Scan, ScanClassification, ScanStatusLog, SystemConfig,
    ]
    Base.metadata.create_all(engine, tables=[model.__table__ for model in tables])
    with Session(engine) as session:
        database = Database(session)
        database.add(UserRole, id=1, name="Admin")
        database.add(UserRole, id=2, name="Operator")
        yield database
    engine.dispose()


def account(db, *, name="Alex Cruz", role="Operator", status=ActiveStatusEnum.ACTIVE):
    account_id, operator_id = uuid4(), uuid4()
    username = f"user-{account_id.hex[:8]}"
    db.add(
        UserAccount, id=account_id, username=username, full_name=name,
        password_hash="unused", role_id=1 if role == "Admin" else 2, status=status,
    )
    if role == "Operator":
        db.add(OperatorProfile, id=operator_id, account_id=account_id)
    return SimpleNamespace(
        id=account_id, operator_id=operator_id, username=username,
        role=SimpleNamespace(name=role),
    )


def scan(
    db, operator, *, at=NOW, confidence=90, flagged=False, prediction="5-7",
    source="Farm A", intake=None, statuses=None,
):
    scan_id = uuid4()
    db.add(
        Scan, id=scan_id, operator_id=operator.operator_id, date_time=at,
        flagged=flagged, source_text=source, intake_id=intake,
    )
    if confidence is not None:
        db.add(
            ScanClassification, scan_id=scan_id, cultivar=CultivarEnum.LAKATAN,
            ripeness=RipenessEnum.RIPE, confidence=confidence,
            spoilage_days=prediction, finger_count=5,
        )
    for status_time, status in statuses or []:
        db.add(ScanStatusLog, scan_id=scan_id, updated_at=status_time, inventory_status=status)
    return scan_id


@pytest.mark.asyncio
async def test_namesakes_and_renames_use_ids_and_filters_cannot_broaden_scope(db):
    admin = account(db, role="Admin")
    own, other = account(db), account(db)
    own_id = scan(db, own, confidence=60, flagged=True)  # Saved below the threshold.
    scan(db, other, confidence=100, flagged=True, prediction="1")
    summary = await dashboard.get_summary(db, admin)
    assert summary.active_operator_count == 2
    assert {o.operator_id for o in summary.operators} == {own.operator_id, other.operator_id}
    own_summary = await dashboard.get_summary(db, own)
    assert own_summary.total_scans == 1 and own_summary.avg_confidence == 60
    assert [s.id for s in own_summary.recent_scans] == [own_id]
    assert own_summary.pending_review_count == 1 and own_summary.expiring_stock_count == 0
    for view in ("all", "today", "review", "expiring"):
        result = await dashboard.list_scans(db, own, view=view, operator_id=other.operator_id)
        assert result.total == 0 and result.items == []
    db.session.execute(
        update(UserAccount).where(UserAccount.id == own.id).values(full_name="New Name")
    )
    renamed = await dashboard.get_summary(db, own)
    assert renamed.total_scans == 1
    assert renamed.operators[0].name == "New Name"
    assert renamed.operators[0].operator_id == own.operator_id


@pytest.mark.asyncio
async def test_manila_midnight_and_pagination_cover_more_than_20_scans(db):
    operator = account(db)
    start, end = dashboard.business_day_bounds(date(2026, 10, 2))
    assert start == datetime(2026, 10, 1, 16, tzinfo=UTC)
    assert end == datetime(2026, 10, 2, 16, tzinfo=UTC)
    before = scan(db, operator, at=start - timedelta(microseconds=1))
    expected = {scan(db, operator, at=start + timedelta(minutes=n)) for n in range(31)}
    scan(db, operator, at=end)
    summary = await dashboard.get_summary(db, operator)
    assert summary.total_scans == 31
    assert summary.sources[0].count == summary.operators[0].scan_count == 31
    first = await dashboard.list_scans(db, operator, page_size=20)
    second = await dashboard.list_scans(db, operator, page=2, page_size=20)
    assert first.total == second.total == 31
    assert {s.id for s in first.items + second.items} == expected
    assert len(summary.recent_scans) == 5
    previous_day = await dashboard.list_scans(db, operator, business_date=date(2026, 10, 1))
    assert [s.id for s in previous_day.items] == [before]
    empty_page = await dashboard.list_scans(db, operator, page=9)
    assert empty_page.total == 31 and empty_page.items == []


@pytest.mark.asyncio
async def test_no_activity_and_missing_confidence_differ_from_zero(db):
    operator = account(db)
    empty = await dashboard.get_summary(db, operator)
    assert empty.total_scans == empty.active_operator_count == 0
    assert empty.avg_confidence is None
    assert empty.recent_scans == empty.operators == empty.sources == []
    missing_id = scan(db, operator, confidence=None)
    missing = await dashboard.get_summary(db, operator)
    assert missing.total_scans == 1 and missing.avg_confidence is None
    assert missing.pending_review_count == missing.expiring_stock_count == 0
    assert missing.operators[0].avg_confidence is None
    assert missing.recent_scans[0].cultivar is None
    zero_id = scan(db, operator, confidence=0)
    measured = await dashboard.get_summary(db, operator)
    # Review is the flag alone; a station scan this low is flagged when it is saved.
    assert measured.avg_confidence == 0 and measured.pending_review_count == 0
    ordered = await dashboard.list_scans(db, operator, sort="confidence")
    assert [s.id for s in ordered.items] == [zero_id, missing_id]
    assert ordered.items[0].confidence == 0 and ordered.items[1].confidence is None


@pytest.mark.asyncio
async def test_review_queue_is_the_flagged_scans_and_matches_drilldown(db):
    operator = account(db)
    db.add(SystemConfig, confidence_threshold=75, data_retention_enabled=False)
    expected = {
        scan(db, operator, at=NOW - timedelta(days=20), confidence=74, flagged=True),
        scan(db, operator, confidence=95, flagged=True),
        scan(db, operator, confidence=None, flagged=True),
    }
    # A person removed the flag after checking it: it leaves the queue although its
    # confidence is below the threshold (the threshold only flags new scans).
    checked = scan(db, operator, confidence=60)
    scan(db, operator, confidence=75)
    scan(db, operator, confidence=None)
    summary = await dashboard.get_summary(db, operator)
    review = await dashboard.list_scans(db, operator, view="review")
    assert summary.confidence_threshold == 75
    assert summary.pending_review_count == review.total == 3
    assert {s.id for s in review.items} == expected
    # Successful = not flagged with a known confidence: the checked scan and the 75.
    assert summary.success_rate == round(2 / 6 * 100, 1)
    assert checked not in {s.id for s in review.items}


@pytest.mark.asyncio
async def test_removing_the_flag_takes_a_scan_out_of_the_review_queue(db):
    operator = account(db)
    db.add(SystemConfig, confidence_threshold=85, data_retention_enabled=False)
    low = scan(db, operator, confidence=40, flagged=True)
    assert (await dashboard.get_summary(db, operator)).pending_review_count == 1
    db.session.execute(update(Scan).where(Scan.id == low).values(flagged=False))
    after = await dashboard.get_summary(db, operator)
    assert after.pending_review_count == 0
    assert (await dashboard.list_scans(db, operator, view="review")).total == 0


@pytest.mark.asyncio
async def test_expiry_ages_ranges_and_uses_latest_status_with_id_tiebreak(db):
    operator = account(db)
    expected = {
        scan(db, operator, at=NOW - timedelta(days=4), prediction="5-7"),
        scan(db, operator, at=NOW - timedelta(days=3), prediction="1"),
        scan(db, operator, prediction="0"),
        scan(db, operator, prediction=" .5 - 1.5 "),
        scan(db, operator, prediction="1", statuses=[
            (NOW, InventoryStatusEnum.SOLD), (NOW, InventoryStatusEnum.IN_STOCK),
        ]),
    }
    scan(db, operator, at=NOW - timedelta(days=3), prediction="5-7")
    scan(db, operator, prediction="1", statuses=[
        (NOW, InventoryStatusEnum.IN_STOCK), (NOW, InventoryStatusEnum.SOLD),
    ])
    scan(db, operator, prediction="1", statuses=[
        (NOW, InventoryStatusEnum.SPOILED),
        (NOW - timedelta(days=1), InventoryStatusEnum.IN_STOCK),
    ])
    scan(db, operator, prediction="1", statuses=[(NOW, InventoryStatusEnum.FOR_PROCESSING)])
    for invalid in ("", "N/A", "NaN", "Infinity", "-1", "3-1", "1-2-3", "1 day", "--"):
        scan(db, operator, prediction=invalid)
    summary = await dashboard.get_summary(db, operator)
    expiring = await dashboard.list_scans(db, operator, view="expiring")
    assert summary.expiring_stock_count == expiring.total == len(expected)
    assert {s.id for s in expiring.items} == expected
    assert all(s.inventory_status == "In Stock" for s in expiring.items)
    assert any(s.remaining_days == -2 for s in expiring.items)


@pytest.mark.asyncio
async def test_fifo_recommendations_group_active_stock_oldest_first(db):
    operator = account(db)
    supplier_id, intake_id = uuid4(), uuid4()
    db.add(Supplier, id=supplier_id, name="FIFO Supplier")
    db.add(
        Intake, id=intake_id, supplier_id=supplier_id, source="FIFO Supplier",
        intake_date=date(2026, 10, 2), status=IntakeStatusEnum.ACTIVE,
    )
    scan(db, operator, at=NOW - timedelta(days=4), prediction="10", source="Loose Batch")
    scan(db, operator, at=NOW - timedelta(days=3), intake=intake_id, prediction="12")
    scan(db, operator, at=NOW - timedelta(days=1), intake=intake_id, prediction="2")
    # Older stock that is no longer sellable never enters the recommendation list.
    scan(db, operator, at=NOW - timedelta(days=9), prediction="1", statuses=[
        (NOW, InventoryStatusEnum.SOLD),
    ])
    depleted_id = uuid4()
    db.add(
        Intake, id=depleted_id, source="Depleted", intake_date=date(2026, 10, 2),
        status=IntakeStatusEnum.DEPLETED,
    )
    scan(db, operator, at=NOW - timedelta(days=8), intake=depleted_id, prediction="1")

    summary = await dashboard.get_summary(db, operator)
    assert len(summary.fifo_recommendations) == 2
    first, second = summary.fifo_recommendations
    assert first.intake_id is None and first.scan_id is not None
    assert first.key == f"scan:{first.scan_id}"
    assert first.source_name == "Loose Batch" and first.hands == 1
    assert first.earliest_remaining_days == pytest.approx(6)
    assert second.intake_id == intake_id and second.scan_id is None
    assert second.key == f"intake:{intake_id}"
    assert second.source_name == "FIFO Supplier" and second.hands == 2
    assert second.earliest_remaining_days == pytest.approx(1)


@pytest.mark.asyncio
async def test_fifo_recommendations_keep_five_groups_and_report_unknown_risk(db):
    operator = account(db)
    for days in range(6):
        scan(db, operator, at=NOW - timedelta(days=6 - days), prediction="N/A")
    summary = await dashboard.get_summary(db, operator)
    assert len(summary.fifo_recommendations) == dashboard.FIFO_LIMIT
    assert all(item.earliest_remaining_days is None for item in summary.fifo_recommendations)
    assert all(item.intake_id is None and item.scan_id is not None for item in summary.fifo_recommendations)


@pytest.mark.asyncio
async def test_supplier_identity_precedes_text_and_depleted_intake_excludes_stock(db):
    operator = account(db)
    supplier_id, intake_id = uuid4(), uuid4()
    db.add(Supplier, id=supplier_id, name="Supplier Name")
    db.add(
        Intake, id=intake_id, supplier_id=supplier_id, source="Legacy Intake Source",
        intake_date=date(2026, 10, 2), status=IntakeStatusEnum.DEPLETED,
    )
    linked = scan(db, operator, intake=intake_id, source="Old copied name", prediction="1")
    text_id = scan(db, operator, source="  Supplier Name  ")
    unknown = scan(db, operator, source=" \t\r\n\u00a0 ")
    summary = await dashboard.get_summary(db, operator)
    assert {s.key for s in summary.sources} == {
        f"supplier:{supplier_id}", "text:Supplier Name", "unknown",
    }
    assert sum(s.count for s in summary.sources) == summary.total_scans
    filters = [
        (f"supplier:{supplier_id}", linked), ("text:Supplier Name", text_id), ("unknown", unknown),
    ]
    for key, expected in filters:
        result = await dashboard.list_scans(db, operator, source_key=key)
        assert result.total == 1 and result.items[0].id == expected
    assert summary.expiring_stock_count == 0
    db.session.execute(
        update(Supplier).where(Supplier.id == supplier_id).values(name="Renamed Supplier")
    )
    renamed = await dashboard.list_scans(db, operator, source_key=f"supplier:{supplier_id}")
    assert renamed.items[0].source_name == "Renamed Supplier"
    assert renamed.items[0].source_key == f"supplier:{supplier_id}"
    assert (await dashboard.list_scans(db, operator, source_key="supplier:invalid")).total == 0


@pytest.mark.asyncio
async def test_unknown_role_denied_and_active_count_means_operators_who_scanned_today(db):
    admin = account(db, role="Admin")
    account(db)  # Enabled but idle.
    past_operator = account(db, status=ActiveStatusEnum.INACTIVE)
    scan(db, past_operator)
    summary = await dashboard.get_summary(db, admin)
    assert summary.active_operator_count == 1
    denied = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="Observer"))
    with pytest.raises(ForbiddenException):
        await dashboard.get_summary(db, denied)
    with pytest.raises(ForbiddenException):
        await dashboard.list_scans(db, denied, view="all")


def test_router_authentication_validation_and_json_contract(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        assert client.get("/api/v1/dashboard").status_code == 401
        assert client.get("/api/v1/dashboard/scans").status_code == 401
        user = account(db)
        app.dependency_overrides[get_current_user] = lambda: user
        response = client.get("/api/v1/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["business_date"] == "2026-10-02" and data["timezone"] == "Asia/Manila"
        assert data["generated_at"].endswith("+08:00") and data["avg_confidence"] is None
        assert data["fifo_recommendations"] == []
        scan_id = scan(db, user)
        fifo = client.get("/api/v1/dashboard").json()["fifo_recommendations"]
        assert fifo == [{
            "key": f"scan:{scan_id}", "intake_id": None, "scan_id": str(scan_id),
            "source_name": "Farm A", "scanned_at": "2026-10-02T12:00:00+08:00",
            "hands": 1, "earliest_remaining_days": 6.0,
        }]
        scans_response = client.get("/api/v1/dashboard/scans")
        assert scans_response.status_code == 200
        scans_data = scans_response.json()
        assert scans_data["total"] == 1
        assert scans_data["page"] == 1 and scans_data["page_size"] == 25
        assert scans_data["items"][0]["id"] == str(scan_id)
        assert scans_data["items"][0]["inventory_status"] == "In Stock"
        assert scans_data["items"][0]["operator_id"] == str(user.operator_id)
        for params in (
            {"view": "invalid"}, {"page": 0}, {"page_size": 101},
            {"business_date": "tomorrow"}, {"operator_id": "bad"}, {"sort": "name"},
        ):
            assert client.get("/api/v1/dashboard/scans", params=params).status_code == 422


def test_production_dialect_compiles_account_scope_and_sql_expiry(db):
    user = account(db)
    projection = dashboard._scoped_projection(user, NOW)
    sql = str(select(projection).compile(dialect=postgresql.dialect()))
    assert "operator_profile.account_id" in sql
    assert "split_part" in sql and "EXTRACT(epoch" in sql
    assert "scan_status_log.updated_at DESC, scan_status_log.id DESC" in sql
