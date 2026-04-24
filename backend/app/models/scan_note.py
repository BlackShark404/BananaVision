"""
ScanNote ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanNote(Base):
    __tablename__ = "scan_note"

    id: Mapped[uuid.UUID] = mapped_column(
        "scnt_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        "scnt_scan_id", UUID(as_uuid=True), ForeignKey("scan.sc_id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column("scnt_text", Text, nullable=False)
    author_name: Mapped[str] = mapped_column("scnt_author_name", String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        "scnt_timestamp", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="notes")
