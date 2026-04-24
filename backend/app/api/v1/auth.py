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

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession):
    """Authenticate a user by username + password."""
    status, user, reason = await authenticate_user(db, body.username, body.password)

    if status == "failed":
        return LoginResponse(status="failed")

    if status == "requires_password_change":
        return LoginResponse(status="requires_password_change", reason=reason)

    # Success
    token = create_user_token(user)
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
async def swap(body: PinSwapRequest, db: DbSession):
    """Swap operator using username + PIN (kiosk mode)."""
    status, user, reason = await swap_operator(db, body.username, body.pin)

    if status == "failed":
        return LoginResponse(status="failed")

    if status == "requires_pin_change":
        return LoginResponse(status="requires_pin_change", reason=reason)

    token = create_user_token(user)
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
async def change_password_route(body: ChangePasswordRequest, db: DbSession):
    """Change password and auto-login."""
    user = await change_password(db, body.username, body.new_password)
    token = create_user_token(user)
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
async def change_pin_route(body: ChangePinRequest, db: DbSession):
    """Change PIN and auto-login."""
    user = await change_pin(db, body.username, body.new_pin)
    token = create_user_token(user)
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
async def logout(user: CurrentUser):
    """Logout (client-side token removal; server acknowledges)."""
    return {"message": "Logged out successfully"}
