"""
Sensor reading model for storing continuous background environment logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila


class SensorReading(Base):
    __tablename__ = "sensor_reading"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(), default=now_manila
    )
    source: Mapped[str] = mapped_column(String(50), default="DHT22")
