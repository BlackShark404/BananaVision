"""
Intake (daily delivery batch) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Enum as SAEnum, DateTime, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Intake(Base):
    __tablename__ = "delivery_intake"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(SAEnum("Active", "Depleted", name="intake_status"), nullable=False, default="Active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    scans = relationship("Scan", back_populates="intake", lazy="selectin")
    supplier = relationship("Supplier", lazy="selectin")
