"""
Intake (daily delivery batch) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Enum as SAEnum, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Intake(Base):
    __tablename__ = "delivery_intake"

    id: Mapped[uuid.UUID] = mapped_column(
        "di_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column("di_source", String(100), nullable=False)
    intake_date: Mapped[date] = mapped_column("di_date", Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        "di_status", SAEnum("Active", "Depleted", name="intake_status"), nullable=False, default="Active"
    )
    created_at: Mapped[datetime] = mapped_column(
        "di_created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        "di_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    scans = relationship("Scan", back_populates="intake", lazy="selectin")
