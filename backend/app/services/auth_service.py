"""
Authentication service — login, PIN swap, password/PIN changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    hash_pin,
    verify_password,
    verify_pin,
)
from app.core.exceptions import CredentialsException, NotFoundException
from app.models.user_account import UserAccount
from sqlalchemy.orm import selectinload


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> tuple[str, UserAccount | None, str | None]:
    """
    Authenticate a user by username + password.

    Returns:
        (status, user_or_none, reason_or_none)
        status: "success" | "failed" | "requires_password_change"
        reason: "new_account" | "password_reset" | None
    """
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        return "failed", None, None

    if user.requires_password_change:
        reason = user.password_setup_reason or "password_change"
        return "requires_password_change", user, reason

    # Update last_active
    user.last_active = datetime.now(timezone.utc)
    return "success", user, None


async def swap_operator(
    db: AsyncSession, username: str, pin: str
) -> tuple[str, UserAccount | None, str | None]:
    """
    Swap operator by username + PIN.

    Returns:
        (status, user_or_none, reason_or_none)
        status: "success" | "failed" | "requires_pin_change"
    """
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not user.operator_profile or not user.operator_profile.pin_hash or not verify_pin(pin, user.operator_profile.pin_hash):
        return "failed", None, None

    if user.operator_profile.requires_pin_change:
        reason = user.operator_profile.pin_setup_reason or "pin_change"
        return "requires_pin_change", user, reason

    user.last_active = datetime.now(timezone.utc)
    return "success", user, None


async def change_password(
    db: AsyncSession, username: str, new_password: str
) -> UserAccount:
    """Change user password and clear the requires_password_change flag."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundException("User")

    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    user.last_active = datetime.now(timezone.utc)
    return user


async def change_pin(
    db: AsyncSession, username: str, new_pin: str
) -> UserAccount:
    """Change user PIN and clear the requires_pin_change flag."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not user.operator_profile:
        raise NotFoundException("Operator Profile")

    user.operator_profile.pin_hash = hash_pin(new_pin)
    user.operator_profile.requires_pin_change = False
    user.operator_profile.pin_setup_reason = None
    user.last_active = datetime.now(timezone.utc)
    return user


def create_user_token(user: UserAccount) -> str:
    """Create a JWT access token for the given user."""
    # Check if role is populated, otherwise fallback dynamically
    role_name = getattr(user.role, "name", "Unknown") if hasattr(user, "role") and user.role else "Unknown"

    return create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": role_name,
        }
    )
