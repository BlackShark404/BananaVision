"""
Intake (daily delivery batch) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from app.core.time import now_manila

from sqlalchemy import Date, Enum as SAEnum, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import IntakeStatusEnum, TreatmentEnum

class Intake(Base):
    __tablename__ = "delivery_intake"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[IntakeStatusEnum] = mapped_column(SAEnum(IntakeStatusEnum), nullable=False, default=IntakeStatusEnum.ACTIVE
    )
    # ── Batch lifecycle fields (for RFR dataset) ────────────────────────────
    treatment: Mapped[TreatmentEnum | None] = mapped_column(
        SAEnum(TreatmentEnum, values_callable=lambda obj: [e.value for e in obj]), nullable=True, default=TreatmentEnum.NATURAL
    )
    harvested_at: Mapped[datetime | None] = mapped_column(
        ManilaDateTime(), nullable=True
    )
    treated_at: Mapped[datetime | None] = mapped_column(
        ManilaDateTime(), nullable=True
    )
    spoiled_at: Mapped[datetime | None] = mapped_column(
        ManilaDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships
    scans = relationship("Scan", back_populates="intake", lazy="selectin")
    supplier = relationship("Supplier", back_populates="intakes", lazy="selectin")
    expected_stock = relationship(
        "IntakeExpectedStock", back_populates="intake", lazy="selectin",
        cascade="all, delete-orphan", order_by="IntakeExpectedStock.cultivar",
    )

