"""Initialize new tables and apply recorded upgrades before any ORM account read.

Run from backend/: python -m app.core.migrations
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

import app.models  # noqa: F401 -- register every table before create_all
from app.core.database import Base, engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def upgrade_connection(connection):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def initialize_schema(database_engine):
    async with database_engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Concurrent application starts share one DDL transaction at a time.
            await connection.execute(text("SELECT pg_advisory_xact_lock(786124903)"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(upgrade_connection)


async def main():
    try:
        await initialize_schema(engine)
        print("Database schema upgraded to the current revision.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
