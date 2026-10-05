"""Temporary credentials are issued once to the creating/resetting administrator."""
import secrets


def temporary_password() -> str:
    return secrets.token_urlsafe(18)


def temporary_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"
