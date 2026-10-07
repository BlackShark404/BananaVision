"""Remaining maintenance integration, using disposable databases and fake hardware only."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scan, ActivityLog, SystemConfig, Device
from tests.test_time_and_writes import application, SessionAdapter  # noqa: F401


@pytest.mark.asyncio
async def test_retention_preserves_all_persisted_history(application, monkeypatch, tmp_path):
    from app.services import data_retention
    monkeypatch.setattr(data_retention, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(data_retention, 'settings', SimpleNamespace(capture_path=tmp_path, max_captures_retention_days=1))
    with Session(application.engine) as db:
        db.scalar(select(SystemConfig)).camera_ids = 'CAM-001, CAM-002, CAM-003, CAM-004'
        before_scans = set(db.scalars(select(Scan.id)))
        before_logs = set(db.scalars(select(ActivityLog.id)))
        db.commit()
    await data_retention._run_retention_cycle()
    with Session(application.engine) as db:
        assert set(db.scalars(select(Scan.id))) == before_scans
        assert set(db.scalars(select(ActivityLog.id))) >= before_logs


@pytest.mark.asyncio
async def test_devices_use_real_logical_mapping_not_cam_number(application, monkeypatch):
    from app.api.v1 import devices
    fake = SimpleNamespace(_device_ids=[4, 2], _logical_ids=['CAM-000', 'RIGHT'], probe_all=lambda: {4: True, 2: False})
    monkeypatch.setattr(devices, 'camera_manager', fake)
    with Session(application.engine) as db:
        db.add_all([Device(camera_id='CAM-000', label='Left', status='Offline'), Device(camera_id='RIGHT', label='Right', status='Online')])
        db.commit()
    async with SessionAdapter(application.engine, application.state) as db:
        rows = await devices.list_devices(db, SimpleNamespace())
    statuses = {row.camera_id: row.status for row in rows}
    assert statuses['CAM-000'] == 'Online'
    assert statuses['RIGHT'] == 'Offline'


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,status', [(503, 'failed'), (504, 'unknown'), (None, 'accepted')])
async def test_power_outcomes_are_durable_and_duplicate_retries_do_not_dispatch(application, monkeypatch, outcome, status):
    from app.services import power_control, runtime_operations
    from fastapi import HTTPException
    from uuid import uuid4
    local = runtime_operations.StationCoordinator()
    monkeypatch.setattr(power_control, 'coordinator', local)
    monkeypatch.setattr(power_control, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(power_control, 'boot_identity', lambda: 'test-boot')
    dispatch = AsyncMock(side_effect=HTTPException(outcome, 'Injected OS failure') if outcome else None)
    monkeypatch.setattr(power_control, '_schedule_power_action', dispatch)
    identifier = str(uuid4())
    result = await power_control.request_power('restart', identifier, application.ids.admin)
    assert result['status'] == status
    assert local.state == ('ready' if outcome == 503 else 'recovery-required' if outcome else 'power-accepted')
    assert await power_control.request_power('restart', identifier, application.ids.admin) == result
    assert dispatch.await_count == 1
    await power_control.reconcile_power()
    assert local.state != 'ready' if status != 'failed' else local.state == 'ready'
    monkeypatch.setattr(power_control, 'boot_identity', lambda: 'new-verified-host-boot')
    local.resume()
    await power_control.reconcile_power()
    assert local.state == 'ready'


@pytest.mark.asyncio
async def test_power_intent_commit_failure_never_dispatches(application, monkeypatch):
    from app.services import power_control, runtime_operations
    from uuid import uuid4
    local = runtime_operations.StationCoordinator()
    monkeypatch.setattr(power_control, 'coordinator', local)
    monkeypatch.setattr(power_control, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(power_control, 'boot_identity', lambda: 'test-boot')
    dispatch = AsyncMock()
    monkeypatch.setattr(power_control, '_schedule_power_action', dispatch)
    application.state.fail_commit = True
    with pytest.raises(RuntimeError):
        await power_control.request_power('shutdown', str(uuid4()), application.ids.admin)
    dispatch.assert_not_awaited()
    assert local.state == 'ready'

