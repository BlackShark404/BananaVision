"""
User management routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException, ConflictException
from app.core.security import hash_password, hash_pin
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from app.models.activity_log import ActivityLog
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserPasswordReset,
    UserPinReset,
)
from app.schemas.enums import RoleEnum, PasswordSetupReasonEnum, PinSetupReasonEnum


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
async def list_users(db: DbSession, user: CurrentUser):
    """List all users."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .order_by(UserAccount.created_at)
    )
    users = result.scalars().all()
    return UserListResponse(
        items=[UserResponse.from_db_model(u) for u in users],
        total=len(users),
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, db: DbSession, admin: AdminUser, request: Request):
    """Create a new user (admin only)."""
    existing = await db.execute(select(UserAccount).where(UserAccount.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Username '{body.username}' already exists")

    role_res = await db.execute(select(UserRole).where(UserRole.name == body.role))
    user_role = role_res.scalar_one_or_none()
    if not user_role:
        raise NotFoundException(f"Role '{body.role}' not found")

    user = UserAccount(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role_id=user_role.id,
        status=body.status,
        requires_password_change=True,
        password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT,
    )
    user.role = user_role  # Explicitly load for from_db_model

    if body.role == RoleEnum.ADMIN.value:
        user.admin_profile = AdminProfile()
    elif body.role == RoleEnum.OPERATOR.value:
        user.operator_profile = OperatorProfile(
            pin_hash=hash_pin(body.pin) if body.pin else None,
            requires_pin_change=True if body.pin else False,
            pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT if body.pin else None,
        )

    db.add(user)

    db.add(ActivityLog(
        user_id=admin.id,
        action="user_created",
        details=f"Created user '{body.username}' with role {body.role}",
        ip_address=request.client.host if request.client else None,
    ))

    await db.flush()
    return UserResponse.from_db_model(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, admin: AdminUser, request: Request):
    """Update a user (admin only)."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    update_data = body.model_dump(exclude_none=True)
    if body.username is not None and body.username != user.username:
        existing = await db.scalar(select(UserAccount.id).where(UserAccount.username == body.username))
        if existing is not None:
            raise ConflictException(f"Username '{body.username}' already exists")
    for field, value in update_data.items():
        if field in ["requires_pin_change", "pin_setup_reason"]:
            if user.operator_profile:
                setattr(user.operator_profile, field, value)
        elif field == "role":
            role_res = await db.execute(select(UserRole).where(UserRole.name == value))
            user_role = role_res.scalar_one_or_none()
            if user_role:
                user.role_id = user_role.id
                user.role = user_role
        else:
            setattr(user, field, value)

    db.add(ActivityLog(
        user_id=admin.id,
        action="user_updated",
        details=f"Updated user '{user.username}': {list(update_data.keys())}",
        ip_address=request.client.host if request.client else None,
    ))

    await db.flush()
    return UserResponse.from_db_model(user)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: uuid.UUID, body: UserPasswordReset, db: DbSession, admin: AdminUser
):
    """Reset a user's password (admin only)."""
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    user.password_hash = hash_password(body.new_password)
    user.requires_password_change = True
    user.password_setup_reason = body.password_setup_reason
    return {"message": "Password reset successfully"}


@router.post("/{user_id}/reset-pin")
async def reset_user_pin(
    user_id: uuid.UUID, body: UserPinReset, db: DbSession, admin: AdminUser
):
    """Reset a user's PIN (admin only)."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user or not user.operator_profile:
        raise NotFoundException("User Operator Profile")

    user.operator_profile.pin_hash = hash_pin(body.new_pin)
    user.operator_profile.requires_pin_change = True
    user.operator_profile.pin_setup_reason = body.pin_setup_reason
    return {"message": "PIN reset successfully"}
