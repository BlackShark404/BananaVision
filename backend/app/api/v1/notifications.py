"""
Notification routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import desc, exists, insert, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundException
from app.core.time import now_manila
from app.models.app_notification import AppNotification
from app.models.app_notification_read import AppNotificationRead

router = APIRouter(prefix="/notifications", tags=["Notifications"])


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

    existing = await db.execute(
        select(AppNotificationRead.notification_id).where(
            AppNotificationRead.notification_id == notification_id,
            AppNotificationRead.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        await db.execute(
            insert(AppNotificationRead).values(
                notification_id=notification_id,
                user_id=user.id,
                read_at=now_manila(),
            )
        )
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_notifications_read(db: DbSession, user: CurrentUser):
    """Mark all visible notifications as read for the current user."""
    visible_ids = (
        await db.execute(select(AppNotification.id).where(_visible_to(user)))
    ).scalars().all()
    if not visible_ids:
        return {"message": "All notifications marked as read"}

    existing_ids = set(
        (
            await db.execute(
                select(AppNotificationRead.notification_id).where(
                    AppNotificationRead.user_id == user.id,
                    AppNotificationRead.notification_id.in_(visible_ids),
                )
            )
        ).scalars().all()
    )
    missing_ids = [
        notification_id
        for notification_id in visible_ids
        if notification_id not in existing_ids
    ]
    if missing_ids:
        read_at = now_manila()
        await db.execute(
            insert(AppNotificationRead).values([
                {
                    "notification_id": notification_id,
                    "user_id": user.id,
                    "read_at": read_at,
                }
                for notification_id in missing_ids
            ])
        )
    return {"message": "All notifications marked as read"}
