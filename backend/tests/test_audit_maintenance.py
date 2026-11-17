"""Audit rows for backup, restore, maintenance, power, retention and startup.

Every test uses the isolated SQLite fixture from ``test_time_and_writes``, temporary capture
directories and fake hardware. No live station database, captures, cameras or OS power.
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import bcrypt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import database
from app.core.rate_limiter import MAX_ATTEMPTS, RateLimiter
from app.core.security import create_access_token
from app.core.time import now_manila
from app.models import ActivityLog, SystemConfig, UserAccount
from app.services import audit
from app.services.runtime_operations import StationCoordinator
from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application_fixture

application = application_fixture
PASSWORD = "Admin-password-123"


def rows(engine, action=None):
    with Session(engine) as db:
        query = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
        if action:
            query = query.where(ActivityLog.action == str(action))
        return db.scalars(query).all()


def actions(engine):
    return [row.action for row in rows(engine)]


def set_admin_password(application, password=PASSWORD):
    with Session(application.engine) as db:
        admin = db.get(UserAccount, application.ids.admin)
        admin.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode()
        admin.requires_password_change = False
        db.commit()


@pytest.fixture
def station(application, monkeypatch, tmp_path):
    """The production maintenance router on the isolated fixture, with a private coordinator."""
    from app.api.v1 import maintenance
    from app.services import backup_restore, power_control
    from app.services.backup_restore import MaintenanceService

    local = StationCoordinator()
    for module in (backup_restore, maintenance, power_control, audit):
        monkeypatch.setattr(module, "coordinator", local)
    limiter = RateLimiter()
    monkeypatch.setattr(maintenance, "credential_limiter", limiter)

    def sessions():
        return SessionAdapter(application.engine, application.state)

    monkeypatch.setattr(power_control, "async_session_factory", sessions)
    monkeypatch.setattr(power_control, "boot_identity", lambda: "test-boot")
    dispatch = AsyncMock()
    monkeypatch.setattr(power_control, "_schedule_power_action", dispatch)
    captures = tmp_path / "captures"
    captures.mkdir()
    service = MaintenanceService(application.engine, sessions, captures)
    service.prepare()
    monkeypatch.setattr(maintenance, "get_service", lambda: service)
    set_admin_password(application)
    with Session(application.engine) as db:
        admin = db.get(UserAccount, application.ids.admin)
        token = create_access_token({"sub": str(admin.id), "tv": admin.token_version},
                                    generation="initial")
    app = FastAPI()
    app.include_router(maintenance.router, prefix="/api/v1")
    audit.install(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, headers={"Authorization": f"Bearer {token}"},
                              token=token, service=service, coordinator=local, limiter=limiter,
                              sessions=sessions, dispatch=dispatch, root=tmp_path,
                              engine=application.engine, ids=application.ids)


def assert_no_secrets(station, *extra):
    for row in rows(station.engine):
        text = f"{row.details} {row.ip_address}"
        assert "$2b$" not in text and "$2a$" not in text, row.details
        assert station.token not in text
        assert str(station.root) not in text and "station.zip" not in text, row.details
        assert PASSWORD not in text
        for value in extra:
            assert value not in text, row.details


# ── Backup ────────────────────────────────────────────────────────────────────

def test_backup_created_is_logged_once_and_replay_does_not_duplicate(station):
    operation = str(uuid4())
    first = station.client.post("/api/v1/config/backups", headers=station.headers,
                                json={"operation_id": operation})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "completed"
    replay = station.client.post("/api/v1/config/backups", headers=station.headers,
                                 json={"operation_id": operation})
    assert replay.json() == first.json()
    [row] = rows(station.engine, "backup_created")
    assert row.user_id == station.ids.admin
    assert operation in row.details
    assert "archive contains credential hashes" in row.details
    tables = first.json()["manifest"]["tables"]
    assert f"{sum(tables.values())} rows" in row.details
    assert f"{len(tables)} tables" in row.details
    assert "0 evidence files" in row.details
    assert rows(station.engine, "backup_failed") == []
    assert_no_secrets(station)


def test_backup_failure_is_logged_once_and_replay_does_not_duplicate(station):
    with Session(station.engine) as db:
        db.get(UserAccount, station.ids.admin).password_hash = "not-a-bcrypt-hash"
        db.commit()
    operation = str(uuid4())
    failed = station.client.post("/api/v1/config/backups", headers=station.headers,
                                 json={"operation_id": operation})
    assert failed.status_code == 422, failed.text
    replay = station.client.post("/api/v1/config/backups", headers=station.headers,
                                 json={"operation_id": operation})
    assert replay.status_code == 200 and replay.json()["status"] == "failed"
    [row] = rows(station.engine, "backup_failed")
    assert operation in row.details and row.user_id == station.ids.admin
    assert "no usable active administrator" in row.details
    assert rows(station.engine, "backup_created") == []
    assert_no_secrets(station, "not-a-bcrypt-hash")


def test_backup_download_is_logged_without_secrets(station):
    operation = str(uuid4())
    created = station.client.post("/api/v1/config/backups", headers=station.headers,
                                  json={"operation_id": operation})
    assert created.status_code == 200, created.text
    downloaded = station.client.get(f"/api/v1/config/backups/{operation}",
                                    headers=station.headers)
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"PK")
    [row] = rows(station.engine, "backup_downloaded")
    assert row.user_id == station.ids.admin
    assert operation in row.details
    assert created.json()["manifest"]["created_at"] in row.details
    assert f"{len(downloaded.content)} bytes" in row.details
    assert_no_secrets(station)


def test_backup_download_fails_closed_when_the_audit_row_cannot_be_written(station, monkeypatch):
    operation = str(uuid4())
    assert station.client.post("/api/v1/config/backups", headers=station.headers,
                               json={"operation_id": operation}).status_code == 200

    async def unavailable(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit, "_write", unavailable)
    refused = station.client.get(f"/api/v1/config/backups/{operation}", headers=station.headers)
    assert refused.status_code == 503
    assert not refused.content.startswith(b"PK")


# ── Re-authentication ─────────────────────────────────────────────────────────

def cancel(station, password):
    return station.client.post("/api/v1/config/power/cancel", headers=station.headers,
                               json={"password": password})


def test_failed_reauthentication_is_logged_once_without_access_denied(station):
    response = cancel(station, "Wrong-guess-1")
    assert response.status_code == 403
    assert response.json() == {"detail": "Administrator password is incorrect"}
    [row] = rows(station.engine, "reauth_failed")
    assert row.user_id == station.ids.admin
    assert "Wrong-guess-1" not in row.details
    assert rows(station.engine, "access_denied") == []


def test_reauthentication_is_rate_limited_and_lockout_is_logged(station):
    for attempt in range(1, MAX_ATTEMPTS):
        assert cancel(station, f"Wrong-guess-{attempt}").status_code == 403
    locked = cancel(station, "Wrong-guess-final")
    assert locked.status_code == 429
    assert locked.headers.get("retry-after")
    # While locked, even the correct password is refused and the refusal is logged.
    blocked = cancel(station, PASSWORD)
    assert blocked.status_code == 429
    assert len(rows(station.engine, "reauth_failed")) == MAX_ATTEMPTS
    [lock] = rows(station.engine, "account_locked")
    [block] = rows(station.engine, "login_blocked")
    assert lock.user_id == block.user_id == station.ids.admin
    assert rows(station.engine, "access_denied") == []
    assert_no_secrets(station, "Wrong-guess")


def test_successful_reauthentication_clears_earlier_failures(station):
    for attempt in range(MAX_ATTEMPTS - 1):
        assert cancel(station, f"Wrong-guess-{attempt}").status_code == 403
    # Correct password: authentication succeeds; there is simply no pending power operation.
    assert cancel(station, PASSWORD).status_code == 409
    assert cancel(station, "Wrong-guess-again").status_code == 403


# ── Restore ───────────────────────────────────────────────────────────────────

def create_backup(station):
    operation = str(uuid4())
    created = station.client.post("/api/v1/config/backups", headers=station.headers,
                                  json={"operation_id": operation})
    assert created.status_code == 200, created.text
    archive = station.client.get(f"/api/v1/config/backups/{operation}", headers=station.headers)
    assert archive.status_code == 200
    return archive.content


def test_restore_validation_success_and_failure_are_logged(station):
    archive = create_backup(station)
    checked = station.client.post("/api/v1/config/restores/validate", headers=station.headers,
                                  content=archive)
    assert checked.status_code == 200, checked.text
    preview = checked.json()
    [row] = rows(station.engine, "restore_validated")
    assert preview["validation_id"] in row.details
    assert "version 4" in row.details
    assert preview["manifest"]["created_at"] in row.details
    import hashlib
    assert f"sha256 {hashlib.sha256(archive).hexdigest()[:12]}" in row.details
    assert hashlib.sha256(archive).hexdigest() not in row.details
    assert preview["token"] not in row.details

    rejected = station.client.post("/api/v1/config/restores/validate", headers=station.headers,
                                   content=b"not a zip archive")
    assert rejected.status_code == 422
    [failure] = rows(station.engine, "restore_validation_failed")
    assert "Invalid or unreadable backup archive" in failure.details
    assert failure.user_id == station.ids.admin
    assert_no_secrets(station, preview["token"])


def test_restore_rejected_before_maintenance_is_logged_as_failed(station):
    operation, validation = uuid4(), uuid4()
    with pytest.raises(HTTPException) as error:
        asyncio.run(station.service.restore(operation, validation, "x" * 40, station.ids.admin,
                                            "session", actor_name="Admin User",
                                            client_ip="10.0.0.8"))
    assert error.value.status_code == 422
    [row] = rows(station.engine, "restore_failed")
    assert str(operation) in row.details and "validation is missing" in row.details
    assert row.user_id == station.ids.admin and row.ip_address == "10.0.0.8"
    assert "x" * 40 not in row.details


def finish_journal(station, operation, actor_id, actor_name="Gone Admin"):
    return {
        "id": str(operation), "validation_id": str(uuid4()), "phase": "restore",
        "actor_id": str(actor_id), "actor_name": actor_name, "client_ip": "10.0.0.7",
        "manifest": {"created_at": "2026-11-16T09:30:00+08:00",
                     "tables": {"activity_log": {"count": 1}, "scan": {"count": 4}},
                     "files": {"a/camera.jpg": {}}},
        "rollback_manifest": {"tables": {"activity_log": {"count": 3}, "scan": {"count": 9}},
                              "files": {}},
    }


def test_restore_outcome_is_written_once_and_survives_a_missing_actor(station):
    service, operation, ghost = station.service, uuid4(), uuid4()
    asyncio.run(service.save_result({"id": str(operation), "kind": "restore",
                                     "actor_id": str(ghost), "status": "restoring"}))
    journal = finish_journal(station, operation, ghost)
    station.coordinator.block("recovery-required")
    asyncio.run(service._finish(journal, "completed", "Station data restored; sign in again"))
    assert station.coordinator.state == "ready"
    # Crash re-entry before the journal was marked finished must not write it again.
    from app.services.backup_restore import atomic_json
    atomic_json(service.journal, {**journal, "phase": "data-verified", "status": "completed",
                                  "message": "Station data restored; sign in again"})
    station.coordinator.block("recovery-required")
    asyncio.run(service.recover())
    [row] = rows(station.engine, "restore_completed")
    assert row.user_id is None  # the requesting account is not in the restored data
    assert "Gone Admin" in row.details and str(operation) in row.details
    assert ("audit history replaced (3 pre-restore audit rows kept in rollback archive "
            f"{operation})") in row.details
    assert row.ip_address == "10.0.0.7"
    assert rows(station.engine, "restore_failed") == []


def test_failed_restore_outcome_names_the_existing_actor(station):
    service, operation = station.service, uuid4()
    asyncio.run(service.save_result({"id": str(operation), "kind": "restore",
                                     "actor_id": str(station.ids.admin), "status": "restoring"}))
    journal = finish_journal(station, operation, station.ids.admin, "Admin User")
    station.coordinator.block("recovery-required")
    message = "Restore failed; rollback verified. Sign in again"
    asyncio.run(service._finish(journal, "failed", message))
    [row] = rows(station.engine, "restore_failed")
    assert row.user_id == station.ids.admin
    assert str(operation) in row.details and "rollback verified" in row.details
    assert "'Admin User'" in row.details
    assert rows(station.engine, "restore_completed") == []


# ── Maintenance recovery and camera application ──────────────────────────────

def test_maintenance_recovery_is_logged_and_flushes_deferred_events(station):
    station.coordinator.block("recovery-required")
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "Admin logged in during recovery"))
    response = station.client.post("/api/v1/config/maintenance/recover", headers=station.headers,
                                   json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    assert station.coordinator.state == "ready"
    assert actions(station.engine) == ["login", "maintenance_recovered"]
    [row] = rows(station.engine, "maintenance_recovered")
    assert row.user_id == station.ids.admin and "recovery-required" in row.details
    assert audit.pending_events() == []


def test_camera_application_is_logged_once_with_per_camera_results(station, monkeypatch):
    from app.services import configuration
    apply = AsyncMock()
    monkeypatch.setattr(configuration, "apply_camera_config", apply)
    operation = str(uuid4())
    first = station.client.post("/api/v1/config/maintenance/apply", headers=station.headers,
                                json={"operation_id": operation})
    assert first.status_code == 200, first.text
    second = station.client.post("/api/v1/config/maintenance/apply", headers=station.headers,
                                 json={"operation_id": operation})
    assert second.json() == first.json() and apply.await_count == 1
    [row] = rows(station.engine, "config_applied")
    assert operation in row.details and row.user_id == station.ids.admin
    for camera, device in (("CAM-001", 0), ("CAM-004", 3)):
        assert f"{camera} device {device} offline" in row.details
    assert first.json()["application_status"] in row.details


# ── Power ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("outcome,word", [(503, "failed"), (504, "outcome unknown")])
def test_failed_power_dispatch_is_logged(station, outcome, word):
    from app.services import power_control
    station.dispatch.side_effect = HTTPException(outcome, "Injected OS failure")
    operation = str(uuid4())
    result = asyncio.run(power_control.request_power("restart", operation, station.ids.admin,
                                                     client_ip="10.0.0.4"))
    assert result["status"] in {"failed", "unknown"}
    assert actions(station.engine) == ["system_restart", "power_failed"]
    [row] = rows(station.engine, "power_failed")
    assert operation in row.details and word in row.details
    assert row.user_id == station.ids.admin and row.ip_address == "10.0.0.4"
    asyncio.run(power_control.request_power("restart", operation, station.ids.admin))
    assert len(rows(station.engine, "power_failed")) == 1


def test_power_cancel_is_logged_once(station):
    from app.services import power_control
    operation = str(uuid4())
    asyncio.run(power_control.request_power("shutdown", operation, station.ids.admin))
    assert station.coordinator.state == "power-accepted"
    response = cancel(station, PASSWORD)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert cancel(station, PASSWORD).status_code == 200  # replay
    [row] = rows(station.engine, "power_cancelled")
    assert operation in row.details and "shutdown" in row.details
    assert row.user_id == station.ids.admin
    assert actions(station.engine) == ["system_shutdown", "power_cancelled"]


def test_failed_power_cancel_is_logged(station):
    from app.services import power_control
    operation = str(uuid4())
    asyncio.run(power_control.request_power("restart", operation, station.ids.admin))
    station.dispatch.side_effect = HTTPException(503, "Injected cancel failure")
    with pytest.raises(HTTPException):
        asyncio.run(power_control.cancel_power(actor_id=station.ids.admin, client_ip="10.0.0.5"))
    [row] = rows(station.engine, "power_failed")
    assert operation in row.details and "cancel" in row.details.lower()
    assert row.ip_address == "10.0.0.5"
    assert rows(station.engine, "power_cancelled") == []


def test_power_completion_is_logged_when_a_new_boot_is_verified(station, monkeypatch):
    from app.services import power_control
    operation = str(uuid4())
    asyncio.run(power_control.request_power("restart", operation, station.ids.admin))
    asyncio.run(power_control.reconcile_power())
    assert rows(station.engine, "power_completed") == []
    monkeypatch.setattr(power_control, "boot_identity", lambda: "new-verified-host-boot")
    station.coordinator.resume()
    asyncio.run(power_control.reconcile_power())
    asyncio.run(power_control.reconcile_power())
    [row] = rows(station.engine, "power_completed")
    assert operation in row.details and "restart" in row.details
    assert row.user_id == station.ids.admin


# ── Retention ─────────────────────────────────────────────────────────────────

def retention(application, monkeypatch, tmp_path):
    from app.services import data_retention
    monkeypatch.setattr(data_retention, "async_session_factory",
                        lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(data_retention, "settings",
                        SimpleNamespace(capture_path=tmp_path, max_captures_retention_days=30))
    return data_retention


def old_orphan(tmp_path):
    folder = tmp_path / str(uuid4())
    folder.mkdir()
    image = folder / "camera.jpg"
    image.write_bytes(b"fixture")
    old = (now_manila() - timedelta(days=40)).timestamp()
    os.utime(image, (old, old))
    os.utime(folder, (old, old))
    return folder


def test_retention_is_logged_only_when_directories_are_removed(application, monkeypatch, tmp_path):
    data_retention = retention(application, monkeypatch, tmp_path)
    asyncio.run(data_retention._run_retention_cycle())
    assert rows(application.engine) == []
    folder = old_orphan(tmp_path)
    asyncio.run(data_retention._run_retention_cycle())
    assert not folder.exists()
    [row] = rows(application.engine, "retention_cleanup")
    assert "removed 1 " in row.details and "30 days" in row.details
    assert str(tmp_path) not in row.details and folder.name not in row.details


def test_retention_disabled_writes_no_row(application, monkeypatch, tmp_path):
    data_retention = retention(application, monkeypatch, tmp_path)
    with Session(application.engine) as db:
        db.scalar(select(SystemConfig)).data_retention_enabled = False
        db.commit()
    old_orphan(tmp_path)
    asyncio.run(data_retention._run_retention_cycle())
    assert rows(application.engine) == []


def test_retention_failure_is_logged(application, monkeypatch, tmp_path):
    data_retention = retention(application, monkeypatch, tmp_path)

    def broken(root, *args):
        raise OSError(f"Permission denied: {root}")

    monkeypatch.setattr(data_retention, "remove_expired_orphans", broken)
    with pytest.raises(OSError):
        asyncio.run(data_retention._run_retention_cycle())
    [row] = rows(application.engine, "retention_failed")
    assert str(tmp_path) not in row.details
    assert rows(application.engine, "retention_cleanup") == []


# ── Startup ───────────────────────────────────────────────────────────────────

def test_bootstrap_administrator_creation_is_logged_without_the_password(application, monkeypatch):
    from app.config import Settings
    from app.core import startup
    database.Base.metadata.drop_all(application.engine)
    database.Base.metadata.create_all(application.engine)
    settings = Settings(_env_file=None, bootstrap_admin_password="random-bootstrap-secret")
    monkeypatch.setattr(startup, "get_settings", lambda: settings)

    async def seed():
        async with SessionAdapter(application.engine, application.state) as db:
            await startup._seed_default_data(db)

    asyncio.run(seed())
    asyncio.run(seed())  # users exist: nothing new is created or logged
    [row] = rows(application.engine, "bootstrap_admin_created")
    with Session(application.engine) as db:
        account = db.scalar(select(UserAccount))
    assert f"'{account.username}'" in row.details and str(account.id) in row.details
    assert "random-bootstrap-secret" not in row.details and "$2b$" not in row.details


def test_runtime_start_is_logged_once_with_camera_counts(application, monkeypatch, tmp_path):
    from app.core import startup
    from app.services import configuration
    model = SimpleNamespace(load=lambda: None, warmup=lambda: None, is_loaded=True,
                            _COCO_MODEL="fake")
    monkeypatch.setattr(startup, "banana_pre_detector", model)
    monkeypatch.setattr(startup, "banana_classifier", model)
    monkeypatch.setattr(startup, "spoilage_predictor", model)
    monkeypatch.setattr(startup, "camera_manager",
                        SimpleNamespace(_health={0: True, 1: False}, online_cameras=[0],
                                        _device_ids=[0, 1]))
    monkeypatch.setattr(startup, "sensor_reader", SimpleNamespace(connect=lambda: True))
    monkeypatch.setattr(startup, "_register_cameras", AsyncMock())
    monkeypatch.setattr(startup, "get_service", lambda: SimpleNamespace())
    monkeypatch.setattr(startup, "settings", SimpleNamespace(
        capture_path=tmp_path / "captures", yolo_model_path="fake", rfr_model_path="fake",
        ood_gate_fail_open=False, app_host="127.0.0.1", app_port=8000))
    monkeypatch.setattr(startup, "async_session_factory",
                        lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(configuration, "apply_camera_config", AsyncMock())
    asyncio.run(startup._initialize_runtime())
    [row] = rows(application.engine, "system_started")
    assert "1/2 cameras online" in row.details
    assert row.user_id is None
