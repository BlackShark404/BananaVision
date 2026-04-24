"""
Sensor reading model for storing continuous background environment logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SensorReading(Base):
    __tablename__ = "sensor_reading"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str] = mapped_column(String(50), default="DHT22")
