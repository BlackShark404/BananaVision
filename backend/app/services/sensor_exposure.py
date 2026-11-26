"""Continuous post-scan DHT22 exposure aggregation and biological aging adjustments."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app.config import get_settings
from app.core.time import as_manila
from app.models.sensor_reading import SensorReading
from app.services.feature_engineering import calc_vpd
from app.services.sensor_reader import (
    DHT22_HUM_MAX_PCT,
    DHT22_HUM_MIN_PCT,
    DHT22_TEMP_MAX_C,
    DHT22_TEMP_MIN_C,
    is_valid_dht22,
)

DEFAULT_REF_TEMP_C = 25.0
DEFAULT_REF_HUM_PCT = 65.0
MIN_AGING_RATE = 0.5
MAX_AGING_RATE = 2.5
MIN_EXPOSURE_COVERAGE = 0.25


@dataclass(frozen=True)
class HourlySensorBucket:
    """Hourly mean DHT22 conditions in Asia/Manila time."""

    hour_start: datetime
    avg_temp: float
    avg_humidity: float
    sample_count: int
    last_recorded_at: datetime | None = None


@dataclass(frozen=True)
class StorageExposureSummary:
    """Continuous storage-exposure summary since scan time."""

    actual_elapsed_days: float
    biological_elapsed_days: float
    exposure_offset_days: int
    exposure_factor: float
    avg_temperature: float
    avg_humidity: float
    avg_vpd: float
    covered_hours: float
    total_hours: float
    reading_count: int


def _parse_bucket_timestamp(raw_bucket, dialect_name: str) -> datetime | None:
    if isinstance(raw_bucket, datetime):
        return as_manila(raw_bucket)
    if isinstance(raw_bucket, str):
        try:
            parsed = datetime.fromisoformat(raw_bucket)
        except ValueError:
            return None
        if parsed.tzinfo is None and dialect_name == "sqlite":
            parsed = parsed.replace(tzinfo=timezone.utc)
        return as_manila(parsed)
    return None


def _session_dialect_name(db) -> str:
    bind = None
    if hasattr(db, "get_bind"):
        with contextlib.suppress(Exception):
            bind = db.get_bind()
    if bind is None and hasattr(db, "session") and hasattr(db.session, "get_bind"):
        with contextlib.suppress(Exception):
            bind = db.session.get_bind()
    if bind is None and hasattr(db, "bind"):
        bind = db.bind
    return getattr(getattr(bind, "dialect", None), "name", "postgresql")


async def _sensor_reading_table_available(db) -> bool:
    """Return True only if `sensor_reading` exists and has at least one row."""
    dialect_name = _session_dialect_name(db)
    if dialect_name == "sqlite":
        exists = await db.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sensor_reading'")
        )
        if not exists:
            return False
    elif dialect_name == "postgresql":
        exists = await db.scalar(text("SELECT to_regclass('sensor_reading')"))
        if exists is None:
            return False
    return (await db.scalar(select(SensorReading.id).limit(1))) is not None


async def load_hourly_sensor_buckets(
    db,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[HourlySensorBucket]:
    """Load hourly valid DHT22 averages between `start_at` and `end_at` in one query."""
    if not getattr(get_settings(), "sensor_exposure_adjustment", True):
        return []
    if start_at is None or end_at is None:
        return []
    start = as_manila(start_at)
    end = as_manila(end_at)
    if end <= start:
        return []

    if not await _sensor_reading_table_available(db):
        return []

    dialect_name = _session_dialect_name(db)
    if dialect_name == "postgresql":
        bucket_expr = func.date_trunc("hour", SensorReading.recorded_at)
    else:
        bucket_expr = func.strftime("%Y-%m-%dT%H:00:00+00:00", SensorReading.recorded_at)

    stmt = (
        select(
            bucket_expr.label("bucket"),
            func.avg(SensorReading.temperature).label("avg_temp"),
            func.avg(SensorReading.humidity).label("avg_hum"),
            func.count(SensorReading.id).label("sample_count"),
            func.max(SensorReading.recorded_at).label("last_recorded_at"),
        )
        .where(
            SensorReading.recorded_at >= start,
            SensorReading.recorded_at <= end,
            SensorReading.temperature.between(DHT22_TEMP_MIN_C, DHT22_TEMP_MAX_C),
            SensorReading.humidity.between(DHT22_HUM_MIN_PCT, DHT22_HUM_MAX_PCT),
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr.asc())
    )
    rows = (await db.execute(stmt)).all()
    buckets: list[HourlySensorBucket] = []
    for row in rows:
        hour_start = _parse_bucket_timestamp(row.bucket, dialect_name)
        if hour_start is None:
            continue
        avg_temp = float(row.avg_temp) if row.avg_temp is not None else None
        avg_hum = float(row.avg_hum) if row.avg_hum is not None else None
        if not is_valid_dht22(avg_temp, avg_hum):
            continue
        last_recorded = _parse_bucket_timestamp(row.last_recorded_at, dialect_name)
        buckets.append(
            HourlySensorBucket(
                hour_start=hour_start.replace(minute=0, second=0, microsecond=0),
                avg_temp=round(avg_temp, 2),
                avg_humidity=round(avg_hum, 2),
                sample_count=int(row.sample_count or 0),
                last_recorded_at=last_recorded,
            )
        )
    buckets.sort(key=lambda item: item.hour_start)
    return buckets


def compute_aging_rate(
    temperature: float,
    humidity: float,
    ref_temperature: float,
    ref_humidity: float,
) -> float:
    """Smooth bounded biological aging rate relative to scan-time reference conditions.

    Returns 1.0 identically when `(temperature, humidity) == (ref_temperature, ref_humidity)`.
    """
    thermal_rate = 2.0 ** ((temperature - ref_temperature) / 10.0)
    excess_rh_now = max(0.0, (humidity - 85.0) / 15.0) * 0.15
    excess_rh_ref = max(0.0, (ref_humidity - 85.0) / 15.0) * 0.15
    vpd_delta = calc_vpd(temperature, humidity) - calc_vpd(ref_temperature, ref_humidity)
    rate = thermal_rate + (excess_rh_now - excess_rh_ref) + 0.04 * vpd_delta
    return max(MIN_AGING_RATE, min(MAX_AGING_RATE, rate))


def compute_exposure(
    scanned_at: datetime | None,
    now: datetime | None,
    *,
    ref_temperature: float | None = None,
    ref_humidity: float | None = None,
    buckets: Sequence[HourlySensorBucket] = (),
    bucket_starts: Sequence[datetime] | None = None,
) -> StorageExposureSummary | None:
    """Compute time-weighted continuous DHT22 exposure between `scanned_at` and `now`."""
    if not buckets or scanned_at is None or now is None:
        return None
    start = as_manila(scanned_at)
    end = as_manila(now)
    if end <= start:
        return None

    has_ref = is_valid_dht22(ref_temperature, ref_humidity)
    t_ref = float(ref_temperature) if has_ref else DEFAULT_REF_TEMP_C
    rh_ref = float(ref_humidity) if has_ref else DEFAULT_REF_HUM_PCT

    starts = bucket_starts if bucket_starts is not None else [b.hour_start for b in buckets]
    first_hour = start.replace(minute=0, second=0, microsecond=0)
    idx = bisect_left(starts, first_hour)

    bio_covered_days = 0.0
    covered_seconds = 0.0
    temp_weighted = 0.0
    hum_weighted = 0.0
    reading_count = 0

    while idx < len(buckets):
        bucket = buckets[idx]
        if bucket.hour_start >= end:
            break
        if bucket.last_recorded_at is not None and bucket.last_recorded_at <= start:
            idx += 1
            continue
        bucket_end = bucket.hour_start + timedelta(hours=1)
        ov_start = max(start, bucket.hour_start)
        ov_end = min(end, bucket_end)
        if ov_end > ov_start:
            ov_seconds = (ov_end - ov_start).total_seconds()
            ov_days = ov_seconds / 86400.0
            rate = compute_aging_rate(bucket.avg_temp, bucket.avg_humidity, t_ref, rh_ref)
            bio_covered_days += ov_days * rate
            covered_seconds += ov_seconds
            temp_weighted += bucket.avg_temp * ov_seconds
            hum_weighted += bucket.avg_humidity * ov_seconds
            reading_count += bucket.sample_count
        idx += 1

    actual_seconds = (end - start).total_seconds()
    if (
        covered_seconds <= 0.0
        or reading_count <= 0
        or actual_seconds <= 0.0
        or (covered_seconds / actual_seconds) < MIN_EXPOSURE_COVERAGE
    ):
        return None
    actual_days = actual_seconds / 86400.0
    covered_days = covered_seconds / 86400.0
    uncovered_days = max(0.0, actual_days - covered_days)
    biological_days = bio_covered_days + uncovered_days

    avg_temp = round(temp_weighted / covered_seconds, 2)
    avg_hum = round(min(DHT22_HUM_MAX_PCT, max(DHT22_HUM_MIN_PCT, hum_weighted / covered_seconds)), 2)
    offset_days = round(biological_days - actual_days)

    return StorageExposureSummary(
        actual_elapsed_days=round(actual_days, 4),
        biological_elapsed_days=round(biological_days, 4),
        exposure_offset_days=offset_days,
        exposure_factor=round(biological_days / actual_days, 3) if actual_days > 0 else 1.0,
        avg_temperature=avg_temp,
        avg_humidity=avg_hum,
        avg_vpd=calc_vpd(avg_temp, avg_hum),
        covered_hours=round(covered_seconds / 3600.0, 2),
        total_hours=round(actual_seconds / 3600.0, 2),
        reading_count=reading_count,
    )


async def load_buckets_for_dates(
    db,
    dates: Iterable[datetime | None],
    now: datetime | None,
) -> tuple[list[HourlySensorBucket], list[datetime]]:
    """Load hourly buckets spanning the earliest timestamp in `dates` through `now`."""
    normalized = [as_manila(dt) for dt in dates if dt is not None]
    if not normalized or now is None:
        return [], []
    buckets = await load_hourly_sensor_buckets(db, min(normalized), now)
    return buckets, [bucket.hour_start for bucket in buckets]


async def load_buckets_for_query(
    db,
    earliest_stmt,
    now: datetime | None,
) -> tuple[list[HourlySensorBucket], list[datetime]]:
    """Load hourly buckets only if SensorReading has rows and `earliest_stmt` yields a date."""
    if not getattr(get_settings(), "sensor_exposure_adjustment", True) or now is None:
        return [], []
    if not await _sensor_reading_table_available(db):
        return [], []
    earliest = await db.scalar(earliest_stmt)
    if earliest is None:
        return [], []
    buckets = await load_hourly_sensor_buckets(db, earliest, now)
    return buckets, [bucket.hour_start for bucket in buckets]


def row_exposure(
    row,
    now: datetime | None,
    *,
    buckets: Sequence[HourlySensorBucket] = (),
    bucket_starts: Sequence[datetime] | None = None,
    respect_closed_status: bool = True,
) -> StorageExposureSummary | None:
    """Evaluate continuous storage exposure for a projected SQL/ORM scan row."""
    if not buckets or now is None:
        return None
    status = getattr(row, "inventory_status", None)
    status_text = status.value if hasattr(status, "value") else status
    if respect_closed_status and status_text in ("Sold", "Spoiled", "For Processing"):
        return None
    return compute_exposure(
        getattr(row, "date_time", None),
        now,
        ref_temperature=getattr(row, "temperature", None),
        ref_humidity=getattr(row, "humidity", None),
        buckets=buckets,
        bucket_starts=bucket_starts,
    )


def effective_remaining_days(
    row,
    now: datetime | None,
    *,
    buckets: Sequence[HourlySensorBucket] = (),
    bucket_starts: Sequence[datetime] | None = None,
) -> float | None:
    """Adjust continuous `remaining_days` using post-scan DHT22 exposure when available."""
    raw_remaining = getattr(row, "remaining_days", None)
    if raw_remaining is None:
        return None
    remaining = float(raw_remaining)
    exposure = row_exposure(
        row,
        now,
        buckets=buckets,
        bucket_starts=bucket_starts,
    )
    if exposure is None:
        return remaining
    predicted = getattr(row, "predicted_days", None)
    if predicted is not None:
        return round(float(predicted) - exposure.biological_elapsed_days, 4)
    return round(remaining + (exposure.actual_elapsed_days - exposure.biological_elapsed_days), 4)

