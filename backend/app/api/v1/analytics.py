"""Analytics routes. Aggregates and metric definitions are shared by all clients."""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import AnalyticsSummary, OperatorPerformanceList
from app.schemas.enums import CultivarEnum, InventoryStatusEnum
from app.services.analytics import DateRange, get_operator_performance, get_summary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    db: DbSession,
    user: CurrentUser,
    date_range: DateRange = Query("week", alias="range"),
    source: str | None = Query(None),
    source_key: str | None = Query(None, max_length=200),
    confidence_threshold: float | None = Query(None, ge=0, le=100),
    cultivar: CultivarEnum | None = None,
    inventory_status: InventoryStatusEnum | None = None,
):
    return await get_summary(
        db, user, date_range=date_range, source_key=source_key, source=source,
        confidence_threshold=confidence_threshold,
        cultivar=cultivar, inventory_status=inventory_status,
    )


@router.get("/operator-performance", response_model=OperatorPerformanceList)
async def operator_performance(
    db: DbSession,
    user: CurrentUser,
    date_range: DateRange = Query("week", alias="range"),
    source: str | None = Query(None),
    source_key: str | None = Query(None, max_length=200),
    cultivar: CultivarEnum | None = None,
    inventory_status: InventoryStatusEnum | None = None,
):
    return await get_operator_performance(
        db, user, date_range=date_range, source_key=source_key, source=source,
        cultivar=cultivar, inventory_status=inventory_status,
    )
