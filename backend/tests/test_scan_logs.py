"""Centralized Scan Logs filters, metrics, scope and complete safe export."""

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.deps import get_current_user
from app.api.v1.scan_logs import router
from app.core import database
from app.core.database import get_db, get_stream_db
from app.core.export_format import format_manila_datetime, format_scan_ref
from app.models.activity_log import ActivityLog
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.supplier import Supplier
from app.models.system_config import SystemConfig
from app.models.user_account import UserAccount
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum
from app.schemas.scan_logs import ScanLogQuery
from app.services import dashboard, scan_logs
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_time_and_writes import SessionAdapter


@pytest.fixture
def logs_db(db, monkeypatch):
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
    # Exports are audited. The rows go to this disposable database: a request's own row
    # through its session, an export stream's row through a separate session.
    engine = db.session.get_bind()
    ActivityLog.__table__.create(engine, checkfirst=True)
    ScanOriginalAiResult.__table__.create(engine, checkfirst=True)
    insert_values = db.add

    def add(model, **values):
        if isinstance(model, type):
            return insert_values(model, **values)
        db.session.add(model)

    db.add = add
    db.audit_state = SimpleNamespace(fail_commit=False, events=[])
    monkeypatch.setattr(
        database, "async_session_factory", lambda: SessionAdapter(engine, db.audit_state),
    )
    return db


def parse_xlsx_dicts(xlsx_bytes: bytes) -> list[dict[str, str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    xml_rows = root.findall("m:sheetData/m:row", ns)
    headers = []
    for cell in xml_rows[0].findall("m:c", ns):
        assert cell.find("m:f", ns) is None
        text = cell.find("m:is/m:t", ns)
        headers.append(text.text if text is not None and text.text is not None else "")
    records: list[dict[str, str]] = []
    for xml_row in xml_rows[1:]:
        values = []
        for cell in xml_row.findall("m:c", ns):
            assert cell.find("m:f", ns) is None
            text = cell.find("m:is/m:t", ns)
            num = cell.find("m:v", ns)
            val = text.text if text is not None else num.text if num is not None else ""
            values.append(val or "")
        records.append(dict(zip(headers, values, strict=True)))
    return records


async def export_rows(db, user, query):
    xlsx_bytes = await scan_logs.export_scan_logs_xlsx(db, user, query)
    return parse_xlsx_dicts(xlsx_bytes)


@pytest.mark.asyncio
@pytest.mark.parametrize("stable", [False, True])
async def test_stock_eligible_filters_list_export_and_snapshot_binding(
    logs_db, monkeypatch, stable,
):
    from app.services import auth_service

    own, other = account(logs_db), account(logs_db)
    expected = {scan(logs_db, own)}  # Explicitly unlinked stock is eligible.
    scan(logs_db, other)  # Eligibility must not broaden account scope.
    scan(logs_db, own, statuses=[(NOW, InventoryStatusEnum.SOLD)])
    for status, provenance, matching_origin in (
        ("Active", "linked", True),
        ("Depleted", "linked", True),
        ("Active", "unverified", True),
        ("Active", "linked", False),
    ):
        intake_id = uuid4()
        logs_db.add(Intake, id=intake_id, source="Farm A", intake_date=NOW.date(),
                    status=status)
        identifier = scan(logs_db, own, intake=intake_id)
        logs_db.session.execute(update(Scan).where(Scan.id == identifier).values(
            intake_provenance=provenance,
            intake_origin_id=intake_id if matching_origin else uuid4(),
        ))
        if status == "Active" and provenance == "linked" and matching_origin:
            expected.add(identifier)

    snapshots = {}

    async def lock(_db, user):
        return user

    async def save(_db, _user, key, payload):
        saved = SimpleNamespace(id=uuid4(), payload=payload, binding=key,
                                expires_at=NOW + timedelta(minutes=10))
        snapshots[saved.id] = saved
        return saved

    async def load(_db, _user, identifier, key, lock=True):
        saved = snapshots[identifier]
        if key != saved.binding:
            raise HTTPException(409, "Filters changed")
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    query = ScanLogQuery(stock_eligible=True, stable=stable, page_size=100)
    result = await scan_logs.list_scan_logs(logs_db, own, query)
    assert result.total == len(expected)
    assert {row.id for row in result.items} == expected
    export_query = query.model_copy(update={"snapshot_id": result.snapshot_id})
    exported = await export_rows(logs_db, own, export_query)
    assert len(exported) == len(expected)
    assert all(row["Inventory Status"] == "In Stock" for row in exported)
    if stable:
        # The frozen result keeps its eligibility decision until refreshed.
        logs_db.session.execute(update(Intake).values(status="Depleted"))
        frozen = await scan_logs.list_scan_logs(logs_db, own, export_query)
        assert {row.id for row in frozen.items} == expected
        refreshed = await scan_logs.list_scan_logs(logs_db, own, query)
        assert refreshed.total == 1
        changed = export_query.model_copy(update={"stock_eligible": False})
        with pytest.raises(HTTPException) as rejected_list:
            await scan_logs.list_scan_logs(logs_db, own, changed)
        assert rejected_list.value.status_code == 409
        with pytest.raises(HTTPException) as rejected_export:
            await export_rows(logs_db, own, changed)
        assert rejected_export.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("stable", [False, True])
async def test_risk_rows_counts_filters_and_export_share_unrounded_stock_rule(
    logs_db, monkeypatch, stable,
):
    from app.services import auth_service
    from app.services.inventory_policy import inventory_facts

    operator = account(logs_db)
    # The range is stored evidence, not a display string to classify in the browser.
    cases = [
        ("1.9999", 0, "In Stock", True),
        ("2", 0, "In Stock", True),
        ("2.00001", 0, "In Stock", False),  # Serialized remaining rounds to 2.
        ("0", 0, "In Stock", True),
        ("1", 2, "In Stock", True),  # Overdue stock remains at risk.
        ("1-3", 0, "In Stock", True),
        ("1-4", 0, "In Stock", False),  # Overlap alone is insufficient.
        ("3-6", 3, "In Stock", True),  # Original range remains unchanged.
        (None, 0, "In Stock", False),
        ("Unknown", 0, "In Stock", False),
        ("3-1", 0, "In Stock", False),
        ("-1", 0, "In Stock", False),
        ("1", 0, "Sold", False),
        ("1", 0, "Spoiled", False),
        ("1", 0, "For Processing", False),
    ]
    expected = {}
    predictions = {}
    for prediction, age, status, at_risk in cases:
        at = NOW - timedelta(days=age)
        identifier = scan(
            logs_db, operator, prediction=prediction, at=at,
            statuses=[(NOW, InventoryStatusEnum(status))],
        )
        expected[identifier] = at_risk
        predictions[identifier] = prediction
        facts = inventory_facts(SimpleNamespace(
            intake_provenance="unlinked", intake_id=None, intake_origin_id=None,
            classification=SimpleNamespace(spoilage_days=prediction), date_time=at,
        ), status, NOW)
        assert (
            facts["inventory_eligible"] and facts["remaining_days"] is not None
            and facts["remaining_days"] <= 2
        ) is at_risk

    for provenance, intake_status, at_risk in (
        ("unverified", "Active", False), ("linked", "Depleted", False),
        ("linked", "Active", True),
    ):
        intake_id = uuid4()
        logs_db.add(Intake, id=intake_id, source="Farm A", intake_date=NOW.date(),
                    status=intake_status)
        identifier = scan(logs_db, operator, prediction="1", intake=intake_id)
        logs_db.session.execute(update(Scan).where(Scan.id == identifier).values(
            intake_provenance=provenance, intake_origin_id=intake_id,
        ))
        expected[identifier] = at_risk
        predictions[identifier] = "1"

    snapshots = {}

    async def lock(_db, user):
        return user

    async def save(_db, _user, key, payload):
        saved = SimpleNamespace(id=uuid4(), payload=payload, binding=key,
                                expires_at=NOW + timedelta(minutes=10))
        snapshots[saved.id] = saved
        return saved

    async def load(_db, _user, identifier, key, lock=True):
        saved = snapshots[identifier]
        if key != saved.binding:
            raise HTTPException(409, "Filters changed")
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    query = ScanLogQuery(stable=stable, page_size=100, sort="spoilage_days", direction="asc")
    all_rows = await scan_logs.list_scan_logs(logs_db, operator, query)
    assert all("at_risk" not in row.model_dump() and "_at_risk" not in row.model_dump()
               for row in all_rows.items)
    assert {row.id: row.spoilage_days for row in all_rows.items} == predictions
    above = next(row for row in all_rows.items if row.spoilage_days == "2.00001")
    assert above.remaining_days == 2
    expected_ids = {identifier for identifier, risk in expected.items() if risk}
    assert all_rows.at_risk_count == len(expected_ids)
    summary = await dashboard.get_summary(logs_db, operator)
    dashboard_rows = await dashboard.list_scans(logs_db, operator, view="expiring", page_size=100)
    assert summary.expiring_stock_count == len(expected_ids)
    assert {row.id for row in dashboard_rows.items} == expected_ids

    risk_query = query.model_copy(update={
        "attention": "at-risk", "page_size": 3, "snapshot_id": all_rows.snapshot_id,
    })
    first = await scan_logs.list_scan_logs(logs_db, operator, risk_query)
    ids = {row.id for row in first.items}
    for page in range(2, (first.total + 2) // 3 + 1):
        part = await scan_logs.list_scan_logs(logs_db, operator, risk_query.model_copy(
            update={"page": page, "snapshot_id": first.snapshot_id},
        ))
        assert part.total == part.at_risk_count == first.at_risk_count
        assert all(row.id in expected_ids for row in part.items)
        assert not ids.intersection(row.id for row in part.items)
        ids.update(row.id for row in part.items)
    assert ids == expected_ids
    exported = await export_rows(logs_db, operator, risk_query.model_copy(
        update={"snapshot_id": first.snapshot_id},
    ))
    assert len(exported) == len(ids)
    assert all("Est. Time Left / Freshness" in row for row in exported)
    if stable:
        monkeypatch.setattr(dashboard, "now_manila", lambda: NOW + timedelta(days=1))
        frozen = await scan_logs.list_scan_logs(logs_db, operator, query.model_copy(
            update={"snapshot_id": all_rows.snapshot_id},
        ))
        assert frozen.model_dump() == all_rows.model_dump()
        refreshed = await scan_logs.list_scan_logs(logs_db, operator, query)
        refreshed_risk = await scan_logs.list_scan_logs(logs_db, operator, query.model_copy(
            update={"snapshot_id": refreshed.snapshot_id, "attention": "at-risk"},
        ))
        assert above.id in {row.id for row in refreshed_risk.items}
        assert refreshed.at_risk_count == refreshed_risk.total
        frozen_risk = await scan_logs.list_scan_logs(logs_db, operator, query.model_copy(
            update={"snapshot_id": all_rows.snapshot_id, "attention": "at-risk"},
        ))
        assert {row.id for row in frozen_risk.items} == expected_ids
        for change in ({"search": "another"}, {"cultivar": "Cardaba"}, {"direction": "desc"}):
            with pytest.raises(HTTPException) as rejected:
                await scan_logs.list_scan_logs(logs_db, operator, risk_query.model_copy(
                    update=change,
                ))
            assert rejected.value.status_code == 409


def test_vpd_logs_api_and_export_preserve_stored_values_and_scope(logs_db):
    own, other = account(logs_db), account(logs_db)
    expected = {}
    for value in (1.555, 0, None):
        identifier = scan(logs_db, own)
        expected[str(identifier)] = value
        logs_db.session.execute(update(ScanClassification).where(
            ScanClassification.scan_id == identifier,
        ).values(temperature=22.29, humidity=53.37, vpd=value))
    expected[str(scan(logs_db, own, confidence=None))] = None
    scan(logs_db, other)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield logs_db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_stream_db] = database
    app.dependency_overrides[get_current_user] = lambda: own
    with TestClient(app) as client:
        response = client.get("/api/v1/scan-logs")
        assert response.status_code == 200
        assert {row["id"]: row["vpd"] for row in response.json()["items"]} == expected
        exported = client.get("/api/v1/scan-logs/export")
        assert exported.status_code == 200
        rows = parse_xlsx_dicts(exported.content)
        assert len(rows) == 4
        # Programmer/scientific fields stay on the API, excluded from client exports.
        assert "VPD (kPa)" not in rows[0]
        assert "Scan ID" not in rows[0]


@pytest.mark.asyncio
async def test_vpd_snapshot_keeps_recorded_value_and_legacy_missing_stays_unknown(
    logs_db, monkeypatch,
):
    from app.services import auth_service

    own = account(logs_db)
    identifier = scan(logs_db, own)
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == identifier,
    ).values(temperature=22.29, humidity=53.37, vpd=1.555))
    saved = None

    async def lock(_db, user):
        return user

    async def save(_db, _user, _key, payload):
        nonlocal saved
        saved = SimpleNamespace(id=uuid4(), payload=payload, expires_at=NOW + timedelta(minutes=10))
        return saved

    async def load(*_args, **_kwargs):
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    first = await scan_logs.list_scan_logs(logs_db, own, ScanLogQuery(stable=True))
    assert first.items[0].model_dump()["vpd"] == 1.555
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == identifier,
    ).values(vpd=2.999))
    query = ScanLogQuery(snapshot_id=first.snapshot_id)
    frozen = await scan_logs.list_scan_logs(logs_db, own, query)
    assert frozen.items[0].vpd == 1.555
    exported_frozen = await export_rows(logs_db, own, query)
    assert len(exported_frozen) == 1 and "VPD (kPa)" not in exported_frozen[0]
    # A snapshot captured before the API extension has no VPD key. Do not derive
    # one from its temperature/humidity or replace it with a current DB reading.
    del saved.payload["items"][0]["vpd"]
    legacy = await scan_logs.list_scan_logs(logs_db, own, query)
    assert legacy.items[0].model_dump(mode="json")["vpd"] is None
    assert len(await export_rows(logs_db, own, query)) == 1


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
    exported = await export_rows(db, admin, query.model_copy(update={"page": 9, "page_size": 1}))
    assert len(exported) == 31
    assert exported[0]["Date & Time"] == format_manila_datetime(first.items[0].date_time)
    assert exported[0]["Source / Supplier"] == "Farm A"
    assert exported[0]["Review Status"] == "Needs Review"
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
    assert await export_rows(db, own, ScanLogQuery(operator_id=other.operator_id)) == []
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
    # Review is the flag alone: an unflagged low-confidence scan was checked by a person.
    assert all_rows.review_count == review.total == summary.pending_review_count == 1
    assert {r.id for r in review.items} == {flagged_high}
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
    assert row.thumbnail_url == "/captures/example.jpg?variant=thumb" and row.is_overridden
    assert row.status_updated_at == NOW
    literal = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(search="%_"))
    assert [r.id for r in literal.items] == [high]
    export_data = await export_rows(db, operator, ScanLogQuery(sort="spoilage_days", direction="asc"))
    assert export_data[0]["Scan Ref"] == format_scan_ref(low)
    assert export_data[0]["Source / Supplier"] == special_source
    assert export_data[0]["Operator"] == "=SUM(1,2)"
    assert export_data[0]["Confidence (%)"] == "0.0"
    assert export_data[2]["Confidence (%)"] == ""
    db.session.execute(update(ScanClassification).where(ScanClassification.scan_id == high).values(
        cultivar=CultivarEnum.LATUNDAN, ripeness=RipenessEnum.SEMI_RIPE,
    ))
    by_enum = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(
        cultivar="Latundan", ripeness="Semi Ripe", search="semi ripe",
    ))
    assert [r.id for r in by_enum.items] == [high]
    by_uuid = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(search=str(high)))
    assert [r.id for r in by_uuid.items] == [high]
    # Direct lookup using the exported short Scan Ref (with and without prefix, case-insensitive).
    high_ref = format_scan_ref(high)
    short_hex = high_ref.removeprefix("SCAN-")
    for query_text in (high_ref, high_ref.lower(), short_hex, short_hex.lower()):
        matched = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(search=query_text))
        assert [r.id for r in matched.items] == [high], query_text


@pytest.mark.asyncio
async def test_export_crosses_stream_batches_without_pagination_truncation(logs_db):
    operator = account(logs_db)
    for index in range(205):
        scan(logs_db, operator, at=NOW - timedelta(seconds=index), source=f"Batch {index:03d}")
    xlsx_bytes = await scan_logs.export_scan_logs_xlsx(
        logs_db, operator, ScanLogQuery(page=20, page_size=1),
    )
    rows = parse_xlsx_dicts(xlsx_bytes)
    assert len(rows) == len({row["Source / Supplier"] for row in rows}) == 205
    pdf_bytes = await scan_logs.export_scan_logs_pdf(
        logs_db, operator, ScanLogQuery(format="pdf", page=20, page_size=1),
    )
    assert pdf_bytes.startswith(b"%PDF-1.4\n")


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
            scan(db, operator, confidence=50, flagged=True)
        app.dependency_overrides[get_current_user] = lambda: operator
        response = client.get("/api/v1/scan-logs", params={"page": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == data["review_count"] == 23
        assert data["page_size"] == 10
        exported = client.get("/api/v1/scan-logs/export", params={"page": 3, "page_size": 1})
        assert exported.status_code == 200
        assert len(parse_xlsx_dicts(exported.content)) == 23
        assert "attachment" in exported.headers["content-disposition"]
        # Paging never limits an export, so it is not recorded as a filter.
        assert db.session.scalars(
            select(ActivityLog.details).where(ActivityLog.action == "data_exported")
        ).all() == ["Exported scan logs (xlsx, own scans): filters none"]
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
    exported = await export_rows(logs_db, own, query)
    assert len(exported) == 8
    assert [row["Scan Ref"] for row in exported] == [format_scan_ref(i) for i in identifiers]
    assert [row["Confidence (%)"] for row in exported] == [
        "" if r.confidence is None else f"{r.confidence:.1f}"
        for page in pages for r in page.items
    ]


@pytest.mark.asyncio
async def test_xlsx_round_trip_special_characters_and_formula_prefixes(logs_db):
    own = account(logs_db)
    values = ['Mangga, saging "hinog" — 日本語', 'line\rreturn', 'line\nfeed', 'line\r\npair',
              '=1+1', '+SUM(1,2)', '-cmd', '@formula', '  =1', '\t+1', '\r-1', '\n@1']
    for value in values:
        scan(logs_db, own, source=value)
    rows = await export_rows(logs_db, own, ScanLogQuery())
    sources = [row["Source / Supplier"] for row in rows]
    # Inline strings keep exact trimmed text without formula elements; XML normalizes CR to LF.
    assert set(sources) == {
        value.strip().replace("\r\n", "\n").replace("\r", "\n") for value in values
    }


@pytest.mark.asyncio
async def test_success_drilldown_matches_dashboard_numerator_and_full_export(logs_db):
    db = logs_db  # noqa: F811 - pytest fixture injection
    own, other = account(db), account(db)
    # Successful = not flagged with a known confidence; the unflagged 60 was checked by a
    # person (low new scans are flagged when saved), unknown confidence is never approved.
    expected = {
        scan(db, own, confidence=85), scan(db, own, confidence=90), scan(db, own, confidence=60),
    }
    scan(db, own, confidence=95, flagged=True)
    scan(db, own, confidence=None)
    scan(db, other, confidence=99)
    summary = await dashboard.get_summary(db, own)
    result = await scan_logs.list_scan_logs(db, own, ScanLogQuery(attention='success'))
    assert summary.success_rate == 60
    assert result.total == 3 and {row.id for row in result.items} == expected
    exported = await export_rows(db, own, ScanLogQuery(attention="success", page=7, page_size=1))
    assert {row["Scan Ref"] for row in exported} == {format_scan_ref(sid) for sid in expected}
    assert {row["Confidence (%)"] for row in exported} == {"85.0", "90.0", "60.0"}


@pytest.mark.asyncio
async def test_at_risk_subset_of_a_snapshot_counts_review_as_flagged(logs_db, monkeypatch):
    from app.services import auth_service

    db = logs_db  # noqa: F811 - pytest fixture injection
    operator = account(db)
    stored = {}

    async def lock(_db, user):
        return user

    async def save(_db, _user, key, payload):
        stored.update(key=key, saved=SimpleNamespace(
            id=uuid4(), payload=payload, expires_at=NOW + timedelta(minutes=10),
        ))
        return stored["saved"]

    async def load(_db, _user, _token, key, lock=True):
        if key != stored["key"]:
            raise HTTPException(409, "Browse filters changed.")
        return stored["saved"]

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    db.add(SystemConfig, confidence_threshold=85, data_retention_enabled=False)
    scan(db, operator, confidence=60, prediction="1")  # Flag removed after a check.
    scan(db, operator, confidence=95, prediction="1", flagged=True)
    parent = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(stable=True))
    subset = await scan_logs.list_scan_logs(
        db, operator, ScanLogQuery(attention="at-risk", snapshot_id=parent.snapshot_id)
    )
    direct = await scan_logs.list_scan_logs(db, operator, ScanLogQuery(attention="at-risk"))
    summary = await dashboard.get_summary(db, operator)
    assert subset.total == direct.total == 2
    assert subset.review_count == subset.flagged_count == direct.review_count == 1
    assert summary.pending_review_count == 1


@pytest.mark.asyncio
async def test_review_drilldown_is_the_flagged_scans(logs_db):
    db = logs_db
    own, other = account(db), account(db)
    flagged_high_conf = scan(db, own, confidence=95, flagged=True)
    scan(db, own, confidence=70, flagged=False)  # Flag removed after a person checked it.
    scan(db, own, confidence=95, flagged=False)
    scan(db, other, confidence=60, flagged=True)

    summary = await dashboard.get_summary(db, own)
    assert summary.pending_review_count == 1

    for query in (
        ScanLogQuery(attention="review"), ScanLogQuery(attention="review", flagged_only=True)
    ):
        result = await scan_logs.list_scan_logs(db, own, query)
        assert result.total == 1
        assert {row.id for row in result.items} == {flagged_high_conf}

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

    # Export binding key must also match when limit alias is used
    export_key = binding("logs", ScanLogQuery(limit=25, snapshot_id=uuid4()).model_dump(mode="json", exclude={"page", "snapshot_id", "stable", "limit"}))
    assert export_key == key_page_size


@pytest.mark.asyncio
async def test_export_scan_logs_with_limit_alias(logs_db):
    db = logs_db
    own = account(db)
    scan(db, own, confidence=88, prediction="3")
    export_query = ScanLogQuery(limit=25)
    rows = await export_rows(db, own, export_query)
    assert len(rows) == 1
    assert rows[0]["Confidence (%)"] == "88.0"


@pytest.mark.asyncio
async def test_pending_count_tracks_only_new_matching_scoped_scans(logs_db, monkeypatch):
    from app.services import auth_service

    session = logs_db
    own, other = account(session), account(session)
    original = scan(session, own, at=NOW - timedelta(minutes=5), source="Farm A")
    scan(session, own, at=NOW - timedelta(minutes=4), source="Farm B")
    snapshots = {}

    async def lock(_db, user):
        return user

    async def save(_db, _user, key, payload):
        saved = SimpleNamespace(id=uuid4(), payload=payload, binding=key,
                                expires_at=NOW + timedelta(minutes=10))
        snapshots[saved.id] = saved
        return saved

    async def load(_db, _user, identifier, key, lock=True):
        saved = snapshots[identifier]
        if key != saved.binding:
            raise HTTPException(409, "Filters changed")
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    query = ScanLogQuery(stable=True, source_key="text:Farm A", page_size=1)
    first = await scan_logs.list_scan_logs(session, own, query)
    frozen_query = query.model_copy(update={"snapshot_id": first.snapshot_id})
    assert (await scan_logs.pending_scan_count(session, own, frozen_query)).new_count == 0

    matching = scan(session, own, at=NOW + timedelta(seconds=1), source="Farm A")
    scan(session, other, at=NOW + timedelta(seconds=1), source="Farm A")
    scan(session, own, at=NOW + timedelta(seconds=1), source="Farm B")
    pending = await scan_logs.pending_scan_count(session, own, frozen_query)
    assert pending.snapshot_id == first.snapshot_id
    assert pending.new_count == 1
    # Repeated checks are absolute, never additive, so reconnects cannot double-count.
    assert (await scan_logs.pending_scan_count(session, own, frozen_query)).new_count == 1
    frozen = await scan_logs.list_scan_logs(session, own, frozen_query)
    assert frozen.total == 1 and [row.id for row in frozen.items] == [original]
    assert matching not in {row.id for row in frozen.items}
