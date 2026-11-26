"""
DHT22 sensor routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.api.deps import CurrentUser, DbSession
from app.core.time import now_manila
from app.models.sensor_reading import SensorReading
from app.schemas.common import SensorHistoryResponse, SensorReadingResponse
from app.services.sensor_reader import (
    DHT22_HUM_MAX_PCT,
    DHT22_HUM_MIN_PCT,
    DHT22_TEMP_MAX_C,
    DHT22_TEMP_MIN_C,
    freshness_window_seconds,
    is_valid_dht22,
)

router = APIRouter(prefix="/sensors", tags=["Sensors"])


def _response(reading) -> SensorReadingResponse:
    return SensorReadingResponse.model_validate(reading).model_copy(update={
        "server_time": now_manila(),
        "stale_after_seconds": freshness_window_seconds(),
    })


@router.get("/latest", response_model=SensorReadingResponse | None)
async def latest_sensor(db: DbSession, user: CurrentUser):
    """Get the latest DHT22 sensor reading."""
    result = await db.execute(
        select(SensorReading)
        .where(
            SensorReading.temperature.between(DHT22_TEMP_MIN_C, DHT22_TEMP_MAX_C),
            SensorReading.humidity.between(DHT22_HUM_MIN_PCT, DHT22_HUM_MAX_PCT),
        )
        .order_by(desc(SensorReading.recorded_at))
        .limit(1)
    )
    reading = result.scalar_one_or_none()
    if not reading:
        # Fall back to the latest in-memory reading if no DB records yet
        from app.services.sensor_reader import sensor_reader
        data = sensor_reader.latest
        if data and is_valid_dht22(data.temperature, data.humidity):
            return SensorReadingResponse(
                temperature=data.temperature,
                humidity=data.humidity,
                recorded_at=data.recorded_at,
                server_time=now_manila(),
                stale_after_seconds=freshness_window_seconds(),
            )
        return None
    return _response(reading)


@router.get("/history", response_model=SensorHistoryResponse)
async def sensor_history(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get sensor reading history."""
    result = await db.execute(
        select(SensorReading)
        .where(
            SensorReading.temperature.between(DHT22_TEMP_MIN_C, DHT22_TEMP_MAX_C),
            SensorReading.humidity.between(DHT22_HUM_MIN_PCT, DHT22_HUM_MAX_PCT),
        )
        .order_by(desc(SensorReading.recorded_at))
        .limit(limit)
    )
    readings = result.scalars().all()
    return SensorHistoryResponse(
        items=[_response(r) for r in readings],
        total=len(readings),
    )
