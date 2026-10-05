"""
Security utilities: JWT token creation/verification and password/PIN hashing.

Uses `bcrypt` directly instead of passlib (passlib is incompatible with
bcrypt >= 4.1 and Python >= 3.13).
"""

from __future__ import annotations

from datetime import timedelta
from app.core.time import now_manila

import jwt
from jwt.exceptions import PyJWTError
import bcrypt

from app.config import get_settings

settings = get_settings()

# ── Password Hashing ────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── PIN Hashing (same bcrypt, separate functions for clarity) ────────────────

def hash_pin(plain_pin: str) -> str:
    """Hash a plain-text PIN using bcrypt."""
    return bcrypt.hashpw(plain_pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify a plain-text PIN against a bcrypt hash."""
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))


# ── JWT Tokens ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    from app.services.maintenance_state import auth_generation
    to_encode["sg"] = auth_generation
    expire = now_manila() + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict | None:
    """Decode and verify a JWT access token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except PyJWTError:
        return None
