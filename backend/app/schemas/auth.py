"""
Pydantic schemas for authentication requests/responses.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

# ── Requests ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    """Self-service password change — requires current password for verification."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class SetupPasswordRequest(BaseModel):
    """First-time / post-reset password setup — user proved identity at login."""
    setup_token: str
    new_password: str = Field(..., min_length=6, max_length=128)


class PinSwapRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class ChangePinRequest(BaseModel):
    """Self-service PIN change — requires current PIN for verification."""
    current_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    new_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class SetupPinRequest(BaseModel):
    """First-time / post-reset PIN setup — user proved identity at PIN swap."""
    setup_token: str
    new_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


# ── Responses ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthUser(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: str
    avatar_url: str | None = None


class LoginResponse(BaseModel):
    status: str  # "success" | "requires_password_change" | "requires_pin_change" etc.
    token: TokenResponse | None = None
    user: AuthUser | None = None
    reason: str | None = None  # "new_account" | "password_reset" etc.
    setup_token: str | None = None
