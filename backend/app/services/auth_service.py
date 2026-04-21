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
from app.models.user import User


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> tuple[str, User | None, str | None]:
    """
    Authenticate a user by username + password.

    Returns:
        (status, user_or_none, reason_or_none)
        status: "success" | "failed" | "requires_password_change"
        reason: "new_account" | "password_reset" | None
    """
    result = await db.execute(select(User).where(User.username == username))
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
) -> tuple[str, User | None, str | None]:
    """
    Swap operator by username + PIN.

    Returns:
        (status, user_or_none, reason_or_none)
        status: "success" | "failed" | "requires_pin_change"
    """
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not user.pin_hash or not verify_pin(pin, user.pin_hash):
        return "failed", None, None

    if user.requires_pin_change:
        reason = user.pin_setup_reason or "pin_change"
        return "requires_pin_change", user, reason

    user.last_active = datetime.now(timezone.utc)
    return "success", user, None


async def change_password(
    db: AsyncSession, username: str, new_password: str
) -> User:
    """Change user password and clear the requires_password_change flag."""
    result = await db.execute(select(User).where(User.username == username))
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
) -> User:
    """Change user PIN and clear the requires_pin_change flag."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundException("User")

    user.pin_hash = hash_pin(new_pin)
    user.requires_pin_change = False
    user.pin_setup_reason = None
    user.last_active = datetime.now(timezone.utc)
    return user


def create_user_token(user: User) -> str:
    """Create a JWT access token for the given user."""
    return create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
    )
