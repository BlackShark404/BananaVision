"""
ScanOriginalAiResult ORM model — tracks the pre-override fused AI result.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila
from app.schemas.enums import CultivarEnum, RipenessEnum


class ScanOriginalAiResult(Base):
    __tablename__ = "scan_original_ai_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    cultivar: Mapped[CultivarEnum | None] = mapped_column(SAEnum(CultivarEnum), nullable=True
    )
    ripeness: Mapped[RipenessEnum | None] = mapped_column(SAEnum(RipenessEnum), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(DECIMAL(5,2), nullable=True)
    spoilage_days: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )

    # Relationships
    scan = relationship("Scan", back_populates="original_ai_result")
