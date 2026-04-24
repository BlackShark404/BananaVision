"""
Device (camera) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Device(Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = mapped_column(
        "dev_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column("dev_camera_id", String(50), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column("dev_label", String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        "dev_status", SAEnum("Online", "Offline", name="device_status"), nullable=False, default="Offline"
    )
    resolution: Mapped[str | None] = mapped_column("dev_resolution", String(20), nullable=True, default="1920x1080")
    last_seen: Mapped[datetime | None] = mapped_column("dev_last_seen", DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        "dev_created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        "dev_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
