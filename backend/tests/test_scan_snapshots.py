"""Cross-request snapshots are immutable, scoped and bounded; generated DB only."""

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Scan, ScanClassification
from tests.test_scan_records import mutation, operator_session
from tests.test_time_and_writes import application  # noqa: F401


def test_history_snapshot_freezes_membership_and_values_across_mutations(application):  # noqa: F811 - pytest fixture injection
    app = application
    first = app.client.get("/api/v1/scans", params={"stable": True, "page_size": 1}).json()
    token = first["snapshot_id"]
    assert token and first["total"] == 1
    app.client.patch(f"/api/v1/scans/{app.ids.scan}/flag", json=mutation(flagged=True))
    with Session(app.engine) as db:
        db.add(Scan(operator_id=app.ids.profile))
        db.commit()
    again = app.client.get(
        "/api/v1/scans", params={"stable": True, "page_size": 1, "snapshot_id": token}
    )
    assert again.status_code == 200
    assert again.json()["items"] == first["items"] and again.json()["total"] == 1
    assert (
        app.client.get("/api/v1/scans", params={"stable": True, "page_size": 1}).json()["total"]
        == 2
    )
    assert (
        app.client.get(
            "/api/v1/scans",
            params={"stable": True, "page_size": 1, "snapshot_id": token, "flagged": True},
        ).status_code
        == 409
    )
    operator_session(app, app.ids.operator)
    assert (
        app.client.get(
            "/api/v1/scans", params={"stable": True, "page_size": 1, "snapshot_id": token}
        ).status_code
        == 403
    )


def test_snapshot_expiry_and_station_restore_generation(application):  # noqa: F811 - pytest fixture injection
    from app.core.time import now_manila
    from app.models.maintenance_state import MaintenanceState
    from app.models.scan_snapshot import ScanSnapshot

    app = application

    def fresh():
        return app.client.get("/api/v1/scans", params={"stable": True}).json()["snapshot_id"]

    token = fresh()
    with Session(app.engine) as db:
        db.execute(update(ScanSnapshot).values(expires_at=now_manila() - timedelta(seconds=1)))
        db.commit()
    assert app.client.get("/api/v1/scans", params={"snapshot_id": token}).status_code == 410
    token = fresh()
    with Session(app.engine) as db:
        db.add(MaintenanceState(id=1, auth_generation="restored", operations={}))
        db.commit()
    assert app.client.get("/api/v1/scans", params={"snapshot_id": token}).status_code == 410


def test_logs_snapshot_exports_original_filtered_population(application):  # noqa: F811 - pytest fixture injection
    from app.api.v1.scan_logs import router

    app = application
    app.app.include_router(router, prefix="/api/v1")
    with app.engine.connect() as connection:
        raw = connection.connection.driver_connection
        raw.create_function(
            "btrim", 2, lambda value, chars: None if value is None else value.strip(chars)
        )
        raw.create_function(
            "split_part",
            3,
            lambda value, sep, n: (
                None
                if value is None
                else (value.split(sep)[n - 1] if len(value.split(sep)) >= n else "")
            ),
        )
    params = {"stable": True, "page_size": 1, "cultivar": "Lakatan"}
    response = app.client.get("/api/v1/scan-logs", params=params)
    assert response.status_code == 200, response.text
    first = response.json()
    with Session(app.engine) as db:
        db.execute(update(ScanClassification).values(cultivar="Cardaba"))
        db.add(Scan(operator_id=app.ids.profile))
        db.commit()
    params["snapshot_id"] = first["snapshot_id"]
    assert app.client.get("/api/v1/scan-logs", params=params).json() == first
    exported = app.client.get("/api/v1/scan-logs/export", params=params)
    assert (
        exported.status_code == 200
        and "Lakatan" in exported.text
        and "Cardaba" not in exported.text
    )


def test_snapshot_limits_eviction_and_invalid_tokens(application, monkeypatch):  # noqa: F811 - pytest fixture injection
    from app.services import scan_snapshots as service

    app = application
    params = {"stable": True}
    tokens = [
        app.client.get("/api/v1/scans", params=params).json()["snapshot_id"]
        for _ in range(service.PER_ACCOUNT + 1)
    ]
    assert app.client.get("/api/v1/scans", params={"snapshot_id": tokens[0]}).status_code == 410
    assert app.client.get("/api/v1/scans", params={"snapshot_id": tokens[-1]}).status_code == 200
    assert app.client.get("/api/v1/scans", params={"snapshot_id": "invalid"}).status_code == 422
    monkeypatch.setattr(service, "MAX_ROWS", 0)
    assert app.client.get("/api/v1/scans", params=params).status_code == 413
    monkeypatch.setattr(service, "MAX_ROWS", 50_000)
    monkeypatch.setattr(service, "MAX_BYTES", 1)
    assert app.client.get("/api/v1/scans", params=params).status_code == 413


def test_snapshot_cannot_cross_credential_rotation(application):  # noqa: F811 - pytest fixture injection
    from types import SimpleNamespace

    from app.api.deps import get_current_user
    from app.models import UserAccount

    app = application
    token = app.client.get("/api/v1/scans", params={"stable": True}).json()["snapshot_id"]
    with Session(app.engine) as db:
        db.execute(
            update(UserAccount).where(UserAccount.id == app.ids.admin).values(token_version=2)
        )
        db.commit()
    assert app.client.get("/api/v1/scans", params={"snapshot_id": token}).status_code == 401
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.admin, token_version=2, role=SimpleNamespace(name="Admin")
    )
    assert app.client.get("/api/v1/scans", params={"snapshot_id": token}).status_code == 410
