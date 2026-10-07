"""Upgrade old and already-current schemas without losing accounts or scan data."""
import os
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import database
from app.core.migrations import initialize_schema, upgrade_connection
from tests.test_time_and_writes import sqlite_jsonb  # noqa: F401 -- SQLite JSONB compiler


def legacy_schema(connection):
    connection.execute(text("CREATE TABLE user_account (id INTEGER PRIMARY KEY, username VARCHAR(50), password_hash VARCHAR(255))"))
    connection.execute(text("INSERT INTO user_account VALUES (1, 'existing-owner', 'unchanged-secret-hash')"))
    connection.execute(text("CREATE TABLE delivery_intake (id INTEGER PRIMARY KEY, source VARCHAR(100))"))
    connection.execute(text("INSERT INTO delivery_intake VALUES (1, 'Existing source')"))
    connection.execute(text("CREATE TABLE scan_classification (id INTEGER PRIMARY KEY, confidence NUMERIC(5,2))"))
    connection.execute(text("INSERT INTO scan_classification VALUES (1, 92.5)"))


def assert_upgraded(connection):
    row = connection.execute(text("SELECT username, password_hash, token_version FROM user_account")).one()
    assert tuple(row) == ("existing-owner", "unchanged-secret-hash", 1)
    assert connection.execute(text("SELECT treatment FROM delivery_intake")).scalar_one() == "Natural"
    assert float(connection.execute(text("SELECT confidence FROM scan_classification")).scalar_one()) == 92.5
    assert {"dew_point", "vpd", "heat_index", "treatment"} <= {
        column["name"] for column in inspect(connection).get_columns("scan_classification")
    }
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004_maintenance_state"


def test_legacy_upgrade_preserves_data_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with engine.begin() as connection:
            legacy_schema(connection)
            upgrade_connection(connection)
            assert_upgraded(connection)
            upgrade_connection(connection)
            assert_upgraded(connection)
    finally:
        engine.dispose()


def test_current_schema_adopts_revision_without_duplicate_columns():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            database.Base.metadata.create_all(connection)
            before = {table: [column["name"] for column in inspect(connection).get_columns(table)]
                      for table in database.Base.metadata.tables}
            upgrade_connection(connection)
            upgrade_connection(connection)
            for table, columns in before.items():
                assert [column["name"] for column in inspect(connection).get_columns(table)] == columns
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004_maintenance_state"
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Optional isolated PostgreSQL instance")
@pytest.mark.parametrize("legacy", [False, True])
async def test_postgresql_schema_startup_upgrade(legacy):
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = f"qa_migrations_{uuid4().hex}"
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        if legacy:
            async with engine.begin() as connection:
                await connection.run_sync(legacy_schema)
                await connection.run_sync(upgrade_connection)
                await connection.run_sync(assert_upgraded)
        else:
            await asyncio.gather(initialize_schema(engine), initialize_schema(engine))
            await initialize_schema(engine)
            async with engine.begin() as connection:
                assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0004_maintenance_state"
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_connection)
            if legacy:
                await connection.run_sync(assert_upgraded)
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()
