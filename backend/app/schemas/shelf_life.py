"""Live shelf-life window, derived on every read; nothing in it is stored."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class ShelfLifeWindow(BaseModel):
    """What is left of a stored estimate, in whole Asia/Manila calendar days.

    `min_days`/`max_days` are the whole-day bounds of the stored estimate and never
    change. `elapsed_days` counts calendar dates from `scan_date` to `as_of_date`,
    never below zero, and the remaining bounds are the estimate minus that count.
    """

    min_days: int
    max_days: int
    elapsed_days: int
    remaining_min_days: int
    remaining_max_days: int
    days_past: int
    state: Literal["active", "final_day", "expired"]
    scan_date: date
    as_of_date: date


class StorageExposureSummary(BaseModel):
    """Continuous storage temperature/humidity exposure since scan time."""

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


RipenessStage = Literal["Unripe", "Semi Ripe", "Ripe", "Overripe"]


class RipenessProjection(BaseModel):
    """Live time-progressed ripeness estimate, derived on read; never stored.

    Anchored at `base_ripeness` (the scan-time or admin-verified classification)
    and advanced monotonically in whole Asia/Manila calendar days using the
    RFR stage thresholds (or monotonic fallback ratios).
    """

    base_ripeness: RipenessStage
    current_ripeness: RipenessStage
    progressed: bool
    elapsed_days: int
    transitions: dict[RipenessStage, int]
    scan_date: date
    as_of_date: date
