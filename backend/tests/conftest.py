"""Shared test defaults."""

import sys

import pytest


@pytest.fixture(autouse=True)
def colour_check_off_for_placeholder_frames(request, monkeypatch):
    """Classifier geometry tests use blank synthetic frames (np.zeros) as placeholders.

    The colour check reads real pixels and would treat a black frame as dark background, so
    it is off unless the test module sets COLOUR_CHECK = True (see test_colour_check.py).
    Only applies when the test already imported the classifier, so import order is unchanged.
    """
    if getattr(request.module, "COLOUR_CHECK", False):
        return
    classification = sys.modules.get("app.services.classification")
    if classification is None:
        return
    settings = classification.settings
    if hasattr(settings, "model_copy"):
        monkeypatch.setattr(classification, "settings",
                            settings.model_copy(update={"yolo_colour_check": False}))


@pytest.fixture(autouse=True)
def fresh_audit_state():
    """The audit throttle, deferred queue and sign-in throttle are per process."""
    from app.api.v1 import auth
    from app.services import audit
    audit.reset_for_tests()
    auth._blocked_seen.clear()
    yield
    audit.reset_for_tests()
    auth._blocked_seen.clear()


@pytest.fixture(autouse=True)
def no_station_database(monkeypatch):
    """Audit writes look up the global session factory at call time. Unless a test installs
    a disposable one (the SQLite fixture, or a PostgreSQL schema), refuse to open the
    configured station database instead of connecting to it."""
    from app.core import database

    monkeypatch.setattr(database, "async_session_factory", _refusing_sessions())


_REFUSING_SESSIONS = None


def _refusing_sessions():
    """Sessions can be created (most requests fail before any query), but connecting raises."""
    global _REFUSING_SESSIONS
    if _REFUSING_SESSIONS is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        async def refuse():
            raise RuntimeError("Tests must not open the configured station database")

        engine = create_async_engine("postgresql+asyncpg://", async_creator=refuse)
        _REFUSING_SESSIONS = async_sessionmaker(engine, expire_on_commit=False)
    return _REFUSING_SESSIONS
