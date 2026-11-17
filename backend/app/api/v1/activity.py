"""
Activity log routes.

AUDIT-01: True server-side pagination, filtering by action/user/search query.
Paging is pinned to an ``as_of`` boundary so rows written while an administrator pages
through the log cannot shift later pages.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.core.time import now_manila
from app.models.activity_log import ActivityLog
from app.schemas.common import ActivityLogListResponse, ActivityLogResponse
from app.schemas.timestamps import InputTimestamp

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=ActivityLogListResponse)
async def list_activity(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user_name: str | None = None,
    search: str | None = None,
    as_of: InputTimestamp | None = None,
):
    """List activity logs with server-side pagination, filtering, and search.

    Count and page only include rows at or before ``as_of``; the response returns the
    boundary used so later pages can pass it back. Without ``as_of`` the boundary is the
    later of now and the newest row, so rows stamped ahead of this clock (a restored backup
    from a station whose clock ran ahead, or a clock stepped back) are never hidden.
    """
    boundary = as_of
    if boundary is None:
        boundary = now_manila()
        newest = await db.scalar(select(func.max(ActivityLog.timestamp)))
        if newest is not None and newest > boundary:
            boundary = newest
    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.user))
        .where(ActivityLog.timestamp <= boundary)
        .order_by(desc(ActivityLog.timestamp), desc(ActivityLog.id))
    )

    # Filter by action type
    if action:
        query = query.where(ActivityLog.action == action)

    # Filter by user name (join with user table)
    if user_name:
        from app.models.user_account import UserAccount
        query = query.join(ActivityLog.user).where(UserAccount.full_name == user_name)

    # Full-text search across user name, action, and details
    if search:
        from app.models.user_account import UserAccount
        search_pattern = f"%{search}%"
        # Need left outer join since user might be null
        query = query.outerjoin(ActivityLog.user).where(
            or_(
                ActivityLog.action.ilike(search_pattern),
                ActivityLog.details.ilike(search_pattern),
                UserAccount.full_name.ilike(search_pattern),
            )
        )

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
        as_of=boundary,
    )
