"""Audit characterization: actual PostgreSQL metric SQL, never station data.

Run via an isolated temporary CWD with backend on sys.path. The explicit audit
URL and server data directory must identify the newly created disposable cluster.
Passing assertions describe current behavior, including documented inconsistencies.
"""
import csv
import io
import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url

from app.core.database import Base
from app.core.time import business_day_bounds
from app.models import Intake, OperatorProfile, Scan, ScanClassification, ScanOriginalAiResult, ScanStatusLog, Supplier, SystemConfig, UserAccount, UserRole
from app.schemas.enums import CultivarEnum, IntakeStatusEnum, InventoryStatusEnum, RipenessEnum
from app.schemas.scan_logs import ScanLogQuery
from app.services import analytics, dashboard, scan_logs

NOW = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def station(monkeypatch):
    url = os.environ['BV_AUDIT_DATABASE_URL']
    parsed = make_url(url)
    assert (parsed.host, parsed.port, parsed.username, parsed.database) == ('127.0.0.1', 56846, 'bv_audit', 'postgres')
    control = create_async_engine(url)
    schema = 'audit_' + uuid4().hex
    async with control.begin() as connection:
        actual = await connection.scalar(text('SHOW data_directory'))
        assert os.path.normcase(os.path.normpath(actual)) == os.path.normcase(os.path.normpath(os.environ['BV_AUDIT_PG_DATA']))
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema, 'timezone': 'Asia/Manila'}})
    monkeypatch.setattr(dashboard, 'now_manila', lambda: NOW)
    monkeypatch.setattr(analytics, 'now_manila', lambda: NOW)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            role = UserRole(name='Operator')
            db.add(role)
            await db.flush()
            users = []
            for index in range(2):
                account = UserAccount(username=f'audit{index}', full_name='Same Name', role_id=role.id, password_hash='isolated-unused')
                db.add(account)
                await db.flush()
                profile = OperatorProfile(account_id=account.id)
                db.add(profile)
                await db.flush()
                users.append(SimpleNamespace(id=account.id, operator_id=profile.id, role=SimpleNamespace(name='Operator')))
            db.add(SystemConfig(confidence_threshold=75, camera_ids='CAM-001', camera_device_ids=[0], canonical_key=1, data_retention_enabled=False))
            await db.commit()
            yield SimpleNamespace(db=db, sessions=sessions, user=users[0], other=users[1])
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


async def scan(x, *, at=NOW, confidence=90, flagged=False, prediction='5-7', intake=None, status=None, source='Farm', other=False):
    sid = uuid4()
    await x.db.execute(insert(Scan).values(id=sid, operator_id=(x.other if other else x.user).operator_id,
        date_time=at, flagged=flagged, source_text=source, intake_id=intake))
    if confidence is not None:
        await x.db.execute(insert(ScanClassification).values(scan_id=sid, cultivar=CultivarEnum.LAKATAN,
            ripeness=RipenessEnum.RIPE, confidence=confidence, spoilage_days=prediction, finger_count=5))
    if status:
        await x.db.execute(insert(ScanStatusLog).values(scan_id=sid, updated_at=NOW, inventory_status=status))
    return sid


async def exported_ids(x, query):
    stream = await scan_logs.export_scan_logs(x.db, x.user, query)
    chunks = [chunk async for chunk in stream]
    rows = list(csv.DictReader(io.StringIO(''.join(chunks).lstrip('\ufeff'))))
    return [row['Scan ID'] for row in rows]


@pytest.mark.asyncio
async def test_review_shortcut_population_differs_but_attention_export_matches(station):
    x = station
    low = await scan(x, confidence=60)
    flagged = await scan(x, confidence=95, flagged=True)
    await scan(x, confidence=75)
    await scan(x, other=True, confidence=1, flagged=True)
    await x.db.commit()
    summary = await dashboard.get_summary(x.db, x.user)
    shortcut = await scan_logs.list_scan_logs(x.db, x.user, ScanLogQuery(flagged_only=True))
    complete = await scan_logs.list_scan_logs(x.db, x.user, ScanLogQuery(attention='review'))
    assert summary.pending_review_count == complete.total == 2
    assert shortcut.total == 1 and shortcut.items[0].id == flagged
    assert {item.id for item in complete.items} == {low, flagged}
    assert set(await exported_ids(x, ScanLogQuery(attention='review', page=4, page_size=1))) == {str(low), str(flagged)}


@pytest.mark.asyncio
async def test_cross_view_eligibility_and_aged_risk_policy(station):
    x = station
    active, depleted = uuid4(), uuid4()
    for identifier, status in [(active, IntakeStatusEnum.ACTIVE), (depleted, IntakeStatusEnum.DEPLETED)]:
        await x.db.execute(insert(Intake).values(id=identifier, source='Farm', intake_date=date(2026,10,6), status=status))
    aged = await scan(x, at=NOW-timedelta(days=4), prediction='5-7', intake=active)
    inactive = await scan(x, prediction='1', intake=depleted)
    unlinked = await scan(x, prediction='1')
    await scan(x, prediction='Unknown', intake=active)
    await scan(x, prediction='1', intake=active, status=InventoryStatusEnum.SOLD)
    await x.db.commit()
    d = await dashboard.get_summary(x.db, x.user)
    a = await analytics.get_summary(x.db, x.user, date_range='all')
    logs = await scan_logs.list_scan_logs(x.db, x.user, ScanLogQuery(attention='at-risk'))
    assert d.expiring_stock_count == logs.total == 3
    assert {item.id for item in logs.items} == {aged, inactive, unlinked}
    assert next(item.remaining_days for item in logs.items if item.id == aged) == 2
    assert (a.current_stock_count, a.at_risk_count, a.risk_unknown_count) == (3, 2, 1)


@pytest.mark.asyncio
async def test_postgres_midnight_original_confidence_and_stable_source(station):
    x = station
    start, _ = business_day_bounds(date(2026,10,10))
    supplier, intake = uuid4(), uuid4()
    await x.db.execute(insert(Supplier).values(id=supplier, name='Original Farm'))
    await x.db.execute(insert(Intake).values(id=intake, supplier_id=supplier, source='Copied Farm', intake_date=date(2026,10,10), status=IntakeStatusEnum.ACTIVE))
    await scan(x, at=start-timedelta(microseconds=1))
    await scan(x, at=start, confidence=0, intake=intake)
    await scan(x, confidence=75, intake=intake)
    corrected = await scan(x, confidence=100, intake=intake)
    await x.db.execute(update(Scan).where(Scan.id==corrected).values(is_overridden=True))
    await x.db.execute(insert(ScanOriginalAiResult).values(scan_id=corrected, cultivar=CultivarEnum.CARDABA,
        ripeness=RipenessEnum.UNRIPE, confidence=60, finger_count=5))
    await scan(x, confidence=None)
    await scan(x, other=True)
    await x.db.commit()
    d = await dashboard.get_summary(x.db, x.user)
    a = await analytics.get_summary(x.db, x.user, date_range='today')
    assert d.total_scans == a.total_scans == 4
    assert (a.classification_count, a.incomplete_count, a.confidence_sample_count) == (3,1,3)
    assert (a.avg_confidence, a.low_confidence_count, a.low_confidence_rate) == (45,2,66.7)
    assert sum(item.count for item in a.hourly_distribution) == 4
    await x.db.execute(update(Supplier).where(Supplier.id==supplier).values(name='Renamed Farm'))
    a = await analytics.get_summary(x.db, x.user, date_range='today', source_key=f'supplier:{supplier}')
    assert a.total_scans == 3 and a.scans_by_source[0].name == 'Renamed Farm'
    empty = await analytics.get_summary(x.db, x.user, date_range='today', source_key='text:Absent')
    assert empty.total_scans == 0 and empty.source_options == a.source_options


@pytest.mark.asyncio
async def test_changing_offset_pages_repeat_rows_while_full_export_uses_current_filter(station):
    x = station
    for offset in range(5):
        await scan(x, at=NOW-timedelta(minutes=offset), source='Chosen')
    await scan(x, source='Excluded')
    await x.db.commit()
    query = dict(page_size=2, source_key='text:Chosen')
    first = await scan_logs.list_scan_logs(x.db, x.user, ScanLogQuery(page=1, **query))
    added = await scan(x, at=NOW+timedelta(seconds=1), source='Chosen')
    await x.db.commit()
    second = await scan_logs.list_scan_logs(x.db, x.user, ScanLogQuery(page=2, **query))
    assert first.total == 5 and second.total == 6
    assert first.items[-1].id == second.items[0].id
    ids = await exported_ids(x, ScanLogQuery(page=2, **query))
    assert len(ids) == len(set(ids)) == 6 and str(added) in ids


@pytest.mark.asyncio
async def test_streamed_export_retains_query_snapshot_across_concurrent_change(station):
    x = station
    original = {str(await scan(x, at=NOW-timedelta(seconds=i), source='Chosen')) for i in range(205)}
    await x.db.commit()
    stream = await scan_logs.export_scan_logs(x.db, x.user, ScanLogQuery(source_key='text:Chosen', page=9, page_size=1))
    chunks = [await anext(stream)]
    async with x.sessions() as writer:
        added = await scan(SimpleNamespace(db=writer, user=x.user), source='Chosen')
        removed = next(iter(original))
        await writer.execute(update(Scan).where(Scan.id==removed).values(source_text='Excluded'))
        await writer.commit()
    chunks.extend([chunk async for chunk in stream])
    rows = list(csv.DictReader(io.StringIO(''.join(chunks).lstrip('\ufeff'))))
    assert len(chunks)==3 and {row['Scan ID'] for row in rows}==original
    fresh = set(await exported_ids(x, ScanLogQuery(source_key='text:Chosen')))
    assert fresh == (original-{removed}) | {str(added)}


@pytest.mark.asyncio
async def test_midstream_failure_propagates_and_closes_cursor(station):
    x = station
    for i in range(205):
        await scan(x, at=NOW-timedelta(seconds=i))
    await x.db.commit()
    closed = False
    class FailingResult:
        def __init__(self, result): self.result = result
        async def partitions(self, size):
            async for batch in self.result.partitions(size):
                yield batch
                raise OSError('Injected cursor failure after first batch')
        async def close(self):
            nonlocal closed
            closed = True
            await self.result.close()
    class FailingDatabase:
        async def scalar(self, statement): return await x.db.scalar(statement)
        async def stream(self, statement): return FailingResult(await x.db.stream(statement))
    stream = await scan_logs.export_scan_logs(FailingDatabase(), x.user, ScanLogQuery())
    assert (await anext(stream)).startswith('\ufeff')
    assert len(list(csv.reader(io.StringIO(await anext(stream)))))==200
    with pytest.raises(OSError, match='Injected cursor'):
        await anext(stream)
    assert closed
