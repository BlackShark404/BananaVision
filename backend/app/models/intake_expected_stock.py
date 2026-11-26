"""Expected received stock recorded per intake and variety."""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import CultivarEnum


class IntakeExpectedStock(Base):
    __tablename__ = "intake_expected_stock"
    __table_args__ = (
        UniqueConstraint("intake_id", "cultivar", name="uq_intake_expected_stock_intake_cultivar"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    intake_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_intake.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    cultivar: Mapped[CultivarEnum] = mapped_column(SAEnum(CultivarEnum), nullable=False
    )
    expected_bunches: Mapped[int] = mapped_column(Integer, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    intake = relationship("Intake", back_populates="expected_stock")