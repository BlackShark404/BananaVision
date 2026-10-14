"""Ownership-session regressions; only run against an explicitly disposable PostgreSQL URL."""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services import maintenance_database as ownership
from app.services.runtime_operations import StationCoordinator

pytestmark = pytest.mark.skipif(
    not os.environ.get('BANANAVISION_TEST_DATABASE_URL'), reason='Isolated PostgreSQL URL required',
)


@pytest_asyncio.fixture
async def pg_owner(monkeypatch):
    schema = 'qa_owner_' + uuid4().hex
    url = os.environ['BANANAVISION_TEST_DATABASE_URL']
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    monkeypatch.setattr(ownership, '_owner_mutex', asyncio.Lock())
    monkeypatch.setattr(ownership, '_owner_connection', None)
    monkeypatch.setattr(ownership, '_owner_lost', False)
    local = StationCoordinator()
    monkeypatch.setattr(ownership, 'coordinator', local)
    try:
        await ownership.acquire_station_owner(engine)
        real = ownership._owner_connection
        pid = await real.scalar(text('SELECT pg_backend_pid()'))
        await real.commit()
        started = asyncio.Event()

        class SlowProbe:
            probes = 0

            def __getattr__(self, name):
                return getattr(real, name)

            async def execute(self, statement, *args, **kwargs):
                if str(statement) == 'SELECT 1':
                    self.probes += 1
                    started.set()
                    return await real.execute(text('SELECT pg_sleep(0.2)'))
                return await real.execute(statement, *args, **kwargs)

        proxy = SlowProbe()
        monkeypatch.setattr(ownership, '_owner_connection', proxy)
        yield SimpleNamespace(engine=engine, real=real, pid=pid, started=started,
                              coordinator=local, proxy=proxy)
    finally:
        await ownership.release_station_owner()
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancellation', ['asyncio', 'anyio'])
async def test_canceled_request_preserves_backend_pid_and_advisory_lock(pg_owner, cancellation):
    state = pg_owner
    scopes = []

    async def request():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            async with state.coordinator.operation():
                pytest.fail('Canceled caller must not be admitted to the handler')

    task = asyncio.create_task(request())
    try:
        await state.started.wait()
        if cancellation == 'asyncio':
            task.cancel()
        else:
            scopes[0].cancel()
        if cancellation == 'asyncio':
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    finally:
        await asyncio.gather(task, return_exceptions=True)
    assert state.coordinator.state == 'ready'
    assert await state.real.scalar(text('SELECT pg_backend_pid()')) == state.pid
    await state.real.commit()
    async with state.engine.connect() as other:
        assert await other.scalar(text('SELECT pg_try_advisory_lock(:key)'),
                                  {'key': ownership.STATION_OWNER_KEY}) is False
    await ownership.verify_station_owner()


@pytest.mark.asyncio
async def test_terminated_owner_blocks_station_without_reacquiring_lock(pg_owner):
    state = pg_owner
    async with state.engine.begin() as other:
        assert await other.scalar(text('SELECT pg_terminate_backend(:pid)'),
                                  {'pid': state.pid}) is True
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await ownership.verify_station_owner()
        assert error.value.status_code == 503
    assert state.coordinator.state == 'recovery-required'
    assert state.proxy.probes == 1  # No retry can reconnect the now-unowned session.
    async with state.engine.connect() as other:
        assert await other.scalar(text('SELECT pg_try_advisory_lock(:key)'),
                                  {'key': ownership.STATION_OWNER_KEY}) is True
        assert await other.scalar(text('SELECT pg_advisory_unlock(:key)'),
                                  {'key': ownership.STATION_OWNER_KEY}) is True
