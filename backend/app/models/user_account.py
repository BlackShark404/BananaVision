"""
UserAccount ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila
from app.schemas.enums import ActiveStatusEnum


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("user_role.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ActiveStatusEnum] = mapped_column(
        SAEnum(ActiveStatusEnum),
        nullable=False,
        default=ActiveStatusEnum.ACTIVE,
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    requires_password_change: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    password_setup_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    last_active: Mapped[datetime | None] = mapped_column(
        ManilaDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )
    token_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False,
        doc="Incremented on logout/credential change to revoke prior JWTs.",
    )

    # Relationships
    role = relationship("UserRole", back_populates="accounts", lazy="selectin")
    admin_profile = relationship(
        "AdminProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    operator_profile = relationship(
        "OperatorProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    activity_logs = relationship("ActivityLog", back_populates="user", lazy="raise")
