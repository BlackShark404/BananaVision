"""
OperatorProfile ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class OperatorProfile(Base):
    __tablename__ = "operator_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_pin_change: Mapped[bool] = mapped_column(Boolean, default=False
    )
    pin_setup_reason: Mapped[str | None] = mapped_column(String(50), nullable=True
    )
    total_scans: Mapped[int] = mapped_column(Integer, default=0)
    flagged_scans: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships
    account = relationship("UserAccount", back_populates="operator_profile", lazy="selectin")
    scans = relationship("Scan", back_populates="operator", lazy="selectin")
