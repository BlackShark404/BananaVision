"""Audit rows around restore on disposable PostgreSQL schemas; NEVER a live station DB."""
import asyncio
import contextvars
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import ActivityLog, UserAccount
from app.services import audit, maintenance_database
from app.services.runtime_operations import maintenance_context
from tests.test_backup_archive import archive_module as archive_module  # noqa: F401
from tests.test_backup_archive import station as station  # noqa: F401
from tests.test_maintenance_postgresql import recovery_station as recovery_station  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get('BANANAVISION_TEST_DATABASE_URL'),
                                reason='Isolated PostgreSQL URL required')


async def audit_rows(sessions, action=None):
    async with sessions() as db:
        query = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
        if action:
            query = query.where(ActivityLog.action == action)
        return list((await db.scalars(query)).all())


async def audit_count(sessions):
    async with sessions() as db:
        return await db.scalar(select(func.count()).select_from(ActivityLog))


@pytest.mark.asyncio
async def test_restore_writes_one_completed_row_after_verification(recovery_station):
    x = recovery_station
    before = await audit_count(x.sessions)
    operation = uuid4()
    result = await x.service.restore(operation, x.validation['validation_id'],
                                     x.validation['token'], x.actor, 'session',
                                     actor_name='Current station name', client_ip='10.0.0.9')
    assert result['status'] == 'completed'
    [row] = await audit_rows(x.sessions, 'restore_completed')
    assert row.user_id == x.actor and row.ip_address == '10.0.0.9'
    assert str(operation) in row.details and "requested by 'Current station name'" in row.details
    assert (f'audit history replaced ({before} pre-restore audit rows kept in rollback archive '
            f'{operation})') in row.details
    # The restored history is exactly the archive's rows plus the outcome row.
    assert await audit_count(x.sessions) == 2
    replay = await x.service.restore(operation, x.validation['validation_id'],
                                     x.validation['token'], x.actor, 'session')
    assert replay['status'] == 'completed'
    assert len(await audit_rows(x.sessions, 'restore_completed')) == 1
    assert x.validation['token'] not in row.details


@pytest.mark.asyncio
async def test_non_owner_emit_during_restore_is_deferred_and_flushed_after(recovery_station,
                                                                           monkeypatch):
    x = recovery_station
    monkeypatch.setattr(audit, 'coordinator', x.coordinator)
    real_replace = x.service._replace
    operation = uuid4()

    async def replace(validated, marker):
        await real_replace(validated, marker)
        # Another request (fresh context: not the maintenance owner) between commit and verify.
        emitted = asyncio.get_running_loop().create_task(
            audit.emit(audit.AuditAction.LOGIN, 'Admin logged in during restore',
                       sessions=x.sessions),
            context=contextvars.Context())
        await emitted
        assert [event['action'] for event in audit.pending_events()] == ['login']

    monkeypatch.setattr(x.service, '_replace', replace)
    result = await x.service.restore(operation, x.validation['validation_id'],
                                     x.validation['token'], x.actor, 'session')
    assert result['status'] == 'completed'  # verification saw no unexpected audit row
    assert audit.pending_events() == []
    saved = await audit_rows(x.sessions)
    assert [row.action for row in saved][-2:] == ['login', 'restore_completed']
    assert len([row for row in saved if row.action == 'restore_completed']) == 1


@pytest.mark.asyncio
async def test_rejected_restore_is_logged_and_unknown_actor_is_fk_safe(recovery_station):
    x = recovery_station
    ghost = uuid4()
    for actor, session in [(ghost, 'session'), (x.actor, 'different-session')]:
        with pytest.raises(Exception) as error:
            await x.service.restore(uuid4(), x.validation['validation_id'], x.validation['token'],
                                    actor, session, actor_name='Someone')
        assert error.value.status_code == 409
    failed = await audit_rows(x.sessions, 'restore_failed')
    assert [row.user_id for row in failed] == [None, x.actor]
    assert all('validation expired, changed or was already used' in row.details for row in failed)
    assert x.coordinator.state == 'ready'


@pytest.mark.asyncio
async def test_http_backup_download_validate_and_restore_are_audited(recovery_station, monkeypatch):
    import httpx

    from app.api.v1 import maintenance
    from app.core import database
    from app.core.rate_limiter import RateLimiter
    from app.core.security import create_access_token
    from app.main import app
    from app.services import runtime_operations

    x = recovery_station
    monkeypatch.setattr(database, 'async_session_factory', x.sessions)
    monkeypatch.setattr(maintenance, 'get_service', lambda: x.service)
    monkeypatch.setattr(maintenance, 'credential_limiter', RateLimiter())
    for module in (maintenance, runtime_operations, audit):
        monkeypatch.setattr(module, 'coordinator', x.coordinator)
    x.coordinator.database_barrier = lambda: maintenance_database.database_barrier(x.engine)
    async with x.sessions() as db:
        user = await db.get(UserAccount, x.actor)
        token = create_access_token({'sub': str(user.id), 'tv': user.token_version},
                                    generation='before')
    headers = {'Authorization': f'Bearer {token}'}
    context = maintenance_context.set(False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            async def request(method, path, **kwargs):
                return await asyncio.wait_for(
                    client.request(method, path, headers=headers, **kwargs), timeout=20)

            backup_id = str(uuid4())
            created = await request('POST', '/api/v1/config/backups',
                                    json={'operation_id': backup_id})
            assert created.status_code == 200, created.text
            downloaded = await request('GET', f'/api/v1/config/backups/{backup_id}')
            assert downloaded.status_code == 200
            wrong = await request('POST', '/api/v1/config/power/cancel', json={'password': 'nope'})
            assert wrong.status_code == 403
            checked = await request('POST', '/api/v1/config/restores/validate',
                                    content=downloaded.content)
            assert checked.status_code == 200, checked.text
            preview = checked.json()
            history = await audit_rows(x.sessions)
            actions = [row.action for row in history]
            assert actions.count('backup_created') == 1 and actions.count('backup_downloaded') == 1
            assert actions.count('reauth_failed') == 1 and 'access_denied' not in actions
            assert actions[-1] == 'restore_validated'
            for row in history:
                assert '$2b$' not in (row.details or '') and token not in (row.details or '')
                assert preview['token'] not in (row.details or '')
                assert str(x.service.root) not in (row.details or '')

            restore_id = str(uuid4())
            restored = await request('POST', '/api/v1/config/restores', json={
                'operation_id': restore_id, 'validation_id': preview['validation_id'],
                'token': preview['token'], 'password': 'password', 'confirmation': 'REPLACE'})
            assert restored.status_code == 200, restored.text
            assert restored.json()['status'] == 'completed'
    finally:
        maintenance_context.reset(context)
    after = await audit_rows(x.sessions)
    [outcome] = [row for row in after if row.action == 'restore_completed']
    assert outcome.user_id == x.actor
    assert (f'audit history replaced ({len(history)} pre-restore audit rows kept in rollback '
            f'archive {restore_id})') in outcome.details
    # The restored archive was taken before its own backup_created row was written.
    assert [row.action for row in after].count('backup_created') == 0
