"""Focused regression tests for client IP capture in ActivityLog across BananaVision."""

import ipaddress
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.http import _parse_ip, get_client_ip
from app.models import ActivityLog
from app.schemas.scan import (
    ScanFlagRequest,
    ScanNoteCreate,
    ScanOverrideRequest,
    ScanStatusUpdate,
)
from tests.test_time_and_writes import SessionAdapter, application  # noqa: F401


# ── 1. Unit tests for get_client_ip and _parse_ip ──────────────────────────────


def test_parse_ip_validation():
    assert _parse_ip("127.0.0.1") == "127.0.0.1"
    assert _parse_ip("192.168.1.100") == "192.168.1.100"
    assert _parse_ip("::1") == "::1"
    assert _parse_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:db8:85a3::8a2e:370:7334"
    assert _parse_ip("  10.0.0.1  ") == "10.0.0.1"
    # Invalid strings must return None, never fabricate
    assert _parse_ip("") is None
    assert _parse_ip(None) is None
    assert _parse_ip("testclient") is None
    assert _parse_ip("invalid-ip") is None
    assert _parse_ip("999.999.999.999") is None
    assert _parse_ip("<script>alert(1)</script>") is None


def test_get_client_ip_direct_and_missing():
    # Missing request or client
    assert get_client_ip(None) is None
    assert get_client_ip(SimpleNamespace(client=None)) is None
    assert get_client_ip(SimpleNamespace(client=SimpleNamespace(host=None))) is None
    assert get_client_ip(SimpleNamespace(client=SimpleNamespace(host="not-an-ip"))) is None

    # Valid direct peer
    req_ipv4 = SimpleNamespace(
        client=SimpleNamespace(host="192.168.1.50"),
        headers={},
    )
    assert get_client_ip(req_ipv4) == "192.168.1.50"

    req_ipv6 = SimpleNamespace(
        client=SimpleNamespace(host="2001:db8::1"),
        headers={},
    )
    assert get_client_ip(req_ipv6) == "2001:db8::1"


def test_get_client_ip_untrusted_proxy_ignores_forwarding_headers(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxies", [])

    # Client tries to spoof X-Forwarded-For and X-Real-IP
    req = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={
            "x-forwarded-for": "203.0.113.195, 10.0.0.1",
            "x-real-ip": "203.0.113.200",
        },
    )
    # Untrusted proxy: headers must be ignored; peer IP must be returned
    assert get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_trusted_proxy_resolves_forwarding(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1", "10.0.0.0/8"])

    # Trusted exact IP proxy with X-Forwarded-For
    req1 = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "203.0.113.195, 198.51.100.1"},
    )
    assert get_client_ip(req1) == "203.0.113.195"

    # Trusted CIDR proxy with X-Real-IP
    req2 = SimpleNamespace(
        client=SimpleNamespace(host="10.1.2.3"),
        headers={"x-real-ip": "198.51.100.42"},
    )
    assert get_client_ip(req2) == "198.51.100.42"

    # Trusted proxy with malformed forwarded header falls back to peer IP
    req3 = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "malicious_string, not_valid"},
    )
    assert get_client_ip(req3) == "127.0.0.1"


# ── 2. Integration tests for Scan Flag and Scan Note IP recording ─────────────


def test_scan_flag_and_note_record_client_ip(application):
    app = application
    # Configure test client with explicit 127.0.0.1 peer
    client = TestClient(app.app, client=("127.0.0.1", 50000))
    url = f"/api/v1/scans/{app.ids.scan}"

    # 1. Flag scan
    flag_body = ScanFlagRequest(
        request_id=uuid4(),
        expected_revision=1,
        flagged=True,
        reason="Quality issue detected",
    )
    flag_res = client.patch(url + "/flag", json=flag_body.model_dump(mode="json"))
    assert flag_res.status_code == 200, flag_res.text
    assert flag_res.json()["flagged"] is True

    # Verify ActivityLog in database
    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "scan_flag")
            .order_by(ActivityLog.id.desc())
        ).scalar_one_or_none()
        assert log is not None
        assert log.ip_address == "127.0.0.1"
        assert f"Scan {app.ids.scan}" in log.details

    # 2. Add review note
    note_body = ScanNoteCreate(
        request_id=uuid4(),
        expected_revision=2,
        note="Inspected bananas for surface defects",
    )
    note_res = client.post(url + "/notes", json=note_body.model_dump(mode="json"))
    assert note_res.status_code == 200, note_res.text

    # Verify ActivityLog for note in database
    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "scan_note")
            .order_by(ActivityLog.id.desc())
        ).scalar_one_or_none()
        assert log is not None
        assert log.ip_address == "127.0.0.1"
        assert f"Scan {app.ids.scan}" in log.details

    # 3. Scan override (correction)
    override_body = ScanOverrideRequest(
        request_id=uuid4(),
        expected_revision=3,
        cultivar="Cardaba",
        finger_count=6,
        reason="Corrected cultivar label",
    )
    override_res = client.patch(url, json=override_body.model_dump(mode="json"))
    assert override_res.status_code == 200, override_res.text

    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "scan_correction")
            .order_by(ActivityLog.id.desc())
        ).scalar_one_or_none()
        assert log is not None
        assert log.ip_address == "127.0.0.1"

    # 4. Scan status change
    status_body = ScanStatusUpdate(
        request_id=uuid4(),
        expected_revision=4,
        inventory_status="Sold",
        reason="Dispatched to customer",
    )
    status_res = client.patch(url + "/status", json=status_body.model_dump(mode="json"))
    assert status_res.status_code == 200, status_res.text

    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "scan_status")
            .order_by(ActivityLog.id.desc())
        ).scalar_one_or_none()
        assert log is not None
        assert log.ip_address == "127.0.0.1"


def test_activity_list_api_returns_ip_address_and_preserves_historical_null(application):
    app = application
    client = TestClient(app.app, client=("127.0.0.1", 50000))

    # Insert a historical record with null IP and a modern record with IP
    with Session(app.engine) as db:
        db.add_all([
            ActivityLog(
                user_id=app.ids.admin,
                action="scan_flag",
                details="Historical legacy flag record",
                ip_address=None,
            ),
            ActivityLog(
                user_id=app.ids.admin,
                action="scan_flag",
                details="Modern flag record with IP",
                ip_address="192.168.1.50",
            ),
        ])
        db.commit()

    # Query ActivityLog API
    res = client.get("/api/v1/activity?action=scan_flag")
    assert res.status_code == 200
    items = res.json()["items"]

    legacy = next(i for i in items if i["details"] == "Historical legacy flag record")
    modern = next(i for i in items if i["details"] == "Modern flag record with IP")

    # Historical record preserves null (which frontend renders as '—')
    assert legacy["ip_address"] is None
    # Modern record provides the actual captured IP
    assert modern["ip_address"] == "192.168.1.50"


def test_untrusted_proxy_header_not_spoofed_in_api(application, monkeypatch):
    app = application
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxies", [])

    client = TestClient(app.app, client=("127.0.0.1", 50000))
    url = f"/api/v1/scans/{app.ids.scan}"

    # Attempt to spoof client IP via header
    flag_body = ScanFlagRequest(
        request_id=uuid4(),
        expected_revision=1,
        flagged=True,
        reason="Header spoof attempt",
    )
    headers = {"X-Forwarded-For": "203.0.113.195"}
    res = client.patch(url + "/flag", json=flag_body.model_dump(mode="json"), headers=headers)
    assert res.status_code == 200

    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.details == f"Scan {app.ids.scan}, revision 2")
            .order_by(ActivityLog.id.desc())
        ).scalar_one()
        # Must record peer IP 127.0.0.1, NOT the spoofed 203.0.113.195
        assert log.ip_address == "127.0.0.1"


def test_trusted_proxy_header_honored_in_api(application, monkeypatch):
    app = application
    settings = get_settings()
    # Trust the proxy peer
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1"])

    client = TestClient(app.app, client=("127.0.0.1", 50000))
    url = f"/api/v1/scans/{app.ids.scan}"

    flag_body = ScanFlagRequest(
        request_id=uuid4(),
        expected_revision=1,
        flagged=True,
        reason="Legitimate proxied request",
    )
    headers = {"X-Forwarded-For": "203.0.113.195, 127.0.0.1"}
    res = client.patch(url + "/flag", json=flag_body.model_dump(mode="json"), headers=headers)
    assert res.status_code == 200

    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.details == f"Scan {app.ids.scan}, revision 2")
            .order_by(ActivityLog.id.desc())
        ).scalar_one()
        # Originating client IP extracted from leftmost forwarded IP
        assert log.ip_address == "203.0.113.195"


def test_config_update_records_client_ip(application):
    app = application
    client = TestClient(app.app, client=("127.0.0.1", 50000))

    res = client.patch("/api/v1/config", json={
        "expected_revision": 1,
        "confidence_threshold": 90,
    })
    assert res.status_code == 200

    with Session(app.engine) as db:
        log = db.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "config_changed")
            .order_by(ActivityLog.id.desc())
        ).scalar_one_or_none()
        assert log is not None
        assert log.ip_address == "127.0.0.1"
