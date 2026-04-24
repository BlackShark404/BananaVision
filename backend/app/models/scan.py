"""
Scan ORM model — the central classification record.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        "sc_operator_id", UUID(as_uuid=True), ForeignKey("operator_profile.op_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    intake_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intakes.id"), nullable=True, index=True
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    cultivar: Mapped[str] = mapped_column(
        SAEnum("Lakatan", "Latundan", "Saba", name="cultivar_type"), nullable=False
    )
    ripeness: Mapped[str] = mapped_column(
        SAEnum("Unripe", "Ripe", "Overripe", "Rotten", name="ripeness_type"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    spoilage_days: Mapped[str] = mapped_column(String(20), nullable=False)
    finger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_status: Mapped[str] = mapped_column(
        SAEnum("In Stock", "Sold", "For Processing", "Spoiled", name="inventory_status_type"),
        nullable=False,
        default="In Stock",
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    original_ai_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    operator = relationship("OperatorProfile", back_populates="scans", lazy="selectin")
    intake = relationship("Intake", back_populates="scans", lazy="selectin")
    detections = relationship("ScanDetection", back_populates="scan", lazy="selectin")
    images = relationship("ScanImage", back_populates="scan", lazy="selectin")
    notes = relationship("ScanNote", back_populates="scan", lazy="selectin")
