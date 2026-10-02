"""Dashboard reads have a separate contract and always enforce account scope."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardScanList, DashboardSort, DashboardSummary, DashboardView
from app.services.dashboard import get_summary, list_scans

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardSummary)
async def dashboard_summary(db: DbSession, user: CurrentUser):
    """Today's business metrics and all-time scoped recent scans/alert queues."""
    return await get_summary(db, user)


@router.get("/scans", response_model=DashboardScanList)
async def dashboard_scans(
    db: DbSession,
    user: CurrentUser,
    view: DashboardView = "today",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    business_date: date | None = None,
    source_key: str | None = None,
    operator_id: UUID | None = None,
    sort: DashboardSort = "date",
):
    """Filter within account scope; confidence sort is ascending, nulls last.

    business_date selects a Manila calendar day only for view=today. Review is
    flagged-or-low-confidence, as no independent review-resolution state exists.
    """
    return await list_scans(
        db, user, view=view, page=page, page_size=page_size, business_date=business_date,
        source_key=source_key, operator_id=operator_id, sort=sort,
    )
