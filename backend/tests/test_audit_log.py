"""Audit-log foundation: the single writer, text hygiene, failure events and refused access.

All tests use the isolated SQLite fixture from ``test_time_and_writes``; no live station
database, captures or hardware are touched.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenException
from app.models import ActivityLog
from app.schemas.enums import ActiveStatusEnum
from app.services import audit
from app.services.runtime_operations import StationCoordinator
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application_fixture

application = application_fixture
APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def rows(app, action=None):
    with Session(app.engine) as db:
        query = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
        if action:
            query = query.where(ActivityLog.action == str(action))
        return db.scalars(query).all()


def as_operator(app):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, token_version=1, full_name="Original Name",
        role=SimpleNamespace(name="Operator"), status=ActiveStatusEnum.ACTIVE,
    )


# ── Text hygiene ──────────────────────────────────────────────────────────────

def test_clean_strips_control_characters_and_caps_length():
    text = audit.clean("\x1b[31mX\nFAKE ROW  tail‮", limit=40)
    assert "\n" not in text and "\x1b" not in text and " " not in text and "‮" not in text
    assert "FAKE ROW" in text
    long = audit.clean("a" * 500, limit=80)
    assert len(long) == 80 and long.endswith("…")
    assert audit.clean(None) == ""
    assert audit.quoted("  x \t y ") == "'x y'"


def test_describe_changes_formats_old_to_new_and_redacts_private_fields():
    before = {"role": ActiveStatusEnum.ACTIVE, "name": "Old", "same": 1, "avatar_url": "data:abc",
              "password": "hunter2", "empty": None}
    after = {"role": ActiveStatusEnum.INACTIVE, "name": "New", "same": 1, "avatar_url": "data:def",
             "password": "letmein", "empty": "set"}
    text = audit.describe_changes(before, after)
    assert "role Active → Inactive" in text
    assert "name 'Old' → 'New'" in text
    assert "same" not in text
    assert "avatar_url changed" in text and "data:" not in text
    assert "password changed" in text and "hunter2" not in text and "letmein" not in text
    assert "empty none → 'set'" in text
    assert audit.describe_changes({"a": 1}, {"a": 1}) == ""


def test_action_vocabulary_is_snake_case_and_fits_the_column():
    limit = ActivityLog.__table__.c.action.type.length
    for action in audit.AuditAction:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", action.value), action
        assert len(action.value) <= limit, action
    # Existing names stay unchanged so stored history and filters keep working.
    for kept in ("login", "login_failed", "pin_failed", "logout", "user_created", "user_updated",
                 "supplier_created", "supplier_updated", "intake_created", "intake_status_changed",
                 "config_changed", "scan_created", "scan_rejected", "scan_flag", "scan_correction",
                 "scan_status", "scan_note", "scan_provenance", "system_restart", "system_shutdown"):
        assert audit.AuditAction(kept)


def test_activity_rows_are_written_only_through_the_audit_helper():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative in {"services/audit.py"} or relative.startswith("models/"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "ActivityLog(" in line:
                offenders.append(f"{relative}:{number}")
    assert offenders == []


# ── Writers ───────────────────────────────────────────────────────────────────

def test_record_writes_in_the_callers_transaction_and_rejects_unknown_actions(application):
    async def run():
        async with SessionAdapter(application.engine, application.state) as db:
            actor = SimpleNamespace(id=application.ids.admin, full_name="Admin User")
            await audit.record(db, audit.AuditAction.SUPPLIER_UPDATED, "Updated\nsupplier",
                               actor=actor, ip="10.0.0.9")
            with pytest.raises(ValueError):
                await audit.record(db, "made_up_action", "x", actor=actor)
            await db.rollback()  # the row belongs to the caller's transaction
            await audit.record(db, "supplier_updated", "kept", actor=actor, ip="10.0.0.9")
            await db.commit()

    asyncio.run(run())
    [row] = rows(application)
    assert (row.action, row.details, row.user_id, row.ip_address) == (
        "supplier_updated", "kept", application.ids.admin, "10.0.0.9")


def test_emit_commits_independently_and_keeps_the_actor_when_it_exists(application):
    actor = SimpleNamespace(id=application.ids.admin, full_name="Admin User")
    asyncio.run(audit.emit(audit.AuditAction.DATA_EXPORTED, "Exported\r\nlogs", actor=actor,
                           ip="10.0.0.5"))
    [row] = rows(application)
    assert row.action == "data_exported" and row.user_id == application.ids.admin
    assert row.details == "Exported logs" and row.ip_address == "10.0.0.5"


def test_emit_resolves_a_missing_actor_to_null_with_its_name(application):
    ghost = SimpleNamespace(id=uuid4(), full_name="Gone User")
    asyncio.run(audit.emit(audit.AuditAction.ACCESS_DENIED, "denied", actor=ghost))
    [row] = rows(application)
    assert row.user_id is None
    assert "Gone User" in row.details


def test_emit_never_raises_and_logs_when_the_write_fails(application, caplog):
    application.state.fail_commit = True
    with caplog.at_level("ERROR", logger="bananavision.audit"):
        asyncio.run(audit.emit(audit.AuditAction.LOGIN_FAILED, "x"))
    assert rows(application) == []
    assert any("login_failed" in record.getMessage() for record in caplog.records)


def test_emit_required_fails_closed_when_the_station_is_ready(application):
    application.state.fail_commit = True
    with pytest.raises(HTTPException) as error:
        asyncio.run(audit.emit(audit.AuditAction.DATA_EXPORTED, "x", required=True))
    assert error.value.status_code == 503


def test_emit_defers_while_the_station_is_not_ready_then_flushes_in_order(application, monkeypatch):
    station = StationCoordinator()
    monkeypatch.setattr(audit, "coordinator", station)
    station.block("recovery-required")
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "first (recovery mode)"))
    assert rows(application) == []
    assert [event["action"] for event in audit.pending_events()] == ["login"]
    station.resume()
    asyncio.run(audit.emit(audit.AuditAction.MAINTENANCE_RECOVERED, "second"))
    saved = rows(application)
    assert [row.action for row in saved] == ["login", "maintenance_recovered"]
    assert saved[0].timestamp <= saved[1].timestamp
    assert audit.pending_events() == []


def test_every_event_is_mirrored_to_the_audit_file_log(application, caplog):
    with caplog.at_level("INFO", logger="bananavision.audit"):
        asyncio.run(audit.emit(audit.AuditAction.LOGOUT, "User x logged out", ip="10.0.0.1"))
    assert any("action=logout" in r.getMessage() and "10.0.0.1" in r.getMessage()
               for r in caplog.records)


# ── Failure events attached to an HTTP error, and refused access ─────────────

def build_app(application, route):
    """A small app with the audit handler; the real dependencies come from the fixture."""
    app = FastAPI()
    audit.install(app)
    app.add_api_route("/api/v1/probe", route, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


def test_attached_events_are_written_after_the_failed_request_and_response_is_unchanged(application):
    async def route():
        raise audit.attach(HTTPException(429, "Too many attempts", headers={"Retry-After": "5"}),
                           audit.AuditAction.ACCOUNT_LOCKED, "Locked after 5 failures")

    client = build_app(application, route)
    response = client.get("/api/v1/probe")
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts"}
    assert response.headers["retry-after"] == "5"
    [row] = rows(application)
    assert row.action == "account_locked" and row.details == "Locked after 5 failures"
    assert row.ip_address == "testclient" or row.ip_address is None


def test_refused_access_is_logged_once_per_throttle_window(application, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(audit, "_clock", lambda: now[0])
    as_operator(application)
    client = application.client
    for _ in range(3):
        response = client.get("/api/v1/users")
        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}
    [row] = rows(application, "access_denied")
    assert row.user_id == application.ids.operator
    assert row.details == "GET /api/v1/users denied (403): Admin access required"
    now[0] += audit.ACCESS_DENIED_WINDOW + 1
    assert client.get("/api/v1/users").status_code == 403
    second = rows(application, "access_denied")[-1]
    assert second.details.endswith("; 2 similar suppressed")


def test_refused_access_by_a_real_signed_in_user_is_logged(application):
    """No test override: the account is resolved from a real token, as in production."""
    from app.models import UserAccount
    from app.services.auth_service import create_user_token
    from sqlalchemy.orm import selectinload

    with Session(application.engine) as db:
        operator = db.scalar(select(UserAccount).options(selectinload(UserAccount.role))
                             .where(UserAccount.id == application.ids.operator))
        token = create_user_token(operator)
    application.app.dependency_overrides.pop(get_current_user)
    response = application.client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    [row] = rows(application, "access_denied")
    assert row.user_id == application.ids.operator
    assert row.details == "GET /api/v1/users denied (403): Admin access required"


def test_audit_follows_whichever_coordinator_reference_is_replaced(application, monkeypatch):
    from app.services import runtime_operations

    station = StationCoordinator()
    station.block("recovery-required")
    monkeypatch.setattr(runtime_operations, "coordinator", station)
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "recovery sign-in"))
    assert rows(application) == []


def test_failures_before_sign_in_share_a_per_minute_cap(application, monkeypatch, caplog):
    monkeypatch.setattr(audit, "ANONYMOUS_PER_MINUTE", 3)
    monkeypatch.setattr(audit, "_clock", lambda: 5000.0)
    with caplog.at_level("WARNING", logger="bananavision.audit"):
        for _ in range(5):
            asyncio.run(audit.emit(audit.AuditAction.LOGIN_FAILED, "Failed sign-in"))
        asyncio.run(audit.emit(audit.AuditAction.ACCOUNT_LOCKED, "Locked"))  # never capped
    assert [row.action for row in rows(application)] == ["login_failed"] * 3 + ["account_locked"]
    assert sum("anonymous rate cap" in r.getMessage() for r in caplog.records) == 2


def test_unauthenticated_401_is_not_written_to_the_database(application):
    application.app.dependency_overrides.pop(get_current_user)
    response = application.client.get("/api/v1/users")
    assert response.status_code == 401
    assert rows(application) == []


def test_refused_access_never_logs_query_strings(application):
    async def route():
        raise ForbiddenException("Not your scan")

    client = build_app(application, route)
    assert client.get("/api/v1/probe?token=SENTINEL-SECRET").status_code == 403
    [row] = rows(application, "access_denied")
    assert "SENTINEL" not in row.details and "token" not in row.details


def test_an_attached_403_is_not_logged_twice(application):
    async def route():
        raise audit.attach(ForbiddenException("Administrator password is incorrect"),
                           audit.AuditAction.REAUTH_FAILED, "Re-authentication failed")

    client = build_app(application, route)
    assert client.get("/api/v1/probe").status_code == 403
    assert [row.action for row in rows(application)] == ["reauth_failed"]


def test_no_secret_shapes_in_any_written_row(application):
    """Run a few writes and scan every stored row for credential shapes."""
    as_operator(application)
    application.client.get("/api/v1/users")
    for row in rows(application):
        text = f"{row.action} {row.details}"
        assert "$2b$" not in text and "eyJ" not in text and "Bearer" not in text


# ── Review findings (2026-11-17) ──────────────────────────────────────────────

@pytest.mark.parametrize("state", ["recovery-required", "draining", "maintenance"])
def test_required_egress_is_refused_while_the_station_is_not_writable(application, monkeypatch, state):
    station = StationCoordinator()
    station.block(state)
    monkeypatch.setattr(audit, "coordinator", station)
    with pytest.raises(HTTPException) as error:
        asyncio.run(audit.emit(audit.AuditAction.BACKUP_DOWNLOADED, "download", required=True))
    assert error.value.status_code == 503
    assert rows(application) == [] and audit.pending_events() == []


def test_required_egress_is_written_at_once_while_power_is_pending(application, monkeypatch):
    station = StationCoordinator()
    station.block("power-accepted")
    monkeypatch.setattr(audit, "coordinator", station)
    asyncio.run(audit.emit(audit.AuditAction.BACKUP_DOWNLOADED, "download", required=True))
    assert [row.action for row in rows(application)] == ["backup_downloaded"]


def test_the_deferred_backlog_is_written_once_by_overlapping_writers(application, monkeypatch):
    station = StationCoordinator()
    monkeypatch.setattr(audit, "coordinator", station)
    station.block("recovery-required")
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "held while recovering"))
    station.resume()

    async def overlap():
        await asyncio.gather(
            audit.emit(audit.AuditAction.MAINTENANCE_RECOVERED, "recovered"),
            audit.flush_deferred(),
            audit.emit(audit.AuditAction.LOGOUT, "bye"),
        )

    asyncio.run(overlap())
    assert sorted(row.action for row in rows(application)) == ["login", "logout", "maintenance_recovered"]
    assert audit.pending_events() == []


def test_a_failed_write_keeps_the_backlog_and_the_event_queued(application, monkeypatch):
    station = StationCoordinator()
    monkeypatch.setattr(audit, "coordinator", station)
    station.block("recovery-required")
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "held"))
    station.resume()
    application.state.fail_commit = True
    asyncio.run(audit.emit(audit.AuditAction.LOGOUT, "not written yet"))
    assert [event["action"] for event in audit.pending_events()] == ["login", "logout"]
    application.state.fail_commit = False
    asyncio.run(audit.flush_deferred())
    assert [row.action for row in rows(application)] == ["login", "logout"]


def test_a_full_deferred_queue_warns_when_it_drops_the_oldest_event(application, monkeypatch, caplog):
    station = StationCoordinator()
    station.block("recovery-required")
    monkeypatch.setattr(audit, "coordinator", station)
    with caplog.at_level("WARNING", logger="bananavision.audit"):
        for number in range(audit.DEFERRED_LIMIT + 1):
            asyncio.run(audit.emit(audit.AuditAction.LOGIN, f"event {number}"))
    assert len(audit.pending_events()) == audit.DEFERRED_LIMIT
    assert audit.pending_events()[0]["details"] == "event 1"
    assert any("queue is full" in r.getMessage() and "event 0" in r.getMessage()
               for r in caplog.records)


def test_failures_against_real_accounts_are_not_capped(application, monkeypatch):
    monkeypatch.setattr(audit, "ANONYMOUS_PER_MINUTE", 1)
    monkeypatch.setattr(audit, "_clock", lambda: 9000.0)
    for _ in range(3):
        asyncio.run(audit.emit(audit.AuditAction.LOGIN_FAILED, "Sign-in failed for 'admin'",
                               capped=False))
    for _ in range(3):
        asyncio.run(audit.emit(audit.AuditAction.LOGIN_FAILED, "an unrecognized username"))
    assert [row.details for row in rows(application)].count("Sign-in failed for 'admin'") == 3
    assert [row.details for row in rows(application)].count("an unrecognized username") == 1


def test_the_file_log_shows_a_recorded_change_only_after_it_commits(application, caplog):
    actor = SimpleNamespace(id=application.ids.admin, full_name="Admin User")

    async def run():
        async with SessionAdapter(application.engine, application.state) as db:
            await audit.record(db, audit.AuditAction.SUPPLIER_UPDATED, "rolled back", actor=actor)
            await db.rollback()
            await audit.record(db, audit.AuditAction.SUPPLIER_UPDATED, "committed", actor=actor)
            await db.commit()

    with caplog.at_level("INFO", logger="bananavision.audit"):
        asyncio.run(run())
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "committed" in messages and "rolled back" not in messages


def test_actor_name_snapshot_is_recorded_and_immutable(application):
    from app.models import UserAccount
    actor = SimpleNamespace(id=application.ids.admin, full_name="Original Name")

    async def run():
        async with SessionAdapter(application.engine, application.state) as db:
            await audit.record(db, audit.AuditAction.USER_UPDATED, "Profile change", actor=actor)
            await db.commit()

    asyncio.run(run())
    [row] = rows(application, audit.AuditAction.USER_UPDATED)
    assert row.actor_name == "Original Name"
    assert row.user_id == application.ids.admin

    # Renaming the user account does not alter the historical audit snapshot.
    with Session(application.engine) as db:
        user = db.get(UserAccount, application.ids.admin)
        user.full_name = "Renamed User"
        db.commit()

    [row] = rows(application, audit.AuditAction.USER_UPDATED)
    assert row.actor_name == "Original Name"


def test_actor_name_snapshot_is_preserved_when_account_missing(application):
    missing_id = uuid4()
    asyncio.run(audit.emit(audit.AuditAction.LOGIN, "Direct emit", actor_id=missing_id,
                           actor_name="Historical Ghost"))
    [row] = rows(application, audit.AuditAction.LOGIN)
    assert row.actor_name == "Historical Ghost"
