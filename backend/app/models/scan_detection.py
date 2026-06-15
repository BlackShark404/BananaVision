"""
ScanDetection ORM model — per-camera raw detection results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, DECIMAL, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanDetection(Base):
    __tablename__ = "scan_detection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(String(20), nullable=False)
    camera_label: Mapped[str] = mapped_column(String(30), nullable=False)
    detected_cultivar: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detected_ripeness: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(DECIMAL(5,2), nullable=True)
    finger_count: Mapped[int] = mapped_column(Integer, default=0)
    bounding_boxes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    inference_time_ms: Mapped[float | None] = mapped_column(DECIMAL(8,2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="detections")
