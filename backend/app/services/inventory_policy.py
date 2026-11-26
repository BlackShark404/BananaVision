"""Single stock policy for projections and hydrated scan responses."""
import math
import re

from sqlalchemy import and_, or_

from app.core.time import as_manila
from app.services.sensor_exposure import StorageExposureSummary, compute_exposure
from app.services.spoilage import RIPENESS_STAGES, spoilage_predictor

CLOSED_INVENTORY_STATUSES = frozenset({"Sold", "Spoiled", "For Processing"})

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


def remaining_shelf_life(
    raw: str | None,
    scanned_at,
    now,
    *,
    exposure: StorageExposureSummary | None = None,
) -> float | None:
    values = _prediction_values(raw)
    if values is None:
        return None
    if exposure is not None:
        return sum(values) / len(values) - exposure.biological_elapsed_days
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


def shelf_life_window(
    raw: str | None,
    scanned_at,
    now,
    *,
    exposure_offset_days: int = 0,
) -> dict | None:
    """What is left of a stored estimate on the Manila calendar date of `now`.

    Nothing is stored or rewritten: the estimate and the scan time stay as they
    were written, and each read subtracts the calendar days elapsed since the
    scan (adjusted by `exposure_offset_days` when continuous storage readings exist).
    The window has passed once more days have elapsed than its upper bound.
    """
    bounds = prediction_bounds(raw)
    if bounds is None or scanned_at is None or now is None:
        return None
    low, high = bounds
    calendar_elapsed = elapsed_manila_days(scanned_at, now)
    elapsed = max(0, calendar_elapsed + int(exposure_offset_days)) if calendar_elapsed > 0 or exposure_offset_days > 0 else 0
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


def _enum_text(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def ripeness_projection(
    ripeness,
    cultivar,
    spoilage_days: str | None,
    scanned_at,
    now,
    *,
    temperature=None,
    humidity=None,
    vpd=None,
    treatment=None,
    inventory_status=None,
    respect_closed_status: bool = True,
    predictor=None,
    exposure_offset_days: int = 0,
) -> dict | None:
    """Derive a live, monotonic time-progressed ripeness estimate on read.

    Never modifies stored ripeness. Anchors at the scanned/admin-verified stage on
    Day 0 and scales RFR stage remaining-life thresholds proportionally to the
    stored `spoilage_days` prediction so admin overrides and legacy ranges stay
    coherent. Closed inventory statuses freeze at the stored ripeness.
    """
    base = _enum_text(ripeness)
    if base not in RIPENESS_STAGES or scanned_at is None or now is None:
        return None
    scan_date = as_manila(scanned_at).date()
    as_of_date = as_manila(now).date()
    status = _enum_text(inventory_status)
    if respect_closed_status and status in CLOSED_INVENTORY_STATUSES:
        return {
            "base_ripeness": base,
            "current_ripeness": base,
            "progressed": False,
            "elapsed_days": 0,
            "transitions": {},
            "scan_date": scan_date.isoformat(),
            "as_of_date": as_of_date.isoformat(),
        }

    calendar_elapsed = elapsed_manila_days(scanned_at, now)
    elapsed = max(0, calendar_elapsed + int(exposure_offset_days)) if calendar_elapsed > 0 or exposure_offset_days > 0 else 0
    stage_idx = RIPENESS_STAGES.index(base)
    transitions: dict[str, int] = {}

    if stage_idx < len(RIPENESS_STAGES) - 1:
        values = _prediction_values(spoilage_days)
        if values is not None:
            anchor_days = sum(values) / len(values)
            active_predictor = predictor or spoilage_predictor
            lifetimes = active_predictor.stage_lifetimes(
                _enum_text(cultivar),
                temperature=None if temperature is None else float(temperature),
                humidity=None if humidity is None else float(humidity),
                vpd=None if vpd is None else float(vpd),
                treatment=_enum_text(treatment),
            )
            base_lifetime = lifetimes[stage_idx]
            for next_idx in range(stage_idx + 1, len(RIPENESS_STAGES)):
                ratio = lifetimes[next_idx] / base_lifetime if base_lifetime > 0 else 0.0
                cutoff = anchor_days * ratio
                transitions[RIPENESS_STAGES[next_idx]] = max(1, math.ceil(anchor_days - cutoff))

    current = base
    for next_idx in range(stage_idx + 1, len(RIPENESS_STAGES)):
        stage_name = RIPENESS_STAGES[next_idx]
        threshold_day = transitions.get(stage_name)
        if threshold_day is not None and elapsed >= threshold_day:
            current = stage_name

    return {
        "base_ripeness": base,
        "current_ripeness": current,
        "progressed": current != base,
        "elapsed_days": elapsed,
        "transitions": transitions,
        "scan_date": scan_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
    }


def scan_storage_exposure(
    scan,
    status,
    now,
    *,
    exposure_buckets=None,
    bucket_starts=None,
    respect_closed_status: bool = True,
) -> StorageExposureSummary | None:
    """Compute post-scan continuous sensor exposure for active stock (or public tracking)."""
    if not exposure_buckets:
        return None
    status_text = _enum_text(status)
    if respect_closed_status and status_text in CLOSED_INVENTORY_STATUSES:
        return None
    classification = getattr(scan, "classification", None)
    return compute_exposure(
        getattr(scan, "date_time", None),
        now,
        ref_temperature=getattr(classification, "temperature", None) if classification else None,
        ref_humidity=getattr(classification, "humidity", None) if classification else None,
        buckets=exposure_buckets,
        bucket_starts=bucket_starts,
    )


def inventory_facts(scan, status, now, *, exposure_buckets=None, bucket_starts=None):
    provenance = scan.intake_provenance
    eligible = status == "In Stock" and (
        (provenance == "unlinked" and scan.intake_id is None and scan.intake_origin_id is None)
        or (provenance == "linked" and scan.intake_id is not None
            and scan.intake_origin_id == scan.intake_id
            and scan.intake is not None and scan.intake.status == "Active")
    )
    classification = scan.classification
    raw = getattr(classification, "spoilage_days", None) if classification else None
    exposure = scan_storage_exposure(
        scan,
        status,
        now,
        exposure_buckets=exposure_buckets,
        bucket_starts=bucket_starts,
    )
    offset_days = exposure.exposure_offset_days if exposure is not None else 0
    remaining = remaining_shelf_life(raw, scan.date_time, now, exposure=exposure)
    return {
        "inventory_eligible": bool(eligible), "remaining_days": remaining, "risk_as_of": now,
        "shelf_life_window": shelf_life_window(
            raw, scan.date_time, now, exposure_offset_days=offset_days,
        ),
        "ripeness_projection": ripeness_projection(
            getattr(classification, "ripeness", None) if classification else None,
            getattr(classification, "cultivar", None) if classification else None,
            raw,
            scan.date_time,
            now,
            temperature=getattr(classification, "temperature", None) if classification else None,
            humidity=getattr(classification, "humidity", None) if classification else None,
            vpd=getattr(classification, "vpd", None) if classification else None,
            treatment=getattr(classification, "treatment", None) if classification else None,
            inventory_status=status,
            exposure_offset_days=offset_days,
        ),
    }
