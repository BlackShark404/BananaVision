"""Timezone-aware timestamp columns with consistent Python representations."""

from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

from app.core.time import as_manila


class ManilaDateTime(TypeDecorator):
    """Keep PostgreSQL TIMESTAMPTZ storage, returning the same instant in +08:00.

    asyncpg normally decodes timestamptz in UTC regardless of the session zone.
    SQLite tests store UTC because SQLite drops offsets, matching legacy data.
    This type changes representation only; no schema/data migration is needed.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = as_manila(value)
        return value.astimezone(timezone.utc) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        return None if value is None else as_manila(value)
