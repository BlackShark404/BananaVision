"""
ScanStatusLog ORM model — tracks inventory lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila
from app.schemas.enums import InventoryStatusEnum


class ScanStatusLog(Base):
    __tablename__ = "scan_status_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), nullable=False
    )
    inventory_status: Mapped[InventoryStatusEnum] = mapped_column(SAEnum(InventoryStatusEnum),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )

    # Relationships
    scan = relationship("Scan", back_populates="status_logs")
