"""
SystemConfig ORM model — typed system configuration.
"""

from __future__ import annotations

from datetime import datetime
from app.core.time import now_manila
import uuid

from sqlalchemy import Integer, ForeignKey, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class SystemConfig(Base):
    __tablename__ = "system_config"
    __table_args__ = (CheckConstraint('canonical_key IS NULL OR canonical_key = 1', name='ck_config_canonical_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_key: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    legacy_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    confidence_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    data_retention_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )
    updated_by_admin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_profile.id", ondelete="SET NULL"), nullable=True
    )

    admin = relationship("AdminProfile", lazy="selectin")
