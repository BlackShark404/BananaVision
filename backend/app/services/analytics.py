"""Authoritative, actor-scoped Analytics aggregates.

Throughput includes every scan in the selected Manila calendar-day cohort.
Classification charts require both known labels. Model confidence uses an
original saved prediction when available, never a human override's confidence.
Current risk is an as-of-now view of available stock in that same scan cohort.
The 14-day trend deliberately has its own fixed window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import and_, case, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import TIMEZONE_NAME, as_manila, business_day_bounds, now_manila
from app.models.operator_profile import OperatorProfile
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.user_account import UserAccount
from app.schemas.analytics import (
    AnalyticsSummary, CultivarCount, CultivarRipeness, HourlyCount,
    OperatorPerformance, OperatorPerformanceList, RipenessConfidence,
    RipenessDistribution, ScanTrend, SourceCount, SourceOption,
)
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum
from app.services.dashboard import (
    _expiring, _mean, _scoped_projection, _source, _source_filter, _threshold,
)
from app.services.inventory_policy import eligible_stock

DateRange = Literal["today", "week", "month", "all"]

METRIC_DEFINITIONS = {
    "throughput": (
        "All scans matching your filters and date range, including incomplete results. "
        "Date ranges include today up to the last update."
    ),
    "classifications": (
        "Scans with both a known cultivar and ripeness. "
        "Incomplete results are excluded from these charts."
    ),
    "model_confidence": (
        "Average AI confidence (0–100%), not measured accuracy. Uses original predictions; "
        "incomplete or invalid results and edited results without a saved prediction are excluded."
    ),
    "low_confidence": (
        "Percentage of valid AI predictions below the confidence threshold. "
        "Uses the same predictions as Avg Confidence."
    ),
    "inventory_risk": (
        "In-stock scans with 2 days or less left, including overdue stock. "
        "Remaining time is the estimate minus time since scanning (midpoint for ranges). "
        "Only active intakes or scans confirmed to have no intake count. "
        "Unknown estimates are excluded."
    ),
    "confidence_by_ripeness": (
        "Average AI confidence and number of valid predictions for each predicted ripeness. "
        "May differ from charts that include manual corrections."
    ),
    "trend": (
        "Daily scans for the last 14 days, including today. Uses source, cultivar and "
        "stock-status filters, but ignores the date-range filter."
    ),
    "sources": (
        "Scans grouped by supplier, or by the recorded source name when no supplier is linked."
    ),
    "operators": (
        "Scans and average AI confidence per operator. Renamed accounts keep their totals. "
        "Confidence describes the AI, not operator accuracy."
    ),
    "hourly": "Scans grouped by time of day in Asia/Manila.",
    "human_verified_accuracy": (
        "Unavailable: no independent verification results are recorded. "
        "Flags and manual edits do not measure accuracy."
    ),
}


def _range_start(range_key: DateRange, now: datetime) -> datetime | None:
    days = {"today": 1, "week": 7, "month": 30}.get(range_key)
    if days is None:
        return None
    return business_day_bounds(as_manila(now).date() - timedelta(days=days - 1))[0]


def _period(
    range_key: DateRange, now: datetime, date_from: date | None, date_to: date | None,
) -> tuple[datetime | None, datetime]:
    """First and last included instant of the selected period.

    Date From and Date To are inclusive Asia/Manila calendar days and replace the preset
    range. The end is never later than now, so the period text names the real last day.
    """
    if date_from is None and date_to is None:
        return _range_start(range_key, now), now
    today = as_manila(now).date()
    if any(day is not None and day > today for day in (date_from, date_to)):
        raise HTTPException(422, "Dates cannot be after today")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(422, "Date from must be on or before Date to")
    start = business_day_bounds(date_from)[0] if date_from is not None else None
    end = now
    if date_to is not None:
        end = min(now, business_day_bounds(date_to)[1] - timedelta(microseconds=1))
    return start, end


def _projection(user: UserAccount, now: datetime):
    scans = _scoped_projection(user, now)
    original = ScanOriginalAiResult

    def model_value(original_column, current_column):
        # A missing original result on an overridden scan is unknown, not a
        # reason to reinterpret the user's correction as model confidence.
        return case(
            (original.id.is_not(None), original_column),
            (scans.c.is_overridden.is_(False), current_column),
            else_=None,
        )

    return (
        select(
            scans,
            model_value(original.cultivar, scans.c.cultivar).label("model_cultivar"),
            model_value(original.ripeness, scans.c.ripeness).label("model_ripeness"),
            model_value(original.confidence, scans.c.confidence).label("model_confidence"),
        )
        .select_from(scans)
        .outerjoin(original, original.scan_id == scans.c.id)
        .subquery("analytics_scans")
    )


def _conditions(
    scans,
    range_key: DateRange,
    now: datetime,
    source_key,
    source,
    cultivar=None,
    inventory_status=None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    start, end = _period(range_key, now, date_from, date_to)
    conditions = [scans.c.date_time <= end]
    if start is not None:
        conditions.append(scans.c.date_time >= start)
    conditions.extend(_source_conditions(scans, source_key, source))
    conditions.extend(_classification_conditions(scans, cultivar, inventory_status))
    return conditions


def _classification_conditions(scans, cultivar, inventory_status):
    conditions = []
    if cultivar is not None:
        conditions.append(scans.c.cultivar == cultivar)
    if inventory_status is not None:
        conditions.append(scans.c.inventory_status == inventory_status)
    return conditions


def _source_conditions(scans, source_key, source):
    if source_key is not None:
        return [_source_filter(scans, source_key)]
    if source and source != "all":
        return [or_(
            scans.c.source_name == source,
            scans.c.original_source_text == source,
            scans.c.legacy_intake_source == source,
        )]
    return []


def _complete(cultivar, ripeness):
    return and_(cultivar.in_(list(CultivarEnum)), ripeness.in_(list(RipenessEnum)))


def _confidence(scans):
    return and_(
        _complete(scans.c.model_cultivar, scans.c.model_ripeness),
        scans.c.model_confidence >= 0,
        scans.c.model_confidence <= 100,
    )


def _current_stock(scans):
    return eligible_stock(scans)


def _label(value):
    return value.value if hasattr(value, "value") else value


async def _operators(db, scans, conditions) -> list[OperatorPerformance]:
    valid = _confidence(scans)
    rows = (await db.execute(
        select(
            scans.c.operator_id,
            UserAccount.full_name.label("operator_name"), UserAccount.username,
            func.count().label("total"),
            func.avg(scans.c.model_confidence).filter(valid).label("confidence"),
            func.count().filter(valid).label("confidence_count"),
            func.count().filter(scans.c.flagged.is_(True)).label("flagged"),
            func.count().filter(scans.c.is_overridden.is_(True)).label("overridden"),
        )
        # Historical name snapshots must not split one operator's activity.
        .select_from(scans)
        .join(OperatorProfile, OperatorProfile.id == scans.c.operator_id)
        .join(UserAccount, UserAccount.id == OperatorProfile.account_id)
        .where(*conditions)
        .group_by(scans.c.operator_id, UserAccount.full_name, UserAccount.username)
        .order_by(func.count().desc(), UserAccount.full_name, scans.c.operator_id)
    )).all()
    return [OperatorPerformance(
        operator_id=r.operator_id, name=r.operator_name, username=r.username,
        total_scans=r.total, avg_confidence=_mean(r.confidence),
        confidence_sample_count=r.confidence_count, flagged_scans=r.flagged,
        flag_rate=round(r.flagged / r.total * 100, 1), overridden_scans=r.overridden,
    ) for r in rows]


async def get_summary(
    db: AsyncSession, user: UserAccount, *, date_range: DateRange = "week",
    source_key: str | None = None, source: str | None = None,
    confidence_threshold: float | None = None,
    cultivar: CultivarEnum | None = None, inventory_status: InventoryStatusEnum | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> AnalyticsSummary:
    now = as_manila(now_manila())
    today = now.date()
    scans = _projection(user, now)
    conditions = _conditions(
        scans, date_range, now, source_key, source, cultivar, inventory_status,
        date_from, date_to,
    )
    threshold = await _threshold(db) if confidence_threshold is None else confidence_threshold
    complete = _complete(scans.c.cultivar, scans.c.ripeness)
    valid_confidence = _confidence(scans)
    stock = _current_stock(scans)
    totals = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(complete).label("classified"),
            func.count().filter(valid_confidence).label("confidence_count"),
            func.avg(scans.c.model_confidence).filter(valid_confidence).label("confidence"),
            func.count().filter(and_(valid_confidence, scans.c.model_confidence < threshold)).label("low"),
            func.count().filter(stock).label("stock"),
            func.count().filter(and_(stock, _expiring(scans))).label("risk"),
            func.count().filter(and_(stock, scans.c.remaining_days.is_(None))).label("unknown_risk"),
        ).select_from(scans).where(*conditions)
    )).one()

    classifications = (await db.execute(
        select(scans.c.cultivar, scans.c.ripeness, func.count().label("count"))
        .where(*conditions, complete)
        .group_by(scans.c.cultivar, scans.c.ripeness)
    )).all()
    matrix = {(_label(r.cultivar), _label(r.ripeness)): r.count for r in classifications}
    ripeness = [RipenessDistribution(
        name=r.value, value=sum(matrix.get((c.value, r.value), 0) for c in CultivarEnum),
    ) for r in RipenessEnum]
    cultivars = [CultivarCount(
        name=c.value, count=sum(matrix.get((c.value, r.value), 0) for r in RipenessEnum),
    ) for c in CultivarEnum]
    most_common = max(cultivars, key=lambda c: c.count)

    confidence_rows = (await db.execute(
        select(
            scans.c.model_ripeness,
            func.avg(scans.c.model_confidence).label("confidence"),
            func.count().label("count"),
        )
        .where(*conditions, valid_confidence)
        .group_by(scans.c.model_ripeness)
    )).all()
    confidence_by_ripeness = {_label(r.model_ripeness): r for r in confidence_rows}

    source_group = (
        select(scans.c.supplier_id, scans.c.source_text, scans.c.source_name, func.count().label("count"))
        .group_by(scans.c.supplier_id, scans.c.source_text, scans.c.source_name)
    )
    source_rows = (await db.execute(
        source_group.where(*conditions).order_by(func.count().desc(), scans.c.source_name, scans.c.supplier_id)
    )).all()
    # Filter choices are intentionally independent of the selected source and
    # range. Stable keys retain a selection after a supplier is renamed.
    option_rows = (await db.execute(
        source_group.order_by(scans.c.source_name, scans.c.supplier_id, scans.c.source_text)
    )).all()

    local_time = func.timezone(TIMEZONE_NAME, scans.c.date_time)
    local_day = func.date(local_time)
    trend_start = today - timedelta(days=13)
    trend_rows = (await db.execute(
        select(local_day.label("day"), func.count().label("count"))
        .where(
            scans.c.date_time >= business_day_bounds(trend_start)[0],
            scans.c.date_time <= now,
            *_source_conditions(scans, source_key, source),
            *_classification_conditions(scans, cultivar, inventory_status),
        )
        .group_by(local_day)
    )).all()
    trend_counts = {str(r.day): r.count for r in trend_rows}
    local_hour = extract("hour", local_time)
    hourly_rows = (await db.execute(
        select(local_hour.label("hour"), func.count().label("count"))
        .where(*conditions).group_by(local_hour).order_by(local_hour)
    )).all()

    range_start, range_end = _period(date_range, now, date_from, date_to)

    return AnalyticsSummary(
        generated_at=now, business_date=today, next_refresh_at=business_day_bounds(today)[1],
        range_start=range_start, range_end=range_end,
        trend_start=trend_start, trend_end=today, confidence_threshold=threshold,
        total_scans=totals.total, classification_count=totals.classified,
        incomplete_count=totals.total - totals.classified,
        confidence_sample_count=totals.confidence_count,
        avg_confidence=_mean(totals.confidence),
        most_common_cultivar=most_common.name if most_common.count else "N/A",
        low_confidence_count=totals.low,
        low_confidence_rate=(round(totals.low / totals.confidence_count * 100, 1) if totals.confidence_count else None),
        at_risk_count=totals.risk, current_stock_count=totals.stock, risk_unknown_count=totals.unknown_risk,
        metric_definitions=METRIC_DEFINITIONS,
        source_options=[SourceOption(key=_source(r)[0], name=r.source_name) for r in option_rows],
        ripeness_distribution=ripeness, cultivar_counts=cultivars,
        cultivar_ripeness=[CultivarRipeness(**{
            "name": c.value, **{r.value: matrix.get((c.value, r.value), 0) for r in RipenessEnum},
        }) for c in CultivarEnum],
        ripeness_confidence=[RipenessConfidence(
            ripeness=r.value,
            avgConfidence=_mean(confidence_by_ripeness[r.value].confidence) if r.value in confidence_by_ripeness else None,
            count=confidence_by_ripeness[r.value].count if r.value in confidence_by_ripeness else 0,
        ) for r in RipenessEnum],
        scans_by_source=[SourceCount(key=_source(r)[0], name=r.source_name, count=r.count) for r in source_rows],
        scan_trend=[ScanTrend(
            date=(trend_start + timedelta(days=i)).strftime("%b %d"),
            count=trend_counts.get((trend_start + timedelta(days=i)).isoformat(), 0),
        ) for i in range(14)],
        hourly_distribution=[HourlyCount(
            hour=f"{int(r.hour) % 12 or 12} {'AM' if int(r.hour) < 12 else 'PM'}", count=r.count,
        ) for r in hourly_rows],
        operator_performance=await _operators(db, scans, conditions),
    )


async def get_operator_performance(
    db: AsyncSession, user: UserAccount, *, date_range: DateRange = "week",
    source_key: str | None = None, source: str | None = None,
    cultivar: CultivarEnum | None = None, inventory_status: InventoryStatusEnum | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> OperatorPerformanceList:
    now = as_manila(now_manila())
    scans = _projection(user, now)
    items = await _operators(
        db,
        scans,
        _conditions(
            scans, date_range, now, source_key, source, cultivar, inventory_status,
            date_from, date_to,
        ),
    )
    return OperatorPerformanceList(items=items, total_operators=len(items))
