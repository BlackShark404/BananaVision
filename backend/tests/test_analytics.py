"""Analytics populations, business boundaries and stable filters on real SQL.

Uses the Dashboard database fixture with a local equivalent of PostgreSQL's
timezone function. Production SQL is also compiled against PostgreSQL.
"""

from datetime import UTC, date, datetime, timedelta
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
from app.models.scan_history import ScanEvent
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
    ScanEvent.__table__.create(db.session.get_bind())

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
    assert result.verified_correct_count == 0 and result.overridden_classification_count == 0
    assert result.override_rate is None
    assert result.current_stock_count == result.at_risk_count == result.risk_unknown_count == 0
    assert result.source_options == result.operator_performance == result.hourly_distribution == []
    assert len(result.scan_trend) == 14 and sum(row.count for row in result.scan_trend) == 0
    assert all(
        row.avgConfidence is None and row.count == 0
        and row.verifiedAccuracy is None and row.verifiedCount == 0
        for row in result.ripeness_confidence
    )
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
    scan(db, user, at=datetime(2026, 10, 1, 23, 30, tzinfo=UTC))
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

    # Custom date_from and date_to filters override preset ranges.
    from_week_start = await analytics.get_summary(db, user, date_from=date(2026, 9, 26))
    assert from_week_start.total_scans == 2
    assert from_week_start.range_start == business_day_bounds(date(2026, 9, 26))[0]

    bounded_range = await analytics.get_summary(
        db, user, date_from=date(2026, 9, 20), date_to=date(2026, 9, 25),
    )
    assert bounded_range.total_scans == 1  # only the scan at week_start - 1us (2026-09-25)
    assert bounded_range.range_start == business_day_bounds(date(2026, 9, 20))[0]
    # Period end is the last instant of Date To (inclusive day), so "Period: … – Sep 25"
    # shows Sep 25, not the exclusive midnight after it.
    last_instant = business_day_bounds(date(2026, 9, 25))[1] - timedelta(microseconds=1)
    assert bounded_range.range_end == last_instant
    up_to_today = await analytics.get_summary(db, user, date_to=NOW.date())
    assert up_to_today.range_start is None and up_to_today.range_end == NOW
    assert up_to_today.total_scans == 5


@pytest.mark.asyncio
async def test_confidence_excludes_missing_invalid_and_unrecoverable_overrides(analytics_db):
    db = analytics_db
    user = account(db)
    db.add(SystemConfig, confidence_threshold=75, data_retention_enabled=False)
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
    assert (unripe.verifiedCount, unripe.verifiedAccuracy) == (1, 0.0)
    assert (ripe.count, ripe.avgConfidence) == (2, 37.5)
    assert (ripe.verifiedCount, ripe.verifiedAccuracy) == (0, None)
    assert result.verified_scan_count == 1 and result.verified_correct_count == 0
    assert result.overridden_classification_count == 1 and result.override_rate == 100.0
    assert result.human_verified_accuracy == 0.0
    operator = result.operator_performance[0]
    assert operator.confidence_sample_count == 3 and operator.avg_confidence == result.avg_confidence
    assert operator.overridden_scans == 2


@pytest.mark.asyncio
async def test_verified_accuracy_distinguishes_confirmed_overrides_non_classification_edits_and_unreviewed(analytics_db):
    db = analytics_db
    admin = account(db, role="Admin")
    op = account(db)

    # Unreviewed scans: one normal, one still flagged awaiting review -> neither is verified.
    scan(db, op, confidence=95)
    scan(db, op, confidence=70, flagged=True)
    # Automated legacy flag cleanup must not count as human verification.
    cleaned = scan(db, op, confidence=88, flagged=False)
    db.add(
        ScanEvent, scan_id=cleaned, revision=2, kind="flag", timestamp=NOW,
        actor_id=admin.id, actor_name="Admin",
        reason="Auto-flag rule corrected: only a confidence below the threshold flags a scan (88% is not below 80%)",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )
    # Previously cleared, then re-flagged for review -> pending review, not currently verified.
    reflagged = scan(db, op, confidence=78, flagged=True)
    db.add(
        ScanEvent, scan_id=reflagged, revision=2, kind="flag", timestamp=NOW,
        actor_id=admin.id, actor_name="Admin",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )
    # 1. Admin QC flag approval (AI Lakatan/Ripe confirmed correct).
    approved = scan(db, op, confidence=76, flagged=False)
    db.add(
        ScanEvent, scan_id=approved, revision=2, kind="flag", timestamp=NOW,
        actor_id=admin.id, actor_name="Admin", reason="Looks ripe on inspection",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )
    # 2. Finger-count-only edit (cultivar & ripeness unchanged -> accurate, not penalized).
    finger_edit = scan(db, op, confidence=92)
    db.session.execute(update(Scan).where(Scan.id == finger_edit).values(is_overridden=True))
    db.session.execute(
        update(ScanClassification).where(ScanClassification.scan_id == finger_edit).values(finger_count=14)
    )
    db.add(
        ScanOriginalAiResult, scan_id=finger_edit, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.RIPE, confidence=84, finger_count=12,
    )
    # 3. Spoilage-only edit on Unripe (cultivar & ripeness unchanged -> accurate).
    spoilage_edit = scan(db, op, confidence=99)
    db.session.execute(update(Scan).where(Scan.id == spoilage_edit).values(is_overridden=True))
    db.session.execute(
        update(ScanClassification)
        .where(ScanClassification.scan_id == spoilage_edit)
        .values(cultivar=CultivarEnum.CARDABA, ripeness=RipenessEnum.UNRIPE, spoilage_days="7-8")
    )
    db.add(
        ScanOriginalAiResult, scan_id=spoilage_edit, cultivar=CultivarEnum.CARDABA,
        ripeness=RipenessEnum.UNRIPE, confidence=86, finger_count=6, spoilage_days="5-6",
    )
    # 4. Cultivar override (original Lakatan/Ripe -> final Cardaba/Ripe -> inaccurate).
    cultivar_override = scan(db, op, confidence=100)
    db.session.execute(update(Scan).where(Scan.id == cultivar_override).values(is_overridden=True))
    db.session.execute(
        update(ScanClassification)
        .where(ScanClassification.scan_id == cultivar_override)
        .values(cultivar=CultivarEnum.CARDABA, ripeness=RipenessEnum.RIPE)
    )
    db.add(
        ScanOriginalAiResult, scan_id=cultivar_override, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.RIPE, confidence=82, finger_count=6,
    )
    # 5. Ripeness override (original Lakatan/Semi Ripe -> final Lakatan/Ripe -> inaccurate).
    ripeness_override = scan(db, op, confidence=100)
    db.session.execute(update(Scan).where(Scan.id == ripeness_override).values(is_overridden=True))
    db.add(
        ScanOriginalAiResult, scan_id=ripeness_override, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.SEMI_RIPE, confidence=74, finger_count=6,
    )
    # Unrecoverable override (no ScanOriginalAiResult) -> excluded from verified & confidence.
    unrecoverable = scan(db, op, confidence=100)
    db.session.execute(update(Scan).where(Scan.id == unrecoverable).values(is_overridden=True))

    summary = await analytics.get_summary(db, admin)
    assert summary.verified_scan_count == 5
    assert summary.verified_correct_count == 3
    assert summary.overridden_classification_count == 2
    assert summary.human_verified_accuracy == 60.0
    assert summary.override_rate == 40.0
    # Confidence uses original AI predictions (95, 70, 88, 78, 76, 84, 86, 82, 74) = 733 / 9 = 81.4
    assert summary.confidence_sample_count == 9
    assert summary.avg_confidence == 81.4

    by_stage = {row.ripeness: row for row in summary.ripeness_confidence}
    assert (by_stage["Unripe"].verifiedCount, by_stage["Unripe"].verifiedAccuracy) == (1, 100.0)
    assert (by_stage["Semi Ripe"].verifiedCount, by_stage["Semi Ripe"].verifiedAccuracy) == (1, 0.0)
    assert (by_stage["Ripe"].verifiedCount, by_stage["Ripe"].verifiedAccuracy) == (3, 66.7)
    assert (by_stage["Overripe"].verifiedCount, by_stage["Overripe"].verifiedAccuracy) == (0, None)


@pytest.mark.asyncio
async def test_verified_accuracy_respects_role_scope_and_manila_custom_date_filters(analytics_db):
    db = analytics_db
    admin = account(db, role="Admin")
    op_a, op_b = account(db), account(db)
    day_prev = business_day_bounds(date(2026, 10, 1))[0] + timedelta(hours=10)

    # Op A on Oct 1: overridden ripeness (inaccurate).
    a_prev = scan(db, op_a, at=day_prev, confidence=100, source="Farm A")
    db.session.execute(update(Scan).where(Scan.id == a_prev).values(is_overridden=True))
    db.add(
        ScanOriginalAiResult, scan_id=a_prev, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.UNRIPE, confidence=75, finger_count=6,
    )
    # Op A on Oct 2: QC flag cleared (accurate).
    a_today = scan(db, op_a, at=NOW, confidence=79, source="Farm A")
    db.add(
        ScanEvent, scan_id=a_today, revision=2, kind="flag", timestamp=NOW,
        actor_id=admin.id, actor_name="Admin",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )
    # Op B on Oct 2: QC flag cleared (accurate).
    b_today = scan(db, op_b, at=NOW, confidence=77, source="Farm B")
    db.add(
        ScanEvent, scan_id=b_today, revision=2, kind="flag", timestamp=NOW,
        actor_id=admin.id, actor_name="Admin",
        previous_values={"flagged": True}, new_values={"flagged": False},
    )

    admin_week = await analytics.get_summary(db, admin, date_range="week")
    assert (admin_week.verified_scan_count, admin_week.verified_correct_count, admin_week.human_verified_accuracy) == (3, 2, 66.7)

    admin_today = await analytics.get_summary(
        db, admin, date_from=date(2026, 10, 2), date_to=date(2026, 10, 2),
    )
    assert (admin_today.verified_scan_count, admin_today.verified_correct_count, admin_today.human_verified_accuracy) == (2, 2, 100.0)

    op_a_week = await analytics.get_summary(db, op_a, date_range="week")
    assert (op_a_week.verified_scan_count, op_a_week.verified_correct_count, op_a_week.human_verified_accuracy) == (2, 1, 50.0)

    op_a_oct1 = await analytics.get_summary(
        db, op_a, date_from=date(2026, 10, 1), date_to=date(2026, 10, 1),
    )
    assert (op_a_oct1.verified_scan_count, op_a_oct1.verified_correct_count, op_a_oct1.human_verified_accuracy) == (1, 0, 0.0)

    op_b_oct1 = await analytics.get_summary(
        db, op_b, date_from=date(2026, 10, 1), date_to=date(2026, 10, 1),
    )
    assert (op_b_oct1.verified_scan_count, op_b_oct1.human_verified_accuracy) == (0, None)


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


@pytest.mark.asyncio
async def test_operator_snapshot_names_do_not_split_totals_or_confidence(analytics_db):
    database = analytics_db
    admin = account(database, role="Admin")
    owner = account(database, name="Current Name")
    namesake = account(database, name="Current Name")
    for snapshot, confidence in [("Old Name", 0), ("New Name", 60), (None, 90), ("Old Name", None)]:
        scan_id = scan(database, owner, confidence=confidence)
        database.session.execute(
            update(Scan).where(Scan.id == scan_id).values(operator_name_snapshot=snapshot)
        )
    scan(database, namesake, confidence=100)

    summary = await analytics.get_summary(database, admin)
    operators = await analytics.get_operator_performance(database, admin)
    assert operators.items == summary.operator_performance
    assert operators.total_operators == 2
    rows = {row.operator_id: row for row in operators.items}
    own = rows[owner.operator_id]
    assert own.name == "Current Name"
    assert (own.total_scans, own.confidence_sample_count, own.avg_confidence) == (4, 3, 50)
    assert rows[namesake.operator_id].total_scans == 1
    scoped = await analytics.get_operator_performance(database, owner)
    assert scoped.items == [own]
    # Aggregating under the current name must not rewrite historical scan records.
    snapshots = database.session.scalars(
        select(Scan.operator_name_snapshot).where(Scan.operator_id == owner.operator_id)
    ).all()
    assert snapshots.count("Old Name") == 2 and "New Name" in snapshots and None in snapshots


@pytest.mark.asyncio
@pytest.mark.parametrize("date_range,days", [
    ("today", 1), ("week", 7), ("month", 30), ("all", None),
])
async def test_operator_metrics_share_calendar_filters_and_original_confidence(
    analytics_db, date_range, days,
):
    database = analytics_db
    admin = account(database, role="Admin")
    owner, other = account(database), account(database)
    start = business_day_bounds(as_manila(NOW).date() - timedelta(days=(days or 90) - 1))[0]
    for at, confidence in [(start - timedelta(microseconds=1), 30), (start, 0), (NOW, 90)]:
        scan(database, owner, at=at, confidence=confidence)
    saved = scan(database, owner, confidence=100)
    database.session.execute(
        update(Scan).where(Scan.id == saved).values(is_overridden=True, flagged=True)
    )
    database.add(
        ScanOriginalAiResult, scan_id=saved, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.RIPE, confidence=60, finger_count=5,
    )
    # Exclude future, other-source, other-cultivar and other-status records.
    scan(database, owner, at=NOW + timedelta(microseconds=1), confidence=100)
    scan(database, owner, source="Farm B", confidence=100)
    different = scan(database, owner, confidence=100)
    database.session.execute(
        update(ScanClassification)
        .where(ScanClassification.scan_id == different).values(cultivar="Cardaba")
    )
    scan(database, owner, confidence=100, statuses=[(NOW, InventoryStatusEnum.SOLD)])
    scan(database, other, confidence=80)
    options = dict(date_range=date_range, source_key="text:Farm A",
                   cultivar=CultivarEnum.LAKATAN, inventory_status=InventoryStatusEnum.IN_STOCK)

    summary = await analytics.get_summary(database, admin, **options)
    operators = await analytics.get_operator_performance(database, admin, **options)
    assert operators.items == summary.operator_performance
    assert operators.total_operators == 2
    own = next(row for row in operators.items if row.operator_id == owner.operator_id)
    expected_count, expected_confidence = (3, 50) if days else (4, 45)
    assert (own.total_scans, own.confidence_sample_count) == (expected_count, expected_count)
    assert own.avg_confidence == expected_confidence
    assert sum(row.total_scans for row in operators.items) == summary.total_scans
    scoped = await analytics.get_operator_performance(database, owner, **options)
    assert scoped.items == [own]
    empty = await analytics.get_operator_performance(database, owner, source_key="text:Absent")
    assert empty.items == [] and empty.total_operators == 0


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
        for params in ({"range": "year"}, {"confidence_threshold": -1},
                       {"confidence_threshold": 101}, {"date_from": "invalid"}):
            assert client.get("/api/v1/analytics/summary", params=params).status_code == 422
        custom_result = client.get("/api/v1/analytics/summary",
                                   params={"date_from": "2026-10-01", "date_to": "2026-10-02"})
        assert custom_result.status_code == 200
        assert custom_result.json()["range_start"] == "2026-10-01T00:00:00+08:00"
        operator_result = client.get("/api/v1/analytics/operator-performance", params={"range": "today"})
        assert operator_result.json()["items"] == data["operator_performance"]

        # Date From after Date To, or a day after today (Asia/Manila), is refused on both routes.
        for route in ("summary", "operator-performance"):
            reversed_dates = client.get(f"/api/v1/analytics/{route}",
                                        params={"date_from": "2026-10-02", "date_to": "2026-10-01"})
            assert reversed_dates.status_code == 422
            assert reversed_dates.json()["detail"] == "Date from must be on or before Date to"
            for params in ({"date_from": "2026-10-03"}, {"date_to": "2026-10-03"}):
                future = client.get(f"/api/v1/analytics/{route}", params=params)
                assert future.status_code == 422
                assert future.json()["detail"] == "Dates cannot be after today"
        same_day = client.get("/api/v1/analytics/summary",
                              params={"date_from": "2026-10-02", "date_to": "2026-10-02"})
        assert same_day.status_code == 200 and same_day.json()["total_scans"] == 1


def test_postgres_queries_keep_stable_scope_elapsed_risk_and_original_model(analytics_db):
    user = account(analytics_db)
    projection = analytics._projection(user, NOW)
    sql = str(select(projection).compile(dialect=postgresql.dialect()))
    assert "operator_profile.account_id" in sql
    assert "scan_original_ai_result" in sql and "model_confidence" in sql
    assert "scan_event" in sql and "has_flag_clearance" in sql
    assert "EXTRACT(epoch" in sql and "split_part" in sql
    assert "scan_status_log.updated_at DESC, scan_status_log.id DESC" in sql
