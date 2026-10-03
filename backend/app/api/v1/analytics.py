"""
Analytics routes.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from app.core.time import TIMEZONE_NAME, business_day_bounds, now_manila

from fastapi import APIRouter, Query
from sqlalchemy import select, func, case, extract, and_
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.operator_profile import OperatorProfile
from app.models.user_account import UserAccount
from app.schemas.common import (
    AnalyticsSummary,
    RipenessDistribution,
    CultivarCount,
    CultivarRipeness,
    RipenessConfidence,
    SourceCount,
    HourlyCount,
    ScanTrend,
    OperatorPerformance,
    OperatorPerformanceList,
)
from app.schemas.enums import RipenessEnum, CultivarEnum


router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _date_filter(range_key: str) -> datetime | None:
    """Return the start datetime for the given range key, or None for 'all'."""
    now = now_manila()
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_key == "week":
        return now - timedelta(days=7)
    elif range_key == "month":
        return now - timedelta(days=30)
    return None  # 'all'


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    db: DbSession,
    user: CurrentUser,
    date_range: str = Query("week", alias="range", regex="^(today|week|month|all)$"),
    source: str = Query("all"),
    confidence_threshold: float = Query(85.0, ge=0, le=100),
):
    """Get aggregated analytics data for the dashboard.

    Supports filtering by date range, source, and confidence threshold.
    All computations run as SQL aggregates against PostgreSQL.
    """

    # ── Build base filter conditions ────────────────────────────────────────
    conditions = []

    start_dt = _date_filter(date_range)
    if start_dt:
        conditions.append(Scan.date_time >= start_dt)

    if source != "all":
        conditions.append(Scan.source_text == source)

    # Helper: base join condition (Scan ↔ ScanClassification)
    base_join = ScanClassification.scan_id == Scan.id

    # ── 1. Total scans ──────────────────────────────────────────────────────
    q = select(func.count()).select_from(Scan)
    if conditions:
        q = q.where(and_(*conditions))
    total_scans = (await db.execute(q)).scalar() or 0

    # ── 2. Average confidence ───────────────────────────────────────────────
    q = select(func.avg(ScanClassification.confidence)).join(Scan, base_join)
    if conditions:
        q = q.where(and_(*conditions))
    avg_confidence = round(float((await db.execute(q)).scalar() or 0), 1)

    # ── 3. Ripeness distribution ────────────────────────────────────────────
    ripeness_dist = []
    for ripeness in RipenessEnum:
        q = (
            select(func.count())
            .select_from(ScanClassification)
            .join(Scan, base_join)
            .where(ScanClassification.ripeness == ripeness)
        )
        if conditions:
            q = q.where(and_(*conditions))
        count = (await db.execute(q)).scalar() or 0
        ripeness_dist.append(RipenessDistribution(name=ripeness.value, value=count))

    # ── 4. Cultivar counts ──────────────────────────────────────────────────
    cultivar_counts = []
    most_common = "N/A"
    max_count = 0
    for cultivar in CultivarEnum:
        q = (
            select(func.count())
            .select_from(ScanClassification)
            .join(Scan, base_join)
            .where(ScanClassification.cultivar == cultivar)
        )
        if conditions:
            q = q.where(and_(*conditions))
        count = (await db.execute(q)).scalar() or 0
        cultivar_counts.append(CultivarCount(name=cultivar.value, count=count))
        if count > max_count:
            max_count = count
            most_common = cultivar.value

    # ── 5. Scan trend (last 14 days) ────────────────────────────────────────
    scan_trend: list[ScanTrend] = []
    today = now_manila().date()
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        start, end = business_day_bounds(day)
        q = select(func.count()).select_from(Scan).where(Scan.date_time >= start, Scan.date_time < end)
        if source != "all":
            q = q.where(Scan.source_text == source)
        count = (await db.execute(q)).scalar() or 0
        scan_trend.append(ScanTrend(date=day.strftime("%b %d"), count=count))

    # ── 6. Low-confidence count ─────────────────────────────────────────────
    q = (
        select(func.count())
        .select_from(ScanClassification)
        .join(Scan, base_join)
        .where(ScanClassification.confidence < confidence_threshold)
    )
    if conditions:
        q = q.where(and_(*conditions))
    low_confidence_count = (await db.execute(q)).scalar() or 0
    low_confidence_rate = round((low_confidence_count / total_scans * 100), 1) if total_scans > 0 else 0.0

    # ── 7. At-risk scans (spoilage ≤ 2 days) ────────────────────────────────
    # spoilage_days is stored as text like "2-3" or "1". Parse: treat "X-Y" → avg.
    # Since this is text, we do a client-side post-filter on the query result.
    q = select(ScanClassification.spoilage_days).join(Scan, base_join)
    if conditions:
        q = q.where(and_(*conditions))
    spoilage_rows = (await db.execute(q)).scalars().all()
    at_risk_count = 0
    for sd in spoilage_rows:
        if not sd:
            continue
        try:
            if "-" in sd:
                parts = sd.split("-")
                avg_val = (float(parts[0]) + float(parts[1])) / 2
            else:
                avg_val = float(sd)
            if avg_val <= 2:
                at_risk_count += 1
        except (ValueError, IndexError):
            pass

    # ── 8. Cultivar × Ripeness breakdown ────────────────────────────────────
    cultivar_ripeness = []
    for cultivar in CultivarEnum:
        row: dict[str, int | str] = {"name": cultivar.value}
        for ripeness in RipenessEnum:
            q = (
                select(func.count())
                .select_from(ScanClassification)
                .join(Scan, base_join)
                .where(
                    ScanClassification.cultivar == cultivar,
                    ScanClassification.ripeness == ripeness,
                )
            )
            if conditions:
                q = q.where(and_(*conditions))
            row[ripeness.value] = (await db.execute(q)).scalar() or 0
        cultivar_ripeness.append(CultivarRipeness(**row))

    # ── 9. Confidence by Ripeness ───────────────────────────────────────────
    ripeness_confidence = []
    for ripeness in RipenessEnum:
        q = (
            select(
                func.avg(ScanClassification.confidence).label("avg_conf"),
                func.count().label("cnt"),
            )
            .select_from(ScanClassification)
            .join(Scan, base_join)
            .where(ScanClassification.ripeness == ripeness)
        )
        if conditions:
            q = q.where(and_(*conditions))
        row = (await db.execute(q)).one()
        ripeness_confidence.append(
            RipenessConfidence(
                ripeness=ripeness.value,
                avgConfidence=round(float(row.avg_conf or 0), 1),
                count=row.cnt or 0,
            )
        )

    # ── 10. Scans by Source ─────────────────────────────────────────────────
    src_col = func.coalesce(Scan.source_text, "Unknown")
    q = (
        select(
            src_col.label("src"),
            func.count().label("cnt"),
        )
        .select_from(Scan)
        .group_by(src_col)
        .order_by(func.count().desc())
    )
    if conditions:
        q = q.where(and_(*conditions))
    source_rows = (await db.execute(q)).all()
    scans_by_source = [SourceCount(name=r.src, count=r.cnt) for r in source_rows]

    # ── 11. Hourly distribution ─────────────────────────────────────────────
    local_hour = extract("hour", func.timezone(TIMEZONE_NAME, Scan.date_time))
    q = (
        select(
            local_hour.label("hr"),
            func.count().label("cnt"),
        )
        .select_from(Scan)
        .group_by(local_hour)
        .order_by(local_hour)
    )
    if conditions:
        q = q.where(and_(*conditions))
    hour_rows = (await db.execute(q)).all()
    hourly_distribution = []
    for r in hour_rows:
        hr = int(r.hr)
        period = "AM" if hr < 12 else "PM"
        display = 12 if hr == 0 else (hr - 12 if hr > 12 else hr)
        hourly_distribution.append(HourlyCount(hour=f"{display} {period}", count=r.cnt))

    return AnalyticsSummary(
        total_scans=total_scans,
        avg_confidence=avg_confidence,
        most_common_cultivar=most_common,
        low_confidence_count=low_confidence_count,
        low_confidence_rate=low_confidence_rate,
        at_risk_count=at_risk_count,
        ripeness_distribution=ripeness_dist,
        cultivar_counts=cultivar_counts,
        scan_trend=scan_trend,
        cultivar_ripeness=cultivar_ripeness,
        ripeness_confidence=ripeness_confidence,
        scans_by_source=scans_by_source,
        hourly_distribution=hourly_distribution,
    )


@router.get("/operator-performance", response_model=OperatorPerformanceList)
async def operator_performance(
    db: DbSession,
    user: CurrentUser,
    date_range: str = Query("week", alias="range", regex="^(today|week|month|all)$"),
    source: str = Query("all"),
):
    """Get per-operator performance metrics aggregated from scan data."""
    conditions = []
    start_dt = _date_filter(date_range)
    if start_dt:
        conditions.append(Scan.date_time >= start_dt)
    if source != "all":
        conditions.append(Scan.source_text == source)

    query = (
        select(
            OperatorProfile.id.label("operator_id"),
            UserAccount.full_name.label("name"),
            func.count(Scan.id).label("total_scans"),
            func.coalesce(func.avg(ScanClassification.confidence), 0).label("avg_confidence"),
            func.sum(case((Scan.flagged == True, 1), else_=0)).label("flagged_scans"),  # noqa: E712
            func.sum(case((Scan.is_overridden == True, 1), else_=0)).label("overridden_scans"),  # noqa: E712
        )
        .join(Scan, Scan.operator_id == OperatorProfile.id)
        .join(UserAccount, UserAccount.id == OperatorProfile.account_id)
        .outerjoin(ScanClassification, ScanClassification.scan_id == Scan.id)
        .group_by(OperatorProfile.id, UserAccount.full_name)
        .order_by(func.count(Scan.id).desc())
    )
    if conditions:
        query = query.where(and_(*conditions))

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        total = row.total_scans or 0
        flagged = int(row.flagged_scans or 0)
        flag_rate = round((flagged / total * 100), 1) if total > 0 else 0.0
        items.append(OperatorPerformance(
            operator_id=row.operator_id,
            name=row.name,
            total_scans=total,
            avg_confidence=round(float(row.avg_confidence), 1),
            flagged_scans=flagged,
            flag_rate=flag_rate,
            overridden_scans=int(row.overridden_scans or 0),
        ))

    return OperatorPerformanceList(
        items=items,
        total_operators=len(items),
    )
