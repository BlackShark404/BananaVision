"""
DHT22 sensor routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select, desc

from app.api.deps import DbSession, CurrentUser
from app.models.sensor_reading import SensorReading
from app.schemas.common import SensorReadingResponse, SensorHistoryResponse


router = APIRouter(prefix="/sensors", tags=["Sensors"])


@router.get("/latest", response_model=SensorReadingResponse | None)
async def latest_sensor(db: DbSession, user: CurrentUser):
    """Get the latest DHT22 sensor reading."""
    result = await db.execute(
        select(SensorReading).order_by(desc(SensorReading.recorded_at)).limit(1)
    )
    reading = result.scalar_one_or_none()
    if not reading:
        # Fall back to the latest in-memory reading if no DB records yet
        from app.services.sensor_reader import sensor_reader
        data = sensor_reader.latest
        if data:
            return SensorReadingResponse(
                temperature=data.temperature,
                humidity=data.humidity,
                recorded_at=data.recorded_at,
            )
        return None
    return SensorReadingResponse.model_validate(reading)


@router.get("/history", response_model=SensorHistoryResponse)
async def sensor_history(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get sensor reading history."""
    result = await db.execute(
        select(SensorReading).order_by(desc(SensorReading.recorded_at)).limit(limit)
    )
    readings = result.scalars().all()
    return SensorHistoryResponse(
        items=[SensorReadingResponse.model_validate(r) for r in readings],
        total=len(readings),
    )
