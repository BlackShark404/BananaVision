"""Account/setup, full profile totals, camera settings, power outcomes and safe cleanup."""
import os
import subprocess
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.v1 import auth, cameras, config, users
from app.config import Settings
from app.core import database, startup
from app.core.security import create_access_token, hash_password, verify_password, decode_access_token
from app.core.time import now_manila
from app.models import ActivityLog, Device, Scan, ScanClassification, SystemConfig, UserAccount
from app.schemas.enums import CultivarEnum, RipenessEnum
from app.services import data_retention, power_control, scan_service
from app.services.capture_cleanup import remove_scan_captures
from tests.test_time_and_writes import application, SessionAdapter  # noqa: F401


@pytest.fixture
def secured(application):
    with Session(application.engine) as db:
        admin = db.get(UserAccount, application.ids.admin)
        admin.password_hash = hash_password("unique-admin-password")
        admin.requires_password_change = False
        db.commit()
    app = FastAPI()
    for router in (users.router, auth.router, cameras.router, config.router):
        app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "unique-admin-password"})
        assert response.status_code == 200, response.text
        token = response.json()["token"]["access_token"]
        yield SimpleNamespace(client=client, headers={"Authorization": f"Bearer {token}"}, app=application)


def test_unique_handoff_setup_scope_and_replay(secured):
    client, headers = secured.client, secured.headers
    accounts = [client.post("/api/v1/users", headers=headers, json={
        "username": f"created-{n}", "full_name": "Same Name", "role": "Operator",
    }) for n in range(2)]
    assert all(r.status_code == 201 for r in accounts), [r.text for r in accounts]
    first, second = [r.json() for r in accounts]
    assert first["temporary_password"] != second["temporary_password"]
    assert len(first["temporary_pin"]) == 4
    with Session(secured.app.engine) as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == first["username"]))
        assert verify_password(first["temporary_password"], account.password_hash)
        assert all(first["temporary_password"] not in (log.details or "") for log in db.scalars(select(ActivityLog)))
    listed = client.get("/api/v1/users", headers=headers).json()
    assert all("temporary_password" not in row for row in listed["items"])
    assert client.post("/api/v1/auth/setup-password", json={"username": first["username"], "new_password": "replacement-password"}).status_code == 422
    login = client.post("/api/v1/auth/login", json={"username": first["username"], "password": first["temporary_password"]}).json()
    token = login["setup_token"]
    assert decode_access_token(token)["scope"] == "setup_password"
    assert client.get("/api/v1/users/me/summary", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/api/v1/auth/setup-pin", json={"setup_token": token, "new_pin": "9876"}).status_code == 401
    assert client.post("/api/v1/auth/setup-password", json={"setup_token": token, "new_password": first["temporary_password"]}).status_code == 401
    response = client.post("/api/v1/auth/setup-password", json={"setup_token": token, "new_password": "replacement-password"})
    assert response.status_code == 200, response.text
    assert client.post("/api/v1/auth/setup-password", json={"setup_token": token, "new_password": "other-password"}).status_code == 401
    reset = client.post(f"/api/v1/users/{first['id']}/reset-password", headers=headers, json={})
    assert reset.status_code == 200 and reset.json()["temporary_password"] != first["temporary_password"]
    old_headers = {"Authorization": f"Bearer {response.json()['token']['access_token']}"}
    assert client.get("/api/v1/users/me/summary", headers=old_headers).status_code == 401
    swap = client.post("/api/v1/auth/swap", json={"username": first["username"], "pin": first["temporary_pin"]}).json()
    new_pin = "9876" if first["temporary_pin"] != "9876" else "6789"
    setup = client.post("/api/v1/auth/setup-pin", json={"setup_token": swap["setup_token"], "new_pin": new_pin})
    assert setup.status_code == 200, setup.text
    assert client.post("/api/v1/auth/setup-pin", json={"setup_token": swap["setup_token"], "new_pin": "2468"}).status_code == 401
    expired = create_access_token(decode_access_token(swap["setup_token"]), expires_delta=timedelta(seconds=-1))
    assert client.post("/api/v1/auth/setup-pin", json={"setup_token": expired, "new_pin": "2468"}).status_code == 401


def test_profile_aggregates_all_rows_and_immutable_owner(secured):
    fixture = secured.app
    with Session(fixture.engine) as db:
        operator = db.get(UserAccount, fixture.ids.operator)
        operator.full_name = "Same Name"
        operator.password_hash = hash_password("operator-password")
        operator.requires_password_change = False
        now = now_manila()
        for _ in range(130):
            scan = Scan(operator_id=fixture.ids.profile, date_time=now)
            scan.classification = ScanClassification(cultivar=CultivarEnum.LAKATAN,
                ripeness=RipenessEnum.RIPE, confidence=80, spoilage_days="3", finger_count=5)
            db.add(scan)
        db.add_all([ActivityLog(user_id=fixture.ids.operator, action="login", details="Own activity"),
                    ActivityLog(user_id=fixture.ids.admin, action="login", details="Private admin activity")])
        db.commit()
    token = secured.client.post("/api/v1/auth/login", json={"username": "operator", "password": "operator-password"}).json()["token"]["access_token"]
    summary = secured.client.get("/api/v1/users/me/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary.status_code == 200, summary.text
    result = summary.json()
    assert result["total_scans"] == 131 and result["last_7_days"] == 130
    assert result["avg_confidence"] == pytest.approx((130 * 80 + 90) / 131)
    assert result["total_users"] is None
    assert all(log["details"] != "Private admin activity" for log in result["activity"])
    assert secured.client.get("/api/v1/users/me/summary", headers=secured.headers).json()["total_users"] == 2


@pytest.mark.asyncio
async def test_bootstrap_requires_explicit_secret_and_forces_replacement(application, monkeypatch):
    with Session(application.engine) as db:
        # Fresh disposable schema, never the deployed database.
        database.Base.metadata.drop_all(application.engine)
        database.Base.metadata.create_all(application.engine)
    monkeypatch.setattr(startup, "get_settings", lambda: SimpleNamespace(bootstrap_admin_password=None))
    async with SessionAdapter(application.engine, application.state) as db:
        with pytest.raises(RuntimeError, match="BOOTSTRAP_ADMIN_PASSWORD"):
            await startup._seed_default_data(db)
    settings = Settings(_env_file=None, bootstrap_admin_password="random-bootstrap-secret")
    monkeypatch.setattr(startup, "get_settings", lambda: settings)
    async with SessionAdapter(application.engine, application.state) as db:
        await startup._seed_default_data(db)
    with Session(application.engine) as db:
        account = db.scalar(select(UserAccount))
        assert account.requires_password_change
        assert verify_password("random-bootstrap-secret", account.password_hash)


@pytest.mark.parametrize("ids", [[], [0, 0], [-1], [0, 1, 2, 3, 4], [True], ["0"]])
def test_camera_mapping_rejects_invalid_values(secured, ids):
    assert secured.client.post("/api/v1/cameras/mapping", headers=secured.headers, json={"device_ids": ids}).status_code == 422


def test_camera_remap_updates_existing_settings_and_runtime(secured, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = cameras.settings
    previous_ids = list(settings.camera_device_ids)
    monkeypatch.setattr(settings, "camera_device_ids", previous_ids)
    fake = SimpleNamespace(release_all=lambda: None, initialize=lambda: {2: True, 0: False}, _device_ids=[], _labels=[])
    monkeypatch.setattr(cameras, "camera_manager", fake)
    response = secured.client.post("/api/v1/cameras/mapping", headers=secured.headers, json={"device_ids": [2, 0]})
    assert response.status_code == 200, response.text
    assert startup.settings is settings and settings.camera_device_ids == fake._device_ids == [2, 0]
    assert "CAMERA_DEVICE_IDS=[2, 0]" in (tmp_path / ".env").read_text()


def test_camera_rename_preserves_device_identity_and_commits_runtime(secured, monkeypatch):
    with Session(secured.app.engine) as db:
        cfg = db.scalar(select(SystemConfig))
        cfg.camera_ids = "LEFT, RIGHT"
        left = Device(camera_id="LEFT", label="Left", status="Online", resolution="640x480")
        right = Device(camera_id="RIGHT", label="Right", status="Offline", resolution=None)
        db.add_all([left, right])
        db.commit()
        left_id, right_id = left.id, right.id
    changed = []
    monkeypatch.setattr(config.camera_manager, "set_logical_ids", changed.append)
    response = secured.client.patch("/api/v1/config", headers=secured.headers, json={"camera_ids": "RIGHT, LEFT"})
    assert response.status_code == 200, response.text
    with Session(secured.app.engine) as db:
        assert db.get(Device, left_id).camera_id == "RIGHT"
        assert db.get(Device, right_id).camera_id == "LEFT"
        assert db.get(Device, left_id).status.value == "Online"
    assert changed == [["RIGHT", "LEFT"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [0, 1, OSError("Permission denied"), subprocess.TimeoutExpired("shutdown", 5)])
async def test_power_command_outcomes_are_checked(monkeypatch, outcome):
    calls = []
    monkeypatch.setattr(power_control.platform, "system", lambda: "Windows")
    def run(command, **kwargs):
        calls.append(command)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(returncode=outcome)
    monkeypatch.setattr(power_control.subprocess, "run", run)
    if outcome == 0:
        await power_control.schedule_power_action("restart")
    else:
        with pytest.raises(HTTPException) as exc:
            await power_control.schedule_power_action("restart")
        assert exc.value.status_code == 503
    assert calls == [["shutdown", "/r", "/t", "10"]]


@pytest.mark.asyncio
async def test_retention_disabled_failed_commit_and_safe_orphans(application, tmp_path, monkeypatch):
    settings = SimpleNamespace(capture_path=tmp_path, max_captures_retention_days=30)
    monkeypatch.setattr(data_retention, "settings", settings)
    monkeypatch.setattr(data_retention, "async_session_factory", lambda: SessionAdapter(application.engine, application.state))
    existing, orphan, recent = str(application.ids.scan), str(uuid4()), str(uuid4())
    for name in (existing, orphan, recent, "unrelated"):
        folder = tmp_path / name
        folder.mkdir()
        image = folder / "camera.jpg"
        image.write_bytes(b"fixture")
        if name != recent:
            old = (now_manila() - timedelta(days=40)).timestamp()
            os.utime(image, (old, old))
            os.utime(folder, (old, old))
    with Session(application.engine) as db:
        db.scalar(select(SystemConfig)).data_retention_enabled = False
        db.commit()
    await data_retention._run_retention_cycle()
    assert (tmp_path / orphan).exists()
    with Session(application.engine) as db:
        db.scalar(select(SystemConfig)).data_retention_enabled = True
        db.commit()
    application.state.fail_commit = True
    with pytest.raises(RuntimeError):
        await data_retention._run_retention_cycle()
    assert (tmp_path / existing).exists() and (tmp_path / orphan).exists()
    application.state.fail_commit = False
    await data_retention._run_retention_cycle()
    assert not (tmp_path / existing).exists() and not (tmp_path / orphan).exists()
    assert (tmp_path / recent).exists() and (tmp_path / "unrelated").exists()
    with pytest.raises(ValueError):
        remove_scan_captures(tmp_path, "../outside")


@pytest.mark.asyncio
async def test_failed_scan_removes_partial_captures(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_service, "get_settings", lambda: SimpleNamespace(capture_path=tmp_path))
    async def capture_all():
        return [SimpleNamespace(frame=None)]
    def save(captures, scan_id):
        directory = tmp_path / scan_id
        directory.mkdir()
        (directory / "partial.jpg").write_bytes(b"fixture")
        raise OSError("Disk write failed halfway through capture")
    monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(online_cameras=[0], capture_all=capture_all, save_captures=save))
    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", AsyncMock())
    with pytest.raises(OSError, match="halfway"):
        await scan_service.execute_scan_pipeline(SimpleNamespace(), uuid4(), uuid4(), "Operator")
    assert list(tmp_path.iterdir()) == []
