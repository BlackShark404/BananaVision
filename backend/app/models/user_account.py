"""
UserAccount ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(
        "ua_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        "ua_username", String(50), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column("ua_full_name", String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(
        "ur_id", ForeignKey("user_role.ur_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        "ua_status",
        SAEnum("Active", "Inactive", name="user_status"),
        nullable=False,
        default="Active",
    )
    avatar_url: Mapped[str | None] = mapped_column("ua_avatar_url", Text, nullable=True)
    password_hash: Mapped[str] = mapped_column("ua_password_hash", String(255), nullable=False)
    requires_password_change: Mapped[bool] = mapped_column(
        "ua_requires_pwd_change", Boolean, default=False
    )
    password_setup_reason: Mapped[str | None] = mapped_column(
        "ua_pwd_setup_reason", String(50), nullable=True
    )
    last_active: Mapped[datetime | None] = mapped_column(
        "ua_last_active", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "ua_created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        "ua_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    role = relationship("UserRole", back_populates="accounts", lazy="selectin")
    admin_profile = relationship(
        "AdminProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    operator_profile = relationship(
        "OperatorProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    activity_logs = relationship("ActivityLog", back_populates="user", lazy="selectin")
