"""
Device (camera) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import CheckConstraint, Enum as SAEnum, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import DeviceStatusEnum

class Device(Base):
    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("slot_index", name="uq_device_slot_index"),
        UniqueConstraint("device_index", name="uq_device_device_index"),
        CheckConstraint(
            "slot_index IS NULL OR (slot_index >= 0 AND slot_index < 4)",
            name="ck_device_slot_index_range",
        ),
        CheckConstraint(
            "device_index IS NULL OR device_index >= 0",
            name="ck_device_device_index_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # Nullable only for operational rows that were never assigned to a saved slot.
    # The saved camera-slot mapping itself is these two columns, not a repeated
    # CSV/JSON field on system_config.
    slot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DeviceStatusEnum] = mapped_column(SAEnum(DeviceStatusEnum), nullable=False, default=DeviceStatusEnum.OFFLINE
    )
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True, default="1920x1080")
    last_seen: Mapped[datetime | None] = mapped_column(ManilaDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships — reverse links to per-camera scan data
    detections = relationship("ScanDetection", back_populates="device", lazy="raise")
    images = relationship("ScanImage", back_populates="device", lazy="raise")
