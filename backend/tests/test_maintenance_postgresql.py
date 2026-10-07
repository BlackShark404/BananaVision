"""Opt-in disposable PostgreSQL schemas; NEVER point this at a live station DB."""
import asyncio
import os
import shutil
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.database import Base
from app.models import UserAccount, MaintenanceState, ScanStatusLog, Scan
from app.services import backup_archive as archive, backup_restore as restore, maintenance_database
from app.services.runtime_operations import StationCoordinator, maintenance_context
from tests.test_backup_archive import station, archive_module, AsyncDB  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get('BANANAVISION_TEST_DATABASE_URL'), reason='Isolated PostgreSQL URL required')


@pytest_asyncio.fixture
async def recovery_station(station, archive_module, tmp_path, monkeypatch):
    from app.services import maintenance_state
    monkeypatch.setattr(maintenance_state, 'auth_generation', 'initial')
    source = tmp_path / 'backup.zip'
    await archive.create_archive(AsyncDB(station[0]), station[1], source)
    schema = 'qa_restore_' + uuid4().hex
    control = create_async_engine(os.environ['BANANAVISION_TEST_DATABASE_URL'])
    async with control.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(os.environ['BANANAVISION_TEST_DATABASE_URL'],
        connect_args={'server_settings': {'search_path': schema, 'timezone': 'Asia/Manila'}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    root = tmp_path / 'station' / 'captures'
    shutil.copytree(station[1], root)
    token = maintenance_context.set(True)
    try:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
            validated = archive.validate_archive(source, tmp_path / 'seed')
            await archive.restore_rows(db, validated)
        async with sessions() as db:
            actor = await db.scalar(select(UserAccount.id))
            await db.execute(update(UserAccount).values(full_name='Current station name'))
            db.add(MaintenanceState(id=1, auth_generation='before', operations={}))
            await db.commit()
        coordinator = StationCoordinator()
        monkeypatch.setattr(restore, 'coordinator', coordinator)
        service = restore.MaintenanceService(engine, sessions, root)
        service.prepare()
        validation_id = uuid4()
        upload = service.directory(validation_id) / 'upload.zip'
        shutil.copyfile(source, upload)
        validation = await service.validate(upload, validation_id, actor, 'session')
        yield SimpleNamespace(service=service, engine=engine, sessions=sessions, actor=actor,
                              validation=validation, coordinator=coordinator, root=root, source=source)
    finally:
        maintenance_context.reset(token)
        await engine.dispose()
        async with control.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.asyncio
async def test_replacement_transaction_and_sequences(recovery_station):
    x = recovery_station
    validated = archive.validate_archive(x.source, x.service.root / 'direct-test')
    await x.service._replace(validated, str(uuid4()))


@pytest.mark.asyncio
async def test_restore_round_trip_and_one_use_validation(recovery_station):
    x = recovery_station
    operation = uuid4()
    result = await x.service.restore(operation, x.validation['validation_id'], x.validation['token'], x.actor, 'session')
    assert result['status'] == 'completed'
    async with x.sessions() as db:
        assert await db.scalar(select(UserAccount.full_name)) == 'Admin'
        state = await db.scalar(select(MaintenanceState))
        assert state.auth_generation != 'before' and state.restore_marker == str(operation)
        # Actual generated IDs were transactionally reset beyond restored values.
        log = ScanStatusLog(scan_id=await db.scalar(select(Scan.id)), inventory_status='Sold')
        db.add(log); await db.commit()
        assert log.id > 1
    assert (await x.service.restore(operation, x.validation['validation_id'], x.validation['token'], x.actor, 'session'))['status'] == 'completed'
    with pytest.raises(Exception) as error:
        await x.service.restore(uuid4(), x.validation['validation_id'], x.validation['token'], x.actor, 'session')
    assert error.value.status_code == 409
    assert x.coordinator.state == 'ready'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['before-commit', 'lost-commit', 'post-commit'])
async def test_restore_failure_boundaries_and_compensation(recovery_station, monkeypatch, failure):
    x = recovery_station
    real_replace, real_verify = x.service._replace, x.service.verify_live
    operation = uuid4()
    async def replace(validated, marker):
        if failure == 'before-commit':
            raise RuntimeError('Injected persistence failure')
        await real_replace(validated, marker)
        if failure == 'lost-commit':
            raise RuntimeError('Lost commit acknowledgement')
    async def verify(expected, directory):
        if failure == 'post-commit' and await x.service.marker() == str(operation):
            raise archive.ArchiveError('Injected verification failure')
        await real_verify(expected, directory)
    monkeypatch.setattr(x.service, '_replace', replace)
    monkeypatch.setattr(x.service, 'verify_live', verify)
    result = await x.service.restore(operation, x.validation['validation_id'], x.validation['token'], x.actor, 'session')
    assert result['status'] == ('completed' if failure == 'lost-commit' else 'failed')
    async with x.sessions() as db:
        assert await db.scalar(select(UserAccount.full_name)) == ('Admin' if failure == 'lost-commit' else 'Current station name')
    assert x.coordinator.state == 'ready'


@pytest.mark.asyncio
async def test_validation_is_bound_to_actor_and_session(recovery_station):
    x = recovery_station
    for actor, session in [(uuid4(), 'session'), (x.actor, 'different-session')]:
        with pytest.raises(Exception) as error:
            await x.service.restore(uuid4(), x.validation['validation_id'], x.validation['token'], actor, session)
        assert error.value.status_code == 409
    assert x.coordinator.state == 'ready'


@pytest.mark.asyncio
async def test_database_lock_blocks_external_writers_and_owner_is_unique(recovery_station):
    x = recovery_station
    await maintenance_database.acquire_station_owner(x.engine)
    try:
        with pytest.raises(RuntimeError, match='Another backend'):
            await maintenance_database.acquire_station_owner(x.engine)
        await asyncio.gather(*(maintenance_database.verify_station_owner() for _ in range(5)))
        async with maintenance_database.database_barrier(x.engine):
            async with x.engine.connect() as db:
                await db.execute(text("SET LOCAL lock_timeout='100ms'"))
                with pytest.raises(Exception):
                    await db.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': maintenance_database.MAINTENANCE_KEY})
                await db.rollback()
    finally:
        await maintenance_database.release_station_owner()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["copy", "flush"])
async def test_restore_preparation_failure_is_terminal_and_preserves_station(recovery_station, monkeypatch, failure_point):
    x = recovery_station
    identifier = uuid4()
    def full_disk(*args, **kwargs):
        raise OSError('Injected disk full during evidence staging')
    if failure_point == 'copy':
        monkeypatch.setattr(restore.shutil, 'copytree', full_disk)
    else:
        monkeypatch.setattr(restore, 'sync_tree', full_disk, raising=False)
    with pytest.raises(OSError):
        await x.service.restore(identifier, x.validation['validation_id'], x.validation['token'], x.actor, 'session')
    result = await x.service.saved_result(identifier, x.actor, 'restore')
    assert result['status'] == 'failed'
    assert not x.service.journal.exists()
    async with x.sessions() as db:
        assert await db.scalar(select(UserAccount.full_name)) == 'Current station name'
    assert x.coordinator.state == 'ready'


@pytest.mark.asyncio
async def test_verified_restore_survives_crash_during_hardware_refresh(recovery_station):
    x = recovery_station
    identifier = uuid4()
    class Crash(BaseException):
        pass
    async def refresh():
        # A legitimate post-restore hardware/status write changes archive hashes.
        async with x.sessions() as db:
            await db.execute(update(UserAccount).values(full_name='After verified restore'))
            await db.commit()
        raise Crash()
    x.service.hardware_refresh = refresh
    with pytest.raises(Crash):
        await x.service.restore(identifier, x.validation['validation_id'], x.validation['token'], x.actor, 'session')
    x.service.hardware_refresh = None
    await x.service.recover()
    assert (await x.service.saved_result(identifier, x.actor, 'restore'))['status'] == 'completed'
    async with x.sessions() as db:
        assert await db.scalar(select(UserAccount.full_name)) == 'After verified restore'
    assert x.coordinator.state == 'ready'
