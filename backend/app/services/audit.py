"""The single writer for the audit log (``activity_log``).

Every row is built here so the vocabulary, the text hygiene and the failure handling are the
same everywhere:

* ``record(db, ...)`` adds the row to the caller's transaction. A change and its audit row
  commit or roll back together, so an unaudited change cannot be saved.
* ``emit(...)`` writes through its own session. It is for events that must survive the
  request's rollback (failed logins, lockouts, refused access) or that happen outside a
  committing session (export streams, maintenance outcomes). It never raises, except for
  ``required=True`` data egress while the station is ready.
* ``attach(exc, ...)`` puts an event on an ``HTTPException``. The handler installed by
  ``install(app)`` writes it after ``get_db`` has rolled back and released its row locks;
  writing it earlier could wait on the request's own ``FOR UPDATE`` lock.
* The same handler logs refused access (403) once per actor, route and reason per window.

While the station is in maintenance or recovery, ``emit`` keeps events in memory (and in the
file log) and writes them once the station is ready again, so a restore never sees rows it
did not expect. Every event is also mirrored to the ``bananavision.audit`` logger.
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
import unicodedata
from collections import deque
from types import SimpleNamespace
from contextvars import ContextVar
from enum import Enum, StrEnum
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.http import get_client_ip
from app.core.time import now_manila
from app.models.activity_log import ActivityLog
from app.services import runtime_operations
from app.services.runtime_operations import (
    coordinator,
    finish_on_disconnect,
    maintenance_context,
    maintenance_owner,
)

logger = logging.getLogger("bananavision.audit")


class AuditAction(StrEnum):
    """Every action the audit log may hold. Existing names are kept for unchanged events."""

    # Sign-in and session
    LOGIN = "login"
    PIN_LOGIN = "pin_login"
    LOGOUT = "logout"
    CREDENTIAL_SETUP_STARTED = "credential_setup_started"
    # Security failures
    LOGIN_FAILED = "login_failed"
    PIN_FAILED = "pin_failed"
    LOGIN_BLOCKED = "login_blocked"
    ACCOUNT_LOCKED = "account_locked"
    LOGIN_DENIED = "login_denied"
    SETUP_TOKEN_REJECTED = "setup_token_rejected"
    ACCESS_DENIED = "access_denied"
    REAUTH_FAILED = "reauth_failed"
    PASSWORD_CHANGE_FAILED = "password_change_failed"
    PIN_CHANGE_FAILED = "pin_change_failed"
    # Credentials
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_SETUP_COMPLETED = "password_setup_completed"
    PIN_CHANGED = "pin_changed"
    PIN_SETUP_COMPLETED = "pin_setup_completed"
    PASSWORD_RESET = "password_reset"
    PIN_RESET = "pin_reset"
    # Records
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_STATUS_CHANGED = "user_status_changed"
    PROFILE_UPDATED = "profile_updated"
    SUPPLIER_CREATED = "supplier_created"
    SUPPLIER_UPDATED = "supplier_updated"
    INTAKE_CREATED = "intake_created"
    INTAKE_STATUS_CHANGED = "intake_status_changed"
    SCAN_CREATED = "scan_created"
    SCAN_REJECTED = "scan_rejected"
    SCAN_FAILED = "scan_failed"
    SCAN_FLAG = "scan_flag"
    SCAN_CORRECTION = "scan_correction"
    SCAN_STATUS = "scan_status"
    SCAN_NOTE = "scan_note"
    SCAN_PROVENANCE = "scan_provenance"
    LABEL_PRINT_REQUESTED = "label_print_requested"
    LABEL_PRINT_RETRIED = "label_print_retried"
    DATA_EXPORTED = "data_exported"
    # Configuration, maintenance and system
    CONFIG_CHANGED = "config_changed"
    CONFIG_APPLIED = "config_applied"
    BACKUP_CREATED = "backup_created"
    BACKUP_FAILED = "backup_failed"
    BACKUP_DOWNLOADED = "backup_downloaded"
    RESTORE_VALIDATED = "restore_validated"
    RESTORE_VALIDATION_FAILED = "restore_validation_failed"
    RESTORE_COMPLETED = "restore_completed"
    RESTORE_FAILED = "restore_failed"
    MAINTENANCE_RECOVERED = "maintenance_recovered"
    SYSTEM_RESTART = "system_restart"
    SYSTEM_SHUTDOWN = "system_shutdown"
    POWER_FAILED = "power_failed"
    POWER_CANCELLED = "power_cancelled"
    POWER_COMPLETED = "power_completed"
    RETENTION_CLEANUP = "retention_cleanup"
    RETENTION_FAILED = "retention_failed"
    SYSTEM_STARTED = "system_started"
    BOOTSTRAP_ADMIN_CREATED = "bootstrap_admin_created"


# Scan edits keep their established names (scan_flag, scan_status, ...).
SCAN_CHANGE_ACTIONS = {
    "flag": AuditAction.SCAN_FLAG,
    "correction": AuditAction.SCAN_CORRECTION,
    "status": AuditAction.SCAN_STATUS,
    "note": AuditAction.SCAN_NOTE,
    "provenance": AuditAction.SCAN_PROVENANCE,
}

MAX_DETAILS = 2000
ACCESS_DENIED_WINDOW = 600  # seconds between rows for the same actor, route and reason
ANONYMOUS_PER_MINUTE = 120  # database rows per minute for events with no signed-in actor
THROTTLE_KEYS = 4096
DEFERRED_LIMIT = 1000

# Values that are secret or private payloads; changes are noted without the value.
SENSITIVE_FIELDS = frozenset({
    "password", "new_password", "current_password", "password_hash", "pin", "new_pin",
    "current_pin", "pin_hash", "token", "setup_token", "access_token", "temporary_password",
    "temporary_pin", "authorization", "avatar_url", "contact_phone", "contact_person",
})

# Who made the request; set when the user is resolved, read by the refused-access handler.
request_actor: ContextVar[Any] = ContextVar("audit_request_actor", default=None)

# Failures before sign-in share the anonymous cap so a username spray cannot flood the table.
# account_locked is never capped. Capped events still reach the audit file log.
ANONYMOUS_CAPPED = frozenset({"login_failed", "pin_failed", "login_blocked", "setup_token_rejected"})
LOCK_TIMEOUT = "5s"  # an audit write never hangs a request on a row lock

_IMPORTED_COORDINATOR = coordinator
_clock = time.monotonic
_deferred: deque[dict] = deque(maxlen=DEFERRED_LIMIT)
_throttle: dict[tuple, list[float]] = {}
_anonymous: list[float] = [0.0, 0.0]  # window start, count


# ── Text hygiene ──────────────────────────────────────────────────────────────

def clean(value: Any, limit: int = 80) -> str:
    """One line of printable text: control/format characters become '?', length is capped."""
    if value is None:
        return ""
    text = value.value if isinstance(value, Enum) else str(value)
    text = "".join(
        "?" if unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} and not char.isspace()
        else (" " if char.isspace() else char)
        for char in text
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def quoted(value: Any, limit: int = 80) -> str:
    return f"'{clean(value, limit)}'"


def _render(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool | int | float | UUID):
        return str(value)
    return quoted(value, 60)


def describe_changes(before: dict, after: dict, fields=None) -> str:
    """'field old → new' for each changed field; private fields only say they changed."""
    keys = list(fields) if fields is not None else list(dict.fromkeys([*before, *after]))
    parts = []
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if key in SENSITIVE_FIELDS:
            parts.append(f"{key} changed")
        else:
            parts.append(f"{key} {_render(old)} → {_render(new)}")
    return "; ".join(parts)


# ── Writers ───────────────────────────────────────────────────────────────────

def _station():
    """The station coordinator; follows a replacement of either module reference."""
    if coordinator is not _IMPORTED_COORDINATOR:
        return coordinator
    return runtime_operations.coordinator


def remember_actor(user) -> None:
    """Note who is making this request for refused-access rows.

    A plain snapshot is kept, not the ORM object: after the request rolls back, the instance
    is expired and reading it would fail.
    """
    if user is None:
        request_actor.set(None)
        return
    request_actor.set(SimpleNamespace(id=getattr(user, "id", None),
                                      full_name=getattr(user, "full_name", None),
                                      username=getattr(user, "username", None)))


def _actor_parts(actor=None, actor_id=None, actor_name=None):
    if actor is not None:
        actor_id = actor_id or getattr(actor, "id", None)
        actor_name = actor_name or getattr(actor, "full_name", None) or getattr(actor, "username", None)
    if isinstance(actor_id, str):
        try:
            actor_id = UUID(actor_id)
        except ValueError:
            actor_id = None
    return actor_id, actor_name


def _event(action, details, *, actor=None, actor_id=None, actor_name=None, ip=None, timestamp=None,
           capped=None):
    action = AuditAction(action)
    actor_id, actor_name = _actor_parts(actor, actor_id, actor_name)
    if capped is None:
        # By default a failure before sign-in is capped; a caller that knows the target is a
        # real account passes capped=False (lockouts bound those per account anyway).
        capped = actor_id is None and action.value in ANONYMOUS_CAPPED
    return {
        "action": action.value,
        "details": clean(details, MAX_DETAILS),
        "user_id": actor_id,
        "actor_name": clean(actor_name, 100) or None,
        "ip": clean(ip, 45) or None,
        "timestamp": timestamp or now_manila(),
        "capped": bool(capped),
    }


def _mirror(event: dict, *, level=logging.INFO, note: str = "") -> None:
    logger.log(level, "audit action=%s user=%s ip=%s details=%r%s", event["action"],
               event["user_id"] or event["actor_name"] or "-", event["ip"] or "-",
               event["details"], note)


def _row(event: dict) -> ActivityLog:
    return ActivityLog(timestamp=event["timestamp"], user_id=event["user_id"],
                       action=event["action"], details=event["details"], ip_address=event["ip"],
                       actor_name=event.get("actor_name"))


async def record(db, action, details, *, actor=None, actor_id=None, actor_name=None, ip=None,
                   timestamp=None):
    """Add an audit row to the caller's transaction (it commits or rolls back with the change).

    The file-log line is written when that transaction commits, so a rolled-back change
    never appears there either.
    """
    event = _event(action, details, actor=actor, actor_id=actor_id, actor_name=actor_name, ip=ip,
                   timestamp=timestamp)
    db.add(_row(event))
    session = getattr(db, "sync_session", None) or getattr(db, "session", None)
    if isinstance(session, Session):
        session.info.setdefault(_MIRROR_KEY, []).append(event)
    else:
        _mirror(event)


_MIRROR_KEY = "bananavision_audit_mirror"


@sa_event.listens_for(Session, "after_commit")
def _mirror_committed(session):
    for event in session.info.pop(_MIRROR_KEY, []):
        _mirror(event)


@sa_event.listens_for(Session, "after_rollback")
def _forget_rolled_back(session):
    session.info.pop(_MIRROR_KEY, None)


async def _known_actor(db, event: dict) -> None:
    """A deleted or restored-away account must not break the foreign key; keep its name."""
    if event["user_id"] is None:
        return
    from sqlalchemy import select

    from app.models.user_account import UserAccount
    exists = await db.scalar(select(UserAccount.id).where(UserAccount.id == event["user_id"]))
    if exists is None:
        name = event["actor_name"] or str(event["user_id"])
        event["details"] = clean(f"{event['details']} (actor {quoted(name)} no longer exists)",
                                 MAX_DETAILS)
        event["user_id"] = None


def _session_factory(sessions=None):
    if sessions is not None:
        return sessions
    from app.core import database
    return database.async_session_factory


async def _write(events: list[dict], sessions=None, owner=False) -> None:
    async def write():
        # A non-owner write takes the shared maintenance lock, so it waits for (and never
        # interleaves with) a restore or backup that holds the exclusive barrier.
        token = maintenance_context.set(bool(owner))
        try:
            async with _session_factory(sessions)() as db:
                if db.get_bind().dialect.name == "postgresql":
                    from sqlalchemy import text
                    await db.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
                for event in events:
                    await _known_actor(db, event)
                    db.add(_row(event))
                await db.commit()
        finally:
            maintenance_context.reset(token)

    await finish_on_disconnect(write())


def _owner(owner: bool) -> bool:
    return bool(owner or maintenance_owner.get())


async def emit(action, details, *, actor=None, actor_id=None, actor_name=None, ip=None,
               sessions=None, owner=False, required=False, timestamp=None, capped=None) -> None:
    """Write an audit row through its own session.

    It never raises, except ``required=True`` (data leaving the station), which raises 503
    when the row cannot be written: no audit row, no download.
    """
    event = _event(action, details, actor=actor, actor_id=actor_id, actor_name=actor_name,
                   ip=ip, timestamp=timestamp, capped=capped)
    await _emit_event(event, sessions=sessions, owner=owner, required=required)


# States in which nothing may be written to the station database by a non-owner: a restore or
# backup holds the barrier, or recovery must find the data exactly as it was left.
_UNWRITABLE = {"draining", "maintenance", "recovery-required"}

_drain_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _drain_lock() -> asyncio.Lock:
    """One lock per event loop: the backlog is taken by exactly one writer at a time."""
    loop = asyncio.get_running_loop()
    lock = _drain_locks.get(loop)
    if lock is None:
        lock = _drain_locks[loop] = asyncio.Lock()
    return lock


def _defer(event: dict, note: str) -> None:
    if len(_deferred) == _deferred.maxlen:
        dropped = _deferred[0]
        logger.warning("audit deferred queue is full; dropping the oldest event (it stays in "
                       "this log): action=%s details=%r", dropped["action"], dropped["details"])
    _deferred.append(event)
    _mirror(event, note=note)


def _take_backlog() -> list[dict]:
    batch = list(_deferred)
    _deferred.clear()
    return batch


def _requeue(batch: list[dict]) -> None:
    """Put unwritten events back in front, oldest first, without exceeding the limit."""
    room = (_deferred.maxlen or len(batch)) - len(_deferred)
    keep = batch[-room:] if room > 0 else []
    for lost in batch[: len(batch) - len(keep)]:
        logger.warning("audit deferred queue is full; dropping event (it stays in this log): "
                       "action=%s details=%r", lost["action"], lost["details"])
    _deferred.extendleft(reversed(keep))


async def _emit_event(event: dict, *, sessions=None, owner=False, required=False) -> None:
    is_owner = _owner(owner)
    state = _station().state
    if event["capped"] and not _anonymous_allowed():
        _mirror(event, level=logging.WARNING, note=" (over the anonymous rate cap; no database row)")
        return
    if not is_owner and state != "ready":
        if required:
            if state in _UNWRITABLE:
                _mirror(event, level=logging.WARNING, note=f" (refused: station {state})")
                raise HTTPException(503, f"Station is {state}; please retry when it is ready",
                                    headers={"Retry-After": "5"})
            # A pending restart or shutdown holds no barrier; the row is written now so it
            # cannot be lost at the reboot.
            await _write_or_raise(event, sessions)
            return
        _defer(event, f" (deferred: station {state})")
        return
    if is_owner:
        _mirror(event)
        try:
            await _write([event], sessions=sessions, owner=True)
        except Exception as exc:
            _write_failed(event, exc, required)
        return
    async with _drain_lock():
        batch = _take_backlog()
        _mirror(event)
        try:
            await _write([*batch, event], sessions=sessions)
        except Exception as exc:
            _requeue(batch if required else [*batch, event])
            _write_failed(event, exc, required)


async def _write_or_raise(event: dict, sessions) -> None:
    _mirror(event)
    try:
        await _write([event], sessions=sessions)
    except Exception as exc:
        _write_failed(event, exc, True)


def _write_failed(event: dict, exc: Exception, required: bool) -> None:
    logger.exception("audit write failed for action=%s details=%r", event["action"],
                     event["details"])
    if required:
        raise HTTPException(503, "Audit log unavailable; please retry",
                            headers={"Retry-After": "5"}) from exc


async def flush_deferred(sessions=None) -> None:
    """Write events kept while the station was in maintenance or recovery."""
    if not _deferred or _station().state != "ready":
        return
    async with _drain_lock():
        batch = _take_backlog()
        if not batch:
            return
        try:
            await _write(batch, sessions=sessions)
        except Exception:
            logger.exception("audit flush failed; %d events stay queued", len(batch))
            _requeue(batch)


def pending_events() -> list[dict]:
    return list(_deferred)


def attach(exc: HTTPException, action, details, **fields) -> HTTPException:
    """Put an audit event on an HTTP error; the installed handler writes it after rollback."""
    events = exc.__dict__.setdefault("_audit_events", [])
    events.append(_event(action, details, **fields))
    return exc


# ── Refused access ────────────────────────────────────────────────────────────

def _throttled(key: tuple) -> int | None:
    """None when the event is suppressed, else how many were suppressed before it."""
    now = _clock()
    entry = _throttle.get(key)
    if entry and now - entry[0] < ACCESS_DENIED_WINDOW:
        entry[1] += 1
        return None
    suppressed = int(entry[1]) if entry else 0
    if len(_throttle) >= THROTTLE_KEYS:
        for stale in [k for k, (start, _) in _throttle.items() if now - start >= ACCESS_DENIED_WINDOW]:
            del _throttle[stale]
        if len(_throttle) >= THROTTLE_KEYS:
            _throttle.pop(next(iter(_throttle)))
    _throttle[key] = [now, 0.0]
    return suppressed


def _anonymous_allowed() -> bool:
    now = _clock()
    if now - _anonymous[0] >= 60:
        _anonymous[0], _anonymous[1] = now, 0
    _anonymous[1] += 1
    return _anonymous[1] <= ANONYMOUS_PER_MINUTE


async def access_denied(request: Request, exc: HTTPException) -> None:
    actor = request_actor.get()
    actor_id, actor_name = _actor_parts(actor)
    ip = get_client_ip(request)
    detail = clean(exc.detail, 100)
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path
    if actor_id is None and not _anonymous_allowed():
        return
    suppressed = _throttled((actor_id or ip, request.method, route_path, detail))
    if suppressed is None:
        return
    details = f"{request.method} {clean(request.url.path, 200)} denied (403): {detail}"
    if suppressed:
        details += f"; {suppressed} similar suppressed"
    await emit(AuditAction.ACCESS_DENIED, details, actor_id=actor_id, actor_name=actor_name, ip=ip)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException):
    try:
        events = exc.__dict__.get("_audit_events")
        if events:
            ip = get_client_ip(request)
            for event in events:
                if event["ip"] is None:
                    event["ip"] = ip
                await _emit_event(event)
        elif exc.status_code == 403:
            await access_denied(request, exc)
        elif exc.status_code == 401:
            logger.info("audit unauthenticated %s %s: %s", request.method, request.url.path,
                        clean(exc.detail, 100))
    except Exception:
        logger.exception("audit handler failed; the response is unchanged")
    return await http_exception_handler(request, exc)


class _RequestActorReset:
    """Each request starts with no known actor (pure ASGI, so the context is shared)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = request_actor.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            request_actor.reset(token)


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_middleware(_RequestActorReset)


def reset_for_tests() -> None:
    _deferred.clear()
    _throttle.clear()
    _anonymous[0], _anonymous[1] = 0.0, 0
