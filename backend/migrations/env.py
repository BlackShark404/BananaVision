"""Online migrations, sharing the startup transaction when provided."""
import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.config import get_settings
from app.core.database import Base

config = context.config


def run_on_connection(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                await connection.execute(text("SELECT pg_advisory_xact_lock(786124903)"))
            await connection.run_sync(run_on_connection)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("These upgrades inspect existing columns and require an online connection")
elif config.attributes.get("connection") is not None:
    run_on_connection(config.attributes["connection"])
else:
    asyncio.run(run_online())
