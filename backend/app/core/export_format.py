"""Shared human-friendly formatting for BananaVision scan exports (XLSX and PDF).

Produces one canonical table of formatted values so Excel and PDF exports share
the exact same columns, row order, and cell contents.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.time import as_manila
from app.services.inventory_policy import prediction_bounds, shelf_life_window

MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

CLOSED_STOCK_STATUSES = frozenset({"Sold", "Spoiled", "For Processing"})

SCAN_EXPORT_HEADERS = [
    "Date & Time",
    "Source / Supplier",
    "Cultivar",
    "Ripeness",
    "Est. Fingers",
    "Est. Shelf Life (Original)",
    "Est. Time Left / Freshness",
    "Inventory Status",
    "Review Status",
    "Confidence (%)",
    "Temperature (°C)",
    "Humidity (%)",
    "Operator",
]


def format_manila_datetime(value: datetime | None) -> str:
    """Format a timestamp as readable Asia/Manila time, e.g. 'Nov 19, 2026, 9:12 PM'."""
    if value is None:
        return ""
    local = as_manila(value)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{MONTHS[local.month - 1]} {local.day}, {local.year}, {hour12}:{local.minute:02d} {ampm}"


def format_manila_date(value: date | datetime | None) -> str:
    """Format a business date as readable Manila calendar text, e.g. 'Nov 19, 2026'."""
    if value is None:
        return ""
    local_date = as_manila(value).date() if isinstance(value, datetime) else value
    return f"{MONTHS[local_date.month - 1]} {local_date.day}, {local_date.year}"


def enum_text(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    text = str(raw)
    return "" if text == "Unknown" else text


def finger_count_is_estimate(
    finger_count: int | None,
    *,
    is_overridden: bool = False,
    original_finger_count: int | None = None,
) -> bool:
    """True unless a person explicitly changed the finger count from the AI baseline."""
    if not is_overridden or original_finger_count is None:
        return True
    return finger_count == original_finger_count


def format_fingers(
    finger_count: int | None,
    *,
    is_overridden: bool = False,
    original_finger_count: int | None = None,
) -> str:
    """Format finger count per estimate wording rules ('Est. 13 fingers' vs '13 fingers')."""
    if finger_count is None or finger_count < 0:
        return ""
    unit = "finger" if finger_count == 1 else "fingers"
    estimated = finger_count_is_estimate(
        finger_count,
        is_overridden=is_overridden,
        original_finger_count=original_finger_count,
    )
    return f"Est. {finger_count} {unit}" if estimated else f"{finger_count} {unit}"


def format_original_shelf_life(spoilage_days: str | None) -> str:
    """Format stored shelf-life prediction as whole days, e.g. '14–15 days' or '1 day'."""
    bounds = prediction_bounds(spoilage_days)
    if bounds is None:
        return ""
    low, high = bounds
    label = str(low) if low == high else f"{low}–{high}"
    unit = "day" if label == "1" else "days"
    return f"{label} {unit}"


def format_freshness(
    spoilage_days: str | None,
    date_time: datetime | None,
    now: datetime,
    inventory_status: str | None,
    window: dict[str, Any] | None = None,
) -> str:
    """Format live shelf-life countdown or closed-stock outcome for human readers."""
    status = enum_text(inventory_status)
    if status in CLOSED_STOCK_STATUSES:
        return status
    resolved = window if window is not None else shelf_life_window(spoilage_days, date_time, now)
    if resolved is None:
        return ""
    state = resolved["state"]
    if state == "final_day":
        return "Final day"
    if state == "expired":
        days_past = int(resolved["days_past"])
        unit = "day" if days_past == 1 else "days"
        return f"Overdue by {days_past} {unit}"
    low = int(resolved["remaining_min_days"])
    high = int(resolved["remaining_max_days"])
    if low == high:
        unit = "day" if high == 1 else "days"
        return f"{high} {unit} left"
    return f"{low}–{high} days left"


def format_review_status(flagged: bool) -> str:
    return "Needs Review" if flagged else "Approved"


def format_confidence(confidence: float | Decimal | None) -> str:
    if confidence is None:
        return ""
    return f"{float(confidence):.1f}%"


def format_temperature(temperature: float | Decimal | None) -> str:
    if temperature is None:
        return ""
    return f"{float(temperature):.1f}°C"


def format_humidity(humidity: float | Decimal | None) -> str:
    if humidity is None:
        return ""
    return f"{float(humidity):.1f}%"


def format_scan_export_row(
    *,
    date_time: datetime | None,
    source_name: str | None,
    cultivar: Any,
    ripeness: Any,
    finger_count: int | None,
    is_overridden: bool,
    original_finger_count: int | None,
    spoilage_days: str | None,
    inventory_status: Any,
    flagged: bool,
    confidence: float | Decimal | None,
    temperature: float | Decimal | None,
    humidity: float | Decimal | None,
    operator_name: str | None,
    as_of: datetime,
    shelf_life: dict[str, Any] | None = None,
) -> list[str]:
    """Return the 13 formatted cell strings matching SCAN_EXPORT_HEADERS."""
    status_text = enum_text(inventory_status) or "In Stock"
    return [
        format_manila_datetime(date_time),
        source_name or "",
        enum_text(cultivar),
        enum_text(ripeness),
        format_fingers(
            finger_count,
            is_overridden=is_overridden,
            original_finger_count=original_finger_count,
        ),
        format_original_shelf_life(spoilage_days),
        format_freshness(
            spoilage_days,
            date_time,
            as_of,
            status_text,
            window=shelf_life,
        ),
        status_text,
        format_review_status(flagged),
        format_confidence(confidence),
        format_temperature(temperature),
        format_humidity(humidity),
        operator_name or "",
    ]


def to_xlsx_rows(rows: list[list[str]]) -> list[list[tuple[str, str] | None]]:
    """Convert formatted string rows to inlineStr cells, keeping blank strings as empty cells."""
    return [
        [None if value == "" else (value, "inlineStr") for value in row]
        for row in rows
    ]
