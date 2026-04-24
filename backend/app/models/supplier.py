"""
Supplier ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Enum as SAEnum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "supplier"

    id: Mapped[uuid.UUID] = mapped_column(
        "sup_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column("sup_name", String(100), unique=True, nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column("sup_contact_person", String(100), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column("sup_contact_phone", String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        "sup_status", SAEnum("Active", "Inactive", name="supplier_status"), nullable=False, default="Active"
    )
    date_added: Mapped[datetime] = mapped_column(
        "sup_date_added", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        "sup_updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
