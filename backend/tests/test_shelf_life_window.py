"""Live shelf-life window: Asia/Manila calendar days over an immutable stored estimate.

The stored `spoilage_days` string and the scan timestamp never change. Every read
derives the remaining range from whole Manila calendar days since the scan.
"""
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm import Session, selectinload

from app.api.v1 import scans as scans_api
from app.core.time import MANILA
from app.models import Scan
from app.schemas.enums import InventoryStatusEnum
from app.schemas.scan import PublicScanResponse, ScanResponse
from app.services import dashboard, scan_logs, scan_records
from app.services.inventory_policy import (
    elapsed_manila_days,
    inventory_facts,
    prediction_bounds,
    remaining_shelf_life,
    shelf_life_window,
)
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_scan_logs import logs_db  # noqa: F401
from tests.test_time_and_writes import application  # noqa: F401

CASES = json.loads(
    (Path(__file__).parent / "data" / "shelf_life_window_cases.json").read_text(encoding="utf-8")
)
# 2026-11-06 10:00 in Manila: an ordinary scan time.
SCANNED = datetime(2026, 11, 6, 10, 0, tzinfo=MANILA)


def manila(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=MANILA)


@pytest.mark.parametrize("case", CASES["bounds"], ids=lambda case: repr(case["stored"]))
def test_stored_estimate_becomes_the_whole_day_window_it_is_displayed_with(case):
    assert prediction_bounds(case["stored"]) == (case["min"], case["max"])


@pytest.mark.parametrize("stored", CASES["invalid"], ids=repr)
def test_unreadable_estimate_has_no_window_and_never_raises(stored):
    assert prediction_bounds(stored) is None
    assert shelf_life_window(stored, SCANNED, SCANNED + timedelta(days=1)) is None


@pytest.mark.parametrize(
    "case", CASES["progression"],
    ids=lambda case: f"{case['min']}-{case['max']} day+{case['elapsed']}",
)
def test_window_counts_down_by_elapsed_calendar_days(case):
    stored = str(case["min"]) if case["min"] == case["max"] else f"{case['min']}-{case['max']}"
    now = SCANNED + timedelta(days=case["elapsed"])
    assert shelf_life_window(stored, SCANNED, now) == {
        "min_days": case["min"],
        "max_days": case["max"],
        "elapsed_days": case["elapsed"],
        "remaining_min_days": case["remaining_min"],
        "remaining_max_days": case["remaining_max"],
        "days_past": case["days_past"],
        "state": case["state"],
        "scan_date": "2026-11-06",
        "as_of_date": now.date().isoformat(),
    }


@pytest.mark.parametrize("case", CASES["roll_forward"], ids=lambda case: case["name"])
def test_server_answer_on_the_later_date_is_what_an_open_page_must_show(case):
    """The page rolls a served window forward by itself; this is the answer it has to reach."""
    stored = str(case["min"]) if case["min"] == case["max"] else f"{case['min']}-{case['max']}"
    scanned = datetime.fromisoformat(case["scan_date"] + "T10:00:00+08:00")
    later = max(case["served_date"], case["page_date"])
    window = shelf_life_window(stored, scanned, datetime.fromisoformat(later + "T09:00:00+08:00"))
    assert (window["elapsed_days"], window["state"]) == (case["elapsed"], case["state"])
    assert window["scan_date"] == case["scan_date"] and window["as_of_date"] == later
    served = shelf_life_window(
        stored, scanned, datetime.fromisoformat(case["served_date"] + "T09:00:00+08:00")
    )
    # What the server sends keeps the scan date even when its own count is clamped at zero.
    assert served["scan_date"] == case["scan_date"]
    assert served["elapsed_days"] == max(
        0, (date.fromisoformat(case["served_date"]) - date.fromisoformat(case["scan_date"])).days
    )


def test_estimate_too_large_for_a_number_has_no_window_instead_of_an_error():
    huge = "9" * 400
    assert prediction_bounds(huge) is None and prediction_bounds("1-" + huge) is None
    assert shelf_life_window(huge, SCANNED, SCANNED) is None
    # The page displays whole days only up to Number.MAX_SAFE_INTEGER
    # (frontend lib/spoilageDisplay.ts); a larger value has no window either.
    assert prediction_bounds("9007199254740991") == (9007199254740991, 9007199254740991)
    assert prediction_bounds("9007199254740992") is None
    assert prediction_bounds("9" * 20) is None
    assert shelf_life_window("9" * 20, SCANNED, SCANNED) is None


@pytest.mark.parametrize("stored", [".5", ".5-1.5", "0-.5", " .5 - 1.5 "])
def test_estimate_the_page_cannot_display_has_no_window(stored):
    """A countdown must never sit beside "Est. Unknown": the page shows "Unknown" for a
    number without a leading digit (frontend lib/spoilageDisplay.ts)."""
    assert prediction_bounds(stored) is None
    assert shelf_life_window(stored, SCANNED, SCANNED) is None


def test_display_rule_does_not_change_the_stock_risk_rule():
    # The at-risk midpoint is a separate, older rule; it still reads these values.
    assert remaining_shelf_life(".5-1.5", SCANNED, SCANNED) == 1.0
    assert remaining_shelf_life("9" * 20, SCANNED, SCANNED) == 1e20


def test_one_to_three_days_is_not_frozen_a_week_later():
    """The reported bug: "1-3" still read as 1-3 days seven days after the scan."""
    today = shelf_life_window("1-3", SCANNED, SCANNED)
    week = shelf_life_window("1-3", SCANNED, SCANNED + timedelta(days=7))
    assert (today["remaining_min_days"], today["remaining_max_days"]) == (1, 3)
    assert today["state"] == "active"
    assert (week["remaining_min_days"], week["remaining_max_days"]) == (0, 0)
    assert week["state"] == "expired" and week["days_past"] == 4
    assert (week["min_days"], week["max_days"]) == (1, 3)  # the baseline is still reported


def test_day_changes_at_manila_midnight_not_after_24_hours():
    created = manila(2026, 11, 6, 23, 50)  # 15:50 UTC
    assert created.astimezone(UTC).hour == 15
    assert elapsed_manila_days(created, manila(2026, 11, 6, 23, 59)) == 0
    after = manila(2026, 11, 7, 0, 5)  # 16:05 UTC, fifteen minutes after the scan
    assert after.astimezone(UTC).date() == date(2026, 11, 6)
    assert elapsed_manila_days(created, after) == 1
    window = shelf_life_window("1-3", created, after)
    assert (window["remaining_min_days"], window["remaining_max_days"]) == (0, 2)
    assert window["as_of_date"] == "2026-11-07" and window["scan_date"] == "2026-11-06"
    # The existing continuous countdown is a different value and keeps its meaning.
    assert remaining_shelf_life("1-3", created, after) == pytest.approx(2 - 15 / 1440)


def test_day_does_not_change_at_utc_midnight():
    created = datetime(2026, 11, 6, 23, 50, tzinfo=UTC)  # 07:50 on the 7th in Manila
    later = datetime(2026, 11, 7, 0, 5, tzinfo=UTC)  # 08:05 the same Manila day
    assert elapsed_manila_days(created, later) == 0
    # Stored instants without a zone are UTC (see app.core.time.as_manila).
    assert elapsed_manila_days(created.replace(tzinfo=None), later.replace(tzinfo=None)) == 0
    assert elapsed_manila_days(
        datetime(2026, 11, 6, 15, 50), datetime(2026, 11, 6, 16, 5)
    ) == 1
    # The two dates sent to the page are Manila dates as well, whatever zone came in.
    for scanned_at, now in (
        (datetime(2026, 9, 30, 17, 0, tzinfo=UTC), datetime(2026, 10, 2, 17, 30, tzinfo=UTC)),
        (datetime(2026, 9, 30, 17, 0), datetime(2026, 10, 2, 17, 30)),
    ):
        window = shelf_life_window("1-3", scanned_at, now)
        assert window["scan_date"] == "2026-10-01"  # 01:00 in Manila the next day
        assert window["as_of_date"] == "2026-10-03"  # 01:30 in Manila the next day
        assert window["elapsed_days"] == 2


def test_clock_skew_before_the_scan_never_goes_negative():
    window = shelf_life_window("1-3", SCANNED, SCANNED - timedelta(days=2, hours=3))
    assert elapsed_manila_days(SCANNED, SCANNED - timedelta(days=2)) == 0
    assert window["elapsed_days"] == 0 and window["state"] == "active"
    assert (window["remaining_min_days"], window["remaining_max_days"]) == (1, 3)


@pytest.mark.parametrize("scanned_at, now", [(None, SCANNED), (SCANNED, None), (None, None)])
def test_missing_timestamp_has_no_window(scanned_at, now):
    assert shelf_life_window("1-3", scanned_at, now) is None


def test_existing_countdown_number_is_unchanged():
    assert remaining_shelf_life("1-3", SCANNED, SCANNED + timedelta(days=1, hours=12)) == 0.5
    assert remaining_shelf_life("3", SCANNED, SCANNED) == 3
    assert remaining_shelf_life(" .5 - 1.5 ", SCANNED, SCANNED) == 1
    for invalid in CASES["invalid"]:
        assert remaining_shelf_life(invalid, SCANNED, SCANNED) is None


def test_inventory_facts_adds_the_window_without_touching_existing_facts():
    record = SimpleNamespace(
        intake_provenance="unlinked", intake_id=None, intake_origin_id=None, intake=None,
        date_time=SCANNED, classification=SimpleNamespace(spoilage_days="1-3"),
    )
    now = SCANNED + timedelta(days=1)
    facts = inventory_facts(record, "In Stock", now)
    assert facts["inventory_eligible"] is True
    assert facts["remaining_days"] == 1 and facts["risk_as_of"] == now
    assert facts["shelf_life_window"] == shelf_life_window("1-3", SCANNED, now)
    assert facts["ripeness_projection"] is None
    assert set(facts) == {
        "inventory_eligible", "remaining_days", "risk_as_of",
        "shelf_life_window", "ripeness_projection",
    }
    # The window does not depend on stock status or eligibility; pages decide what to show.
    for status in ("Sold", "Spoiled", "For Processing"):
        sold = inventory_facts(record, status, now)
        assert sold["inventory_eligible"] is False
        assert sold["shelf_life_window"] == facts["shelf_life_window"]
    record.intake_provenance = "unverified"
    unverified = inventory_facts(record, "In Stock", now)
    assert unverified["inventory_eligible"] is False
    assert unverified["shelf_life_window"] == facts["shelf_life_window"]
    record.classification = None
    assert inventory_facts(record, "In Stock", now)["shelf_life_window"] is None
    # Reading never writes back to the record.
    assert record.date_time == SCANNED


def test_response_schemas_accept_payloads_saved_before_the_window_existed():
    """Replayed receipts and frozen snapshot rows have no window key."""
    assert ScanResponse.model_fields["shelf_life_window"].default is None
    assert PublicScanResponse.model_fields["shelf_life_window"].default is None
    assert dashboard.DashboardScan.model_fields["shelf_life_window"].default is None


def freeze(monkeypatch, moment):
    monkeypatch.setattr(scan_records, "now_manila", lambda: moment)
    monkeypatch.setattr(scans_api, "now_manila", lambda: moment)


def stored_record(app):
    with Session(app.engine) as session:
        record = session.get(Scan, app.ids.scan)
        return (
            record.classification.spoilage_days, record.date_time, record.revision,
            record.updated_at,
        )


def test_reads_count_down_and_leave_the_database_unchanged(application, monkeypatch):  # noqa: F811
    app = application
    created = manila(2026, 11, 6, 23, 50)
    with Session(app.engine) as session:
        record = session.get(Scan, app.ids.scan)
        record.date_time = created
        record.classification.spoilage_days = "1-3"
        session.commit()
    before = stored_record(app)
    assert before[0] == "1-3" and before[1] == created
    detail_url = f"/api/v1/scans/{app.ids.scan}"
    expected = {
        manila(2026, 11, 6, 23, 59): (0, 1, 3, "active", 0),
        manila(2026, 11, 7, 0, 5): (1, 0, 2, "active", 0),
        manila(2026, 11, 8, 9, 0): (2, 0, 1, "active", 0),
        manila(2026, 11, 9, 9, 0): (3, 0, 0, "final_day", 0),
        manila(2026, 11, 13, 23, 50): (7, 0, 0, "expired", 4),
    }
    for moment, (elapsed, low, high, state, past) in expected.items():
        freeze(monkeypatch, moment)
        responses = {
            "detail": app.client.get(detail_url),
            "track": app.client.get(detail_url + "/track"),
            "list": app.client.get("/api/v1/scans"),
        }
        for name, response in responses.items():
            assert response.status_code == 200, (name, response.text)
            body = response.json()
            body = body["items"][0] if name == "list" else body
            assert body["spoilage_days"] == "1-3", name  # the stored estimate is still served
            assert body["shelf_life_window"] == {
                "min_days": 1, "max_days": 3, "elapsed_days": elapsed,
                "remaining_min_days": low, "remaining_max_days": high,
                "days_past": past, "state": state, "scan_date": "2026-11-06",
                "as_of_date": moment.date().isoformat(),
            }, (name, moment)
            assert body["risk_as_of"].startswith(moment.isoformat()[:19]), name
        # Reading at any age writes nothing.
        assert stored_record(app) == before
    assert app.state.events.count("response:200") == 3 * len(expected)


def test_bulk_status_event_carries_the_window(application, monkeypatch):  # noqa: F811
    app = application
    freeze(monkeypatch, manila(2025, 1, 4, 8, 0))  # the fixture scan is at 2025-01-02 00:30 Manila
    with Session(app.engine) as session:
        record = session.get(
            Scan, app.ids.scan,
            options=[selectinload(Scan.status_logs), selectinload(Scan.classification),
                     selectinload(Scan.intake)],
        )
        payload = scan_records.partial_scan_event_payload(record)
    assert payload["shelf_life_window"] == {
        "min_days": 3, "max_days": 3, "elapsed_days": 2, "remaining_min_days": 1,
        "remaining_max_days": 1, "days_past": 0, "state": "active", "scan_date": "2025-01-02",
        "as_of_date": "2025-01-04",
    }
    # The event is published as JSON without a schema, so the window must already be JSON-safe.
    assert json.loads(json.dumps(payload["shelf_life_window"])) == payload["shelf_life_window"]
    # Two days and 7.5 hours later the continuous number has its own, unchanged value.
    assert payload["remaining_days"] == pytest.approx(3 - (48 + 7.5) / 24)


@pytest.mark.asyncio
async def test_dashboard_and_log_rows_carry_the_window_without_changing_risk(logs_db):  # noqa: F811
    operator = account(logs_db)
    # NOW is noon on 2026-10-02 in Manila.
    late = scan(logs_db, operator, at=datetime(2026, 9, 30, 15, 50, tzinfo=UTC),
                prediction="1-3")  # 23:50 on 2026-09-30 in Manila: two calendar days ago
    decimal = scan(logs_db, operator, at=NOW - timedelta(days=7), prediction="4.861489519142744")
    sold = scan(logs_db, operator, at=NOW - timedelta(days=1), prediction="2",
                statuses=[(NOW, InventoryStatusEnum.SOLD)])
    unknown = scan(logs_db, operator, prediction="N/A")
    rows = {row.id: row for row in (await dashboard.list_scans(
        logs_db, operator, view="all", page_size=100)).items}
    assert rows[late].shelf_life_window.model_dump(mode="json") == {
        "min_days": 1, "max_days": 3, "elapsed_days": 2, "remaining_min_days": 0,
        "remaining_max_days": 1, "days_past": 0, "state": "active", "scan_date": "2026-09-30",
        "as_of_date": "2026-10-02",
    }
    # The risk number stays the continuous midpoint: 2 - 36h10m, still at risk.
    assert rows[late].remaining_days == pytest.approx(2 - (36 + 10 / 60) / 24, abs=1e-4)
    window = rows[decimal].shelf_life_window
    assert (window.min_days, window.max_days, window.elapsed_days) == (4, 5, 7)
    assert window.state == "expired" and window.days_past == 2
    assert rows[sold].shelf_life_window.state == "active"  # computed for every status
    assert rows[unknown].shelf_life_window is None and rows[unknown].remaining_days is None
    assert {row.id: row.spoilage_days for row in rows.values()} == {
        late: "1-3", decimal: "4.861489519142744", sold: "2", unknown: "N/A",
    }
    logs = {row.id: row for row in (await scan_logs.list_scan_logs(
        logs_db, operator, scan_logs.ScanLogQuery(page_size=100))).items}
    assert {identifier: row.shelf_life_window for identifier, row in logs.items()} == {
        identifier: row.shelf_life_window for identifier, row in rows.items()
    }
    summary = await dashboard.get_summary(logs_db, operator)
    # Risk rule unchanged: both in-stock scans are within two days by the midpoint number;
    # the sold scan and the unreadable estimate are not counted.
    assert summary.expiring_stock_count == 2


def test_frozen_snapshot_does_not_store_the_window_and_rebuilds_it_as_frozen(
    application, monkeypatch,  # noqa: F811
):
    """The derived window must not spend the snapshot size budget or drift after freezing."""
    from app.models.scan_snapshot import ScanSnapshot
    from app.services import scan_snapshots

    app = application
    created = manila(2026, 11, 6, 23, 50)
    with Session(app.engine) as session:
        record = session.get(Scan, app.ids.scan)
        record.date_time = created
        record.classification.spoilage_days = "1-3"
        session.commit()
    freeze(monkeypatch, manila(2026, 11, 7, 0, 5))
    first = app.client.get("/api/v1/scans", params={"stable": True})
    assert first.status_code == 200, first.text
    frozen_window = first.json()["items"][0]["shelf_life_window"]
    assert frozen_window["elapsed_days"] == 1 and frozen_window["as_of_date"] == "2026-11-07"
    with Session(app.engine) as session:
        stored = session.get(ScanSnapshot, UUID(first.json()["snapshot_id"])).payload
    assert all("shelf_life_window" not in row for row in stored["items"])
    assert stored["items"][0]["spoilage_days"] == "1-3"
    # The size limit is measured without the window: the same rows, frozen at the same
    # instant, fit exactly as they did before the window existed.
    limit = scan_snapshots.MAX_BYTES
    monkeypatch.setattr(scan_snapshots, "MAX_BYTES", len(json.dumps(stored).encode()))
    assert app.client.get("/api/v1/scans", params={"stable": True}).status_code == 200
    monkeypatch.setattr(scan_snapshots, "MAX_BYTES", len(json.dumps(stored).encode()) - 1)
    assert app.client.get("/api/v1/scans", params={"stable": True}).status_code == 413
    monkeypatch.setattr(scan_snapshots, "MAX_BYTES", limit)
    # Two days later the same snapshot reads exactly as it was frozen; the page rolls it on.
    freeze(monkeypatch, manila(2026, 11, 9, 9, 0))
    again = app.client.get(
        "/api/v1/scans", params={"stable": True, "snapshot_id": first.json()["snapshot_id"]}
    )
    assert again.status_code == 200 and again.json()["items"] == first.json()["items"]
    live = app.client.get("/api/v1/scans").json()["items"][0]
    assert live["shelf_life_window"]["elapsed_days"] == 3


def test_snapshot_rows_frozen_without_their_own_time_use_the_snapshot_time():
    """Scan Logs rows carry no risk_as_of; the snapshot's generated_at is their instant."""
    from app.services.scan_snapshots import slice_snapshot

    rows = [
        {"id": "a", "spoilage_days": "1-3", "date_time": "2026-11-06T23:50:00+08:00"},
        {"id": "b", "spoilage_days": "N/A", "date_time": "2026-11-06T23:50:00+08:00"},
        {"id": "c", "spoilage_days": "2", "date_time": "not a time"},
        {"id": "d", "spoilage_days": "2", "date_time": "2026-11-05T08:00:00+08:00",
         "risk_as_of": "2026-11-05T09:00:00+08:00", "shelf_life_window": {"stale": True}},
        {"id": "e"},
    ]
    saved = SimpleNamespace(id="token", expires_at=None, payload={
        "items": rows, "meta": {"generated_at": "2026-11-07T00:05:00+08:00"},
    })
    page = slice_snapshot(saved, 1, 10)
    windows = {row["id"]: row["shelf_life_window"] for row in page["items"]}
    assert windows["a"] == shelf_life_window(
        "1-3", manila(2026, 11, 6, 23, 50), manila(2026, 11, 7, 0, 5)
    )
    assert windows["a"]["elapsed_days"] == 1
    assert windows["b"] is None and windows["c"] is None and windows["e"] is None
    # A row's own instant wins, and a stored copy is never trusted.
    assert windows["d"]["as_of_date"] == "2026-11-05" and windows["d"]["elapsed_days"] == 0
    assert rows[0] == {"id": "a", "spoilage_days": "1-3", "date_time": "2026-11-06T23:50:00+08:00"}
    assert page["total"] == 5 and page["generated_at"] == "2026-11-07T00:05:00+08:00"
    undated = SimpleNamespace(id="t", expires_at=None, payload={"items": rows[:1]})
    assert slice_snapshot(undated, 1, 10)["items"][0]["shelf_life_window"] is None


def test_sold_records_still_receive_the_window_on_every_response(application, monkeypatch):  # noqa: F811
    """The public page counts down for every status, so the server must not gate the window."""
    from app.models.scan_status_log import ScanStatusLog

    app = application
    created = manila(2026, 11, 6, 23, 50)
    with Session(app.engine) as session:
        record = session.get(Scan, app.ids.scan)
        record.date_time = created
        record.classification.spoilage_days = "1-3"
        session.add(ScanStatusLog(
            scan_id=app.ids.scan, inventory_status=InventoryStatusEnum.SOLD,
            updated_at=manila(2026, 11, 7, 8, 0),
        ))
        session.commit()
    freeze(monkeypatch, manila(2026, 11, 8, 9, 0))
    url = f"/api/v1/scans/{app.ids.scan}"
    bodies = {
        "detail": app.client.get(url).json(),
        "track": app.client.get(url + "/track").json(),
        "list": app.client.get("/api/v1/scans").json()["items"][0],
    }
    for name, body in bodies.items():
        assert body["inventory_status"] == "Sold", name
        window = body["shelf_life_window"]
        assert (window["elapsed_days"], window["remaining_min_days"],
                window["remaining_max_days"], window["state"]) == (2, 0, 1, "active"), name
    assert bodies["detail"]["inventory_eligible"] is False
    with Session(app.engine) as session:
        record = session.get(
            Scan, app.ids.scan,
            options=[selectinload(Scan.status_logs), selectinload(Scan.classification),
                     selectinload(Scan.intake)],
        )
        payload = scan_records.partial_scan_event_payload(record)
    assert payload["inventory_status"] == InventoryStatusEnum.SOLD
    assert payload["shelf_life_window"] == bodies["detail"]["shelf_life_window"]
