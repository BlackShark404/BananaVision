"""Demo seeding on an explicitly disposable PostgreSQL schema, never station data."""

import asyncio
import csv
import io
import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import seed
from app.core.time import MANILA
from app.models import Scan, ScanEvent, UserAccount
from app.schemas.scan_logs import ScanLogQuery
from app.services import analytics, scan_logs, scan_records
from app.services.feature_engineering import calc_vpd
from app.services.spoilage import SpoilagePredictor

pytestmark = pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"),
    reason="Disposable PostgreSQL required",
)


@pytest_asyncio.fixture
async def empty_seed_database(monkeypatch):
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = "qa_seed_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {"search_path": schema, "timezone": "Asia/Manila"},
        },
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(seed, "engine", engine)
    # Also permits RED reproduction against the old factory-based generator.
    monkeypatch.setattr(seed, "async_session_factory", sessions, raising=False)
    monkeypatch.setattr(
        seed,
        "get_settings",
        lambda: SimpleNamespace(
            is_production=False,
            bootstrap_admin_username="seed_admin",
            bootstrap_admin_password=SecretStr("Disposable-Test-Only!42"),
            camera_device_ids=[0, 1, 2, 3],
        ),
    )
    monkeypatch.setattr(seed, "now_manila", lambda: datetime(2026, 10, 19, 0, 15, tzinfo=MANILA))
    try:
        yield SimpleNamespace(engine=engine, sessions=sessions)
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


async def test_seed_environment_matches_stored_precision_and_current_scan_contract(
    empty_seed_database,
):
    await seed.main()
    async with empty_seed_database.sessions() as db:
        scans = (await db.scalars(select(Scan))).all()
        assert len(scans) == 25
        predictor = SpoilagePredictor()
        predictor.load()
        for scan in scans:
            c = scan.classification
            assert c.vpd is not None, "New synthetic readings should include computed VPD"
            assert float(c.vpd) == calc_vpd(float(c.temperature), float(c.humidity))
            assert c.treatment == scan.intake.treatment
            expected_spoilage = predictor.predict(
                c.cultivar.value,
                c.ripeness.value,
                float(c.temperature),
                float(c.humidity),
                vpd=float(c.vpd),
                treatment=c.treatment.value,
            )
            if expected_spoilage != c.spoilage_days:
                assert float(c.spoilage_days) == pytest.approx(float(expected_spoilage))
            assert (
                c.dew_point is None and c.heat_index is None
            )  # Production does not persist these.
            assert scan.operator_name_snapshot == scan.operator.account.full_name
            assert scan.source_name_snapshot == scan.intake.supplier.name
            assert scan.operator_name_snapshot.startswith("Demo ")
            assert scan.source_name_snapshot.startswith("Demo ")
            assert scan.intake_origin_id == scan.intake_id and scan.intake_provenance == "linked"
            assert scan.intake.created_at <= scan.date_time <= scan.updated_at
            assert scan.intake.intake_date <= scan.date_time.date()
            original = scan.original_ai_result
            assert original is not None
            assert (
                original.cultivar,
                original.ripeness,
                original.confidence,
                original.finger_count,
                original.spoilage_days,
            ) == (
                c.cultivar,
                c.ripeness,
                c.confidence,
                c.finger_count,
                c.spoilage_days,
            )
            assert original.created_at == scan.date_time


async def test_seeder_loads_shared_predictor_before_generating_scans(empty_seed_database, monkeypatch):
    predictor = SpoilagePredictor()
    loaded = []

    def load():
        loaded.append(True)

    def predict(*args, **kwargs):
        assert loaded == [True]
        assert kwargs["vpd"] == calc_vpd(args[2], args[3])
        assert kwargs["treatment"] in ("Natural", "Ethephon")
        return "2.00001"

    monkeypatch.setattr(predictor, "load", load)
    monkeypatch.setattr(predictor, "predict", predict)
    monkeypatch.setattr(seed, "SpoilagePredictor", lambda: predictor)
    await seed.main()
    async with empty_seed_database.sessions() as db:
        scans = (await db.scalars(select(Scan))).all()
        assert len(scans) == 25
        assert all(s.classification.spoilage_days == "2.00001" for s in scans)
        assert all(s.original_ai_result.spoilage_days == "2.00001" for s in scans)


@pytest.mark.parametrize("reset_demo", [False, True])
async def test_seed_history_and_consumer_apis_are_consistent(empty_seed_database, reset_demo):
    await seed.main()
    if reset_demo:
        await seed.main(reset_demo=True)
    async with empty_seed_database.sessions() as db:
        admin = await db.scalar(select(UserAccount).where(UserAccount.username == "seed_admin"))
        scans = (await db.scalars(select(Scan))).all()
        events = (await db.scalars(select(ScanEvent))).all()
        assert len(events) == 35  # 25 creations and 10 later sales.
        for scan in scans:
            detail = await scan_records.serialize_detail(db, scan, admin)
            assert detail.history and not any(e.legacy for e in detail.history)
            assert detail.history[0].kind == "created"
            assert all(e.actor_name == "Demo Seeder" and e.actor_id is None for e in detail.history)
            assert all("Synthetic" in e.reason for e in detail.history)
            assert detail.history[-1].revision == scan.revision
        summary = await analytics.get_summary(db, admin, date_range="all")
        assert summary.total_scans == summary.confidence_sample_count == 25
        assert sum(row.total_scans for row in summary.operator_performance) == 25
        logs = await scan_logs.list_scan_logs(db, admin, ScanLogQuery(page_size=100))
        assert logs.total == 25 and all(row.vpd is not None for row in logs.items)
        content = await scan_logs.export_scan_logs(db, admin, ScanLogQuery())
        rows = list(
            csv.DictReader(io.StringIO("".join([part async for part in content]).lstrip("\ufeff")))
        )
        assert len(rows) == 25
        assert {row["VPD (kPa)"] for row in rows} == {f"{s.classification.vpd:.3f}" for s in scans}


async def test_seed_refuses_repeat_without_changing_existing_rows(empty_seed_database):
    await seed.main()
    async with empty_seed_database.sessions() as db:
        before = set(await db.scalars(select(Scan.id)))
    with pytest.raises(seed.DatabaseNotEmptyError, match="empty"):
        await seed.main()
    async with empty_seed_database.sessions() as db:
        assert set(await db.scalars(select(Scan.id))) == before


async def test_seed_refuses_any_existing_data_before_schema_changes(empty_seed_database):
    async with empty_seed_database.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE user_evidence (message TEXT)"))
        await connection.execute(text("INSERT INTO user_evidence VALUES ('keep me')"))
    with pytest.raises(seed.DatabaseNotEmptyError, match="empty"):
        await seed.main()
    async with empty_seed_database.engine.connect() as connection:
        assert await connection.scalar(text("SELECT message FROM user_evidence")) == "keep me"
        assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == [
            "user_evidence"
        ]


async def test_seed_rolls_back_schema_and_rows_on_failure(empty_seed_database, monkeypatch):
    generate = seed.seed_data

    async def fail_after_generation(db):
        await generate(db)
        raise RuntimeError("fixture failure before commit")

    monkeypatch.setattr(seed, "seed_data", fail_after_generation)
    with pytest.raises(RuntimeError, match="fixture failure"):
        await seed.main()
    async with empty_seed_database.engine.connect() as connection:
        assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == []


async def test_explicit_reset_replaces_demo_records_and_reapplies_migrations(empty_seed_database):
    await seed.main()
    async with empty_seed_database.sessions() as db:
        before = set(await db.scalars(select(Scan.id)))
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
    async with empty_seed_database.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE user_evidence (message TEXT)"))
        await connection.execute(text("INSERT INTO user_evidence VALUES ('keep me')"))
    await seed.main(reset_demo=True)
    async with empty_seed_database.sessions() as db:
        after = set(await db.scalars(select(Scan.id)))
        assert len(after) == 25 and before.isdisjoint(after)
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == revision
        assert await db.scalar(text("SELECT message FROM user_evidence")) == "keep me"
        scans = (await db.scalars(select(Scan))).all()
        assert all(s.classification.vpd is not None and s.original_ai_result for s in scans)


async def test_failed_reset_restores_existing_records_and_schema(empty_seed_database, monkeypatch):
    await seed.main()
    async with empty_seed_database.sessions() as db:
        scans_before = set(await db.scalars(select(Scan.id)))
        users_before = set(await db.scalars(select(UserAccount.id)))
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
    generate = seed.seed_data

    async def fail(db):
        await generate(db)
        raise RuntimeError("reset fixture failure")

    monkeypatch.setattr(seed, "seed_data", fail)
    with pytest.raises(RuntimeError, match="reset fixture failure"):
        await seed.main(reset_demo=True)
    async with empty_seed_database.sessions() as db:
        assert set(await db.scalars(select(Scan.id))) == scans_before
        assert set(await db.scalars(select(UserAccount.id))) == users_before
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == revision


async def test_concurrent_explicit_resets_leave_one_complete_dataset(empty_seed_database):
    await seed.main()
    await asyncio.gather(seed.main(reset_demo=True), seed.main(reset_demo=True))
    async with empty_seed_database.sessions() as db:
        assert len((await db.scalars(select(Scan.id))).all()) == 25
        assert len((await db.scalars(select(ScanEvent.id))).all()) == 35


async def test_concurrent_seeds_create_only_one_dataset(empty_seed_database):
    results = await asyncio.gather(seed.main(), seed.main(), return_exceptions=True)
    assert sum(result is None for result in results) == 1
    errors = [result for result in results if isinstance(result, RuntimeError)]
    assert len(errors) == 1 and "empty" in str(errors[0])
    async with empty_seed_database.sessions() as db:
        assert len((await db.scalars(select(Scan.id))).all()) == 25


async def test_seed_keeps_zero_vpd(empty_seed_database, monkeypatch):
    uniform = seed.random.uniform
    monkeypatch.setattr(
        seed.random, "uniform", lambda a, b: 100 if (a, b) == (50, 60) else uniform(a, b)
    )
    await seed.main()
    async with empty_seed_database.sessions() as db:
        for scan in (await db.scalars(select(Scan))).all():
            assert scan.classification.humidity == 100
            assert scan.classification.vpd == 0


@pytest.mark.parametrize("production,password", [(True, SecretStr("test")), (False, None)])
@pytest.mark.parametrize("reset_demo", [False, True])
async def test_seed_guards_environment_before_touching_database(
    empty_seed_database,
    monkeypatch,
    production,
    password,
    reset_demo,
):
    monkeypatch.setattr(
        seed,
        "get_settings",
        lambda: SimpleNamespace(
            is_production=production,
            bootstrap_admin_password=password,
        ),
    )
    with pytest.raises(RuntimeError, match="non-production"):
        await seed.main(reset_demo=reset_demo)
    async with empty_seed_database.engine.connect() as connection:
        assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == []


def test_seed_cli_reports_expected_refusal_without_traceback(monkeypatch, caplog):
    async def refuse(**kwargs):
        raise seed.DatabaseNotEmptyError("existing data was not changed")

    monkeypatch.setattr(seed, "main", refuse)
    assert seed.run_cli([]) == 20
    assert "Demo seeding skipped" in caplog.text
    assert "existing data was not changed" in caplog.text
    assert "empty development database" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_seed_cli_does_not_swallow_unexpected_failures(monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("unexpected fixture failure")

    monkeypatch.setattr(seed, "main", fail)
    with pytest.raises(RuntimeError, match="unexpected fixture failure"):
        seed.run_cli([])


@pytest.mark.parametrize("arguments,reset_demo", [([], False), (["--reset-demo"], True)])
def test_seed_cli_reports_success_only_after_completion(monkeypatch, arguments, reset_demo):
    completed = []

    async def succeed(**kwargs):
        completed.append(kwargs["reset_demo"])

    monkeypatch.setattr(seed, "main", succeed)
    assert seed.run_cli(arguments) == 0
    assert completed == [reset_demo]
