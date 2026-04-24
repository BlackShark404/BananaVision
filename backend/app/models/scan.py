"""
Scan ORM model — the core scan record.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Scan(Base):
    __tablename__ = "scan"

    id: Mapped[uuid.UUID] = mapped_column(
        "sc_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date_time: Mapped[datetime] = mapped_column(
        "sc_date_time", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    flagged: Mapped[bool] = mapped_column("sc_flagged", Boolean, default=False)
    is_overridden: Mapped[bool] = mapped_column("sc_is_overridden", Boolean, default=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        "sc_operator_id", UUID(as_uuid=True), ForeignKey("operator_profile.op_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    intake_id: Mapped[uuid.UUID | None] = mapped_column(
        "sc_intake_id", UUID(as_uuid=True), ForeignKey("delivery_intake.di_id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_text: Mapped[str | None] = mapped_column("sc_source_text", String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        "sc_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    operator = relationship("OperatorProfile", back_populates="scans", lazy="selectin")
    intake = relationship("Intake", back_populates="scans", lazy="selectin")
    classification = relationship("ScanClassification", back_populates="scan", uselist=False, lazy="selectin", cascade="all, delete-orphan")
    status_logs = relationship("ScanStatusLog", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
    original_ai_result = relationship("ScanOriginalAiResult", back_populates="scan", uselist=False, lazy="selectin", cascade="all, delete-orphan")
    detections = relationship("ScanDetection", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
    images = relationship("ScanImage", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
    notes = relationship("ScanNote", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
