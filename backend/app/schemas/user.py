"""
Pydantic schemas for user management.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
