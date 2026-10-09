"""Scan ownership and mutation contracts, using disposable database fixtures."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import OperatorProfile, Scan, ScanNote, ScanStatusLog, UserAccount
from tests.test_time_and_writes import application  # noqa: F401


def operator_session(app, account_id):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=account_id, full_name="Original Name", role=SimpleNamespace(name="Operator"),
    )


def test_scan_ownership_applies_to_list_detail_and_writes(application):
    app = application
    other_id = uuid4()
    with Session(app.engine) as db:
        db.add(UserAccount(id=other_id, role_id=2, username="namesake",
                           full_name="Original Name", password_hash="unused"))
        db.flush()
        db.add(OperatorProfile(account_id=other_id))
        db.commit()
    operator_session(app, other_id)
    url = f"/api/v1/scans/{app.ids.scan}"
    listing = app.client.get("/api/v1/scans").json()
    assert listing["total"] == 0 and listing["items"] == []
    for response in (
        app.client.get(url),
        app.client.patch(url + "/flag", json={"flagged": True}),
        app.client.patch(url + "/status", json={"inventory_status": "Sold"}),
    ):
        assert response.status_code == 403, response.text
    with Session(app.engine) as db:
        assert db.get(Scan, app.ids.scan).flagged is False
        assert db.scalar(select(func.count()).select_from(ScanStatusLog)) == 1


def test_owner_detail_and_list_do_not_expose_admin_notes(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    assert app.client.post(url + "/notes", json={"note": "Private review"}).status_code == 200
    assert app.client.get(url).json()["notes"][0]["text"] == "Private review"
    operator_session(app, app.ids.operator)
    detail = app.client.get(url)
    assert detail.status_code == 200
    assert detail.json()["notes"] == [] and detail.json()["has_notes"] is False
    assert app.client.get("/api/v1/scans").json()["items"][0]["has_notes"] is False
    assert app.client.get(url + "/notes").status_code == 403
    assert app.client.post(url + "/notes", json={"note": "Not allowed"}).status_code == 403
    assert app.client.patch(url, json={"cultivar": "Cardaba"}).status_code == 403
    assert app.client.patch(url + "/flag", json={"flagged": True}).status_code == 200
    assert app.client.patch(url + "/status", json={"inventory_status": "Sold"}).status_code == 200


@pytest.mark.parametrize("role", [None, "Observer"])
def test_unknown_role_cannot_read_scan_data(application, role):
    app = application
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, role=SimpleNamespace(name=role) if role else None,
    )
    assert app.client.get("/api/v1/scans").status_code == 403
    assert app.client.get(f"/api/v1/scans/{app.ids.scan}").status_code == 403


def test_notes_missing_scan_is_not_an_empty_success(application):
    app = application
    assert app.client.get(f"/api/v1/scans/{uuid4()}/notes").status_code == 404
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(ScanNote)) == 0


def test_real_credentials_scope_and_revocation(application):
    from app.core.security import create_access_token
    from app.schemas.enums import ActiveStatusEnum

    app = application
    app.app.dependency_overrides.pop(get_current_user)
    url = f"/api/v1/scans/{app.ids.scan}"
    assert app.client.get(url).status_code == 401
    token = create_access_token({"sub": str(app.ids.operator), "tv": 1, "role": "Admin"})
    headers = {"Authorization": f"Bearer {token}"}
    assert app.client.get(url, headers=headers).status_code == 200
    assert app.client.get(url + "/notes", headers=headers).status_code == 403
    with Session(app.engine) as db:
        db.get(UserAccount, app.ids.operator).token_version = 2
        db.commit()
    assert app.client.get(url, headers=headers).status_code == 401
    token = create_access_token({"sub": str(app.ids.operator), "tv": 2})
    headers = {"Authorization": f"Bearer {token}"}
    with Session(app.engine) as db:
        db.get(UserAccount, app.ids.operator).status = ActiveStatusEnum.INACTIVE
        db.commit()
    assert app.client.get(url, headers=headers).status_code == 403
