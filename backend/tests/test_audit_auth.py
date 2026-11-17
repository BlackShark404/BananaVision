"""Audit rows for sign-in, kiosk PIN, credential changes, setup tokens and logout.

The real authentication router runs against the isolated SQLite fixture from
``test_time_and_writes`` with the production audit handler installed. Rate limiters and the
blocked-attempt throttle are replaced per test; no live station database is touched.
"""

from __future__ import annotations

import asyncio
import os
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import auth
from app.core.rate_limiter import RateLimiter
from app.core.security import create_access_token, hash_password, hash_pin, verify_password
from app.models import ActivityLog, OperatorProfile, UserAccount
from app.schemas.enums import ActiveStatusEnum
from app.services import audit, runtime_operations
from app.services.runtime_operations import StationCoordinator
from tests.test_time_and_writes import application  # noqa: F401

ADMIN_PASSWORD = "Admin-Secret-Pass-1"
OPERATOR_PASSWORD = "Operator-Secret-Pass-2"
NEW_PASSWORD = "Replacement-Secret-3"
PIN = "8642"
NEW_PIN = "1593"
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def station(application, monkeypatch):  # noqa: F811 - imported pytest fixture
    ids = application.ids
    with Session(application.engine) as db:
        db.get(UserAccount, ids.admin).password_hash = hash_password(ADMIN_PASSWORD)
        db.get(UserAccount, ids.operator).password_hash = hash_password(OPERATOR_PASSWORD)
        profile = db.get(OperatorProfile, ids.profile)
        profile.pin_hash = hash_pin(PIN)
        profile.requires_pin_change = False
        db.commit()
    for name in ("login_limiter", "pin_limiter", "credential_limiter"):
        monkeypatch.setattr(auth, name, RateLimiter(), raising=False)
    now = [1000.0]
    monkeypatch.setattr(auth, "_clock", lambda: now[0], raising=False)
    monkeypatch.setattr(auth, "_blocked_seen", {}, raising=False)
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")
    audit.install(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, engine=application.engine, ids=ids, now=now,
                              secrets={ADMIN_PASSWORD, OPERATOR_PASSWORD, NEW_PASSWORD})


def rows(station, action=None):
    with Session(station.engine) as db:
        query = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
        if action:
            query = query.where(ActivityLog.action == action)
        return db.scalars(query).all()


def update_account(station, account_id, **values):
    with Session(station.engine) as db:
        account = db.get(UserAccount, account_id)
        for key, value in values.items():
            setattr(account, key, value)
        db.commit()


def update_profile(station, **values):
    with Session(station.engine) as db:
        profile = db.get(OperatorProfile, station.ids.profile)
        for key, value in values.items():
            setattr(profile, key, value)
        db.commit()


def login(station, username, password):
    station.secrets.add(password)
    return station.client.post("/api/v1/auth/login",
                               json={"username": username, "password": password})


def swap(station, username, pin):
    return station.client.post("/api/v1/auth/swap", json={"username": username, "pin": pin})


def bearer(station, account_id, version=1):
    token = create_access_token({"sub": str(account_id), "tv": version})
    station.secrets.add(token)
    return {"Authorization": f"Bearer {token}"}


def assert_no_secrets(station):
    for row in rows(station):
        text = f"{row.action} {row.details}"
        for secret in station.secrets:
            assert secret not in text, (secret, text)
        without_ids = UUID_PATTERN.sub("", text)
        for pin in (PIN, NEW_PIN, "0000", "9999"):
            assert pin not in without_ids, text
        assert "$2b$" not in text and "eyJ" not in text and "Bearer" not in text


# ── Password sign-in ──────────────────────────────────────────────────────────

def test_the_attempt_that_locks_an_account_survives_the_429_and_the_lock_is_logged(station):
    for attempt in range(4):
        response = login(station, "admin", f"Wrong-Guess-{attempt}")
        assert response.status_code == 200 and response.json()["status"] == "failed"
    locked = login(station, "admin", "Wrong-Guess-4")
    assert locked.status_code == 429
    assert locked.json() == {
        "detail": "Too many failed login attempts. Account locked for 300 seconds."}

    failed = rows(station, "login_failed")
    assert len(failed) == 5
    admin = f"account 'admin' (id {station.ids.admin})"
    assert all(admin in row.details and row.user_id is None for row in failed)
    assert failed[0].details == f"Sign-in failed for {admin}: incorrect password; 4 attempts left"
    assert sum(row.details.endswith("; sign-in locked") for row in failed) == 1
    [locked_row] = rows(station, "account_locked")
    assert locked_row.details == (
        f"Account 'admin' (id {station.ids.admin}) sign-in locked for 300 s "
        "after 5 failed sign-in attempts")
    assert_no_secrets(station)


def test_refused_attempts_while_locked_write_one_row_per_window(station):
    for attempt in range(5):
        login(station, "admin", f"Wrong-Guess-{attempt}")
    for _ in range(3):
        refused = login(station, "admin", ADMIN_PASSWORD)
        assert refused.status_code == 429
        assert refused.json()["detail"].startswith("Too many failed login attempts. Try again in")
    [blocked] = rows(station, "login_blocked")
    assert blocked.details.startswith(
        f"Sign-in refused for account 'admin' (id {station.ids.admin}): locked for another ")
    assert "suppressed" not in blocked.details

    station.now[0] += 61
    assert login(station, "admin", ADMIN_PASSWORD).status_code == 429
    blocked_rows = rows(station, "login_blocked")
    assert len(blocked_rows) == 2
    assert sum(row.details.endswith("; 2 similar suppressed") for row in blocked_rows) == 1
    assert not rows(station, "login")
    assert_no_secrets(station)


def test_an_unrecognized_username_is_never_written(station):
    typed = "Pa55word-typed-as-username"
    for attempt in range(5):
        login(station, typed, f"Wrong-Guess-{attempt}")
    assert login(station, typed, "Wrong-Guess-5").status_code == 429
    assert swap(station, typed, "0000").json()["status"] == "failed"

    saved = rows(station)
    assert {row.action for row in saved} == {
        "login_failed", "account_locked", "login_blocked", "pin_failed"}
    assert all(typed not in row.details and "Pa55word" not in row.details for row in saved)
    assert all("an unrecognized username" in row.details for row in saved)
    [locked] = rows(station, "account_locked")
    assert locked.details == (
        "Sign-in for an unrecognized username locked for 300 s after 5 failed sign-in attempts")
    assert_no_secrets(station)


def test_inactive_and_temporary_credential_sign_ins_are_logged(station):
    update_account(station, station.ids.operator, status=ActiveStatusEnum.INACTIVE)
    inactive = login(station, "operator", OPERATOR_PASSWORD)
    assert inactive.status_code == 200
    assert inactive.json() == {"status": "inactive", "token": None, "user": None,
                               "reason": "Account is inactive", "setup_token": None}
    [denied] = rows(station, "login_denied")
    assert denied.details == (
        f"Sign-in denied for account 'operator' (id {station.ids.operator}): account is inactive")

    update_account(station, station.ids.admin, requires_password_change=True,
                   password_setup_reason="password_reset")
    temporary = login(station, "admin", ADMIN_PASSWORD)
    assert temporary.json()["status"] == "requires_password_change"
    station.secrets.add(temporary.json()["setup_token"])
    [started] = rows(station, "credential_setup_started")
    assert started.user_id == station.ids.admin
    assert started.details == (
        "User 'admin' signed in with a temporary password; password setup started "
        "(reason password_reset)")
    assert not rows(station, "login")
    assert_no_secrets(station)


def test_successful_sign_in_and_logout_are_logged(station):
    signed_in = login(station, "admin", ADMIN_PASSWORD)
    assert signed_in.json()["status"] == "success"
    [row] = rows(station, "login")
    assert row.user_id == station.ids.admin and row.details == "User admin logged in"

    token = signed_in.json()["token"]["access_token"]
    station.secrets.add(token)
    out = station.client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert out.status_code == 200 and out.json() == {"message": "Logged out successfully"}
    [row] = rows(station, "logout")
    assert row.user_id == station.ids.admin
    assert row.details == "User admin logged out; sessions revoked"
    assert_no_secrets(station)


def test_recovery_mode_sign_in_events_are_deferred_not_written(station, monkeypatch):
    local = StationCoordinator()
    local.block("recovery-required")
    monkeypatch.setattr(runtime_operations, "coordinator", local)
    monkeypatch.setattr(audit, "coordinator", local)

    assert login(station, "admin", ADMIN_PASSWORD).json()["status"] == "success"
    assert login(station, "operator", OPERATOR_PASSWORD).status_code == 403
    assert login(station, "admin", "Wrong-Guess-0").json()["status"] == "failed"

    assert rows(station) == []
    pending = audit.pending_events()
    assert [event["action"] for event in pending] == ["login", "login_denied", "login_failed"]
    assert pending[0]["details"] == "User admin logged in (recovery mode)"
    assert pending[1]["details"].startswith(
        f"Recovery sign-in denied for account 'operator' (id {station.ids.operator})")


# ── Kiosk PIN sign-in ─────────────────────────────────────────────────────────

def test_kiosk_pin_sign_in_events(station):
    assert swap(station, "operator", PIN).json()["status"] == "success"
    [row] = rows(station, "pin_login")
    assert row.user_id == station.ids.operator
    assert row.details == "Operator operator swapped in session"
    assert not rows(station, "login")

    assert swap(station, "operator", "0000").json()["status"] == "failed"
    [failed] = rows(station, "pin_failed")
    assert failed.details == (
        f"PIN sign-in failed for account 'operator' (id {station.ids.operator}): incorrect PIN; "
        "4 attempts left")

    update_profile(station, requires_pin_change=True, pin_setup_reason="pin_reset")
    temporary = swap(station, "operator", PIN)
    assert temporary.json()["status"] == "requires_pin_change"
    station.secrets.add(temporary.json()["setup_token"])
    [started] = rows(station, "credential_setup_started")
    assert started.user_id == station.ids.operator
    assert started.details == (
        "User 'operator' signed in with a temporary PIN; PIN setup started (reason pin_reset)")

    update_profile(station, requires_pin_change=False)
    update_account(station, station.ids.operator, status=ActiveStatusEnum.INACTIVE)
    assert swap(station, "operator", PIN).json()["status"] == "inactive"
    [denied] = rows(station, "login_denied")
    assert denied.details == (
        f"PIN sign-in denied for account 'operator' (id {station.ids.operator}): "
        "account is inactive")
    assert_no_secrets(station)


def test_kiosk_pin_lockout_and_refusal_are_logged(station):
    for _ in range(4):
        assert swap(station, "operator", "0000").status_code == 200
    locked = swap(station, "operator", "0000")
    assert locked.status_code == 429
    assert locked.json() == {
        "detail": "Too many failed PIN attempts. Account locked for 300 seconds."}
    assert len(rows(station, "pin_failed")) == 5
    [locked_row] = rows(station, "account_locked")
    assert locked_row.details == (
        f"Account 'operator' (id {station.ids.operator}) PIN sign-in locked for 300 s "
        "after 5 failed PIN attempts")
    assert swap(station, "operator", PIN).status_code == 429
    [blocked] = rows(station, "login_blocked")
    assert blocked.details.startswith(
        f"PIN sign-in refused for account 'operator' (id {station.ids.operator}): "
        "locked for another ")
    assert_no_secrets(station)


@pytest.mark.parametrize("username", ["", "x" * 51])
def test_pin_swap_username_length_is_validated(station, username):
    response = swap(station, username, PIN)
    assert response.status_code == 422
    assert rows(station) == []


# ── Credential changes ────────────────────────────────────────────────────────

def test_credential_changes_use_specific_actions(station):
    changed = station.client.post(
        "/api/v1/auth/change-password", headers=bearer(station, station.ids.admin),
        json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD})
    assert changed.status_code == 200, changed.text
    [row] = rows(station, "password_changed")
    assert row.user_id == station.ids.admin
    assert row.details == "User 'admin' changed password; other sessions revoked"

    changed = station.client.post(
        "/api/v1/auth/change-pin", headers=bearer(station, station.ids.operator),
        json={"current_pin": PIN, "new_pin": NEW_PIN})
    assert changed.status_code == 200, changed.text
    [row] = rows(station, "pin_changed")
    assert row.user_id == station.ids.operator
    assert row.details == "User 'operator' changed PIN; other sessions revoked"
    assert not rows(station, "user_updated")
    assert_no_secrets(station)


def test_failed_password_change_is_logged_and_rate_limited(station):
    headers = bearer(station, station.ids.admin)
    path = "/api/v1/auth/change-password"
    for attempt in range(4):
        wrong = station.client.post(path, headers=headers, json={
            "current_password": f"Wrong-Guess-{attempt}", "new_password": NEW_PASSWORD})
        station.secrets.add(f"Wrong-Guess-{attempt}")
        assert wrong.status_code == 401
        assert wrong.json() == {"detail": "Current password is incorrect"}
    locked = station.client.post(path, headers=headers, json={
        "current_password": "Wrong-Guess-4", "new_password": NEW_PASSWORD})
    station.secrets.add("Wrong-Guess-4")
    assert locked.status_code == 429
    assert locked.json() == {
        "detail": "Too many failed password attempts. Try again in 300 seconds."}

    failed = rows(station, "password_change_failed")
    assert len(failed) == 5 and all(row.user_id == station.ids.admin for row in failed)
    assert any(row.details == (
        "Password change failed for user 'admin': current password incorrect; "
        "4 attempts left") for row in failed)
    [locked_row] = rows(station, "account_locked")
    assert locked_row.details == (
        f"Account 'admin' (id {station.ids.admin}) password change locked for 300 s "
        "after 5 failed attempts")

    still_locked = station.client.post(path, headers=headers, json={
        "current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD})
    assert still_locked.status_code == 429
    [blocked] = rows(station, "login_blocked")
    assert blocked.user_id == station.ids.admin
    assert blocked.details.startswith(
        "Password change refused for user 'admin': locked for another ")
    with Session(station.engine) as db:
        assert verify_password(ADMIN_PASSWORD, db.get(UserAccount, station.ids.admin).password_hash)
    assert not rows(station, "password_changed")
    assert_no_secrets(station)


def test_failed_pin_change_is_logged_and_rate_limited(station):
    headers = bearer(station, station.ids.operator)
    path = "/api/v1/auth/change-pin"
    for _ in range(4):
        wrong = station.client.post(path, headers=headers,
                                    json={"current_pin": "0000", "new_pin": NEW_PIN})
        assert wrong.status_code == 401
        assert wrong.json() == {"detail": "Current PIN is incorrect"}
    locked = station.client.post(path, headers=headers,
                                 json={"current_pin": "0000", "new_pin": NEW_PIN})
    assert locked.status_code == 429
    assert locked.json() == {"detail": "Too many failed PIN attempts. Try again in 300 seconds."}
    failed = rows(station, "pin_change_failed")
    assert len(failed) == 5 and all(row.user_id == station.ids.operator for row in failed)
    [locked_row] = rows(station, "account_locked")
    assert "PIN change locked for 300 s after 5 failed attempts" in locked_row.details
    still_locked = station.client.post(path, headers=headers,
                                       json={"current_pin": PIN, "new_pin": NEW_PIN})
    assert still_locked.status_code == 429
    assert len(rows(station, "login_blocked")) == 1
    assert not rows(station, "pin_changed")
    assert_no_secrets(station)


# ── Setup tokens ──────────────────────────────────────────────────────────────

def test_setup_completion_and_rejected_setup_tokens(station):
    garbage = "not-a-real-token-SENTINEL"
    station.secrets.add(garbage)
    rejected = station.client.post("/api/v1/auth/setup-password", json={
        "setup_token": garbage, "new_password": NEW_PASSWORD})
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "Invalid or expired setup authorization; sign in again"}
    [row] = rows(station, "setup_token_rejected")
    assert row.user_id is None
    assert row.details == "Password setup refused: setup authorization invalid or expired"

    update_account(station, station.ids.admin, requires_password_change=True,
                   password_setup_reason="new_account")
    token = login(station, "admin", ADMIN_PASSWORD).json()["setup_token"]
    station.secrets.add(token)
    done = station.client.post("/api/v1/auth/setup-password", json={
        "setup_token": token, "new_password": NEW_PASSWORD})
    assert done.status_code == 200, done.text
    [completed] = rows(station, "password_setup_completed")
    assert completed.user_id == station.ids.admin
    assert completed.details == "User 'admin' completed password setup; other sessions revoked"

    replay = station.client.post("/api/v1/auth/setup-password", json={
        "setup_token": token, "new_password": "Another-Secret-4"})
    station.secrets.add("Another-Secret-4")
    assert replay.status_code == 401
    assert replay.json() == {"detail": "Setup authorization revoked; sign in again"}
    revoked = [r for r in rows(station, "setup_token_rejected") if "revoked" in r.details]
    assert len(revoked) == 1
    assert revoked[0].details == (
        f"Password setup refused for user id {station.ids.admin}: setup authorization revoked")

    update_profile(station, requires_pin_change=True, pin_setup_reason="new_account")
    pin_token = swap(station, "operator", PIN).json()["setup_token"]
    station.secrets.add(pin_token)
    wrong_purpose = station.client.post("/api/v1/auth/setup-password", json={
        "setup_token": pin_token, "new_password": NEW_PASSWORD})
    assert wrong_purpose.status_code == 401
    assert any(r.details == (f"Password setup refused for user id {station.ids.operator}: "
                             "setup authorization has the wrong purpose")
               for r in rows(station, "setup_token_rejected"))
    pin_done = station.client.post("/api/v1/auth/setup-pin", json={
        "setup_token": pin_token, "new_pin": NEW_PIN})
    assert pin_done.status_code == 200, pin_done.text
    [completed] = rows(station, "pin_setup_completed")
    assert completed.user_id == station.ids.operator
    assert completed.details == "User 'operator' completed PIN setup; other sessions revoked"
    assert not rows(station, "user_updated")
    assert_no_secrets(station)


# ── PostgreSQL: failure events after a row lock must not wait on that lock ─────

@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("BANANAVISION_TEST_DATABASE_URL"),
                    reason="Disposable PostgreSQL required")
async def test_locked_credential_failures_are_written_after_rollback_on_postgresql(monkeypatch):
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core import database
    from app.models import UserRole
    from app.services import maintenance_state

    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = "qa_audit_auth_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    # A write that waits on the request's own row lock fails after 5 s instead of hanging.
    engine = create_async_engine(url, connect_args={"server_settings": {
        "search_path": schema, "timezone": "Asia/Manila", "lock_timeout": "5000"}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as db:
            await db.run_sync(database.Base.metadata.create_all)
        async with sessions() as db:
            admin_role, operator_role = UserRole(name="Admin"), UserRole(name="Operator")
            db.add_all([admin_role, operator_role])
            await db.flush()
            admin = UserAccount(username="admin", full_name="Admin User", role_id=admin_role.id,
                                password_hash=hash_password(ADMIN_PASSWORD))
            operator = UserAccount(username="operator", full_name="Operator",
                                   role_id=operator_role.id,
                                   password_hash=hash_password(OPERATOR_PASSWORD))
            db.add_all([admin, operator])
            await db.flush()
            db.add(OperatorProfile(account_id=operator.id, pin_hash=hash_pin(PIN)))
            await db.commit()
            admin_id, operator_id = admin.id, operator.id

        monkeypatch.setattr(database, "async_session_factory", sessions)
        monkeypatch.setattr(maintenance_state, "auth_generation", "initial")
        for name in ("login_limiter", "pin_limiter", "credential_limiter"):
            monkeypatch.setattr(auth, name, RateLimiter())
        monkeypatch.setattr(auth, "_blocked_seen", {})
        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        audit.install(app)

        async def post(client, path, **kwargs):
            return await asyncio.wait_for(client.post(path, **kwargs), timeout=30)

        def headers(account_id):
            token = create_access_token({"sub": str(account_id), "tv": 1})
            return {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as client:
            wrong_password = {"current_password": "Wrong-Guess", "new_password": NEW_PASSWORD}
            for _ in range(4):
                wrong = await post(client, "/api/v1/auth/change-password",
                                   headers=headers(admin_id), json=wrong_password)
                assert wrong.status_code == 401
            locked = await post(client, "/api/v1/auth/change-password",
                                headers=headers(admin_id), json=wrong_password)
            assert locked.status_code == 429
            wrong_pin = await post(client, "/api/v1/auth/change-pin", headers=headers(operator_id),
                                   json={"current_pin": "0000", "new_pin": NEW_PIN})
            assert wrong_pin.status_code == 401
            revoked = create_access_token(
                {"sub": str(admin_id), "tv": 0, "scope": "setup_password"})
            rejected = await post(client, "/api/v1/auth/setup-password",
                                  json={"setup_token": revoked, "new_password": NEW_PASSWORD})
            assert rejected.status_code == 401
            for attempt in range(5):
                await post(client, "/api/v1/auth/login",
                           json={"username": "admin", "password": f"Wrong-Guess-{attempt}"})
            out = await post(client, "/api/v1/auth/logout", headers=headers(admin_id))
            assert out.status_code == 200

        async with sessions() as db:
            saved = (await db.execute(select(ActivityLog.action, ActivityLog.user_id))).all()
            account = await db.get(UserAccount, admin_id)
            assert verify_password(ADMIN_PASSWORD, account.password_hash)
        counts = {action: sum(1 for row in saved if row.action == action)
                  for action in {row.action for row in saved}}
        assert counts == {"password_change_failed": 5, "account_locked": 2, "pin_change_failed": 1,
                          "setup_token_rejected": 1, "login_failed": 5, "logout": 1}
        assert all(row.user_id in {admin_id, operator_id, None} for row in saved)
    finally:
        await engine.dispose()
        async with control.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()
