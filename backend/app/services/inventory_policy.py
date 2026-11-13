"""Single stock policy for projections and hydrated scan responses."""
import math
import re

from sqlalchemy import and_, or_

from app.core.time import as_manila

WHITESPACE = " \t\r\n\v\f\u00a0"
NUMBER = r"([0-9]+([.][0-9]+)?|[.][0-9]+)"
PREDICTION_PATTERN = rf"^{NUMBER}([ \t\r\n]*-[ \t\r\n]*{NUMBER})?$"
# What the page can display (frontend lib/spoilageDisplay.ts): every number starts with
# a digit, and whole days stay within Number.MAX_SAFE_INTEGER.
DISPLAY_NUMBER = r"[0-9]+([.][0-9]+)?"
DISPLAY_PATTERN = rf"^{DISPLAY_NUMBER}([ \t\r\n]*-[ \t\r\n]*{DISPLAY_NUMBER})?$"
MAX_DISPLAY_DAYS = 2**53 - 1


def eligible_stock(scans):
    return and_(
        scans.c.inventory_status == "In Stock",
        or_(
            and_(scans.c.intake_provenance == "unlinked", scans.c.intake_id.is_(None),
                 scans.c.intake_origin_id.is_(None)),
            and_(scans.c.intake_provenance == "linked",
                 scans.c.intake_origin_id == scans.c.intake_id,
                 scans.c.intake_status == "Active"),
        ),
    )


def _prediction_values(raw: str | None) -> list[float] | None:
    """A stored estimate as [value] or [low, high]; None when it is not a valid one."""
    if not isinstance(raw, str):
        return None
    stripped = raw.strip(WHITESPACE)
    if not re.fullmatch(PREDICTION_PATTERN, stripped):
        return None
    values = [float(value.strip(WHITESPACE)) for value in stripped.split("-")]
    if len(values) > 1 and values[1] < values[0]:
        return None
    return values


def remaining_shelf_life(raw: str | None, scanned_at, now) -> float | None:
    values = _prediction_values(raw)
    if values is None:
        return None
    return (
        sum(values) / len(values)
        - (as_manila(now) - as_manila(scanned_at)).total_seconds() / 86400
    )


def prediction_bounds(raw: str | None) -> tuple[int, int] | None:
    """Whole-day window of a stored estimate.

    These are the bounds the estimate is displayed with (frontend
    lib/spoilageDisplay.ts): a decimal spans floor to ceiling, a known zero stays
    zero, and a positive estimate below one day counts as one day. A value that
    page shows as "Unknown" (a number without a leading digit, or above its
    largest exact whole number) has no window, so a countdown never sits beside
    an unknown estimate.
    """
    values = _prediction_values(raw)
    if values is None or not re.fullmatch(DISPLAY_PATTERN, raw.strip(WHITESPACE)):
        return None
    low, high = values[0], values[-1]
    if not high <= MAX_DISPLAY_DAYS:
        # Also rejects the infinity of hundreds of digits overflowing a float.
        return None
    return (0 if low == 0 else max(1, math.floor(low))), math.ceil(high)


def elapsed_manila_days(scanned_at, now) -> int:
    """Whole Asia/Manila calendar days from the scan date to today, never negative."""
    return max(0, (as_manila(now).date() - as_manila(scanned_at).date()).days)


def shelf_life_window(raw: str | None, scanned_at, now) -> dict | None:
    """What is left of a stored estimate on the Manila calendar date of `now`.

    Nothing is stored or rewritten: the estimate and the scan time stay as they
    were written, and each read subtracts the calendar days elapsed since the
    scan. The window has passed once more days have elapsed than its upper bound.
    """
    bounds = prediction_bounds(raw)
    if bounds is None or scanned_at is None or now is None:
        return None
    low, high = bounds
    elapsed = elapsed_manila_days(scanned_at, now)
    return {
        "min_days": low,
        "max_days": high,
        "elapsed_days": elapsed,
        "remaining_min_days": max(0, low - elapsed),
        "remaining_max_days": max(0, high - elapsed),
        "days_past": max(0, elapsed - high),
        "state": "expired" if elapsed > high else "final_day" if elapsed == high else "active",
        # Both dates travel with the count so a page can keep it exact without a new read,
        # also when the scan is dated after the server's own date.
        "scan_date": as_manila(scanned_at).date().isoformat(),
        "as_of_date": as_manila(now).date().isoformat(),
    }


def inventory_facts(scan, status, now):
    provenance = scan.intake_provenance
    eligible = status == "In Stock" and (
        (provenance == "unlinked" and scan.intake_id is None and scan.intake_origin_id is None)
        or (provenance == "linked" and scan.intake_id is not None
            and scan.intake_origin_id == scan.intake_id
            and scan.intake is not None and scan.intake.status == "Active")
    )
    raw = scan.classification.spoilage_days if scan.classification else None
    remaining = remaining_shelf_life(raw, scan.date_time, now)
    return {
        "inventory_eligible": bool(eligible), "remaining_days": remaining, "risk_as_of": now,
        "shelf_life_window": shelf_life_window(raw, scan.date_time, now),
    }
