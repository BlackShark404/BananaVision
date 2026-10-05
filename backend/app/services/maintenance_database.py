"""PostgreSQL station ownership and transaction-level maintenance coordination."""
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.services.runtime_operations import coordinator, maintenance_context

STATION_OWNER_KEY = 786124904
MAINTENANCE_KEY = 786124905
_owner_connection = None


@event.listens_for(Session, "after_begin")
def protect_transaction(session, transaction, connection):
    if connection.dialect.name == "postgresql" and not maintenance_context.get():
        connection.execute(text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": MAINTENANCE_KEY})


async def acquire_station_owner(engine):
    global _owner_connection
    if engine.dialect.name != "postgresql":
        return
    connection = await engine.connect()
    try:
        owned = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": STATION_OWNER_KEY})
        await connection.commit()
        if not owned:
            raise RuntimeError("Another backend owns this station; run exactly one hardware-owning worker")
        _owner_connection = connection
        coordinator.owner_check = verify_station_owner
    except BaseException:
        await connection.close()
        raise


async def verify_station_owner():
    if _owner_connection is None:
        return
    try:
        if _owner_connection.invalidated or _owner_connection.closed:
            raise RuntimeError("Station ownership connection was lost")
        await _owner_connection.execute(text("SELECT 1"))
        await _owner_connection.commit()
    except Exception:
        coordinator.block("recovery-required")
        raise


async def release_station_owner():
    global _owner_connection
    connection, _owner_connection = _owner_connection, None
    coordinator.owner_check = None
    if connection is not None:
        try:
            if not connection.invalidated:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": STATION_OWNER_KEY})
                await connection.commit()
        finally:
            await connection.close()


@asynccontextmanager
async def database_barrier(engine):
    if engine.dialect.name != "postgresql":
        yield
        return
    async with engine.connect() as connection:
        locked = False
        try:
            await connection.execute(text("SELECT set_config('lock_timeout', '120s', true)"))
            await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MAINTENANCE_KEY})
            locked = True
            await connection.commit()
            yield
        finally:
            if locked and not connection.invalidated:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MAINTENANCE_KEY})
                await connection.commit()
