"""
Device (camera) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import DeviceStatusEnum

class Device(Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
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
