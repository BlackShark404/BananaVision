"""Shared human-friendly formatting for BananaVision scan exports (XLSX and PDF).

Produces one canonical table so Excel and PDF exports share the exact same
columns, row order, and displayed values while keeping measurement/percentage
columns numeric in Excel spreadsheets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.time import as_manila
from app.services.inventory_policy import (
    prediction_bounds,
    ripeness_projection,
    shelf_life_window,
)

MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

CLOSED_STOCK_STATUSES = frozenset({"Sold", "Spoiled", "For Processing"})

SCAN_EXPORT_HEADERS = [
    "Scan Ref",
    "Date & Time",
    "Source / Supplier",
    "Cultivar",
    "Scanned Ripeness",
    "Est. Current Ripeness",
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


@dataclass(frozen=True)
class ExportCell:
    """One canonical cell carrying both its exact display text and Excel cell typing."""

    text: str
    xlsx_type: str = "inlineStr"  # "inlineStr" | "n"
    xlsx_value: str | None = None
    xlsx_style: int = 1


def _text_cell(value: str) -> ExportCell:
    return ExportCell(text=value)


def _fixed1_cell(value: float | Decimal | None) -> ExportCell:
    """Format a 1-decimal measurement/percentage that stays numeric in Excel."""
    if value is None:
        return ExportCell(text="")
    formatted = f"{float(value):.1f}"
    # Style index 3 applies Excel number format "0.0" so Excel displays 1 decimal place
    # while preserving native numeric sorting and formulas (AVERAGE, MIN, MAX).
    return ExportCell(text=formatted, xlsx_type="n", xlsx_value=formatted, xlsx_style=3)


def format_scan_ref(scan_id: UUID | str | None) -> str:
    """Deterministic short scan code derived from scan.id, e.g. 'SCAN-DEB78E6B'."""
    if scan_id is None:
        return ""
    cleaned = str(scan_id).strip().replace("-", "")
    return f"SCAN-{cleaned[:8].upper()}" if cleaned else ""


def format_manila_datetime(value: datetime | None) -> str:
    """Format a timestamp as readable Asia/Manila time with seconds ('Nov 25, 2026, 1:45:11 PM')."""
    if value is None:
        return ""
    local = as_manila(value)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return (
        f"{MONTHS[local.month - 1]} {local.day}, {local.year}, "
        f"{hour12}:{local.minute:02d}:{local.second:02d} {ampm}"
    )


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


def format_current_ripeness(
    ripeness: Any,
    cultivar: Any,
    spoilage_days: str | None,
    date_time: datetime | None,
    now: datetime,
    inventory_status: Any,
    *,
    temperature: float | Decimal | None = None,
    humidity: float | Decimal | None = None,
    vpd: float | Decimal | None = None,
    treatment: Any = None,
    projection: dict[str, Any] | None = None,
) -> str:
    """Format time-progressed ripeness for In Stock scans, or '—' when stock is closed."""
    base = enum_text(ripeness)
    if not base:
        return ""
    status = enum_text(inventory_status)
    if status in CLOSED_STOCK_STATUSES:
        return "—"
    resolved = (
        projection
        if projection is not None
        else ripeness_projection(
            base,
            cultivar,
            spoilage_days,
            date_time,
            now,
            temperature=temperature,
            humidity=humidity,
            vpd=vpd,
            treatment=treatment,
            inventory_status=status or "In Stock",
        )
    )
    if resolved is None:
        return base
    current = str(resolved["current_ripeness"])
    return f"Est. {current}" if resolved.get("progressed") else current


def format_scan_export_cells(
    *,
    scan_id: UUID | str | None,
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
    vpd: float | Decimal | None = None,
    treatment: Any = None,
    ripeness_proj: dict[str, Any] | None = None,
) -> list[ExportCell]:
    """Return the 15 canonical cells matching SCAN_EXPORT_HEADERS."""
    status_text = enum_text(inventory_status) or "In Stock"
    return [
        _text_cell(format_scan_ref(scan_id)),
        _text_cell(format_manila_datetime(date_time)),
        _text_cell(source_name or ""),
        _text_cell(enum_text(cultivar)),
        _text_cell(enum_text(ripeness)),
        _text_cell(format_current_ripeness(
            ripeness,
            cultivar,
            spoilage_days,
            date_time,
            as_of,
            status_text,
            temperature=temperature,
            humidity=humidity,
            vpd=vpd,
            treatment=treatment,
            projection=ripeness_proj,
        )),
        _text_cell(format_fingers(
            finger_count,
            is_overridden=is_overridden,
            original_finger_count=original_finger_count,
        )),
        _text_cell(format_original_shelf_life(spoilage_days)),
        _text_cell(format_freshness(
            spoilage_days,
            date_time,
            as_of,
            status_text,
            window=shelf_life,
        )),
        _text_cell(status_text),
        _text_cell(format_review_status(flagged)),
        _fixed1_cell(confidence),
        _fixed1_cell(temperature),
        _fixed1_cell(humidity),
        _text_cell(operator_name or ""),
    ]


def to_xlsx_rows(rows: list[list[ExportCell]]) -> list[list[dict[str, Any] | None]]:
    """Convert canonical export cells to typed XLSX cell specs (blank for empty cells)."""
    xlsx_rows: list[list[dict[str, Any] | None]] = []
    for row in rows:
        out_row: list[dict[str, Any] | None] = []
        for cell in row:
            if cell.text == "":
                out_row.append(None)
            elif cell.xlsx_type == "n":
                out_row.append({
                    "value": cell.xlsx_value if cell.xlsx_value is not None else cell.text,
                    "type": "n",
                    "style": cell.xlsx_style,
                })
            else:
                out_row.append({"value": cell.text, "type": "inlineStr", "style": cell.xlsx_style})
        xlsx_rows.append(out_row)
    return xlsx_rows


def to_pdf_rows(rows: list[list[ExportCell]]) -> list[list[str]]:
    """Convert canonical export cells to display strings for PDF rendering."""
    return [[cell.text for cell in row] for row in rows]
