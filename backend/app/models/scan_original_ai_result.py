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


from app.schemas.enums import CultivarEnum, RipenessEnum

class ScanOriginalAiResult(Base):
    __tablename__ = "scan_original_ai_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    cultivar: Mapped[CultivarEnum] = mapped_column(SAEnum(CultivarEnum), nullable=False
    )
    ripeness: Mapped[RipenessEnum] = mapped_column(SAEnum(RipenessEnum), nullable=False
    )
    confidence: Mapped[float] = mapped_column(DECIMAL(5,2), nullable=False)
    finger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="original_ai_result")
