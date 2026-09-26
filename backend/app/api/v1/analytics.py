"""
Analytics routes.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from sqlalchemy import select, func, case, cast, Float
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
    ScanTrend,
    OperatorPerformance,
    OperatorPerformanceList,
)
from app.schemas.enums import RipenessEnum, CultivarEnum


router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(db: DbSession, user: CurrentUser):
    """Get aggregated analytics data for the dashboard."""
    # Total scans
    total_result = await db.execute(select(func.count()).select_from(Scan))
    total_scans = total_result.scalar() or 0

    # Average confidence
    avg_result = await db.execute(select(func.avg(ScanClassification.confidence)))
    avg_confidence = round(float(avg_result.scalar() or 0), 1)

    # Ripeness distribution
    ripeness_dist = []
    for ripeness in RipenessEnum:
        count_result = await db.execute(
            select(func.count()).where(ScanClassification.ripeness == ripeness)
        )
        ripeness_dist.append(RipenessDistribution(
            name=ripeness.value,
            value=count_result.scalar() or 0,
        ))

    # Cultivar counts
    cultivar_counts = []
    most_common = "N/A"
    max_count = 0
    for cultivar in CultivarEnum:
        count_result = await db.execute(
            select(func.count()).where(ScanClassification.cultivar == cultivar)
        )
        count = count_result.scalar() or 0
        cultivar_counts.append(CultivarCount(name=cultivar.value, count=count))
        if count > max_count:
            max_count = count
            most_common = cultivar.value

    # Scan trend (last 14 days)
    scan_trend: list[ScanTrend] = []
    today = datetime.now(timezone.utc).date()
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        count_result = await db.execute(
            select(func.count()).where(
                func.date(Scan.date_time) == day
            )
        )
        scan_trend.append(ScanTrend(
            date=day.strftime("%b %d"),
            count=count_result.scalar() or 0,
        ))

    return AnalyticsSummary(
        total_scans=total_scans,
        avg_confidence=avg_confidence,
        most_common_cultivar=most_common,
        ripeness_distribution=ripeness_dist,
        cultivar_counts=cultivar_counts,
        scan_trend=scan_trend,
    )


@router.get("/operator-performance", response_model=OperatorPerformanceList)
async def operator_performance(db: DbSession, user: CurrentUser):
    """Get per-operator performance metrics aggregated from scan data."""
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

