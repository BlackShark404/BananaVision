"""
Authentication routes — login, logout, operator swap, password/PIN changes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DbSession, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    AuthUser,
    ChangePasswordRequest,
    PinSwapRequest,
    ChangePinRequest,
)
from app.services.auth_service import (
    authenticate_user,
    swap_operator,
    change_password,
    change_pin,
    create_user_token,
)
from app.models.activity_log import ActivityLog

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
    """Authenticate a user by username + password."""
    status, user, reason = await authenticate_user(db, body.username, body.password)

    if status == "failed":
        return LoginResponse(status="failed")

    if status == "inactive":
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_password_change":
        return LoginResponse(status="requires_password_change", reason=reason)

    # Success
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
    """Swap operator using username + PIN (kiosk mode)."""
    status, user, reason = await swap_operator(db, body.username, body.pin)

    if status == "failed":
        return LoginResponse(status="failed")

    if status == "inactive":
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_pin_change":
        return LoginResponse(status="requires_pin_change", reason=reason)

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
async def change_password_route(body: ChangePasswordRequest, db: DbSession, request: Request):
    """Change password and auto-login."""
    user = await change_password(db, body.username, body.new_password)
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


@router.post("/change-pin", response_model=LoginResponse)
async def change_pin_route(body: ChangePinRequest, db: DbSession, request: Request):
    """Change PIN and auto-login."""
    user = await change_pin(db, body.username, body.new_pin)
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


@router.post("/logout")
async def logout(user: CurrentUser, db: DbSession, request: Request):
    """Logout (client-side token removal; server acknowledges)."""
    db.add(ActivityLog(
        user_id=user.id,
        action="logout",
        details=f"User {user.username} logged out",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()
    return {"message": "Logged out successfully"}
