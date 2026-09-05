"""
Activity log routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser
from app.models.activity_log import ActivityLog
from app.schemas.common import ActivityLogResponse, ActivityLogListResponse


router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=ActivityLogListResponse)
async def list_activity(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
):
    """List activity logs with pagination."""
    query = select(ActivityLog).options(selectinload(ActivityLog.user)).order_by(desc(ActivityLog.timestamp))

    if action:
        query = query.where(ActivityLog.action == action)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return ActivityLogListResponse(
        items=[
            ActivityLogResponse(
                id=log.id,
                user_name=log.user.full_name if log.user else None,
                action=log.action,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.timestamp,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
