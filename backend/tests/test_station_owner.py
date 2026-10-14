"""Station admission survives canceled requests without replacing its ownership session."""
import asyncio
from types import SimpleNamespace

import anyio
import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.services import maintenance_database as ownership
from app.services.runtime_operations import StationCoordinator


@pytest_asyncio.fixture
async def station_owner(monkeypatch):
    state = SimpleNamespace(started=asyncio.Event(), finish=asyncio.Event(),
                            phase='execute', calls=[], tasks=[], concurrent=0, maximum=0)

    class Connection:
        invalidated = False
        closed = False

        async def execute(self, statement, *args):
            if str(statement) == 'SELECT 1':
                state.concurrent += 1
                state.maximum = max(state.maximum, state.concurrent)
                state.calls.append('query')
                if state.phase == 'execute':
                    state.started.set()
                    try:
                        await state.finish.wait()
                    except asyncio.CancelledError:
                        self.invalidated = True
                        raise
            else:
                state.calls.append('unlock')

        async def commit(self):
            if state.phase == 'commit':
                state.started.set()
                try:
                    await state.finish.wait()
                except asyncio.CancelledError:
                    self.invalidated = True
                    raise
            state.calls.append('commit')
            state.concurrent = max(0, state.concurrent - 1)

        async def close(self):
            state.calls.append('close')
            self.closed = True

        async def invalidate(self):
            state.calls.append('invalidate')
            self.invalidated = True

    state.connection = Connection()
    state.coordinator = StationCoordinator()
    monkeypatch.setattr(ownership, '_owner_mutex', asyncio.Lock())
    monkeypatch.setattr(ownership, '_owner_connection', state.connection)
    monkeypatch.setattr(ownership, '_owner_lost', False, raising=False)
    monkeypatch.setattr(ownership, 'coordinator', state.coordinator)
    state.coordinator.owner_check = ownership.verify_station_owner
    yield state
    state.finish.set()
    await asyncio.gather(*state.tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['execute', 'commit'])
async def test_canceled_caller_keeps_admission_until_owner_check_finishes(station_owner, phase):
    state = station_owner
    state.phase = phase

    async def request():
        async with state.coordinator.operation():
            pytest.fail('Canceled request must not enter its handler')

    task = asyncio.create_task(request())
    state.tasks.append(task)
    await state.started.wait()
    task.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert state.coordinator.active == 1
    assert state.connection.invalidated is False
    state.finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state.coordinator.active == 0
    assert state.calls == ['query', 'commit']
    assert state.coordinator.state == 'ready'
    await ownership.verify_station_owner()
    assert state.calls == ['query', 'commit', 'query', 'commit']


@pytest.mark.asyncio
async def test_anyio_cancel_scope_cannot_poison_owner_connection(station_owner):
    state = station_owner
    scopes = []

    async def request():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            async with state.coordinator.operation():
                pytest.fail('Canceled request must not enter its handler')

    async with anyio.create_task_group() as group:
        group.start_soon(request)
        await state.started.wait()
        scopes[0].cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert state.coordinator.active == 1
        assert state.connection.invalidated is False
        state.finish.set()
    assert state.coordinator.active == 0
    assert state.coordinator.state == 'ready'
    assert state.calls == ['query', 'commit']


@pytest.mark.asyncio
async def test_release_waits_for_check_and_canceled_queued_check(station_owner):
    state = station_owner
    first = asyncio.create_task(ownership.verify_station_owner())
    state.tasks.append(first)
    await state.started.wait()
    second = asyncio.create_task(ownership.verify_station_owner())
    state.tasks.append(second)
    await asyncio.sleep(0)
    second.cancel()
    release = asyncio.create_task(ownership.release_station_owner())
    state.tasks.append(release)
    await asyncio.sleep(0)
    assert 'unlock' not in state.calls and 'close' not in state.calls
    assert state.connection.invalidated is False
    state.finish.set()
    await first
    with pytest.raises(asyncio.CancelledError):
        await second
    await release
    assert state.maximum == 1
    assert state.calls[-3:] == ['unlock', 'commit', 'close']


@pytest.mark.asyncio
async def test_real_ownership_loss_stays_blocked_without_reconnecting(station_owner):
    state = station_owner
    state.connection.invalidated = True
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await ownership.verify_station_owner()
        assert error.value.status_code == 503
    assert state.coordinator.state == 'recovery-required'
    assert state.calls == []


@pytest.mark.asyncio
async def test_failed_unlock_invalidates_session_before_pool_close(station_owner, monkeypatch):
    state = station_owner

    async def failed_unlock(*args):
        raise RuntimeError('Injected unlock failure')

    monkeypatch.setattr(state.connection, 'execute', failed_unlock)
    with pytest.raises(RuntimeError, match='unlock failure'):
        await ownership.release_station_owner()
    assert state.calls == ['invalidate', 'close']
    assert state.connection.invalidated and state.connection.closed
    assert ownership._owner_connection is None
