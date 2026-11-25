"""Audit rows for record changes, exports, printing and scans.

Every test runs on the isolated SQLite fixture from ``test_time_and_writes`` (or a disposable
PostgreSQL schema when ``BANANAVISION_TEST_DATABASE_URL`` is set). No live station database,
captures, cameras or printers are touched.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import cameras, printing, scan_logs
from app.models import ActivityLog, Intake, PrintJob, Scan
from app.schemas.enums import IntakeStatusEnum
from app.services import configuration, print_jobs, scan_service
from tests.test_scan_records import mutation
from tests.test_scan_records_postgresql import station as station_fixture
from tests.test_scan_trigger import scan_station as scan_station_fixture
from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application_fixture

# Shared pytest fixtures: the isolated SQLite station, its scan pipeline and PostgreSQL.
application = application_fixture
scan_station = scan_station_fixture
station = station_fixture


def rows(app, action=None):
    with Session(app.engine) as db:
        query = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
        if action:
            query = query.where(ActivityLog.action == action)
        return db.scalars(query).all()


def details(app, action):
    return [row.details for row in rows(app, action)]


# ── Users ─────────────────────────────────────────────────────────────────────

def test_created_user_names_identity_role_and_status_but_no_credential(application):
    app = application
    response = app.client.post("/api/v1/users", json={
        "username": "new-op", "full_name": "New Operator", "role": "Operator",
        "status": "Inactive",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    [row] = rows(app, "user_created")
    assert row.details == (
        f"Created user 'new-op' ({body['id']}) with role Operator, status Inactive; "
        "temporary credentials issued"
    )
    assert body["temporary_password"] not in row.details
    assert row.user_id == app.ids.admin


def test_user_update_records_old_and_new_values_and_skips_no_op(application):
    app = application
    url = f"/api/v1/users/{app.ids.operator}"
    client = TestClient(app.app, client=("10.1.2.3", 50000))
    first = client.patch(url, json={"username": "op-two", "full_name": "Renamed Operator"})
    assert first.status_code == 200, first.text
    [row] = rows(app, "user_updated")
    assert row.details == (
        f"Updated user 'operator' ({app.ids.operator}): username 'operator' → 'op-two'; "
        "full_name 'Original Name' → 'Renamed Operator'"
    )
    assert row.user_id == app.ids.admin and row.ip_address == "10.1.2.3"
    # Saving the same values again changes nothing, so nothing is logged.
    again = client.patch(url, json={"username": "op-two", "full_name": "Renamed Operator"})
    assert again.status_code == 200, again.text
    assert len(rows(app, "user_updated")) == 1
    avatar = client.patch(url, json={"avatar_url": "data:image/png;base64,U0VDUkVU"})
    assert avatar.status_code == 200, avatar.text
    [_, avatar_row] = rows(app, "user_updated")
    assert avatar_row.details == f"Updated user 'op-two' ({app.ids.operator}): avatar_url changed"


def test_role_and_status_changes_have_their_own_actions_and_note_revoked_sessions(application):
    app = application
    url = f"/api/v1/users/{app.ids.operator}"
    promoted = app.client.patch(url, json={"role": "Admin"})
    assert promoted.status_code == 200, promoted.text
    [role_row] = rows(app, "user_role_changed")
    assert role_row.details.startswith(
        f"Updated user 'operator' ({app.ids.operator}): role Operator → Admin"
    )
    assert role_row.details.endswith("; sessions revoked")
    disabled = app.client.patch(url, json={"status": "Inactive"})
    assert disabled.status_code == 200, disabled.text
    assert details(app, "user_status_changed") == [
        f"Updated user 'operator' ({app.ids.operator}): status Active → Inactive; "
        "sessions revoked"
    ]
    assert rows(app, "user_updated") == []


def test_own_avatar_change_is_logged_without_the_image(application):
    app = application
    image = "data:image/png;base64," + "QUJD" * 20
    response = app.client.patch("/api/v1/users/me/profile", json={"avatar_url": image})
    assert response.status_code == 200, response.text
    assert details(app, "profile_updated") == [
        f"Updated profile of user 'admin' ({app.ids.admin}): avatar changed"
    ]
    # The same image again, or no change at all, is not a new event.
    for body in ({"avatar_url": image}, {}):
        assert app.client.patch("/api/v1/users/me/profile", json=body).status_code == 200
    assert len(rows(app, "profile_updated")) == 1


def test_credential_resets_are_logged_without_the_temporary_credential(application):
    app = application
    url = f"/api/v1/users/{app.ids.operator}"
    password = app.client.post(url + "/reset-password", json={})
    assert password.status_code == 200, password.text
    assert details(app, "password_reset") == [
        f"Reset password for user 'operator' ({app.ids.operator}); setup required; "
        "sessions revoked"
    ]
    assert password.json()["temporary_password"] not in details(app, "password_reset")[0]
    pin = app.client.post(url + "/reset-pin", json={})
    assert pin.status_code == 200, pin.text
    assert details(app, "pin_reset") == [
        f"Reset PIN for user 'operator' ({app.ids.operator}); setup required; sessions revoked"
    ]
    assert rows(app, "user_updated") == []


# ── Suppliers and intakes ─────────────────────────────────────────────────────

def test_supplier_rows_record_values_but_never_contact_details(application):
    app = application
    created = app.client.post("/api/v1/suppliers", json={
        "name": "Farm North", "contact_person": "Ana Reyes", "contact_phone": "0917-555-0101",
    })
    assert created.status_code == 201, created.text
    supplier_id = created.json()["id"]
    assert details(app, "supplier_created") == [
        f"Created supplier 'Farm North' ({supplier_id}), status Active"
    ]
    url = f"/api/v1/suppliers/{supplier_id}"
    updated = app.client.patch(url, json={
        "name": "Farm South", "contact_phone": "0918-555-0102", "status": "Inactive",
    })
    assert updated.status_code == 200, updated.text
    [row] = rows(app, "supplier_updated")
    assert row.details == (
        f"Updated supplier 'Farm North' ({supplier_id}): name 'Farm North' → 'Farm South'; "
        "contact_phone changed; status Active → Inactive"
    )
    assert "0918" not in row.details and "0917" not in row.details
    assert app.client.patch(url, json={"name": "Farm South"}).status_code == 200
    assert len(rows(app, "supplier_updated")) == 1


def test_intake_creation_names_supplier_batch_source_and_treatment(application):
    app = application
    created = app.client.post("/api/v1/intakes", json={
        "supplier_id": str(app.ids.supplier), "batch_number": "B-17", "source": "Kiosk",
        "treatment": "Ethephon",
    })
    assert created.status_code == 200, created.text
    assert details(app, "intake_created") == [
        f"Created intake {created.json()['id']} for supplier 'Original Supplier' "
        f"({app.ids.supplier}): batch 'B-17', source 'Kiosk', treatment Ethephon"
    ]


def test_manual_intake_status_change_records_old_and_new_and_skips_no_op(application):
    app = application
    url = f"/api/v1/intakes/{app.ids.intake}/status"
    assert app.client.patch(url, json={"status": "Depleted"}).status_code == 200
    assert app.client.patch(url, json={"status": "Depleted"}).status_code == 200
    assert details(app, "intake_status_changed") == [
        f"Intake {app.ids.intake} status Active → Depleted"
    ]


def test_bulk_inventory_summary_has_counts_reason_and_intake_change(application):
    app = application
    reason = "Dispatched to the Tuesday market " + "x" * 300
    response = app.client.patch(f"/api/v1/intakes/{app.ids.intake}/bulk-inventory", json={
        "inventory_status": "Sold", "request_id": str(uuid4()),
        "expected_revisions": {str(app.ids.scan): 1}, "reason": reason,
    })
    assert response.status_code == 200, response.text
    [summary] = rows(app, "intake_status_changed")
    assert summary.details.startswith(
        f"Bulk inventory for intake {app.ids.intake}: 1 of 1 scans set to Sold; "
        "reason 'Dispatched to the Tuesday market xxx"
    )
    assert summary.details.endswith("…'; intake status Active → Depleted")
    assert len(summary.details) < 400
    [scan_row] = rows(app, "scan_status")
    assert scan_row.details.startswith(
        f"Scan {app.ids.scan}, revision 2: inventory_status In Stock → Sold; "
        "reason 'Dispatched to the Tuesday market"
    )


# ── Scan edits ────────────────────────────────────────────────────────────────

def test_scan_changes_list_each_changed_field_and_the_reason(application):
    app = application
    url = f"/api/v1/scans/{app.ids.scan}"
    flag = app.client.patch(url + "/flag", json=mutation(1, flagged=True, reason="Bruised"))
    assert flag.status_code == 200, flag.text
    assert details(app, "scan_flag") == [
        f"Scan {app.ids.scan}, revision 2: flagged False → True; reason 'Bruised'"
    ]
    correction = app.client.patch(url, json=mutation(
        2, cultivar="Latundan", ripeness="Ripe", finger_count=6, reason="Counted by hand",
    ))
    assert correction.status_code == 200, correction.text
    # Ripeness was already Ripe, so only the two real changes are listed.
    assert details(app, "scan_correction") == [
        f"Scan {app.ids.scan}, revision 3: cultivar Lakatan → Latundan; finger_count 5 → 6; "
        "reason 'Counted by hand'"
    ]


def test_scan_note_text_is_never_written_to_the_audit_log(application):
    app = application
    note = "Buyer phone 0917-555-0199; pallet 4"
    response = app.client.post(
        f"/api/v1/scans/{app.ids.scan}/notes", json=mutation(1, note=note),
    )
    assert response.status_code == 200, response.text
    [row] = rows(app, "scan_note")
    assert row.details == f"Scan {app.ids.scan}, revision 2: note added ({len(note)} chars)"
    assert all("0917" not in (entry.details or "") for entry in rows(app))


# ── Configuration ─────────────────────────────────────────────────────────────

def test_config_change_records_old_and_new_values_and_skips_no_op(application):
    app = application
    changed = app.client.patch("/api/v1/config", json={
        "expected_revision": 1, "confidence_threshold": 90, "data_retention_enabled": False,
    })
    assert changed.status_code == 200, changed.text
    assert details(app, "config_changed") == [
        "Config revision 1 → 2: confidence_threshold 85 → 90; "
        "data_retention_enabled True → False"
    ]
    same = app.client.patch("/api/v1/config", json={
        "expected_revision": 2, "confidence_threshold": 90,
    })
    assert same.status_code == 200, same.text
    assert len(rows(app, "config_changed")) == 1


def test_camera_mapping_records_old_and_new_device_indices(application, monkeypatch):
    app = application
    monkeypatch.setattr(configuration, "apply_camera_config", AsyncMock())
    monkeypatch.setattr(configuration, "sync_devices", AsyncMock())
    app.app.include_router(cameras.router, prefix="/api/v1")
    response = app.client.post("/api/v1/cameras/mapping", json={
        "expected_revision": 1, "operation_id": str(uuid4()), "device_ids": [1, 0, 2, 3],
    })
    assert response.status_code == 200, response.text
    assert details(app, "config_changed") == [
        "Camera mapping revision 1 → 2: camera_device_ids '0, 1, 2, 3' → '1, 0, 2, 3'"
    ]


# ── Scan pipeline ─────────────────────────────────────────────────────────────

def as_scanning_operator(app):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )


@pytest.mark.parametrize("linked", [True, False])
def test_saved_scan_row_names_the_scan_and_its_intake_and_auto_label_is_not_logged(
    scan_station, linked,
):
    app, submit = scan_station
    as_scanning_operator(app)
    response = app.client.post("/api/v1/scans/trigger", json={
        "intake_id": str(app.ids.intake) if linked else None,
    })
    assert response.status_code == 200, response.text
    scan_id = response.json()["id"]
    where = f"intake {app.ids.intake}" if linked else "no intake"
    [row] = rows(app, "scan_created")
    assert row.details.startswith(f"Scan {scan_id} ({where}): Scanned Lakatan (Ripe)")
    # The automatic label is printed, but it is not a person's print request.
    assert submit.call_count == 1
    assert rows(app, "label_print_requested") == [] and rows(app, "label_print_retried") == []


def test_capture_fault_is_logged_as_scan_failed_not_as_a_rejection(scan_station, monkeypatch):
    app, _ = scan_station
    as_scanning_operator(app)

    async def no_frames():
        return []

    monkeypatch.setattr(scan_service.camera_manager, "capture_all", no_frames)
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 503, response.text
    [row] = rows(app, "scan_failed")
    assert row.details.startswith("Scan ")
    assert row.details.endswith(
        "(no intake) failed (capture_unavailable): no camera produced a frame"
    )
    assert row.user_id == app.ids.operator
    assert rows(app, "scan_rejected") == []


def test_inactive_intake_conflict_is_logged_as_scan_failed(scan_station):
    app, _ = scan_station
    as_scanning_operator(app)
    with Session(app.engine) as db:
        db.get(Intake, app.ids.intake).status = IntakeStatusEnum.DEPLETED
        db.commit()
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(app.ids.intake)})
    assert response.status_code == 409, response.text
    [row] = rows(app, "scan_failed")
    assert f"(intake {app.ids.intake}) failed (409): This intake is no longer active" in row.details
    with Session(app.engine) as db:
        assert db.query(Scan).count() == 1


def test_out_of_distribution_rejection_is_logged_once(scan_station, monkeypatch):
    app, _ = scan_station
    as_scanning_operator(app)
    monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
        detect=lambda _: SimpleNamespace(banana_detected=False, boxes=[], best_confidence=0.0),
    ))
    response = app.client.post("/api/v1/scans/trigger", json={})
    assert response.status_code == 422, response.text
    [row] = rows(app, "scan_rejected")
    assert row.details.startswith("Scan rejected (no_banana): ")
    assert rows(app, "scan_failed") == []


# ── Printing ──────────────────────────────────────────────────────────────────

@pytest.fixture
def printer(application, monkeypatch):
    application.app.include_router(printing.router, prefix="/api/v1")
    submit = MagicMock(side_effect=RuntimeError("Printer offline"))
    monkeypatch.setattr(print_jobs, "print_prediction_label", submit)
    monkeypatch.setattr(print_jobs, "get_settings", lambda: SimpleNamespace(
        bananavision_printer_name="Fixture Printer", bananavision_label_width_mm=40,
        bananavision_label_height_mm=30,
    ))
    application.submit = submit
    return application


def test_manual_print_and_retry_are_each_logged_once(printer):
    app = printer
    url = f"/api/v1/scans/{app.ids.scan}"
    job_id = str(uuid4())
    body = {"request_id": job_id, "quantity": 2}
    assert app.client.post(url + "/print", json=body).status_code == 200
    # Delivering the same request again is a replay, not a second print request.
    assert app.client.post(url + "/print", json=body).status_code == 200
    assert details(app, "label_print_requested") == [
        f"Print job {job_id} for scan {app.ids.scan}: 2 labels on printer 'Fixture Printer'"
    ]
    app.submit.side_effect = None
    app.submit.return_value = 715
    retry_url = url + f"/print-jobs/{job_id}/retry"
    assert app.client.post(retry_url, json={"expected_attempt": 1}).status_code == 200
    assert app.client.post(retry_url, json={"expected_attempt": 1}).status_code == 409
    assert details(app, "label_print_retried") == [
        f"Retried print job {job_id} for scan {app.ids.scan}: 2 labels on printer "
        "'Fixture Printer' (attempt 2)"
    ]
    with Session(app.engine) as db:
        assert db.scalar(select(PrintJob.status)) == "SUBMITTED"


# ── Exports ───────────────────────────────────────────────────────────────────

def test_inventory_summary_export_is_logged(application):
    app = application
    for kind in ("xlsx", "pdf"):
        response = app.client.get("/api/v1/config/export", params={"format": kind})
        assert response.status_code == 200, response.text
    assert details(app, "data_exported") == [
        "Exported inventory summary (xlsx): 1 scan",
        "Exported inventory summary (pdf): 1 scan",
    ]


def test_inventory_summary_export_fails_closed_without_its_audit_row(application):
    app = application
    app.state.fail_commit = True
    response = app.client.get("/api/v1/config/export")
    app.state.fail_commit = False
    assert response.status_code == 500
    assert b"PK\x03\x04" not in response.content
    assert rows(app, "data_exported") == []


@pytest.fixture
def logs(application, monkeypatch):
    class Rows:
        def __init__(self, result):
            self.result = result

        async def partitions(self, size):
            for batch in self.result.partitions(size):
                yield batch

        async def close(self):
            self.result.close()

    async def stream(adapter, statement):
        return Rows(adapter.session.execute(statement))

    # The SQLite adapter has no server-side cursor; a buffered result streams the same rows.
    monkeypatch.setattr(SessionAdapter, "stream", stream, raising=False)
    with application.engine.connect() as connection:  # PostgreSQL string functions
        raw = connection.connection.driver_connection
        raw.create_function("btrim", 2, lambda value, chars: value.strip(chars) if value else value)
        raw.create_function("split_part", 3, lambda value, sep, n: (
            None if value is None else (value.split(sep) + [""] * n)[n - 1]
        ))
    application.app.include_router(scan_logs.router, prefix="/api/v1")
    return application


def test_scan_log_export_is_logged_with_format_scope_and_filters(logs):
    app = logs
    response = app.client.get("/api/v1/scan-logs/export", params={
        "cultivar": "Lakatan", "search": "Original\nSupplier", "flagged_only": "false",
        "page": 3,
    })
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"PK\x03\x04")
    pdf = app.client.get("/api/v1/scan-logs/export", params={"format": "pdf"})
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-1.4\n")
    # The export stream's session never commits; the audit row has its own transaction.
    assert details(app, "data_exported") == [
        "Exported scan logs (xlsx, all accounts): filters cultivar Lakatan, "
        "search 'Original Supplier'",
        "Exported scan logs (pdf, all accounts): filters none",
    ]
    assert {row.user_id for row in rows(app, "data_exported")} == {app.ids.admin}


def test_scan_log_export_by_an_operator_names_its_scope(logs):
    app = logs
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, token_version=1, full_name="Original Name",
        role=SimpleNamespace(name="Operator"),
    )
    response = app.client.get("/api/v1/scan-logs/export", params={"inventory_status": "Sold"})
    assert response.status_code == 200, response.text
    assert details(app, "data_exported") == [
        "Exported scan logs (xlsx, own scans): filters inventory_status Sold"
    ]


def test_scan_log_export_fails_closed_when_the_audit_write_fails(logs):
    app = logs
    app.state.fail_commit = True
    response = app.client.get("/api/v1/scan-logs/export")
    app.state.fail_commit = False
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == "5"
    assert str(app.ids.scan) not in response.text
    assert rows(app, "data_exported") == []


def test_refused_scan_log_export_is_not_logged_as_an_export(logs):
    app = logs
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, token_version=1, full_name="Original Name",
        role=SimpleNamespace(name="Auditor"),
    )
    assert app.client.get("/api/v1/scan-logs/export").status_code == 403
    assert rows(app, "data_exported") == []


def test_snapshot_export_that_fails_validation_is_not_logged_as_an_export(logs):
    """An expired or unknown browse snapshot is refused before the export row is written."""
    app = logs
    response = app.client.get("/api/v1/scan-logs/export",
                              params={"snapshot_id": str(uuid4()), "stable": "true"})
    assert response.status_code == 410, response.text
    assert rows(app, "data_exported") == []


# ── PostgreSQL: the export audit row is written before the snapshot lock ──────

@pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required",
)
@pytest.mark.asyncio
async def test_snapshot_export_audit_row_does_not_wait_on_its_own_lock(station, monkeypatch):
    from starlette.requests import Request

    from app.core import database
    from app.models import UserAccount
    from app.schemas.scan_logs import ScanLogQuery
    from app.services.scan_logs import list_scan_logs

    x = station

    def audit_sessions():
        # Were the audit insert made after the snapshot lock, it would wait on this request's
        # own row lock for ever; the lock timeout turns that into a quick failure (503).
        session = x.sessions()

        @event.listens_for(session.sync_session, "after_begin")
        def limit_lock_wait(_session, _transaction, connection):
            connection.exec_driver_sql("SET LOCAL lock_timeout = '3s'")

        return session

    monkeypatch.setattr(database, "async_session_factory", audit_sessions)
    async with x.sessions() as db:
        user = await db.get(UserAccount, x.actors[0])
        saved = await list_scan_logs(db, user, ScanLogQuery(stable=True))
        await db.commit()
    peer = Request({"type": "http", "method": "GET", "path": "/api/v1/scan-logs/export",
                    "headers": [], "query_string": b"", "client": ("10.0.0.7", 5000)})
    async with x.sessions() as stream:
        user = await stream.get(UserAccount, x.actors[0])
        query = ScanLogQuery(snapshot_id=saved.snapshot_id, stable=True)
        response = await scan_logs.scan_logs_export(peer, stream, user, query)
        body = response.body
        await stream.rollback()
    assert body.startswith(b"PK\x03\x04")
    async with x.sessions() as db:
        [row] = (await db.execute(
            select(ActivityLog).where(ActivityLog.action == "data_exported")
        )).scalars().all()
    assert row.user_id == x.actors[0] and row.ip_address == "10.0.0.7"
    assert row.details.startswith("Exported scan logs (xlsx, all accounts): filters none")
    assert f"snapshot {saved.snapshot_id}" in row.details
