"""Remaining maintenance integration, using disposable databases and fake hardware only."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scan, ActivityLog, Device
from tests.test_time_and_writes import application, SessionAdapter  # noqa: F401


@pytest.mark.asyncio
async def test_retention_preserves_all_persisted_history(application, monkeypatch, tmp_path):
    from app.services import data_retention
    monkeypatch.setattr(data_retention, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(data_retention, 'settings', SimpleNamespace(capture_path=tmp_path, max_captures_retention_days=1))
    with Session(application.engine) as db:
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



@pytest.mark.asyncio
async def test_power_cancellation_resumes_runtime_once(application, monkeypatch):
    from app.services import power_control, runtime_operations
    from uuid import uuid4
    local = runtime_operations.StationCoordinator()
    monkeypatch.setattr(power_control, 'coordinator', local)
    monkeypatch.setattr(power_control, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(power_control, 'boot_identity', lambda: 'test-boot')
    dispatch = AsyncMock()
    monkeypatch.setattr(power_control, '_schedule_power_action', dispatch)
    await power_control.request_power('restart', str(uuid4()), application.ids.admin)
    initialized = []
    async def initialize():
        assert local.state != 'ready'
        initialized.append(True)
    local.runtime_resume = initialize
    first = await power_control.cancel_power()
    second = await power_control.cancel_power()
    assert first == second and first['status'] == 'cancelled'
    assert initialized == [True]
    assert local.state == 'ready'
    assert [call.args[0] for call in dispatch.await_args_list] == ['restart', 'cancel']


def test_recovery_login_is_admin_only_and_does_not_change_application_data(application, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1 import auth
    from app.services import audit, runtime_operations, maintenance_state
    from app.core.security import hash_password, decode_access_token
    from app.models import UserAccount, MaintenanceState
    from sqlalchemy import func
    local = runtime_operations.StationCoordinator()
    local.block('recovery-required')
    monkeypatch.setattr(runtime_operations, 'coordinator', local)
    # Production has one coordinator: audit events raised while it is blocked are deferred.
    monkeypatch.setattr(audit, 'coordinator', local)
    monkeypatch.setattr(maintenance_state, 'auth_generation', 'old-process-generation')
    with Session(application.engine) as db:
        for user in db.scalars(select(UserAccount)):
            user.password_hash = hash_password('Recovery-test-123')
        db.add(MaintenanceState(id=1, auth_generation='restored-generation', operations={}))
        db.commit()
        before = [(u.id, u.last_active, u.updated_at) for u in db.scalars(select(UserAccount).order_by(UserAccount.id))]
        logs = db.scalar(select(func.count()).select_from(ActivityLog))
    app = FastAPI()
    app.include_router(auth.router, prefix='/api/v1')
    app.add_middleware(runtime_operations.StationAdmissionMiddleware)
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/login', json={'username':'admin','password':'Recovery-test-123'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'success'
        assert decode_access_token(response.json()['token']['access_token'])['sg'] == 'restored-generation'
        assert client.post('/api/v1/auth/login', json={'username':'operator','password':'Recovery-test-123'}).status_code == 403
        client.post('/api/v1/auth/login', json={'username':'admin','password':'incorrect'})
    with Session(application.engine) as db:
        assert [(u.id,u.last_active,u.updated_at) for u in db.scalars(select(UserAccount).order_by(UserAccount.id))] == before
        assert db.scalar(select(func.count()).select_from(ActivityLog)) == logs


@pytest.mark.asyncio
async def test_recovery_initializes_deferred_runtime_once(monkeypatch):
    from app.core import startup
    from app.services.runtime_operations import StationCoordinator
    local = StationCoordinator()
    local.block('recovery-required')
    monkeypatch.setattr(startup, 'coordinator', local)
    monkeypatch.setattr(startup, '_runtime_ready', False, raising=False)
    initialized, background = AsyncMock(), AsyncMock()
    monkeypatch.setattr(startup, '_initialize_runtime', initialized, raising=False)
    monkeypatch.setattr(startup, 'start_background_tasks', background)
    await startup.resume_runtime()
    await startup.resume_runtime()
    assert initialized.await_count == 1
    assert background.await_count == 1


@pytest.mark.asyncio
async def test_camera_apply_operation_replay_does_not_reinitialize(application, monkeypatch):
    from uuid import uuid4
    from app.api.v1 import maintenance
    from app.services import backup_restore, configuration
    from app.services.runtime_operations import StationCoordinator
    import asyncio
    monkeypatch.setattr(maintenance, 'coordinator', StationCoordinator())
    monkeypatch.setattr(maintenance, 'get_service', lambda: SimpleNamespace(_lock=asyncio.Lock()))
    apply = AsyncMock()
    monkeypatch.setattr(configuration, 'apply_camera_config', apply)
    body = maintenance.OperationRequest(operation_id=uuid4())
    admin = SimpleNamespace(id=application.ids.admin)
    from starlette.requests import Request

    from app.core.security import create_access_token
    from app.models import UserAccount

    with Session(application.engine) as session:
        version = session.get(UserAccount, admin.id).token_version
    token = create_access_token({'sub':str(admin.id), 'tv':version}, generation='initial')
    request = Request({'type':'http', 'headers':[(b'authorization', f'Bearer {token}'.encode())]})
    async with SessionAdapter(application.engine, application.state) as db:
        first = await maintenance.apply_cameras(body, db, admin, request)
    async with SessionAdapter(application.engine, application.state) as db:
        second = await maintenance.apply_cameras(body, db, admin, request)
    assert first == second
    assert apply.await_count == 1


@pytest.mark.asyncio
async def test_old_power_cancel_retry_cannot_reopen_admission_during_restore(application, monkeypatch):
    from fastapi import HTTPException
    from app.models import MaintenanceState
    from app.services import power_control
    from app.services.runtime_operations import StationCoordinator
    local = StationCoordinator(); local.kind = 'restore'; local.block('recovery-required')
    monkeypatch.setattr(power_control, 'coordinator', local)
    monkeypatch.setattr(power_control, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    with Session(application.engine) as db:
        db.add(MaintenanceState(id=1, auth_generation='test', operations={}, power={'id':'old','kind':'restart','status':'cancelled'}))
        db.commit()
    with pytest.raises(HTTPException):
        await power_control.cancel_power()
    assert local.state == 'recovery-required'


@pytest.mark.asyncio
async def test_power_cancel_waits_until_initial_dispatch_is_settled(application, monkeypatch):
    import asyncio
    from uuid import uuid4
    from app.services import power_control
    from app.services.runtime_operations import StationCoordinator
    local = StationCoordinator()
    monkeypatch.setattr(power_control, 'coordinator', local)
    monkeypatch.setattr(power_control, 'async_session_factory', lambda: SessionAdapter(application.engine, application.state))
    monkeypatch.setattr(power_control, 'boot_identity', lambda: 'test-boot')
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def dispatch(action):
        if action == 'restart':
            entered.set(); await release.wait()
        else:
            cancelled.set()
    monkeypatch.setattr(power_control, '_schedule_power_action', dispatch)
    task = asyncio.create_task(power_control.request_power('restart', str(uuid4()), application.ids.admin))
    await entered.wait()
    cancel = asyncio.create_task(power_control.cancel_power())
    try:
        await asyncio.sleep(0)
        assert not cancelled.is_set()
        assert local.state != 'ready'
    finally:
        release.set()
        await asyncio.gather(task, cancel)
    assert cancelled.is_set() and local.state == 'ready'


def test_production_application_blocks_ordinary_requests_during_recovery(application, monkeypatch):
    from app.main import app
    from app.services import runtime_operations
    from fastapi.testclient import TestClient
    local = runtime_operations.StationCoordinator(); local.block('recovery-required')
    monkeypatch.setattr(runtime_operations, 'coordinator', local)
    # No lifespan: all DB dependencies use the isolated application fixture.
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.get('/api/v1/scans')
        assert response.status_code == 503, response.text
        assert 'recovery-required' in response.text
        assert client.get('/captures/does-not-exist.jpg').status_code == 503
    finally:
        client.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('revocation', ['generation', 'token_version', 'role'])
async def test_queued_backup_rechecks_authorization(application, monkeypatch, tmp_path, revocation):
    import asyncio
    from uuid import uuid4
    from starlette.requests import Request
    from fastapi import HTTPException
    from app.api.v1 import maintenance
    from app.models import UserAccount, MaintenanceState
    from app.core.security import create_access_token
    from app.services.backup_restore import MaintenanceService
    from app.services import backup_restore
    from app.services.runtime_operations import StationCoordinator
    local = StationCoordinator()
    monkeypatch.setattr(backup_restore, 'coordinator', local)
    sessions = lambda: SessionAdapter(application.engine, application.state)
    service = MaintenanceService(application.engine, sessions, tmp_path / 'captures')
    monkeypatch.setattr(maintenance, 'get_service', lambda: service)
    with Session(application.engine) as db:
        user = db.get(UserAccount, application.ids.admin)
        token = create_access_token({'sub':str(user.id), 'tv':user.token_version}, generation='initial')
    request = Request({'type':'http', 'headers':[(b'authorization', f'Bearer {token}'.encode())]})
    async with sessions() as db:
        # Model initial HTTP authentication, then queue behind another maintenance operation.
        from app.api.deps import get_current_user
        admin = await get_current_user(db, f'Bearer {token}')
        await service._lock.acquire()
        task = asyncio.create_task(maintenance.create_backup(maintenance.OperationRequest(operation_id=uuid4()), db, admin, request))
        try:
            await asyncio.sleep(0)
            with Session(application.engine) as other:
                if revocation == 'generation':
                    other.add(MaintenanceState(id=1, auth_generation='restored', operations={}))
                elif revocation == 'token_version':
                    other.get(UserAccount, application.ids.admin).token_version += 1
                else:
                    other.get(UserAccount, application.ids.admin).role_id = 2
                other.commit()
        finally:
            service._lock.release()
        with pytest.raises(HTTPException) as rejected:
            await task
        assert rejected.value.status_code in (401, 403)
    assert not service.root.exists(), 'No backup material may be created by the revoked request'
