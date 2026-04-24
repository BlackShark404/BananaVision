"""
ScanImage ORM model — captured image metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanImage(Base):
    __tablename__ = "scan_image"

    id: Mapped[uuid.UUID] = mapped_column(
        "si_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        "si_scan_id", UUID(as_uuid=True), ForeignKey("scan.sc_id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column("si_camera_id", String(20), nullable=False)
    file_path: Mapped[str] = mapped_column("si_file_path", String(500), nullable=False)
    width: Mapped[int | None] = mapped_column("si_width", Integer, nullable=True)
    height: Mapped[int | None] = mapped_column("si_height", Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column("si_file_size_bytes", Integer, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        "si_captured_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    scan = relationship("Scan", back_populates="images")
