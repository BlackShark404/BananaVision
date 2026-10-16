"""Centralized Scan Logs filters, metrics, scope and complete safe export."""

import csv
import io
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.api.deps import get_current_user
from app.api.v1.scan_logs import router
from app.core.database import get_db, get_stream_db
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.supplier import Supplier
from app.models.user_account import UserAccount
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum
from app.schemas.scan_logs import ScanLogQuery
from app.services import dashboard, scan_logs
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401


@pytest.fixture
def logs_db(db):
    class AsyncRows:
        def __init__(self, result):
            self.result = result

        async def partitions(self, size):
            for batch in self.result.partitions(size):
                yield batch

        async def close(self):
            self.result.close()

    async def stream(statement):
        return AsyncRows(db.session.execute(statement))

    db.stream = stream
    return db


async def csv_rows(db, user, query):
    contents = await scan_logs.export_scan_logs(db, user, query)
    text = "".join([chunk async for chunk in contents]).lstrip("\ufeff")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.asyncio
async def test_combined_filters_full_counts_pagination_and_export(logs_db):
    db = logs_db
    admin, own, other = account(db, role="Admin"), account(db), account(db)
    intake_id = uuid4()
    db.add(Intake, id=intake_id, source="Farm A", intake_date=NOW.date())
    expected = {
        scan(db, own, at=NOW - timedelta(minutes=n), confidence=60, prediction="1",
             flagged=True, intake=intake_id)
        for n in range(31)
    }
    scan(db, other, confidence=60, prediction="1", flagged=True, intake=intake_id)
    scan(db, own, confidence=60, prediction="1", flagged=True)  # Wrong intake.
    scan(db, own, at=NOW - timedelta(days=1), confidence=60, flagged=True, intake=intake_id)
    scan(db, own, source="Elsewhere", confidence=60, flagged=True, intake=intake_id)
    scan(db, own, confidence=90, flagged=False, intake=intake_id)
    scan(db, own, confidence=60, flagged=True, intake=intake_id,
         statuses=[(NOW, InventoryStatusEnum.SOLD)])
    query = ScanLogQuery(
        business_date=date(2026, 10, 2), source_key="text:Farm A",
        operator_id=own.operator_id, intake_id=intake_id, cultivar="Lakatan", ripeness="Ripe",
        inventory_status="In Stock", flagged_only=True, attention="review", search="alex",
        page_size=20,
    )
    first = await scan_logs.list_scan_logs(db, admin, query)
    second = await scan_logs.list_scan_logs(db, admin, query.model_copy(update={"page": 2}))
    assert first.total == second.total == first.review_count == first.flagged_count == 31
    assert first.at_risk_count == 31 and first.avg_confidence == 60
    assert {r.id for r in first.items + second.items} == expected
    exported = await csv_rows(db, admin, query.model_copy(update={"page": 9, "page_size": 1}))
    assert len(exported) == 31
    assert {r["Scan ID"] for r in exported} == {str(scan_id) for scan_id in expected}
    assert exported[0]["Scan ID"] == str(first.items[0].id)
    # Options remain all-time/account-scoped even when the filtered page is empty.
    empty = await scan_logs.list_scan_logs(
        db, admin, query.model_copy(update={"search": "does not exist"})
    )
    assert empty.total == 0 and empty.avg_confidence is None
    assert {o.operator_id for o in empty.options.operators} == {own.operator_id, other.operator_id}
    assert {s.key for s in empty.options.sources} == {"text:Farm A", "text:Elsewhere"}


@pytest.mark.asyncio
async def test_scope_namesakes_renames_and_source_history(logs_db):
    db = logs_db
    own, other = account(db), account(db)
    supplier_id, intake_id = uuid4(), uuid4()
    db.add(Supplier, id=supplier_id, name="Old Supplier")
    db.add(Intake, id=intake_id, supplier_id=supplier_id,
           source="Old Intake Source", intake_date=NOW.date())
    own_id = scan(db, own, intake=intake_id, source="Old Supplier", at=NOW - timedelta(days=4))
    scan(db, other, source="Private Other Source")
    db.session.execute(update(Supplier).where(Supplier.id == supplier_id).values(name="New Supplier"))
    db.session.execute(update(UserAccount).where(UserAccount.id == own.id).values(full_name="Renamed"))
    all_rows = await scan_logs.list_scan_logs(db, own, ScanLogQuery())
    assert all_rows.total == 1 and all_rows.items[0].id == own_id
    assert all_rows.items[0].operator_name == "Renamed"
    assert all_rows.items[0].source_name == "New Supplier"
    assert [o.operator_id for o in all_rows.options.operators] == [own.operator_id]
    assert [s.key for s in all_rows.options.sources] == [f"supplier:{supplier_id}"]
    for source in ("New Supplier", "Old Supplier", "Old Intake Source"):
        result = await scan_logs.list_scan_logs(db, own, ScanLogQuery(source=source))
        assert result.total == 1
    stable = await scan_logs.list_scan_logs(db, own, ScanLogQuery(
        source_key=f"supplier:{supplier_id}", source="Unrelated stale name",
    ))
    assert stable.total == 1
    denied_filter = await scan_logs.list_scan_logs(db, own, ScanLogQuery(operator_id=other.operator_id))
    assert denied_filter.total == 0
    assert await csv_rows(db, own, ScanLogQuery(operator_id=other.operator_id)) == []
    today = await scan_logs.list_scan_logs(db, own, ScanLogQuery(business_date=NOW.date()))
    assert today.total == 0 and len(today.options.sources) == 1


@pytest.mark.asyncio
async def test_risk_review_and_flag_metrics_match_dashboard_predicates(logs_db):
    db = logs_db
    operator = account(db)
    unflagged_low = scan(db, operator, confidence=50, prediction="1")
    flagged_high = scan(db, operator, confidence=95, prediction="1", flagged=True)
    aged = scan(db, operator, at=NOW - timedelta(days=6), confidence=90, prediction="5-7")
    scan(db, operator, confidence=90, prediction="1", statuses=[(NOW, InventoryStatusEnum.SOLD)])
    scan(db, operator, confidence=None)
    scan(db, operator, prediction="N/A")
    summary = await dashboard.get_summary(db, operator)
    all_rows = await scan_logs.list_scan_logs(db, operator, ScanLogQuery())
    review = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(attention="review"))
    risk = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(attention="at-risk"))
    flagged = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(flagged_only=True))
    assert all_rows.review_count == review.total == summary.pending_review_count == 2
    assert {r.id for r in review.items} == {unflagged_low, flagged_high}
    assert all_rows.at_risk_count == risk.total == summary.expiring_stock_count == 3
    assert {r.id for r in risk.items} == {unflagged_low, flagged_high, aged}
    assert all_rows.flagged_count == flagged.total == 1
    assert flagged.items[0].id == flagged_high


@pytest.mark.asyncio
async def test_selected_business_day_applies_to_dashboard_groups_and_logs(logs_db):
    db = logs_db
    admin, yesterday_op, today_op = account(db, role="Admin"), account(db), account(db)
    start, end = dashboard.business_day_bounds(NOW.date())
    before = scan(db, yesterday_op, at=start - timedelta(microseconds=1), source="Yesterday")
    at_start = scan(db, today_op, at=start, source="Today")
    scan(db, today_op, at=end, source="Tomorrow")
    today = await dashboard.get_summary(db, admin)
    yesterday = await dashboard.get_summary(db, admin, business_date=NOW.date() - timedelta(days=1))
    assert today.total_scans == today.active_operator_count == 1
    assert [(s.name, s.count) for s in today.sources] == [("Today", 1)]
    assert [o.operator_id for o in today.operators] == [today_op.operator_id]
    assert yesterday.business_date == NOW.date() - timedelta(days=1)
    assert yesterday.total_scans == 1
    assert [(s.name, s.count) for s in yesterday.sources] == [("Yesterday", 1)]
    selected = await scan_logs.list_scan_logs(db, admin, ScanLogQuery(business_date=NOW.date()))
    previous = await scan_logs.list_scan_logs(db, admin, ScanLogQuery(business_date=yesterday.business_date))
    assert [r.id for r in selected.items] == [at_start]
    assert [r.id for r in previous.items] == [before]
    assert (await scan_logs.list_scan_logs(db, admin, ScanLogQuery())).total == 3


@pytest.mark.asyncio
async def test_extended_fields_numeric_sort_literal_search_and_safe_csv(logs_db):
    db = logs_db
    operator = account(db, name="=SUM(1,2)")
    special_source = '@formula,"quoted"\nnext'
    low = scan(db, operator, source=special_source, prediction="1-3", confidence=0,
               statuses=[(NOW - timedelta(hours=1), InventoryStatusEnum.SOLD),
                         (NOW, InventoryStatusEnum.IN_STOCK)])
    high = scan(db, operator, source="Farm 100%_literal", prediction="9-11", confidence=80)
    missing = scan(db, operator, source="Normal", confidence=None)
    db.session.execute(update(Scan).where(Scan.id == low).values(is_overridden=True))
    db.session.execute(update(ScanClassification).where(ScanClassification.scan_id == low).values(
        temperature=0, humidity=0, finger_count=0, thumbnail_url="/captures/example.jpg",
    ))
    by_days = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(sort="spoilage_days", direction="asc"))
    assert [r.id for r in by_days.items] == [low, high, missing]
    row = by_days.items[0]
    assert row.temperature == row.humidity == row.finger_count == row.confidence == 0
    assert row.thumbnail_url == "/captures/example.jpg" and row.is_overridden
    assert row.status_updated_at == NOW
    literal = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(search="%_"))
    assert [r.id for r in literal.items] == [high]
    csv_data = await csv_rows(db, operator, ScanLogQuery(sort="spoilage_days", direction="asc"))
    assert csv_data[0]["Source"] == "'" + special_source
    assert csv_data[0]["Operator"] == "'=SUM(1,2)"
    assert csv_data[0]["Confidence (%)"] == "0.0"
    assert csv_data[2]["Confidence (%)"] == ""
    db.session.execute(update(ScanClassification).where(ScanClassification.scan_id == high).values(
        cultivar=CultivarEnum.LATUNDAN, ripeness=RipenessEnum.SEMI_RIPE,
    ))
    by_enum = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(
        cultivar="Latundan", ripeness="Semi Ripe", search="semi ripe",
    ))
    assert [r.id for r in by_enum.items] == [high]
    by_uuid = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(search=str(high)))
    assert [r.id for r in by_uuid.items] == [high]


@pytest.mark.asyncio
async def test_export_crosses_stream_batches_without_pagination_truncation(logs_db):
    operator = account(logs_db)
    for index in range(205):
        scan(logs_db, operator, at=NOW - timedelta(seconds=index))
    stream = await scan_logs.export_scan_logs(
        logs_db, operator, ScanLogQuery(page=20, page_size=1),
    )
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 3  # Header, 200 rows, then the final 5 rows.
    rows = list(csv.DictReader(io.StringIO("".join(chunks).lstrip("\ufeff"))))
    assert len(rows) == len({row["Scan ID"] for row in rows}) == 205


def test_api_query_validation_authentication_export_and_page_independent_metrics(logs_db):
    db = logs_db
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_stream_db] = database
    with TestClient(app) as client:
        assert client.get("/api/v1/scan-logs").status_code == 401
        assert client.get("/api/v1/scan-logs/export").status_code == 401
        operator = account(db)
        for _ in range(23):
            scan(db, operator, confidence=50)
        app.dependency_overrides[get_current_user] = lambda: operator
        response = client.get("/api/v1/scan-logs", params={"page": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == data["review_count"] == 23
        assert data["page_size"] == 10
        exported = client.get("/api/v1/scan-logs/export", params={"page": 3, "page_size": 1})
        assert exported.status_code == 200
        assert len(list(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))) == 23
        assert "attachment" in exported.headers["content-disposition"]
        for params in (
            {"page": 0}, {"page_size": 101}, {"business_date": "bad"}, {"operator_id": "bad"},
            {"intake_id": "bad"}, {"cultivar": "bad"}, {"ripeness": "bad"},
            {"inventory_status": "bad"}, {"attention": "bad"}, {"sort": "bad"},
            {"direction": "bad"}, {"flagged_only": "bad"},
        ):
            assert client.get("/api/v1/scan-logs", params=params).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sort", ["date_time", "cultivar", "confidence", "spoilage_days", "finger_count"]
)
@pytest.mark.parametrize('direction', ['asc', 'desc'])
async def test_equal_key_pages_are_deterministic_and_account_scoped(logs_db, sort, direction):
    own, other = account(logs_db), account(logs_db)
    expected = {scan(logs_db, own, confidence=75, prediction='4') for _ in range(7)}
    expected.add(scan(logs_db, own, confidence=None))
    scan(logs_db, other, confidence=75, prediction='4')
    query = ScanLogQuery(sort=sort, direction=direction, page_size=3)
    pages = [
        await scan_logs.list_scan_logs(logs_db, own, query.model_copy(update={"page": page}))
        for page in (1, 2, 3)
    ]
    identifiers = [row.id for page in pages for row in page.items]
    assert len(identifiers) == len(set(identifiers)) == 8
    assert set(identifiers) == expected
    again = await scan_logs.list_scan_logs(logs_db, own, query)
    assert [row.id for row in again.items] == identifiers[:3]
    assert [row["Scan ID"] for row in await csv_rows(logs_db, own, query)] == [
        str(i) for i in identifiers
    ]


@pytest.mark.asyncio
async def test_csv_round_trip_special_characters_and_formula_prefixes(logs_db):
    own = account(logs_db)
    values = ['Mangga, saging "hinog" — 日本語', 'line\rreturn', 'line\nfeed', 'line\r\npair',
              '=1+1', '+SUM(1,2)', '-cmd', '@formula', '  =1', '\t+1', '\r-1', '\n@1']
    ids = [scan(logs_db, own, source=value) for value in values]
    rows = {row['Scan ID']: row for row in await csv_rows(logs_db, own, ScanLogQuery())}
    for identifier, value in zip(ids, values, strict=True):
        # Source labels have always been trimmed by the shared SQL projection.
        normalized = value.strip()
        expected = "'" + normalized if normalized.startswith(('=', '+', '-', '@')) else normalized
        assert rows[str(identifier)]['Source'] == expected
        if value.lstrip().startswith(('=', '+', '-', '@')):
            assert scan_logs._safe_cell(value) == "'" + value
    assert scan_logs._safe_cell(-1.5) == -1.5

@pytest.mark.asyncio
async def test_success_drilldown_matches_dashboard_numerator_and_full_export(logs_db):
    db = logs_db  # noqa: F811 - pytest fixture injection
    own, other = account(db), account(db)
    expected = {scan(db, own, confidence=85), scan(db, own, confidence=90)}
    scan(db, own, confidence=60)
    scan(db, own, confidence=95, flagged=True)
    scan(db, own, confidence=None)
    scan(db, other, confidence=99)
    summary = await dashboard.get_summary(db, own)
    result = await scan_logs.list_scan_logs(db, own, ScanLogQuery(attention='success'))
    assert summary.success_rate == 40
    assert result.total == 2 and {row.id for row in result.items} == expected
    assert {
        row["Scan ID"]
        for row in await csv_rows(db, own, ScanLogQuery(attention="success", page=7, page_size=1))
    } == {str(sid) for sid in expected}


@pytest.mark.asyncio
async def test_review_drilldown_preserves_low_confidence_scans_with_flagged_status(logs_db):
    db = logs_db
    own, other = account(db), account(db)
    flagged_high_conf = scan(db, own, confidence=95, flagged=True)
    unflagged_low_conf = scan(db, own, confidence=70, flagged=False)
    scan(db, own, confidence=95, flagged=False)
    scan(db, other, confidence=60, flagged=True)

    summary = await dashboard.get_summary(db, own)
    assert summary.pending_review_count == 2

    result = await scan_logs.list_scan_logs(
        db, own, ScanLogQuery(attention="review", flagged_only=True)
    )
    assert result.total == 2
    assert {row.id for row in result.items} == {flagged_high_conf, unflagged_low_conf}

    flagged_only_result = await scan_logs.list_scan_logs(
        db, own, ScanLogQuery(flagged_only=True)
    )
    assert flagged_only_result.total == 1
    assert flagged_only_result.items[0].id == flagged_high_conf


def test_scan_logs_query_limit_alias_syncs_with_page_size():
    q_default = ScanLogQuery()
    assert q_default.page_size == 10
    assert q_default.limit is None

    q_limit = ScanLogQuery(limit=25)
    assert q_limit.page_size == 25
    assert q_limit.limit == 25

    q_page_size = ScanLogQuery(page_size=50)
    assert q_page_size.page_size == 50

    from app.services.scan_snapshots import binding
    # Binding key should match whether limit or page_size was specified for the same page_size
    key_limit = binding("logs", q_limit.model_dump(mode="json", exclude={"page", "snapshot_id", "stable", "limit"}))
    key_page_size = binding("logs", ScanLogQuery(page_size=25).model_dump(mode="json", exclude={"page", "snapshot_id", "stable", "limit"}))
    assert key_limit == key_page_size

