"""Scan ownership and mutation contracts, using disposable database fixtures."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.deps import get_current_user
from app.models import OperatorProfile, Scan, ScanNote, ScanStatusLog, UserAccount
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.test_time_and_writes import application as application


def operator_session(app, account_id):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=account_id,
        token_version=1,
        full_name="Original Name",
        role=SimpleNamespace(name="Operator"),
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
        app.client.patch(url + "/flag", json=mutation(flagged=True)),
        app.client.patch(
            url + "/status", json=mutation(inventory_status="Sold", reason="Dispatched")
        ),
    ):
        assert response.status_code == 403, response.text
    with Session(app.engine) as db:
        assert db.get(Scan, app.ids.scan).flagged is False
        assert db.scalar(select(func.count()).select_from(ScanStatusLog)) == 1


def test_owner_detail_and_list_do_not_expose_admin_notes(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    assert app.client.post(url + "/notes", json=mutation(note="Private review")).status_code == 200
    assert app.client.get(url).json()["notes"][0]["text"] == "Private review"
    operator_session(app, app.ids.operator)
    detail = app.client.get(url)
    assert detail.status_code == 200
    assert detail.json()["notes"] == [] and detail.json()["has_notes"] is False
    assert app.client.get("/api/v1/scans").json()["items"][0]["has_notes"] is False
    assert app.client.get(url + "/notes").status_code == 403
    assert app.client.post(url + "/notes", json=mutation(2, note="Not allowed")).status_code == 403
    assert (
        app.client.patch(url, json=mutation(2, cultivar="Cardaba", reason="Correction")).status_code
        == 403
    )
    assert app.client.patch(url + "/flag", json=mutation(2, flagged=True)).status_code == 200
    assert (
        app.client.patch(
            url + "/status", json=mutation(3, inventory_status="Sold", reason="Dispatched")
        ).status_code
        == 200
    )


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


def test_revision_and_legacy_history_preserve_recorded_evidence(application):
    app = application
    with Session(app.engine) as db:
        db.add(ScanNote(scan_id=app.ids.scan, author_name="Former administrator",
                        text="Historical note", timestamp=app.historical))
        db.commit()
    detail = app.client.get(f"/api/v1/scans/{app.ids.scan}").json()
    assert detail["revision"] == 1
    assert len(detail["history"]) == 2
    status = next(e for e in detail["history"] if e["kind"] == "status")
    assert status["legacy"] and status["actor_name"] is None and status["reason"] is None
    assert status["timestamp"] == "2025-01-02T00:30:00+08:00"
    note = next(e for e in detail["history"] if e["kind"] == "note")
    assert note["actor_name"] == "Former administrator" and note["legacy"]
    operator_session(app, app.ids.operator)
    assert [
        e["kind"] for e in app.client.get(f"/api/v1/scans/{app.ids.scan}").json()["history"]
    ] == ["status"]


def test_known_deletion_uses_recorded_owner_without_creating_a_delete_api(application):
    app = application
    with Session(app.engine) as db:
        db.delete(db.get(Scan, app.ids.scan))
        db.commit()
    url = f"/api/v1/scans/{app.ids.scan}"
    assert app.client.get(url).status_code == 410
    operator_session(app, app.ids.operator)
    assert app.client.get(url).status_code == 410
    operator_session(app, uuid4())
    assert app.client.get(url).status_code == 403
    assert app.client.get(f"/api/v1/scans/{uuid4()}").status_code == 404


def mutation(revision=1, **fields):
    return {"request_id": str(uuid4()), "expected_revision": revision, **fields}


def test_status_cas_retry_history_and_actor_snapshot(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    body = mutation(inventory_status="Sold", reason="Dispatched to customer")
    first = app.client.patch(url + '/status', json=body)
    assert first.status_code == 200, first.text
    saved = first.json()
    assert saved['revision'] == 2 and not saved['is_overridden']
    assert saved['inventory_status'] == 'Sold'
    event = saved['history'][-1]
    assert event['previous_values'] == {'inventory_status': 'In Stock'}
    assert event['new_values'] == {'inventory_status': 'Sold'}
    assert event['actor_name'] == 'Admin User' and event['reason'] == body['reason']
    assert not event['legacy']
    assert len(saved['history']) == 2  # New status has one linked event, no duplicate legacy row.
    assert app.client.patch(url + '/status', json=body).json() == saved
    assert (
        app.client.patch(url + "/status", json={**body, "inventory_status": "Spoiled"}).status_code
        == 409
    )
    assert app.client.patch(url + '/flag', json=mutation(flagged=True)).status_code == 409
    with Session(app.engine) as db:
        db.get(UserAccount, app.ids.admin).full_name = 'Renamed Admin'
        db.commit()
    assert app.client.get(url).json()['history'][-1]['actor_name'] == 'Admin User'


def test_source_only_and_noop_do_not_override_classification(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    response = app.client.patch(
        url, json=mutation(source_text="Corrected source", reason="Source typo")
    )
    assert response.status_code == 200, response.text
    assert response.json()['is_overridden'] is False
    assert response.json()['original_ai_result'] is None
    no_op = app.client.patch(url, json=mutation(2, cultivar='Lakatan', reason='Checked'))
    assert no_op.status_code == 200 and no_op.json()['revision'] == 2
    changed = app.client.patch(
        url, json=mutation(2, cultivar="Cardaba", reason="Verified cultivar")
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()['revision'] == 3 and changed.json()['is_overridden']
    assert changed.json()['original_ai_result']['cultivar'] == 'Lakatan'
    assert changed.json()['original_ai_result']['spoilage_days'] == '3'


def test_mutation_validation_and_failed_commit_are_atomic(application):
    from app.models import ScanEvent, ScanMutation
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    assert app.client.patch(url + '/flag', json={'flagged': True}).status_code == 422
    assert (
        app.client.patch(
            url + "/status", json=mutation(inventory_status="Sold", reason="   ")
        ).status_code
        == 422
    )
    assert (
        app.client.patch(
            url, json=mutation(reason="Correction", inventory_status="Sold")
        ).status_code
        == 422
    )
    body = mutation(flagged=True)
    app.state.fail_commit = True
    assert app.client.patch(url + '/flag', json=body).status_code == 500
    with Session(app.engine) as db:
        scan = db.get(Scan, app.ids.scan)
        assert scan.revision == 1 and not scan.flagged
        assert db.scalar(select(func.count()).select_from(ScanEvent)) == 0
        assert db.scalar(select(func.count()).select_from(ScanMutation)) == 0
    app.state.fail_commit = False
    assert app.client.patch(url + '/flag', json=body).json()['revision'] == 2


def test_bulk_membership_conflict_and_retry_are_atomic(application):
    app = application
    url = f'/api/v1/intakes/{app.ids.intake}'
    snapshot = app.client.get(url + '/scan-revisions')
    assert snapshot.status_code == 200, snapshot.text
    revisions = snapshot.json()['revisions']
    assert revisions == {str(app.ids.scan): 1}
    body = dict(request_id=str(uuid4()), expected_revisions=revisions,
                inventory_status='Sold', reason='Delivery dispatched')
    conflict = app.client.patch(url + '/bulk-inventory', json={**body, 'expected_revisions': {}})
    assert conflict.status_code == 409
    saved = app.client.patch(url + '/bulk-inventory', json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['revisions'] == {str(app.ids.scan): 2}
    assert app.client.patch(url + '/bulk-inventory', json=body).json() == saved.json()
    detail = app.client.get(f'/api/v1/scans/{app.ids.scan}').json()
    assert detail['revision'] == 2 and detail['inventory_status'] == 'Sold'
    assert detail['history'][-1]['reason'] == body['reason']

def test_incomplete_classification_keeps_original_unknowns_and_rejects_null_count(application):
    app = application
    with Session(app.engine) as db:
        record = db.get(Scan, app.ids.scan)
        record.classification.cultivar = None
        record.classification.ripeness = None
        record.classification.confidence = None
        db.commit()
    url = f'/api/v1/scans/{app.ids.scan}'
    invalid = app.client.patch(url, json=mutation(reason='Count correction', finger_count=None))
    assert invalid.status_code == 422, invalid.text
    saved = app.client.patch(url, json=mutation(reason='Verified cultivar', cultivar='Cardaba'))
    assert saved.status_code == 200, saved.text
    assert saved.json()['original_ai_result']['cultivar'] is None
    assert saved.json()['original_ai_result']['confidence'] is None
    assert saved.json()['is_overridden']
