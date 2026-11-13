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
