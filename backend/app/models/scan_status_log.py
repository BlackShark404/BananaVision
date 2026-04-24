"""
ScanStatusLog ORM model — tracks inventory lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanStatusLog(Base):
    __tablename__ = "scan_status_log"

    id: Mapped[int] = mapped_column("sslg_id", Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        "sslg_scan_id", UUID(as_uuid=True), ForeignKey("scan.sc_id", ondelete="CASCADE"), nullable=False
    )
    inventory_status: Mapped[str] = mapped_column(
        "sslg_inventory_status",
        SAEnum("In Stock", "Sold", "For Processing", "Spoiled", name="inventory_status_type"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        "sslg_updated_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="status_logs")
