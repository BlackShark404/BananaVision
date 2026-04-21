"""
User ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Enum as SAEnum, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        SAEnum("Admin", "Operator", name="user_role"), nullable=False, default="Operator"
    )
    status: Mapped[str] = mapped_column(
        SAEnum("Active", "Inactive", name="user_status"), nullable=False, default="Active"
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    password_setup_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    requires_pin_change: Mapped[bool] = mapped_column(Boolean, default=False)
    pin_setup_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_active: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    scans = relationship("Scan", back_populates="operator", lazy="selectin")
    activity_logs = relationship("ActivityLog", back_populates="user", lazy="selectin")
    scan_notes = relationship("ScanNote", back_populates="author", lazy="selectin")
