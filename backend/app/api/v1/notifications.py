"""
Notification routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select, update, desc

from app.api.deps import DbSession, CurrentUser
from app.core.exceptions import NotFoundException
from app.models.app_notification import AppNotification


router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(db: DbSession, user: CurrentUser):
    """List notifications for the current user."""
    query = (
        select(AppNotification)
        .where(
            (AppNotification.user_id == user.id) | (AppNotification.user_id.is_(None))
        )
        .order_by(desc(AppNotification.timestamp))
        .limit(50)
    )
    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "items": [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "timestamp": n.timestamp.isoformat(),
                "read": n.is_read,
                "href": n.href,
            }
            for n in notifications
        ],
        "total": len(notifications),
    }


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID, db: DbSession, user: CurrentUser
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(AppNotification).where(AppNotification.id == notification_id)
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise NotFoundException("Notification")

    notif.is_read = True
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_notifications_read(db: DbSession, user: CurrentUser):
    """Mark all notifications as read for current user."""
    await db.execute(
        update(AppNotification)
        .where(
            (AppNotification.user_id == user.id) | (AppNotification.user_id.is_(None))
        )
        .values(is_read=True)
    )
    return {"message": "All notifications marked as read"}
