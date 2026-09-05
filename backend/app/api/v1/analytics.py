"""
Analytics routes.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from sqlalchemy import select, func

from app.api.deps import DbSession, CurrentUser
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.schemas.common import (
    AnalyticsSummary,
    RipenessDistribution,
    CultivarCount,
    ScanTrend,
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
