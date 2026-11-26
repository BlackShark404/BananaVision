"""Regression coverage for live-session revocation, role/PIN access and admin races."""
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt.api_jwt
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.api.v1 import users
from app.core import database
from app.core.exceptions import CredentialsException
from app.core.security import create_access_token, hash_pin
from app.models import AdminProfile, OperatorProfile, UserAccount, UserRole
from app.schemas.enums import ActiveStatusEnum
from app.schemas.user import UserUpdate
from app.services.auth_service import lock_current_account
from app.ws import handlers
from app.ws.authorization import current_socket_role
from app.ws.manager import ConnectionManager
from tests.test_assigned_fixes import secured  # noqa: F401
from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application  # noqa: F401


def token_for(account_id, **claims):
    return create_access_token({"sub": str(account_id), "tv": 1, "role": "Admin", **claims})


class Socket:
    def __init__(self):
        self.messages = []
        self.close_code = None
        self.accepts = 0

    async def accept(self):
        self.accepts += 1

    async def send_text(self, value):
        self.messages.append(json.loads(value))

    async def close(self, code, reason=""):
        self.close_code = code


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ["room", "broadcast", "personal"])
@pytest.mark.parametrize("revocation", ["version", "inactive", "role", "expired"])
async def test_connected_socket_revalidates_before_every_delivery(application, delivery, revocation, monkeypatch):
    manager, socket = ConnectionManager(), Socket()
    token = token_for(application.ids.admin)
    await manager.connect(socket, ["dashboard"], token=token)
    await manager.send_personal(socket, "healthy", {})
    assert [message["event"] for message in socket.messages] == ["healthy"]
    if revocation == "expired":
        future = datetime.now(UTC) + timedelta(days=3650)

        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return future.astimezone(tz) if tz else future.replace(tzinfo=None)

        monkeypatch.setattr(jwt.api_jwt, "datetime", ExpiredClock)
    else:
        change = {"version": {"token_version": 2}, "inactive": {"status": ActiveStatusEnum.INACTIVE},
                  "role": {"role_id": 2}}[revocation]
        with Session(application.engine) as db:
            db.execute(update(UserAccount).where(UserAccount.id == application.ids.admin).values(**change))
            db.commit()
    if delivery == "room":
        await manager.send_to_room("dashboard", "secret", {})
    elif delivery == "broadcast":
        await manager.broadcast("secret", {})
    else:
        await manager.send_personal(socket, "secret", {})
    assert [message["event"] for message in socket.messages] == ["healthy"]
    assert socket.close_code == 4001 and manager.total_connections == 0


@pytest.mark.asyncio
async def test_socket_uses_database_role_rejects_setup_and_fails_closed(application, monkeypatch):
    # Even a signed token carrying an old Admin claim gets the current Operator role.
    assert await current_socket_role(token_for(application.ids.operator)) == "Operator"
    assert await current_socket_role(token_for(application.ids.admin, scope="setup_password")) is None
    manager, socket = ConnectionManager(), Socket()
    await manager.connect(socket, ["kiosk"], token=token_for(application.ids.operator))

    def unavailable():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(database, "async_session_factory", unavailable)
    await manager.broadcast("secret", {})
    assert not socket.messages and socket.close_code == 4001


def test_socket_subscriptions_accept_once_and_idle_revocation(application, monkeypatch):
    manager = ConnectionManager()
    monkeypatch.setattr(handlers, "ws_manager", manager)
    monkeypatch.setattr(handlers, "SESSION_CHECK_INTERVAL", 0.01)
    app = FastAPI()
    app.add_api_websocket_route("/ws", handlers.websocket_endpoint)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?token={token_for(application.ids.operator)}") as socket:
            socket.send_json({"event": "subscribe", "data": {"rooms": ["dashboard", "devices"]}})
            socket.send_json(["malformed", "message"])
            socket.send_json({"event": "subscribe", "data": {"rooms": [42]}})
            socket.send_json({"event": "ping"})
            assert socket.receive_json()["event"] == "pong"
            assert set(manager._connections) == {"kiosk"}
            with Session(application.engine) as db:
                db.execute(update(UserAccount).where(UserAccount.id == application.ids.operator)
                           .values(token_version=2))
                db.commit()
            # No client ping or outbound broadcast is needed to expire an idle socket.
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 4001
    assert manager.total_connections == 0


def test_role_transition_retires_pin_preserves_history_and_revokes_sessions(secured):
    client, fixture = secured.client, secured.app
    operator_id = fixture.ids.operator
    with Session(fixture.engine) as db:
        profile = db.get(OperatorProfile, fixture.ids.profile)
        profile.pin_hash = hash_pin("1357")
        profile.requires_pin_change = False
        db.commit()
    swap = client.post("/api/v1/auth/swap", json={"username": "operator", "pin": "1357"})
    assert swap.json()["status"] == "success"
    old_headers = {"Authorization": f"Bearer {swap.json()['token']['access_token']}"}
    promoted = client.patch(f"/api/v1/users/{operator_id}", headers=secured.headers, json={"role": "Admin"})
    assert promoted.status_code == 200, promoted.text
    with Session(fixture.engine) as db:
        account = db.get(UserAccount, operator_id)
        assert account.operator_profile.id == fixture.ids.profile  # existing scan ownership survives
        assert account.operator_profile.pin_hash is None and account.admin_profile
        assert not account.operator_profile.requires_pin_change
    assert client.get("/api/v1/users/me/summary", headers=old_headers).status_code == 401
    assert client.post("/api/v1/auth/swap", json={"username": "operator", "pin": "1357"}).json()["status"] == "failed"
    assert client.post(f"/api/v1/users/{operator_id}/reset-pin", headers=secured.headers, json={}).status_code == 403
    # Also reject legacy Admin rows that still have a valid operator-profile PIN.
    with Session(fixture.engine) as db:
        db.get(OperatorProfile, fixture.ids.profile).pin_hash = hash_pin("1357")
        db.commit()
    assert client.post("/api/v1/auth/swap", json={"username": "operator", "pin": "1357"}).json()["status"] == "failed"
    promoted_headers = {"Authorization": f"Bearer {token_for(operator_id, tv=2)}"}
    assert client.post("/api/v1/auth/change-pin", headers=promoted_headers,
                       json={"current_pin": "1357", "new_pin": "2468"}).status_code == 403
    assert client.post("/api/v1/auth/setup-pin", json={
        "setup_token": token_for(operator_id, tv=2, scope="setup_pin"), "new_pin": "2468",
    }).status_code == 403
    demoted = client.patch(f"/api/v1/users/{operator_id}", headers=secured.headers, json={"role": "Operator"})
    assert demoted.status_code == 200 and demoted.json()["requires_pin_change"]
    assert client.post("/api/v1/auth/swap", json={"username": "operator", "pin": "1357"}).json()["status"] == "failed"
    reset = client.post(f"/api/v1/users/{operator_id}/reset-pin", headers=secured.headers, json={})
    assert reset.status_code == 200
    assert client.post("/api/v1/auth/swap", json={"username": "operator", "pin": reset.json()["temporary_pin"]}).json()["status"] == "requires_pin_change"


def test_inactive_reactivation_does_not_restore_old_session(secured):
    token = token_for(secured.app.ids.operator, role="Operator")
    for status in ("Inactive", "Active"):
        changed = secured.client.patch(f"/api/v1/users/{secured.app.ids.operator}",
                                       headers=secured.headers, json={"status": status})
        assert changed.status_code == 200, changed.text
    assert secured.client.get("/api/v1/users/me/summary", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.asyncio
async def test_credential_write_refresh_rejects_stale_authenticated_account(application):
    db = SessionAdapter(application.engine, application.state)
    stale = db.session.get(UserAccount, application.ids.admin)
    with Session(application.engine) as other:
        other.execute(update(UserAccount).where(UserAccount.id == stale.id).values(token_version=2))
        other.commit()
    with pytest.raises(CredentialsException):
        await lock_current_account(db, stale)
    await db.close()


class ThreadedSessionAdapter(SessionAdapter):
    """Independent real transactions; blocking locks must not block the event loop."""
    async def execute(self, statement):
        return await asyncio.to_thread(self.session.execute, statement)

    async def flush(self):
        await asyncio.to_thread(self.session.flush)


async def race_admin_changes(factory, ids, mutation, self_change=True):
    ready, start = 0, asyncio.Event()

    async def change(account_id):
        nonlocal ready
        async with factory() as db:
            ready += 1
            if ready == 2:
                start.set()
            await start.wait()
            actor = SimpleNamespace(id=account_id, token_version=1)
            try:
                target_id = account_id if self_change else next(value for value in ids if value != account_id)
                await users.update_user(target_id, UserUpdate(**mutation), db, actor,
                                        Request({"type": "http", "client": ("127.0.0.1", 123)}))
                if isinstance(db, ThreadedSessionAdapter):
                    await asyncio.to_thread(db.session.commit)
                else:
                    await db.commit()
                return 200
            except HTTPException as error:
                if isinstance(db, ThreadedSessionAdapter):
                    await asyncio.to_thread(db.session.rollback)
                else:
                    await db.rollback()
                return error.status_code

    outcomes = await asyncio.wait_for(asyncio.gather(*(change(account_id) for account_id in ids)), 20)
    assert sorted(outcomes) == [200, 409 if self_change else 403]
    async with factory() as db:
        active = (await db.execute(select(func.count()).select_from(UserAccount).join(UserRole)
                                  .where(UserRole.name == "Admin", UserAccount.status == ActiveStatusEnum.ACTIVE))).scalar()
        assert active == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [{"status": "Inactive"}, {"role": "Operator"}])
@pytest.mark.parametrize("self_change", [True, False])
async def test_last_admin_guard_serializes_concurrent_transactions(tmp_path, mutation, self_change):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin-race.db'}", connect_args={"check_same_thread": False, "timeout": 15})
    database.Base.metadata.create_all(engine)
    ids = [uuid4(), uuid4()]
    with Session(engine) as db:
        db.add_all([UserRole(id=1, name="Admin"), UserRole(id=2, name="Operator")])
        db.flush()
        for index, account_id in enumerate(ids):
            db.add(UserAccount(id=account_id, role_id=1, username=f"admin-{index}", full_name="Admin", password_hash="unused", admin_profile=AdminProfile()))
        db.commit()
    try:
        await race_admin_changes(lambda: ThreadedSessionAdapter(engine, SimpleNamespace()), ids, mutation, self_change)
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Optional isolated PostgreSQL instance")
@pytest.mark.parametrize("mutation", [{"status": "Inactive"}, {"role": "Operator"}])
@pytest.mark.parametrize("self_change", [True, False])
async def test_postgresql_last_admin_guard(mutation, self_change):
    # The opt-in URL must point to a disposable TEST database, never the station DB.
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = f"qa_security_{uuid4().hex}"
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = [uuid4(), uuid4()]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
        async with factory() as db:
            db.add_all([UserRole(id=1, name="Admin"), UserRole(id=2, name="Operator")])
            await db.flush()
            for index, account_id in enumerate(ids):
                db.add(UserAccount(id=account_id, role_id=1, username=f"admin-{index}", full_name="Admin", password_hash="unused", admin_profile=AdminProfile()))
            await db.commit()
        await race_admin_changes(factory, ids, mutation, self_change)
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.asyncio
async def test_scan_events_reach_only_the_owning_account_and_current_admin(application):
    manager = ConnectionManager()
    admin, owner, other = Socket(), Socket(), Socket()
    with Session(application.engine) as db:
        other_id = uuid4()
        db.add(
            UserAccount(
                id=other_id,
                role_id=2,
                username="other-socket",
                full_name="Other",
                password_hash="unused",
            )
        )
        db.commit()
    for socket, account in [
        (admin, application.ids.admin),
        (owner, application.ids.operator),
        (other, other_id),
    ]:
        await manager.connect(socket, ["kiosk"], token=token_for(account))
    await manager.send_to_room(
        "kiosk", "scan:completed", {"private_result": True}, account_id=application.ids.operator
    )
    assert len(admin.messages) == len(owner.messages) == 1
    assert other.messages == [] and other.close_code is None
    with Session(application.engine) as db:
        db.execute(
            update(UserAccount).where(UserAccount.id == application.ids.admin).values(role_id=2)
        )
        db.commit()
    await manager.send_to_room(
        "kiosk", "scan:captured", {"private_image": True}, account_id=application.ids.operator
    )
    assert len(admin.messages) == 1 and len(owner.messages) == 2 and other.messages == []
