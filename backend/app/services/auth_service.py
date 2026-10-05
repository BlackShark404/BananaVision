"""
Authentication service — login, PIN swap, password/PIN changes.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    hash_pin,
    verify_password,
    verify_pin,
    decode_access_token,
)
from app.core.exceptions import CredentialsException, NotFoundException, ForbiddenException
from app.models.user_account import UserAccount
from sqlalchemy.orm import selectinload
from app.schemas.enums import ActiveStatusEnum, RoleEnum


def create_setup_token(user: UserAccount, purpose: str) -> str:
    """Ten-minute proof of temporary-credential authentication, never an access token."""
    return create_access_token(
        {"sub": str(user.id), "tv": user.token_version, "scope": purpose},
        expires_delta=timedelta(minutes=10),
    )


async def verify_setup_token(db: AsyncSession, token: str, purpose: str) -> UserAccount:
    payload = decode_access_token(token)
    if not payload or payload.get("scope") != purpose:
        raise CredentialsException("Invalid or expired setup authorization; sign in again")
    from app.services.maintenance_state import generation_matches
    if not await generation_matches(db, payload):
        raise CredentialsException("Station data changed; sign in again")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise CredentialsException("Invalid setup authorization")
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if not user or user.status != ActiveStatusEnum.ACTIVE or payload.get("tv") != user.token_version:
        raise CredentialsException("Setup authorization revoked; sign in again")
    return user


async def lock_current_account(db: AsyncSession, user: UserAccount) -> UserAccount:
    """Refresh under lock so concurrent credential changes cannot reuse a version."""
    version = user.token_version
    account = (await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not account or account.status != ActiveStatusEnum.ACTIVE or account.token_version != version:
        raise CredentialsException("Session has been revoked; sign in again")
    return account


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

    if user.status == ActiveStatusEnum.INACTIVE:
        return "inactive", None, None

    if user.requires_password_change:
        reason = user.password_setup_reason or "password_change"
        return "requires_password_change", user, reason

    # Update last_active
    user.last_active = now_manila()
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

    if (not user or not user.role or user.role.name != RoleEnum.OPERATOR.value
            or not user.operator_profile or not user.operator_profile.pin_hash
            or not verify_pin(pin, user.operator_profile.pin_hash)):
        return "failed", None, None

    if user.status == ActiveStatusEnum.INACTIVE:
        return "inactive", None, None

    if user.operator_profile.requires_pin_change:
        reason = user.operator_profile.pin_setup_reason or "pin_change"
        return "requires_pin_change", user, reason

    user.last_active = now_manila()
    return "success", user, None


async def change_password(
    db: AsyncSession, user: UserAccount, current_password: str, new_password: str
) -> UserAccount:
    """
    Self-service password change — requires the authenticated user object
    and their current password for verification.

    Raises CredentialsException if current_password does not match.
    """
    user = await lock_current_account(db, user)
    if not verify_password(current_password, user.password_hash):
        raise CredentialsException("Current password is incorrect")

    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user


async def setup_password(
    db: AsyncSession, setup_token: str, new_password: str
) -> UserAccount:
    """
    First-time / post-reset password setup.
    Only allowed when the account has requires_password_change=True.

    This is called after the user proved identity by logging in with their
    temporary password.
    """
    user = await verify_setup_token(db, setup_token, "setup_password")

    if not user.requires_password_change:
        raise CredentialsException(
            "Password setup is only allowed for accounts that require a password change"
        )

    if verify_password(new_password, user.password_hash):
        raise CredentialsException("Choose a different password from the temporary password")

    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user


async def change_pin(
    db: AsyncSession, user: UserAccount, current_pin: str, new_pin: str
) -> UserAccount:
    """
    Self-service PIN change — requires the authenticated user object
    and their current PIN for verification.

    Raises CredentialsException if current_pin does not match.
    """
    user = await lock_current_account(db, user)
    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")
    if not user.operator_profile:
        raise NotFoundException("Operator Profile")

    if not user.operator_profile.pin_hash or not verify_pin(current_pin, user.operator_profile.pin_hash):
        raise CredentialsException("Current PIN is incorrect")

    user.operator_profile.pin_hash = hash_pin(new_pin)
    user.operator_profile.requires_pin_change = False
    user.operator_profile.pin_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user


async def setup_pin(
    db: AsyncSession, setup_token: str, new_pin: str
) -> UserAccount:
    """
    First-time / post-reset PIN setup.
    Only allowed when the operator profile has requires_pin_change=True.
    """
    user = await verify_setup_token(db, setup_token, "setup_pin")

    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")

    if not user or not user.operator_profile:
        raise NotFoundException("Operator Profile")

    if not user.operator_profile.requires_pin_change:
        raise CredentialsException(
            "PIN setup is only allowed for accounts that require a PIN change"
        )

    if user.operator_profile.pin_hash and verify_pin(new_pin, user.operator_profile.pin_hash):
        raise CredentialsException("Choose a different PIN from the temporary PIN")

    user.operator_profile.pin_hash = hash_pin(new_pin)
    user.operator_profile.requires_pin_change = False
    user.operator_profile.pin_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
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
            "tv": user.token_version,
        }
    )
