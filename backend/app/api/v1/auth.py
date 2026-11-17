"""
Authentication routes — login, logout, operator swap, password/PIN changes.

AUTH-04: Login and PIN swap endpoints are rate-limited per-username. Changing a password or
PIN re-checks the current secret under a per-account limit (``credential_limiter``).

Audit (``app.services.audit``):
* Sign-in outcomes before a session exists are written with ``audit.emit``: the login session
  holds no row locks, the row survives the 429 that a lockout raises, and while the station
  is in recovery the event is deferred instead of touching the data being verified.
* Failures after ``lock_current_account`` (``SELECT ... FOR UPDATE``) are attached to the
  raised error and written by the audit handler after the request has rolled back.
* Successful sign-ins and credential changes use ``audit.record`` so the row commits with
  the change.
* A typed username that is not an existing account is written only as "an unrecognized
  username"; passwords, PINs and tokens are never written.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import CurrentCredentialIncorrect, SetupTokenRejected
from app.core.http import get_client_ip
from app.core.rate_limiter import MAX_ATTEMPTS, credential_limiter, login_limiter, pin_limiter
from app.schemas.auth import (
    AuthUser,
    ChangePasswordRequest,
    ChangePinRequest,
    LoginRequest,
    LoginResponse,
    PinSwapRequest,
    SetupPasswordRequest,
    SetupPinRequest,
    TokenResponse,
)
from app.services import audit
from app.services.audit import AuditAction
from app.services.auth_service import (
    authenticate_user,
    change_password,
    change_pin,
    create_setup_token,
    create_user_token,
    find_account,
    lock_current_account,
    setup_password,
    setup_pin,
    swap_operator,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

UNRECOGNIZED = "an unrecognized username"
BLOCKED_WINDOW = 60  # seconds between login_blocked rows for the same channel and key
BLOCKED_KEYS = 1024

_clock = time.monotonic
# (channel, username or user id) -> [window start, refused attempts not written since]
_blocked_seen: dict[tuple[str, str], list[float]] = {}


# ── Audit wording ─────────────────────────────────────────────────────────────

def _name(account) -> str:
    """An existing account's stored username, quoted (never the typed text)."""
    return audit.quoted(account.username)


def _account(account) -> str:
    return f"account {_name(account)} (id {account.id})"


def _subject(account) -> str:
    return _account(account) if account is not None else UNRECOGNIZED


def _user(account) -> str:
    return f"user {_name(account)}"


def _attempts_left(count: int) -> str:
    return f"{count} attempt{'' if count == 1 else 's'} left"


def _locked(account, scope: str, seconds: int, attempts: str) -> str:
    """'Account 'x' (id …) <scope> locked for <n> s after <k> failed <attempts>'."""
    if account is None:
        return (f"{scope[0].upper()}{scope[1:]} for {UNRECOGNIZED} locked for {seconds} s "
                f"after {MAX_ATTEMPTS} failed {attempts}")
    return (f"Account {_name(account)} (id {account.id}) {scope} locked for {seconds} s "
            f"after {MAX_ATTEMPTS} failed {attempts}")


def _with_suppressed(details: str, suppressed: int) -> str:
    return f"{details}; {suppressed} similar suppressed" if suppressed else details


def _blocked_suppressed(channel: str, key: str) -> int | None:
    """None when a refused attempt for this channel and key was written in the last window;
    otherwise how many refused attempts were left unwritten since the previous row."""
    now = _clock()
    seen = _blocked_seen
    entry = seen.get((channel, key))
    if entry and now - entry[0] < BLOCKED_WINDOW:
        entry[1] += 1
        return None
    suppressed = int(entry[1]) if entry else 0
    if len(seen) >= BLOCKED_KEYS:
        for stale in [k for k, (start, _) in seen.items() if now - start >= BLOCKED_WINDOW]:
            del seen[stale]
        while len(seen) >= BLOCKED_KEYS:
            seen.pop(next(iter(seen)))
    seen[(channel, key)] = [now, 0]
    return suppressed


def _session_response(user, token: str) -> LoginResponse:
    return LoginResponse(
        status="success",
        token=TokenResponse(access_token=token),
        user=AuthUser(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=getattr(user.role, "name", "Unknown") if user.role else "Unknown",
            avatar_url=user.avatar_url,
        ),
    )


async def _refused_while_locked(db, channel: str, username: str, what: str, remaining: int,
                                ip: str | None) -> None:
    """One login_blocked row per username and channel per window, naming only real accounts."""
    suppressed = _blocked_suppressed(channel, username)
    if suppressed is None:
        return
    account = await find_account(db, username)
    await audit.emit(AuditAction.LOGIN_BLOCKED, _with_suppressed(
        f"{what} refused for {_subject(account)}: locked for another {remaining} s", suppressed,
    ), ip=ip)


@router.get("/operators")
async def list_kiosk_operators(db: DbSession):
    """
    Public endpoint — returns active operators for the kiosk selection modal.
    No authentication required so fresh kiosk sessions can populate the operator list.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.user_account import UserAccount
    from app.models.user_role import UserRole
    from app.schemas.enums import ActiveStatusEnum, RoleEnum

    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .join(UserAccount.role)
        .where(UserAccount.status == ActiveStatusEnum.ACTIVE)
        .where(UserRole.name == RoleEnum.OPERATOR.value)
        .order_by(UserAccount.full_name)
    )
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "Operator",
            "status": u.status.value if u.status else "Active",
            "avatar_url": u.avatar_url,
        }
        for u in users
    ]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, request: Request):
    """Authenticate a user by username + password. Rate-limited (AUTH-04)."""
    ip = get_client_ip(request)
    # ── AUTH-04: Check rate limit ────────────────────────────────────────
    locked, remaining = login_limiter.is_locked(body.username)
    if locked:
        await _refused_while_locked(db, "login", body.username, "Sign-in", remaining, ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
        )

    from app.services.runtime_operations import coordinator
    recovery_login = coordinator.state in {"power-accepted", "recovery-required"}
    status, user, reason = await authenticate_user(db, body.username, body.password, readonly=recovery_login)
    # Only these statuses mean the password was accepted; ``user`` otherwise only names the
    # account for the audit log.
    accepted = status in {"success", "requires_password_change"}
    if recovery_login and accepted and (
            not user.role or user.role.name != 'Admin' or user.requires_password_change):
        denial = 'Recovery requires an active administrator with completed credential setup'
        raise audit.attach(
            HTTPException(403, denial), AuditAction.LOGIN_DENIED,
            f"Recovery sign-in denied for {_account(user)}: {denial[0].lower()}{denial[1:]}",
            ip=ip,
        )

    if status == "failed":
        is_locked, info = login_limiter.record_failure(body.username)
        failure = f"Sign-in failed for {_subject(user)}"
        if reason == "incorrect_password":
            failure += ": incorrect password"
        if is_locked:
            await audit.emit(AuditAction.LOGIN_FAILED, f"{failure}; sign-in locked", ip=ip)
            await audit.emit(AuditAction.ACCOUNT_LOCKED,
                             _locked(user, "sign-in", info, "sign-in attempts"), ip=ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Account locked for {info} seconds.",
            )
        await audit.emit(AuditAction.LOGIN_FAILED, f"{failure}; {_attempts_left(info)}", ip=ip)
        return LoginResponse(status="failed")

    if status == "inactive":
        await audit.emit(AuditAction.LOGIN_DENIED,
                         f"Sign-in denied for {_account(user)}: account is inactive", ip=ip)
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_password_change":
        login_limiter.record_success(body.username)
        await audit.record(
            db, AuditAction.CREDENTIAL_SETUP_STARTED,
            f"User {_name(user)} signed in with a temporary password; password setup started "
            f"(reason {audit.clean(reason, 40)})",
            actor=user, ip=ip,
        )
        return LoginResponse(status="requires_password_change", reason=reason,
                             setup_token=create_setup_token(user, "setup_password"))

    # Success — clear rate limit record
    login_limiter.record_success(body.username)
    if recovery_login:
        from sqlalchemy import select
        from app.models.maintenance_state import MaintenanceState
        generation = await db.scalar(select(MaintenanceState.auth_generation).where(MaintenanceState.id == 1))
        token = create_user_token(user, generation=generation or 'initial')
        # Deferred by the audit writer until the station is ready; recovery writes nothing.
        await audit.emit(AuditAction.LOGIN, f"User {user.username} logged in (recovery mode)",
                         actor=user, ip=ip)
    else:
        token = create_user_token(user)
        await audit.record(db, AuditAction.LOGIN, f"User {user.username} logged in",
                           actor=user, ip=ip)

    return _session_response(user, token)


@router.post("/swap", response_model=LoginResponse)
async def swap(body: PinSwapRequest, db: DbSession, request: Request):
    """Swap operator using username + PIN (kiosk mode). Rate-limited (AUTH-04)."""
    ip = get_client_ip(request)
    # ── AUTH-04: Check rate limit ────────────────────────────────────────
    locked, remaining = pin_limiter.is_locked(body.username)
    if locked:
        await _refused_while_locked(db, "pin", body.username, "PIN sign-in", remaining, ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed PIN attempts. Try again in {remaining} seconds.",
        )

    status, user, reason = await swap_operator(db, body.username, body.pin)

    if status == "failed":
        is_locked, info = pin_limiter.record_failure(body.username)
        failure = f"PIN sign-in failed for {_subject(user)}"
        if reason == "incorrect_pin":
            failure += ": incorrect PIN"
        elif reason == "no_pin":
            failure += ": account has no kiosk PIN"
        if is_locked:
            await audit.emit(AuditAction.PIN_FAILED, f"{failure}; PIN sign-in locked", ip=ip)
            await audit.emit(AuditAction.ACCOUNT_LOCKED,
                             _locked(user, "PIN sign-in", info, "PIN attempts"), ip=ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed PIN attempts. Account locked for {info} seconds.",
            )
        await audit.emit(AuditAction.PIN_FAILED, f"{failure}; {_attempts_left(info)}", ip=ip)
        return LoginResponse(status="failed")

    if status == "inactive":
        await audit.emit(AuditAction.LOGIN_DENIED,
                         f"PIN sign-in denied for {_account(user)}: account is inactive", ip=ip)
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_pin_change":
        pin_limiter.record_success(body.username)
        await audit.record(
            db, AuditAction.CREDENTIAL_SETUP_STARTED,
            f"User {_name(user)} signed in with a temporary PIN; PIN setup started "
            f"(reason {audit.clean(reason, 40)})",
            actor=user, ip=ip,
        )
        return LoginResponse(status="requires_pin_change", reason=reason,
                             setup_token=create_setup_token(user, "setup_pin"))

    # Success
    pin_limiter.record_success(body.username)
    token = create_user_token(user)
    await audit.record(db, AuditAction.PIN_LOGIN, f"Operator {user.username} swapped in session",
                       actor=user, ip=ip)
    return _session_response(user, token)


# ── Credential changes ────────────────────────────────────────────────────────

def _refuse_change_while_locked(key: str, noun: str, what: str, user, ip: str | None) -> None:
    """A locked password/PIN change is refused before the current secret is checked."""
    locked, remaining = credential_limiter.is_locked(key)
    if not locked:
        return
    error = HTTPException(
        status_code=429,
        detail=f"Too many failed {noun} attempts. Try again in {remaining} seconds.",
        headers={"Retry-After": str(max(remaining, 1))},
    )
    suppressed = _blocked_suppressed("credential", key)
    if suppressed is not None:
        audit.attach(error, AuditAction.LOGIN_BLOCKED, _with_suppressed(
            f"{what} refused for {_user(user)}: locked for another {remaining} s", suppressed,
        ), actor=user, ip=ip)
    raise error


def _failed_change(error: HTTPException, key: str, noun: str, scope: str, action, user,
                   ip: str | None) -> HTTPException:
    """Count a wrong current secret; the 5th within the window locks further changes.

    ``lock_current_account`` holds the account row lock, so the events ride on the error and
    are written after the request rolls back.
    """
    is_locked, info = credential_limiter.record_failure(key)
    failure = f"{scope[0].upper()}{scope[1:]} failed for {_user(user)}: current {noun} incorrect"
    if not is_locked:
        return audit.attach(error, action, f"{failure}; {_attempts_left(info)}",
                            actor=user, ip=ip)
    locked = HTTPException(
        status_code=429,
        detail=f"Too many failed {noun} attempts. Try again in {info} seconds.",
        headers={"Retry-After": str(info)},
    )
    audit.attach(locked, action, f"{failure}; {scope} locked", actor=user, ip=ip)
    audit.attach(locked, AuditAction.ACCOUNT_LOCKED, _locked(user, scope, info, "attempts"),
                 actor=user, ip=ip)
    return locked


def _rejected_setup(error: SetupTokenRejected, what: str, ip: str | None) -> HTTPException:
    """The token text is never written; the signed user id is, when the token named one."""
    target = f" for user id {error.user_id}" if error.user_id else ""
    return audit.attach(error, AuditAction.SETUP_TOKEN_REJECTED,
                        f"{what} refused{target}: setup authorization {error.reason}", ip=ip)


@router.post("/change-password", response_model=LoginResponse)
async def change_password_route(
    body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service password change — requires authentication (JWT) and
    current password verification.
    """
    ip = get_client_ip(request)
    key = f"password:{user.id}"
    _refuse_change_while_locked(key, "password", "Password change", user, ip)
    try:
        user = await change_password(db, user, body.current_password, body.new_password)
    except CurrentCredentialIncorrect as error:
        raise _failed_change(error, key, "password", "password change",
                             AuditAction.PASSWORD_CHANGE_FAILED, user, ip) from None
    credential_limiter.record_success(key)
    token = create_user_token(user)
    await audit.record(db, AuditAction.PASSWORD_CHANGED,
                       f"User {_name(user)} changed password; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)


@router.post("/setup-password", response_model=LoginResponse)
async def setup_password_route(body: SetupPasswordRequest, db: DbSession, request: Request):
    """
    First-time / post-reset password setup.
    Only allowed for accounts with requires_password_change=True.
    The user proved identity by logging in with the temporary password.
    """
    ip = get_client_ip(request)
    try:
        user = await setup_password(db, body.setup_token, body.new_password)
    except SetupTokenRejected as error:
        raise _rejected_setup(error, "Password setup", ip) from None
    token = create_user_token(user)
    await audit.record(db, AuditAction.PASSWORD_SETUP_COMPLETED,
                       f"User {_name(user)} completed password setup; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)


@router.post("/change-pin", response_model=LoginResponse)
async def change_pin_route(
    body: ChangePinRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service PIN change — requires authentication (JWT) and
    current PIN verification.
    """
    ip = get_client_ip(request)
    key = f"pin:{user.id}"
    _refuse_change_while_locked(key, "PIN", "PIN change", user, ip)
    try:
        user = await change_pin(db, user, body.current_pin, body.new_pin)
    except CurrentCredentialIncorrect as error:
        raise _failed_change(error, key, "PIN", "PIN change",
                             AuditAction.PIN_CHANGE_FAILED, user, ip) from None
    credential_limiter.record_success(key)
    token = create_user_token(user)
    await audit.record(db, AuditAction.PIN_CHANGED,
                       f"User {_name(user)} changed PIN; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)


@router.post("/setup-pin", response_model=LoginResponse)
async def setup_pin_route(body: SetupPinRequest, db: DbSession, request: Request):
    """
    First-time / post-reset PIN setup.
    Only allowed for operator accounts with requires_pin_change=True.
    The user proved identity by authenticating with the temporary PIN.
    """
    ip = get_client_ip(request)
    try:
        user = await setup_pin(db, body.setup_token, body.new_pin)
    except SetupTokenRejected as error:
        raise _rejected_setup(error, "PIN setup", ip) from None
    token = create_user_token(user)
    await audit.record(db, AuditAction.PIN_SETUP_COMPLETED,
                       f"User {_name(user)} completed PIN setup; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)


@router.post("/logout")
async def logout(user: CurrentUser, db: DbSession, request: Request):
    """Logout — revokes all existing tokens by bumping token_version."""
    user = await lock_current_account(db, user)
    # Increment token_version so every previously issued JWT becomes invalid
    user.token_version += 1
    await audit.record(db, AuditAction.LOGOUT, f"User {user.username} logged out; sessions revoked",
                       actor=user, ip=get_client_ip(request))
    return {"message": "Logged out successfully"}
