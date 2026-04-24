"""
ScanOriginalAiResult ORM model — tracks the pre-override fused AI result.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, DECIMAL, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanOriginalAiResult(Base):
    __tablename__ = "scan_original_ai_result"

    id: Mapped[int] = mapped_column("soar_id", Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        "soar_scan_id", UUID(as_uuid=True), ForeignKey("scan.sc_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    cultivar: Mapped[str] = mapped_column(
        "soar_cultivar", SAEnum("Lakatan", "Latundan", "Saba", name="cultivar_type"), nullable=False
    )
    ripeness: Mapped[str] = mapped_column(
        "soar_ripeness", SAEnum("Unripe", "Ripe", "Overripe", "Rotten", name="ripeness_type"), nullable=False
    )
    confidence: Mapped[float] = mapped_column("soar_confidence", DECIMAL(5,2), nullable=False)
    finger_count: Mapped[int] = mapped_column("soar_finger_count", Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "soar_created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="original_ai_result")
