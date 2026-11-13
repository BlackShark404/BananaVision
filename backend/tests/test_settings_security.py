"""Production refuses predictable signing secrets; development keeps its placeholders."""
import pytest
from app.config import Settings
from pydantic import ValidationError

STRONG = "k" * 48


def clear_secret_environment(monkeypatch):
    for name in ("APP_ENV", "APP_SECRET_KEY", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_production_requires_strong_unique_secrets(monkeypatch):
    clear_secret_environment(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            app_secret_key=STRONG,
            jwt_secret_key="change-me",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            app_secret_key=STRONG,
            jwt_secret_key="short",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            app_secret_key=STRONG,
            jwt_secret_key="change-me" + "x" * 40,
        )


def test_production_accepts_strong_secrets(monkeypatch):
    clear_secret_environment(monkeypatch)
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_secret_key=STRONG,
        jwt_secret_key="j" * 48,
    )
    assert settings.is_production


def test_development_keeps_placeholder_secrets(monkeypatch):
    clear_secret_environment(monkeypatch)
    settings = Settings(_env_file=None)
    assert not settings.is_production
    assert settings.jwt_secret_key == "change-me"
