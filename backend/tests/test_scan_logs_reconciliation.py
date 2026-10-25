"""Fresh overlay of frozen Logs pages, using only disposable SQLite fixtures."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from app.api.deps import get_current_user
from app.api.v1.scan_logs import router
from app.core.time import now_manila
from app.models import OperatorProfile, Scan, ScanClassification, UserAccount
from app.models.maintenance_state import MaintenanceState
from app.models.scan_snapshot import ScanSnapshot
from app.services import dashboard
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from tests.test_scan_records import operator_session
from tests.test_time_and_writes import application  # noqa: F401


@pytest.fixture
def logs_app(request, monkeypatch):
    app = request.getfixturevalue("application")
    app.app.include_router(router, prefix="/api/v1")
    with app.engine.connect() as connection:
        raw = connection.connection.driver_connection
        raw.create_function("btrim", 2, lambda value, chars: value.strip(chars) if value else value)
        raw.create_function("split_part", 3, lambda value, sep, n: (
            None if value is None else (value.split(sep)[n - 1]
                                       if len(value.split(sep)) >= n else "")
        ))
    monkeypatch.setattr(dashboard, "now_manila", lambda: app.historical)
    return app


def snapshot(app, **params):
    params = {"stable": True, **params}
    response = app.client.get("/api/v1/scan-logs", params=params)
    assert response.status_code == 200, response.text
    frozen = response.json()
    return frozen, {**params, "snapshot_id": frozen["snapshot_id"]}


def reconcile(app, params):
    response = app.client.get("/api/v1/scan-logs/reconcile", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def add_scan(db, app, **values):
    identifier = uuid4()
    db.add(Scan(id=identifier, operator_id=app.ids.profile,
                date_time=app.historical, **values))
    db.flush()
    db.add(ScanClassification(scan_id=identifier, cultivar="Lakatan", ripeness="Ripe",
                              confidence=90, spoilage_days="3", finger_count=5))
    return identifier


def test_reconcile_updates_only_frozen_page_with_whole_filter_metrics(logs_app):
    app = logs_app
    with Session(app.engine) as db:
        for _ in range(3):
            add_scan(db, app)
        db.commit()
    frozen, params = snapshot(app, page=2, page_size=2, sort="confidence")
    export_before = app.client.get("/api/v1/scan-logs/export", params=params).content
    visible = [row["id"] for row in frozen["items"]]
    with Session(app.engine) as db:
        db.execute(update(Scan).values(flagged=True, revision=2))
        db.execute(update(ScanClassification).values(confidence=60))
        # Change sort values on the visible page: its original order must survive.
        db.execute(update(ScanClassification).where(
            ScanClassification.scan_id == UUID(visible[0]),
        ).values(confidence=40))
        add_scan(db, app)
        db.commit()
    fresh = reconcile(app, params)
    assert [row["id"] for row in fresh["items"]] == visible
    assert all(row["revision"] == 2 and row["flagged"] for row in fresh["items"])
    assert fresh["total"] == 5
    assert fresh["flagged_count"] == fresh["review_count"] == 4
    assert fresh["avg_confidence"] == 62
    assert fresh["snapshot_id"] == frozen["snapshot_id"]
    assert app.client.get("/api/v1/scan-logs", params=params).json() == frozen
    assert app.client.get("/api/v1/scan-logs/export", params=params).content == export_before


@pytest.mark.parametrize("change", ["delete", "reassign", "filter"])
def test_reconcile_omits_removed_inaccessible_and_filter_exits(logs_app, change):
    app = logs_app
    operator_session(app, app.ids.operator)
    _, params = snapshot(app, cultivar="Lakatan")
    with Session(app.engine) as db:
        if change == "delete":
            db.execute(delete(Scan).where(Scan.id == app.ids.scan))
        elif change == "reassign":
            other, profile = uuid4(), uuid4()
            db.add(UserAccount(id=other, role_id=2, username="other", full_name="Other",
                               password_hash="unused"))
            db.flush()
            db.add(OperatorProfile(id=profile, account_id=other))
            db.flush()
            db.execute(update(Scan).values(operator_id=profile))
        else:
            db.execute(update(ScanClassification).values(cultivar="Cardaba"))
        db.commit()
    fresh = reconcile(app, params)
    assert fresh["items"] == fresh["at_risk_ids"] == []
    assert fresh["total"] == fresh["review_count"] == fresh["at_risk_count"] == 0
    assert fresh["avg_confidence"] is None


def test_reconcile_risk_uses_unrounded_predicate(logs_app):
    app = logs_app
    with Session(app.engine) as db:
        db.execute(update(Scan).values(
            intake_id=None, intake_origin_id=None, intake_provenance="unlinked",
        ))
        db.execute(update(ScanClassification).values(spoilage_days="2"))
        above = add_scan(db, app)
        db.execute(update(ScanClassification).where(
            ScanClassification.scan_id == above,
        ).values(spoilage_days="2.00001"))
        db.commit()
    _, params = snapshot(app)
    fresh = reconcile(app, params)
    assert all(row["remaining_days"] == 2 for row in fresh["items"])
    assert fresh["at_risk_ids"] == [str(app.ids.scan)]
    assert fresh["at_risk_count"] == 1


@pytest.mark.parametrize("failure", ["binding", "owner", "expiry", "generation", "token"])
def test_reconcile_enforces_snapshot_security_and_lifecycle(logs_app, failure):
    app = logs_app
    _, params = snapshot(app)
    status = 410
    if failure == "binding":
        params["search"] = "changed"
        status = 409
    elif failure == "owner":
        operator_session(app, app.ids.operator)
        status = 403
    else:
        with Session(app.engine) as db:
            if failure == "expiry":
                db.execute(update(ScanSnapshot).values(
                    expires_at=now_manila() - timedelta(seconds=1),
                ))
            elif failure == "generation":
                db.add(MaintenanceState(id=1, auth_generation="restored", operations={}))
            else:
                db.execute(update(ScanSnapshot).values(token_version=99))
            db.commit()
    assert app.client.get("/api/v1/scan-logs/reconcile", params=params).status_code == status


def test_reconcile_requires_authentication_and_snapshot(logs_app):
    app = logs_app
    assert app.client.get("/api/v1/scan-logs/reconcile").status_code == 422
    app.app.dependency_overrides.pop(get_current_user)
    assert app.client.get("/api/v1/scan-logs/reconcile").status_code == 401
