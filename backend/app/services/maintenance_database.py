"""PostgreSQL station ownership and transaction-level maintenance coordination."""
from contextlib import asynccontextmanager
import asyncio

import anyio
from fastapi import HTTPException
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.services.runtime_operations import coordinator, finish_on_disconnect, maintenance_context

STATION_OWNER_KEY = 786124904
MAINTENANCE_KEY = 786124905
_owner_connection = None
_owner_mutex = asyncio.Lock()
_owner_lost = False


@event.listens_for(Session, "after_begin")
def protect_transaction(session, transaction, connection):
    if connection.dialect.name == "postgresql" and not maintenance_context.get():
        connection.execute(text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": MAINTENANCE_KEY})


async def acquire_station_owner(engine):
    global _owner_connection, _owner_lost
    if engine.dialect.name != "postgresql":
        return
    async with _owner_mutex:
        connection = await engine.connect()
        try:
            owned = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": STATION_OWNER_KEY},
            )
            await connection.commit()
            if not owned:
                raise RuntimeError(
                    "Another backend owns this station; run exactly one hardware-owning worker",
                )
            _owner_connection = connection
            _owner_lost = False
            coordinator.owner_check = verify_station_owner
        except BaseException:
            await connection.close()
            raise


async def verify_station_owner():
    # The persistent session holds the station lock. A canceled HTTP caller must not
    # cancel its query/commit, release the mutex early, or invalidate that session.
    # AnyIO's level cancellation also needs a shield to avoid repeated cancellation.
    with anyio.CancelScope(shield=True):
        await finish_on_disconnect(_verify_station_owner())
    await anyio.lowlevel.checkpoint_if_cancelled()


async def _verify_station_owner():
    global _owner_lost
    async with _owner_mutex:
        connection = _owner_connection
        if connection is None:
            return
        try:
            if _owner_lost or connection.invalidated or connection.closed:
                raise RuntimeError("Station ownership connection was lost")
            await connection.execute(text("SELECT 1"))
            await connection.commit()
        except Exception as exc:
            # Never reconnect/reuse a replacement session: it would not hold our lock.
            _owner_lost = True
            coordinator.block("recovery-required")
            raise HTTPException(
                503, "Station database ownership was lost. Restart the backend before retrying.",
                headers={"Retry-After": "5"},
            ) from exc


async def release_station_owner():
    with anyio.CancelScope(shield=True):
        await finish_on_disconnect(_release_station_owner())
    await anyio.lowlevel.checkpoint_if_cancelled()


async def _release_station_owner():
    global _owner_connection, _owner_lost
    async with _owner_mutex:
        connection, _owner_connection = _owner_connection, None
        coordinator.owner_check = None
        if connection is not None:
            try:
                if not _owner_lost and not connection.invalidated and not connection.closed:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": STATION_OWNER_KEY},
                    )
                    await connection.commit()
                elif not connection.closed:
                    await connection.invalidate()
            except BaseException:
                # Closing/pooling a live session alone does not release its session lock.
                await connection.invalidate()
                raise
            finally:
                await connection.close()
                _owner_lost = False


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
