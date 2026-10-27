"""Durable, immutable label snapshots and print submission history."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila


class PrintJob(Base):
    # Separate from any historical automatic-print table behind revision 0007.
    __tablename__ = "scan_label_print_job"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'SUBMITTED', 'FAILED')"),
        CheckConstraint("quantity BETWEEN 1 AND 10"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scan.id", ondelete="CASCADE"), index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int] = mapped_column(Integer)
    printer_name: Mapped[str] = mapped_column(String(260))
    label_data: Mapped[dict] = mapped_column(JSON)
    width_mm: Mapped[float]
    height_mm: Mapped[float]
    status: Mapped[str] = mapped_column(String(12), default="QUEUED")
    windows_job_id: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila)
    updated_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(), default=now_manila, onupdate=now_manila,
    )

    # Relationships
    scan = relationship("Scan", back_populates="print_jobs", lazy="selectin")
    owner = relationship("UserAccount", lazy="selectin")
