"""
Shared FastAPI dependencies — database session, current user extraction.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_stream_db
from app.core.exceptions import CredentialsException, ForbiddenException
from app.core.security import decode_access_token
from app.models.user_account import UserAccount
from sqlalchemy.orm import selectinload
from app.schemas.enums import ActiveStatusEnum, RoleEnum

async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    authorization: str = Header(default=""),
) -> UserAccount:
    """Extract and validate the current user from the Authorization header."""
    if not authorization.startswith("Bearer "):
        raise CredentialsException("Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)

    if not payload or "sub" not in payload:
        raise CredentialsException("Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise CredentialsException("Malformed token payload")

    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise CredentialsException("User not found")

    if user.status != ActiveStatusEnum.ACTIVE:
        raise ForbiddenException("Account is inactive")

    # ── Token version check (AUTH-02 fix) ────────────────────────────────
    # Reject tokens issued before the latest logout / credential change.
    token_version = payload.get("tv")
    if token_version is None or token_version != user.token_version:
        raise CredentialsException("Session has been revoked — please log in again")

    return user


async def require_admin(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserAccount:
    """Require the current user to have Admin role."""
    if not user.role or user.role.name != RoleEnum.ADMIN.value:
        raise ForbiddenException("Admin access required")
    return user


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
StreamDbSession = Annotated[AsyncSession, Depends(get_stream_db, scope="request")]
CurrentUser = Annotated[UserAccount, Depends(get_current_user)]
AdminUser = Annotated[UserAccount, Depends(require_admin)]
