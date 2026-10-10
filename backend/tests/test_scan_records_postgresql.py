"""Real locking tests on an explicitly configured disposable PostgreSQL database."""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.api.v1.intakes import IntakeBulkInventoryUpdate, bulk_update_intake_inventory
from app.core.database import Base
from app.core.time import now_manila
from app.models import Intake, OperatorProfile, Scan, ScanEvent, ScanMutation, UserAccount, UserRole
from app.schemas.scan import ScanFlagRequest, ScanStatusUpdate
from app.services import scan_records as records
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

pytestmark = pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)


@pytest_asyncio.fixture
async def station():
    url = os.environ['BANANAVISION_TEST_DATABASE_URL']
    schema = 'qa_scan_' + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema, "timezone": "Asia/Manila"}}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            role = UserRole(name='Admin')
            db.add(role)
            await db.flush()
            users = [
                UserAccount(
                    username=f"admin{i}",
                    full_name=f"Admin {i}",
                    role_id=role.id,
                    password_hash="test-only",
                )
                for i in range(2)
            ]
            db.add_all(users)
            await db.flush()
            profile = OperatorProfile(account_id=users[0].id)
            intake = Intake(source='Historical supplier', intake_date=now_manila().date())
            db.add_all([profile, intake])
            await db.flush()
            scan = Scan(operator_id=profile.id, intake_id=intake.id, date_time=now_manila())
            db.add(scan)
            await db.commit()
            yield SimpleNamespace(
                sessions=sessions,
                scan=scan.id,
                actors=[u.id for u in users],
                intake=intake.id,
                operator=profile.id,
            )
    finally:
        await engine.dispose()
        async with control.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


async def write(x, actor, body, kind='flag'):
    async with x.sessions() as db:
        user = await db.get(UserAccount, actor)
        try:
            result = await records.mutate_scan(db, x.scan, user, kind, body)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise


@pytest.mark.asyncio
async def test_concurrent_writers_only_one_revision_commits(station):
    x = station
    bodies = [
        ScanFlagRequest(request_id=uuid4(), expected_revision=1, flagged=True) for _ in range(2)
    ]
    result = await asyncio.gather(
        *(write(x, actor, body) for actor, body in zip(x.actors, bodies, strict=True)),
        return_exceptions=True,
    )
    assert sorted(r["revision"] if isinstance(r, dict) else r.status_code for r in result) == [
        2,
        409,
    ]
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ScanEvent)) == 1
        assert await db.scalar(select(func.count()).select_from(ScanMutation)) == 1


@pytest.mark.asyncio
async def test_concurrent_exact_retries_replay_once_and_reject_different_actor(station):
    x = station
    body = ScanStatusUpdate(
        request_id=uuid4(), expected_revision=1, inventory_status="Sold", reason="Shipment"
    )
    a, b = await asyncio.gather(
        write(x, x.actors[0], body, "status"), write(x, x.actors[0], body, "status")
    )
    assert a == b and a['revision'] == 2 and not a['is_overridden']
    with pytest.raises(Exception) as error:
        await write(x, x.actors[1], body, 'status')
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_queued_mutation_rechecks_revoked_session(station, monkeypatch):
    x = station
    body = ScanFlagRequest(request_id=uuid4(), expected_revision=1, flagged=True)
    original_lock = records.lock_mutation
    entered = asyncio.Event()
    async def observed_lock(db, identifier):
        entered.set()
        await original_lock(db, identifier)
    async with x.sessions() as blocker:
        await original_lock(blocker, body.request_id)
        monkeypatch.setattr(records, 'lock_mutation', observed_lock)
        queued = asyncio.create_task(write(x, x.actors[0], body))
        await asyncio.wait_for(entered.wait(), 5)
        async with x.sessions() as db:
            user = await db.get(UserAccount, x.actors[0])
            user.token_version += 1
            await db.commit()
        await blocker.rollback()
        with pytest.raises(Exception) as error:
            await asyncio.wait_for(queued, 5)
        assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_bulk_waits_for_parent_and_rejects_changed_membership(station):
    x = station
    body = IntakeBulkInventoryUpdate(
        request_id=uuid4(),
        expected_revisions={x.scan: 1},
        inventory_status="Sold",
        reason="Shipment",
    )
    started = asyncio.Event()
    async def bulk():
        async with x.sessions() as db:
            user = await db.get(UserAccount, x.actors[0])
            started.set()
            try:
                result = await bulk_update_intake_inventory(
                    x.intake, body, db, user, Request({"type": "http"})
                )
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise
    async with x.sessions() as attachment:
        await attachment.execute(select(Intake.id).where(Intake.id == x.intake).with_for_update())
        pending = asyncio.create_task(bulk())
        await asyncio.wait_for(started.wait(), 5)
        attachment.add(Scan(operator_id=x.operator, intake_id=x.intake, date_time=now_manila()))
        await attachment.commit()
        with pytest.raises(Exception) as error:
            await asyncio.wait_for(pending, 5)
        assert error.value.status_code == 409
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ScanEvent)) == 0
        assert await db.scalar(select(func.count()).select_from(ScanMutation)) == 0


@pytest.mark.asyncio
async def test_single_and_bulk_writers_cannot_silently_overwrite(station):
    x = station
    async def bulk():
        async with x.sessions() as db:
            user = await db.get(UserAccount, x.actors[1])
            body = IntakeBulkInventoryUpdate(
                request_id=uuid4(),
                expected_revisions={x.scan: 1},
                inventory_status="Sold",
                reason="Shipment",
            )
            result = await bulk_update_intake_inventory(
                x.intake, body, db, user, Request({"type": "http"})
            )
            await db.commit()
            return result
    single = ScanFlagRequest(request_id=uuid4(), expected_revision=1, flagged=True)
    results = await asyncio.gather(write(x, x.actors[0], single), bulk(), return_exceptions=True)
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert [r.status_code for r in results if isinstance(r, Exception)] == [409]
