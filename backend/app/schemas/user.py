"""
Pydantic schemas for user management.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.user_account import UserAccount


# ── Requests ─────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=4, max_length=128)
    pin: str | None = Field(None, min_length=4, max_length=4)
    role: str = "Operator"


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    status: str | None = None
    avatar_url: str | None = None
    requires_password_change: bool | None = None
    password_setup_reason: str | None = None
    requires_pin_change: bool | None = None
    pin_setup_reason: str | None = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=128)
    password_setup_reason: str = "password_reset"


class UserPinReset(BaseModel):
    new_pin: str = Field(..., min_length=4, max_length=4)
    pin_setup_reason: str = "pin_reset"


# ── Responses ────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: str
    status: str
    avatar_url: str | None = None
    requires_password_change: bool = False
    requires_pin_change: bool = False
    last_active: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_db_model(cls, account: "UserAccount") -> "UserResponse":
        return cls(
            id=account.id,
            username=account.username,
            full_name=account.full_name,
            role=account.role.name if account.role else "Unknown",
            status=account.status,
            avatar_url=account.avatar_url,
            requires_password_change=account.requires_password_change,
            requires_pin_change=account.operator_profile.requires_pin_change if account.operator_profile else False,
            last_active=account.last_active,
            created_at=account.created_at,
        )


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
