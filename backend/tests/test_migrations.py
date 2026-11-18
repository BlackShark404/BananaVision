"""Upgrade old and already-current schemas without losing accounts or scan data."""
import os
import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import database
from app.core.migrations import BACKEND_ROOT, initialize_schema, upgrade_connection
from tests.test_time_and_writes import sqlite_jsonb  # noqa: F401 -- SQLite JSONB compiler


def legacy_schema(connection):
    # Real station account IDs are UUIDs; dependent FKs must validate on PostgreSQL.
    connection.execute(text(
        "CREATE TABLE user_account (id UUID PRIMARY KEY, "
        "username VARCHAR(50), password_hash VARCHAR(255))"
    ))
    connection.execute(text(
        "INSERT INTO user_account VALUES "
        "('00000000-0000-0000-0000-000000000001', 'existing-owner', 'unchanged-secret-hash')"
    ))
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
    assert (
        connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        == "0013_confidence_threshold_default"
    )


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
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0013_confidence_threshold_default"
            )
    finally:
        engine.dispose()


def test_notification_read_receipt_migration_replaces_shared_flag():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE user_account ("
                "id CHAR(36) PRIMARY KEY, status VARCHAR(20) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE app_notification ("
                "id CHAR(36) PRIMARY KEY, type VARCHAR(30) NOT NULL, "
                "title VARCHAR(200) NOT NULL, message TEXT NOT NULL, "
                "timestamp DATETIME NOT NULL, is_read BOOLEAN NOT NULL, "
                "href VARCHAR(200), user_id CHAR(36))"
            ))
            connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO alembic_version VALUES ('0009_camera_slots')"
            ))
            connection.execute(text(
                "INSERT INTO user_account VALUES "
                "('00000000-0000-0000-0000-000000000001', 'ACTIVE'), "
                "('00000000-0000-0000-0000-000000000002', 'ACTIVE'), "
                "('00000000-0000-0000-0000-000000000003', 'INACTIVE')"
            ))
            connection.execute(text(
                "INSERT INTO app_notification "
                "(id, type, title, message, timestamp, is_read, href, user_id) VALUES "
                "('00000000-0000-0000-0000-000000000010', 'scan', 'Private', "
                "'Private read', '2025-01-01 00:00:00', 1, NULL, "
                "'00000000-0000-0000-0000-000000000001'), "
                "('00000000-0000-0000-0000-000000000011', 'scan', 'Broadcast', "
                "'Broadcast read', '2025-01-01 00:00:00', 1, NULL, NULL), "
                "('00000000-0000-0000-0000-000000000012', 'scan', 'Broadcast', "
                "'Broadcast unread', '2025-01-01 00:00:00', 0, NULL, NULL)"
            ))

            upgrade_connection(connection)

            assert (
                connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == "0013_confidence_threshold_default"
            assert "is_read" not in {
                column["name"]
                for column in inspect(connection).get_columns("app_notification")
            }
            assert connection.execute(text(
                "SELECT notification_id, user_id FROM app_notification_read "
                "ORDER BY notification_id, user_id"
            )).all() == [
                ("00000000000000000000000000000010",
                 "00000000000000000000000000000001"),
                ("00000000000000000000000000000011",
                 "00000000000000000000000000000001"),
                ("00000000000000000000000000000011",
                 "00000000000000000000000000000002"),
            ]
            assert connection.execute(text(
                "SELECT COUNT(*) FROM app_notification_read WHERE read_at IS NULL"
            )).scalar_one() == 0
    finally:
        engine.dispose()


def test_scan_history_upgrade_preserves_old_rows():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        legacy_schema(connection)
        connection.execute(
            text(
                "CREATE TABLE scan (id CHAR(32) PRIMARY KEY, "
                "date_time DATETIME, source_text VARCHAR(100))"
            )
        )
        connection.execute(
            text("INSERT INTO scan VALUES ('abc', '2025-01-02 00:30:00', 'Original source')")
        )
        upgrade_connection(connection)
        row = connection.execute(
            text(
                "SELECT revision, operator_name_snapshot, source_name_snapshot, "
                "date_time, source_text FROM scan"
            )
        ).one()
        assert tuple(row) == (1, None, None, '2025-01-02 00:30:00', 'Original source')
        assert {"scan_event", "scan_mutation", "scan_tombstone"} <= set(
            inspect(connection).get_table_names()
        )
        assert connection.execute(text('SELECT COUNT(*) FROM scan_event')).scalar_one() == 0
    engine.dispose()


def test_provenance_migration_quarantines_legacy_null_without_changing_stock():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        legacy_schema(connection)
        connection.execute(text("CREATE TABLE scan (id CHAR(32) PRIMARY KEY, intake_id CHAR(32))"))
        connection.execute(
            text("INSERT INTO scan VALUES ('linked', 'known-intake'), ('ambiguous', NULL)")
        )
        upgrade_connection(connection)
        assert connection.execute(
            text("SELECT id, intake_origin_id, intake_provenance FROM scan ORDER BY id")
        ).all() == [("ambiguous", None, "unverified"), ("linked", "known-intake", "linked")]
        connection.execute(
            text("UPDATE scan SET intake_provenance='unlinked' WHERE id='ambiguous'")
        )
        upgrade_connection(connection)
        assert (
            connection.execute(
                text("SELECT intake_provenance FROM scan WHERE id='ambiguous'")
            ).scalar_one()
            == "unlinked"
        )
        assert connection.execute(text('SELECT COUNT(*) FROM scan_event')).scalar_one() == 0
    engine.dispose()


def test_camera_slots_migration_normalizes_saved_arrays_and_counters():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE user_account (id UUID PRIMARY KEY, "
                "username VARCHAR(50), password_hash VARCHAR(255))"
            ))
            connection.execute(text("CREATE TABLE delivery_intake (id INTEGER PRIMARY KEY, source VARCHAR(100))"))
            connection.execute(text("CREATE TABLE scan_classification (id INTEGER PRIMARY KEY, confidence NUMERIC(5,2))"))
            connection.execute(text(
                "CREATE TABLE system_config (id INTEGER PRIMARY KEY, "
                "camera_ids VARCHAR(255), camera_device_ids JSON, canonical_key INTEGER, "
                "revision INTEGER NOT NULL DEFAULT 1, legacy_conflict BOOLEAN NOT NULL DEFAULT 0, "
                "confidence_threshold INTEGER NOT NULL DEFAULT 85, "
                "data_retention_enabled BOOLEAN NOT NULL DEFAULT 1, updated_at DATETIME, "
                "updated_by_admin UUID)"
            ))
            connection.execute(text(
                "CREATE TABLE device (id CHAR(32) PRIMARY KEY, camera_id VARCHAR(50) UNIQUE NOT NULL, "
                "label VARCHAR(100) NOT NULL, status VARCHAR(20) NOT NULL, resolution VARCHAR(20), "
                "last_seen DATETIME, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE operator_profile (id UUID PRIMARY KEY, account_id UUID, "
                "pin_hash VARCHAR(255), requires_pin_change BOOLEAN, pin_setup_reason VARCHAR(50), "
                "total_scans INTEGER NOT NULL DEFAULT 0, flagged_scans INTEGER NOT NULL DEFAULT 0, "
                "created_at DATETIME, updated_at DATETIME)"
            ))
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0008_windows_label_jobs")
            device_id, profile_id = uuid4(), uuid4()
            connection.execute(text(
                "INSERT INTO device VALUES (:id, 'CAM-001', 'Left scanner', 'Online', '640x480', "
                "NULL, '2025-01-01 00:00:00', '2025-01-01 00:00:00')"
            ), {"id": str(device_id)})
            connection.execute(text(
                "INSERT INTO system_config (id, camera_ids, camera_device_ids, canonical_key, "
                "confidence_threshold, data_retention_enabled, updated_at) VALUES "
                "(1, 'CAM-002, CAM-001', '[3, 1]', 1, 75, 1, '2025-01-02 00:00:00')"
            ))
            connection.execute(text(
                "INSERT INTO operator_profile (id, total_scans, flagged_scans, created_at, updated_at) "
                "VALUES (:id, 12, 3, '2025-01-01 00:00:00', '2025-01-01 00:00:00')"
            ), {"id": str(profile_id)})
            upgrade_connection(connection)

            config_columns = {c["name"] for c in inspect(connection).get_columns("system_config")}
            operator_columns = {c["name"] for c in inspect(connection).get_columns("operator_profile")}
            assert "camera_ids" not in config_columns and "camera_device_ids" not in config_columns
            assert "total_scans" not in operator_columns and "flagged_scans" not in operator_columns
            rows = connection.execute(text(
                "SELECT camera_id, slot_index, device_index, label, status FROM device "
                "ORDER BY slot_index"
            )).all()
            assert rows == [("CAM-002", 0, 3, "Scanner 1", "Offline"),
                            ("CAM-001", 1, 1, "Left scanner", "Online")]
            indexes = {index["name"]: index for index in inspect(connection).get_indexes("device")}
            assert indexes["ix_device_camera_id"]["unique"]
            assert indexes["uq_device_slot_index"]["unique"]
            assert indexes["uq_device_device_index"]["unique"]
            checks = {
                check["name"] for check in inspect(connection).get_check_constraints("device")
            }
            assert {"ck_device_slot_index_range",
                    "ck_device_device_index_nonnegative"} <= checks
            assert connection.execute(text(
                "SELECT confidence_threshold FROM system_config"
            )).scalar_one() == 75
            assert connection.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar_one() == "0013_confidence_threshold_default"
            with pytest.raises(IntegrityError):
                connection.execute(text(
                    "INSERT INTO device (id, camera_id, label, status, created_at, updated_at) "
                    "VALUES ('duplicate', 'CAM-001', 'Duplicate', 'Offline', "
                    "'2025-01-01 00:00:00', '2025-01-01 00:00:00')"
                ))
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
                # PostgreSQL enforces the new history FK; the old fixture omitted
                # this base table even though every real station already has it.
                await connection.execute(text('CREATE TABLE scan (id UUID PRIMARY KEY)'))
                await connection.run_sync(upgrade_connection)
                await connection.run_sync(assert_upgraded)
        else:
            await asyncio.gather(initialize_schema(engine), initialize_schema(engine))
            await initialize_schema(engine)
            async with engine.begin() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == "0013_confidence_threshold_default"
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_connection)
            if legacy:
                await connection.run_sync(assert_upgraded)
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


def test_audit_integrity_migration_adds_column_and_preserves_rows():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE user_account (id CHAR(36) PRIMARY KEY, "
                "username VARCHAR(50), full_name VARCHAR(100), password_hash VARCHAR(255))"
            ))
            connection.execute(text(
                "CREATE TABLE activity_log (id CHAR(36) PRIMARY KEY, "
                "user_id CHAR(36), action VARCHAR(50) NOT NULL, details TEXT, "
                "ip_address VARCHAR(45), timestamp DATETIME NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO alembic_version VALUES ('0011_device_scan_links')"
            ))
            connection.execute(text(
                "INSERT INTO user_account VALUES "
                "('00000000-0000-0000-0000-000000000001', 'admin', 'Admin User', 'hash')"
            ))
            connection.execute(text(
                "INSERT INTO activity_log VALUES "
                "('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', "
                "'login', 'Original login', '127.0.0.1', '2025-01-01 00:00:00')"
            ))

            upgrade_connection(connection)

            assert (
                connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == "0013_confidence_threshold_default"
            assert "actor_name" in {
                column["name"]
                for column in inspect(connection).get_columns("activity_log")
            }
            row = connection.execute(text(
                "SELECT id, action, details FROM activity_log"
            )).one()
            assert row[1] == "login" and row[2] == "Original login"
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"),
    reason="Optional isolated PostgreSQL instance",
)
async def test_postgresql_audit_integrity_trigger_and_backfill():
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = f"qa_audit_trigger_{uuid4().hex}"
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "CREATE TABLE user_account (id UUID PRIMARY KEY, "
                "username VARCHAR(50) NOT NULL, full_name VARCHAR(100) NOT NULL, "
                "password_hash VARCHAR(255) NOT NULL)"
            ))
            await connection.execute(text(
                "CREATE TABLE activity_log (id UUID PRIMARY KEY, "
                "user_id UUID REFERENCES user_account(id) ON DELETE SET NULL, "
                "action VARCHAR(50) NOT NULL, details TEXT, ip_address VARCHAR(45), "
                "timestamp TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            await connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            ))
            await connection.execute(text(
                "INSERT INTO alembic_version VALUES ('0011_device_scan_links')"
            ))
            user_id = str(uuid4())
            log_id = str(uuid4())
            await connection.execute(text(
                f"INSERT INTO user_account VALUES ('{user_id}', 'admin', 'Original Admin', 'hash')"
            ))
            await connection.execute(text(
                f"INSERT INTO activity_log (id, user_id, action, details) "
                f"VALUES ('{log_id}', '{user_id}', 'login', 'Historical action')"
            ))

            await connection.run_sync(upgrade_connection)

            row = (await connection.execute(text(
                f"SELECT actor_name FROM activity_log WHERE id = '{log_id}'"
            ))).one()
            assert row[0] == "Original Admin"

            # 2. Verify append-only trigger prevents UPDATE
            with pytest.raises(Exception) as exc_info:
                async with connection.begin_nested():
                    await connection.execute(text(
                        f"UPDATE activity_log SET details = 'tampered' WHERE id = '{log_id}'"
                    ))
            assert "activity_log is append-only" in str(exc_info.value)

            # 3. Verify append-only trigger prevents DELETE
            with pytest.raises(Exception) as exc_info:
                async with connection.begin_nested():
                    await connection.execute(text(
                        f"DELETE FROM activity_log WHERE id = '{log_id}'"
                    ))
            assert "activity_log is append-only" in str(exc_info.value)

            # 4. Verify append-only trigger prevents TRUNCATE
            with pytest.raises(Exception) as exc_info:
                async with connection.begin_nested():
                    await connection.execute(text("TRUNCATE activity_log"))
            assert "activity_log is append-only" in str(exc_info.value)

            new_log_id = str(uuid4())
            await connection.execute(text(
                "INSERT INTO activity_log (id, user_id, action, details, actor_name) "
                f"VALUES ('{new_log_id}', '{user_id}', 'logout', 'Legitimate insert', "
                "'Original Admin')"
            ))

            await connection.execute(text("SET LOCAL bananavision.audit_restore = 'on'"))
            await connection.execute(text(
                f"UPDATE activity_log SET details = 'restored' WHERE id = '{new_log_id}'"
            ))
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


def test_confidence_threshold_default_migration_updates_85_to_80():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE system_config (id INTEGER PRIMARY KEY, "
                "confidence_threshold INTEGER NOT NULL, data_retention_enabled BOOLEAN NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO alembic_version VALUES ('0012_audit_integrity')"
            ))
            connection.execute(text(
                "INSERT INTO system_config VALUES (1, 85, 1)"
            ))
            connection.execute(text(
                "INSERT INTO system_config VALUES (2, 70, 1)"
            ))
            upgrade_connection(connection)
            rows = dict(connection.execute(text("SELECT id, confidence_threshold FROM system_config")).fetchall())
            assert rows[1] == 80
            assert rows[2] == 70
    finally:
        engine.dispose()

