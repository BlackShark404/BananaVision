"""
Notification routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import desc, exists, literal, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundException
from app.core.time import now_manila
from app.models.app_notification import AppNotification
from app.models.app_notification_read import AppNotificationRead

router = APIRouter(prefix="/notifications", tags=["Notifications"])


async def _record_reads(db, user, notification_id=None):
    # Resolve duplicate deliveries in the database, including overlapping
    # single/read-all requests. SELECT-before-INSERT cannot ensure idempotence.
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    visible = select(
        AppNotification.id,
        literal(user.id, type_=AppNotificationRead.user_id.type),
        literal(now_manila(), type_=AppNotificationRead.read_at.type),
    ).where(_visible_to(user)).order_by(AppNotification.id)
    if notification_id is not None:
        visible = visible.where(AppNotification.id == notification_id)
    await db.execute(
        insert(AppNotificationRead).from_select(
            ["notification_id", "user_id", "read_at"], visible,
        ).on_conflict_do_nothing(
            index_elements=[AppNotificationRead.notification_id, AppNotificationRead.user_id],
        )
    )


def _visible_to(user: CurrentUser):
    return (
        (AppNotification.user_id == user.id)
        | (AppNotification.user_id.is_(None))
    )


@router.get("")
async def list_notifications(db: DbSession, user: CurrentUser):
    """List notifications for the current user with their read state."""
    read_receipt = exists(
        select(AppNotificationRead.notification_id).where(
            AppNotificationRead.notification_id == AppNotification.id,
            AppNotificationRead.user_id == user.id,
        )
    )
    query = (
        select(AppNotification, read_receipt.label("read"))
        .where(_visible_to(user))
        .order_by(desc(AppNotification.timestamp))
        .limit(50)
    )
    result = await db.execute(query)
    notifications = result.all()

    return {
        "items": [
            {
                "id": str(notification.id),
                "type": notification.type,
                "title": notification.title,
                "message": notification.message,
                "timestamp": notification.timestamp.isoformat(),
                "read": bool(is_read),
                "href": notification.href,
            }
            for notification, is_read in notifications
        ],
        "total": len(notifications),
    }


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID, db: DbSession, user: CurrentUser
):
    """Mark a notification visible to the current user as read."""
    visible = await db.execute(
        select(AppNotification.id).where(
            AppNotification.id == notification_id,
            _visible_to(user),
        )
    )
    if visible.scalar_one_or_none() is None:
        raise NotFoundException("Notification")

    await _record_reads(db, user, notification_id)
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_notifications_read(db: DbSession, user: CurrentUser):
    """Mark all visible notifications as read for the current user."""
    await _record_reads(db, user)
    return {"message": "All notifications marked as read"}
