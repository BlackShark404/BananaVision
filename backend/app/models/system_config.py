"""
SystemConfig ORM model — typed system configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, Text, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column("sc_id", Integer, primary_key=True, autoincrement=True)
    camera_ids: Mapped[str] = mapped_column("sc_camera_ids", Text, nullable=False, default="CAM-001, CAM-002, CAM-003, CAM-004")
    confidence_threshold: Mapped[int] = mapped_column("sc_confidence_threshold", Integer, nullable=False, default=85)
    data_retention_enabled: Mapped[bool] = mapped_column("sc_data_retention", Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        "sc_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    upd_by_admin: Mapped[uuid.UUID | None] = mapped_column(
        "sc_upt_by_admin", UUID(as_uuid=True), ForeignKey("admin_profile.ap_id", ondelete="SET NULL"), nullable=True
    )

    admin = relationship("AdminProfile", lazy="selectin")
