"""
Authentication routes — login, logout, operator swap, password/PIN changes.

AUTH-04: Login and PIN swap endpoints are rate-limited per-username.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from app.api.deps import DbSession, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    AuthUser,
    ChangePasswordRequest,
    SetupPasswordRequest,
    PinSwapRequest,
    ChangePinRequest,
    SetupPinRequest,
)
from app.services.auth_service import (
    authenticate_user,
    swap_operator,
    change_password,
    setup_password,
    change_pin,
    setup_pin,
    create_user_token,
    create_setup_token,
    lock_current_account,
)
from app.models.activity_log import ActivityLog
from app.core.rate_limiter import login_limiter, pin_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


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
    # ── AUTH-04: Check rate limit ────────────────────────────────────────
    locked, remaining = login_limiter.is_locked(body.username)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
        )

    status, user, reason = await authenticate_user(db, body.username, body.password)

    if status == "failed":
        is_locked, info = login_limiter.record_failure(body.username)
        # AUDIT-02: Record failed login attempt
        db.add(ActivityLog(
            user_id=None,
            action="login_failed",
            details=f"Failed login attempt for username '{body.username}'",
            ip_address=request.client.host if request.client else None,
        ))
        await db.flush()
        if is_locked:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Account locked for {info} seconds.",
            )
        return LoginResponse(status="failed")

    if status == "inactive":
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_password_change":
        login_limiter.record_success(body.username)
        return LoginResponse(status="requires_password_change", reason=reason,
                             setup_token=create_setup_token(user, "setup_password"))

    # Success — clear rate limit record
    login_limiter.record_success(body.username)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="login",
        details=f"User {user.username} logged in",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/swap", response_model=LoginResponse)
async def swap(body: PinSwapRequest, db: DbSession, request: Request):
    """Swap operator using username + PIN (kiosk mode). Rate-limited (AUTH-04)."""
    # ── AUTH-04: Check rate limit ────────────────────────────────────────
    locked, remaining = pin_limiter.is_locked(body.username)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed PIN attempts. Try again in {remaining} seconds.",
        )

    status, user, reason = await swap_operator(db, body.username, body.pin)

    if status == "failed":
        is_locked, info = pin_limiter.record_failure(body.username)
        # AUDIT-02: Record failed PIN attempt
        db.add(ActivityLog(
            user_id=None,
            action="pin_failed",
            details=f"Failed PIN swap attempt for username '{body.username}'",
            ip_address=request.client.host if request.client else None,
        ))
        await db.flush()
        if is_locked:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed PIN attempts. Account locked for {info} seconds.",
            )
        return LoginResponse(status="failed")

    if status == "inactive":
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_pin_change":
        pin_limiter.record_success(body.username)
        return LoginResponse(status="requires_pin_change", reason=reason,
                             setup_token=create_setup_token(user, "setup_pin"))

    # Success
    pin_limiter.record_success(body.username)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="login",
        details=f"Operator {user.username} swapped in session",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/change-password", response_model=LoginResponse)
async def change_password_route(
    body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service password change — requires authentication (JWT) and
    current password verification.
    """
    user = await change_password(db, user, body.current_password, body.new_password)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="user_updated",
        details=f"User {user.username} changed password",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/setup-password", response_model=LoginResponse)
async def setup_password_route(body: SetupPasswordRequest, db: DbSession, request: Request):
    """
    First-time / post-reset password setup.
    Only allowed for accounts with requires_password_change=True.
    The user proved identity by logging in with the temporary password.
    """
    user = await setup_password(db, body.setup_token, body.new_password)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="user_updated",
        details=f"User {user.username} completed password setup",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/change-pin", response_model=LoginResponse)
async def change_pin_route(
    body: ChangePinRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service PIN change — requires authentication (JWT) and
    current PIN verification.
    """
    user = await change_pin(db, user, body.current_pin, body.new_pin)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="user_updated",
        details=f"User {user.username} changed PIN",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/setup-pin", response_model=LoginResponse)
async def setup_pin_route(body: SetupPinRequest, db: DbSession, request: Request):
    """
    First-time / post-reset PIN setup.
    Only allowed for operator accounts with requires_pin_change=True.
    The user proved identity by authenticating with the temporary PIN.
    """
    user = await setup_pin(db, body.setup_token, body.new_pin)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="user_updated",
        details=f"User {user.username} completed PIN setup",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

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


@router.post("/logout")
async def logout(user: CurrentUser, db: DbSession, request: Request):
    """Logout — revokes all existing tokens by bumping token_version."""
    user = await lock_current_account(db, user)
    # Increment token_version so every previously issued JWT becomes invalid
    user.token_version += 1

    db.add(ActivityLog(
        user_id=user.id,
        action="logout",
        details=f"User {user.username} logged out",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()
    return {"message": "Logged out successfully"}
