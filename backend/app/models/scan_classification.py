"""
ScanClassification ORM model — fused AI classification result.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, DECIMAL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanClassification(Base):
    __tablename__ = "scan_classification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    cultivar: Mapped[str] = mapped_column(SAEnum("Lakatan", "Latundan", "Saba", name="cultivar_type"), nullable=False
    )
    ripeness: Mapped[str] = mapped_column(SAEnum("Unripe", "Ripe", "Overripe", "Rotten", name="ripeness_type"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(DECIMAL(5,2), nullable=False)
    temperature: Mapped[float | None] = mapped_column(DECIMAL(5,2), nullable=True)
    humidity: Mapped[float | None] = mapped_column(DECIMAL(5,2), nullable=True)
    spoilage_days: Mapped[str] = mapped_column(String(20), nullable=False)
    finger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    scan = relationship("Scan", back_populates="classification")
