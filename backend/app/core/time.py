"""Business timestamps share one zone; existing database instants never move."""

from datetime import date, datetime, time, timedelta, timezone

# Manila is UTC+8 without DST for the system's operational dates. A fixed zone
# also works on Windows without requiring a separate tzdata installation.
MANILA = timezone(timedelta(hours=8), name="Asia/Manila")
TIMEZONE_NAME = "Asia/Manila"


def now_manila() -> datetime:
    return datetime.now(MANILA)


def as_manila(value: datetime) -> datetime:
    """Normalize stored timestamps; legacy zone-less database values are UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MANILA)


def input_manila(value: datetime) -> datetime:
    """A new zone-less business form timestamp denotes Manila local time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=MANILA)
    return value.astimezone(MANILA)


def business_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=MANILA)
    return start, start + timedelta(days=1)
