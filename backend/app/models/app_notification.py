"""
AppNotification ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AppNotification(Base):
    __tablename__ = "app_notification"

    id: Mapped[uuid.UUID] = mapped_column(
        "notif_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column("notif_type", String(30), nullable=False)
    title: Mapped[str] = mapped_column("notif_title", String(200), nullable=False)
    message: Mapped[str] = mapped_column("notif_message", Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        "notif_timestamp", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    is_read: Mapped[bool] = mapped_column("notif_is_read", Boolean, default=False)
    href: Mapped[str | None] = mapped_column("notif_href", String(200), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        "notif_user_id", UUID(as_uuid=True), ForeignKey("user_account.ua_id", ondelete="CASCADE"), nullable=True
    )

    user = relationship("UserAccount")
