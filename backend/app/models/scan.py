"""
Scan ORM model — the core scan record.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class Scan(Base):
    __tablename__ = "scan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date_time: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila, index=True
    )
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operator_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    intake_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_intake.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # No FK: this evidence must survive a parent's deletion. Unknown legacy
    # provenance stays excluded until an administrator records a review.
    intake_origin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        default=lambda context: context.get_current_parameters().get("intake_id"),
    )
    intake_provenance: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unverified",
        default=lambda context: "linked" if context.get_current_parameters().get("intake_id") else "unlinked",
    )
    source_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    operator_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships
    operator = relationship("OperatorProfile", back_populates="scans", lazy="selectin")
    intake = relationship("Intake", back_populates="scans", lazy="selectin")
    classification = relationship("ScanClassification", back_populates="scan", uselist=False, lazy="selectin", cascade="all, delete-orphan")
    status_logs = relationship("ScanStatusLog", back_populates="scan", lazy="selectin", cascade="all, delete-orphan", order_by="(ScanStatusLog.updated_at, ScanStatusLog.id)")
    original_ai_result = relationship("ScanOriginalAiResult", back_populates="scan", uselist=False, lazy="selectin", cascade="all, delete-orphan")
    detections = relationship("ScanDetection", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
    images = relationship("ScanImage", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
    notes = relationship("ScanNote", back_populates="scan", lazy="selectin", cascade="all, delete-orphan")
