"""Admission/drain contracts; all work is synthetic, never host power or cameras."""
import asyncio
import threading

import pytest
from fastapi import HTTPException

from app.services import runtime_operations as runtime


@pytest.mark.asyncio
async def test_drain_rejects_new_work_and_waits_for_admitted_work():
    coordinator = runtime.StationCoordinator()
    entered, release, maintained = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        async with coordinator.operation():
            entered.set()
            await release.wait()

    async def maintenance():
        async with coordinator.exclusive("backup"):
            maintained.set()
            assert coordinator.active == 0

    active = asyncio.create_task(work())
    await entered.wait()
    draining = asyncio.create_task(maintenance())
    await asyncio.sleep(0)
    assert coordinator.state == "draining"
    with pytest.raises(HTTPException) as rejected:
        async with coordinator.operation():
            pytest.fail("new work admitted during drain")
    assert rejected.value.status_code == 503
    assert not maintained.is_set()
    release.set()
    await asyncio.gather(active, draining)
    assert maintained.is_set()
    assert coordinator.state == "ready"


@pytest.mark.asyncio
async def test_drain_timeout_does_not_cancel_active_operation():
    coordinator = runtime.StationCoordinator(drain_timeout=0.01)
    entered, release = asyncio.Event(), asyncio.Event()

    async def work():
        async with coordinator.operation():
            entered.set()
            await release.wait()

    active = asyncio.create_task(work())
    await entered.wait()
    with pytest.raises(HTTPException) as error:
        async with coordinator.exclusive("restart"):
            pytest.fail("drain should time out")
    assert error.value.status_code == 409
    assert not active.done()
    assert coordinator.state == "ready"
    release.set()
    await active


@pytest.mark.asyncio
async def test_cancelled_threaded_work_keeps_admission_until_thread_finishes():
    coordinator = runtime.StationCoordinator()
    entered, release = threading.Event(), threading.Event()

    def blocking():
        entered.set()
        release.wait(timeout=5)

    async def work():
        async with coordinator.operation():
            await runtime.run_blocking(blocking)

    active = asyncio.create_task(work())
    await asyncio.to_thread(entered.wait, 2)
    active.cancel()
    await asyncio.sleep(0)
    assert coordinator.active == 1
    assert not active.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert coordinator.active == 0


@pytest.mark.asyncio
async def test_exclusive_preserves_blocked_outcome_and_rejects_second_request():
    coordinator = runtime.StationCoordinator()
    async with coordinator.exclusive("restart"):
        coordinator.block("power-accepted")
    assert coordinator.state == "power-accepted"
    with pytest.raises(HTTPException):
        async with coordinator.exclusive("backup"):
            pytest.fail("accepted power must block maintenance")


@pytest.mark.asyncio
async def test_nested_work_counts_once_and_failure_releases_admission():
    coordinator = runtime.StationCoordinator()
    with pytest.raises(ValueError):
        async with coordinator.operation():
            async with coordinator.operation():
                assert coordinator.active == 1
                raise ValueError("write failed")
    assert coordinator.active == 0


@pytest.mark.asyncio
async def test_restore_generation_revokes_token_without_changing_account_version(application):
    from app.api.deps import get_current_user
    from app.core.security import create_access_token
    from app.services import maintenance_state
    from tests.test_time_and_writes import SessionAdapter
    from sqlalchemy import update
    from app.models.user_account import UserAccount

    async with SessionAdapter(application.engine, application.state) as db:
        account = await db.scalar(__import__("sqlalchemy").select(UserAccount).where(UserAccount.id == application.ids.admin))
        token = create_access_token({"sub": str(account.id), "tv": account.token_version})
        assert (await get_current_user(db, "Bearer " + token)).id == account.id
        state = await maintenance_state.get_state(db)
        state.auth_generation = "a-new-restore-generation"
        await db.commit()
        with pytest.raises(Exception) as rejected:
            await get_current_user(db, "Bearer " + token)
        assert rejected.value.status_code == 401


# Reuse the isolated real-route SQLite fixture; never the configured station database.
from tests.test_time_and_writes import application  # noqa: E402,F401


@pytest.mark.asyncio
async def test_maintenance_and_recovery_fail_closed_after_ownership_loss():
    coordinator = runtime.StationCoordinator()
    async def lost_owner():
        coordinator.block('recovery-required')
        raise RuntimeError('Station ownership lost')
    coordinator.owner_check = lost_owner
    with pytest.raises(RuntimeError, match='ownership'):
        async with coordinator.exclusive('backup'):
            pytest.fail('maintenance cannot proceed without ownership')
    with pytest.raises(RuntimeError, match='ownership'):
        await coordinator.finish_recovery()
    assert coordinator.state == 'recovery-required'
