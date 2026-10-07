"""Persisted scan mutation, privacy and replay contracts without station hardware."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import Scan, ScanStatusLog, ScanNote, UserAccount
from tests.test_time_and_writes import application  # noqa: F401


def mutation(revision=1, **values):
    return {"expected_revision": revision, "request_id": str(uuid4()), **values}


def test_status_history_is_atomic_replayable_and_payload_bound(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    body = mutation(inventory_status="Sold", reason="  Sold at market  ")
    changed = app.client.patch(url + "/status", json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    event = changed.json()["history"][-1]
    assert event["actor_name"] == "Admin User"
    assert event["reason"] == "Sold at market"
    assert event["previous_values"] == {"inventory_status": "In Stock"}
    assert event["new_values"] == {"inventory_status": "Sold"}
    replay = app.client.patch(url + "/status", json=body)
    assert replay.json() == changed.json()
    assert app.client.patch(url + "/status", json={**body, "reason": "Different"}).status_code == 409
    assert app.client.patch(url + "/status", json=mutation(inventory_status="Spoiled", reason="Expired")).status_code == 409
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(ScanStatusLog)) == 2


def test_correction_preserves_original_and_source_only_is_not_override(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    source = app.client.patch(url, json=mutation(source_text="Farm B", reason="Source correction"))
    assert source.status_code == 200, source.text
    assert source.json()["is_overridden"] is False
    corrected = app.client.patch(url, json=mutation(2, spoilage_days="7", reason="Reviewed shelf life"))
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["original_ai_result"]["spoilage_days"] == "3"
    assert corrected.json()["is_overridden"] is True
    assert app.client.patch(url, json=mutation(3, inventory_status="Sold", reason="Incorrect endpoint")).status_code == 422


def test_detail_scope_note_privacy_missing_and_deleted(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    note = app.client.post(url + "/notes", json=mutation(note="Private review"))
    assert note.status_code == 200, note.text
    assert note.json()["revision"] == 2
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Operator", role=SimpleNamespace(name="Operator"))
    detail = app.client.get(url)
    assert detail.status_code == 200
    assert detail.json()["notes"] == []
    assert all(event["kind"] != "note" for event in detail.json()["history"])
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), full_name="Other", role=SimpleNamespace(name="Operator"))
    assert app.client.get(url).status_code == 403
    with Session(app.engine) as db:
        db.delete(db.get(Scan, app.ids.scan))
        db.commit()
    assert app.client.get(url).status_code == 403
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Operator", role=SimpleNamespace(name="Operator"))
    assert app.client.get(url).status_code == 410
    assert app.client.get(f"/api/v1/scans/{uuid4()}").status_code == 404


def test_flag_noop_and_note_replay_do_not_duplicate_history(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    noop = app.client.patch(url + "/flag", json=mutation(flagged=False))
    assert noop.status_code == 200, noop.text
    assert noop.json()["revision"] == 1
    body = mutation(note="Review")
    first = app.client.post(url + "/notes", json=body)
    second = app.client.post(url + "/notes", json=body)
    assert first.json() == second.json()
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(ScanNote)) == 1


@pytest.mark.parametrize("suffix,body", [("/status", {"inventory_status": "Sold", "reason": " "}),
                                         ("", {"cultivar": "Lakatan", "reason": " "}),
                                         ("/flag", {"flagged": True})])
def test_missing_precondition_or_blank_reason_rejected(application, suffix, body):
    response = application.client.patch(f"/api/v1/scans/{application.ids.scan}{suffix}", json=body)
    assert response.status_code == 422
