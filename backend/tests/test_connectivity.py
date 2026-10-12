"""Transport regressions. No lifespan or live station resources are used."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from tests.test_time_and_writes import SessionAdapter, application  # noqa: F401


def test_legacy_detail_loads_operator_account_before_serialization(application):
    from app.services.scan_records import load_authorized_scan, serialize_detail
    from types import SimpleNamespace

    async def check():
        actor = SimpleNamespace(id=application.ids.admin, role=SimpleNamespace(name="Admin"))
        async with SessionAdapter(application.engine, application.state) as db:
            scan = await load_authorized_scan(db, application.ids.scan, actor)
            assert not scan.operator_name_snapshot
            assert "account" not in inspect(scan.operator).unloaded
            result = await serialize_detail(db, scan, actor)
            assert result.operator_name == "Original Name"
    asyncio.run(check())


def test_flag_mutation_loads_operator_account_before_serialization(application):
    from app.services.scan_records import mutate_scan
    from app.schemas.scan import ScanFlagRequest
    from types import SimpleNamespace
    from uuid import uuid4

    async def check():
        actor = SimpleNamespace(id=application.ids.admin, role=SimpleNamespace(name="Admin"), token_version=1)
        async with SessionAdapter(application.engine, application.state) as db:
            body = ScanFlagRequest(request_id=uuid4(), expected_revision=1, flagged=True, reason="Need expert check")
            result = await mutate_scan(db, application.ids.scan, actor, "flag", body)
            assert result["flagged"] is True
            assert result["operator_name"] == "Original Name"
            assert result["revision"] == 2
    asyncio.run(check())


@pytest.mark.parametrize("status", [401, 403, 404, 410, 503, 500])
def test_production_cors_covers_errors_without_allowing_other_origins(monkeypatch, status):
    import logging
    import logging.handlers
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", lambda *a, **k: logging.NullHandler())
    from app.main import app

    # Replace only the downstream router; preserve the actual production middleware.
    async def failing(scope, receive, send):
        if status == 500:
            raise RuntimeError("isolated test failure")
        from starlette.responses import JSONResponse
        await JSONResponse({"detail": "test"}, status_code=status)(scope, receive, send)

    monkeypatch.setattr(app, "router", failing)
    monkeypatch.setattr(app, "middleware_stack", None)
    client = TestClient(app, raise_server_exceptions=False)
    try:
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            response = client.get("/health", headers={"Origin": origin})
            assert response.status_code == status
            assert response.headers.get("access-control-allow-origin") == origin
        rejected = client.get("/health", headers={"Origin": "https://untrusted.invalid"})
        assert "access-control-allow-origin" not in rejected.headers
    finally:
        client.close()


def test_preflight_is_allowed_without_authentication(monkeypatch):
    from app.main import app
    monkeypatch.setattr(app, "middleware_stack", None)
    # Do not enter the client: production lifespan must never run here.
    client = TestClient(app)
    try:
        response = client.options("/api/v1/scans", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        client.close()
