"""Validate live sessions against the current account, including JWT expiry."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core import database
from app.core.security import decode_access_token
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.schemas.enums import ActiveStatusEnum

ROLE_ROOMS = {
    "Admin": {"kiosk", "dashboard", "devices", "admin"},
    "Operator": {"kiosk"},
}


async def current_socket_role(token: str) -> str | None:
    payload = decode_access_token(token)
    if not payload or payload.get("scope", "access") != "access" or "exp" not in payload:
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    async with database.async_session_factory() as db:
        from app.services.maintenance_state import generation_matches
        if not await generation_matches(db, payload):
            return None
        row = (await db.execute(
            select(UserAccount.token_version, UserAccount.status, UserRole.name)
            .join(UserRole, UserAccount.role_id == UserRole.id)
            .where(UserAccount.id == user_id)
        )).one_or_none()
    if not row or row.status != ActiveStatusEnum.ACTIVE or row.token_version != payload.get("tv"):
        return None
    return row.name if row.name in ROLE_ROOMS else None


def authorized_rooms(role: str, requested: list[str]) -> list[str]:
    allowed = ROLE_ROOMS.get(role, set())
    return list(dict.fromkeys(room for room in requested if room in allowed)) or ["kiosk"]
