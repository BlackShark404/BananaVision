"""Final policy/snapshot acceptance on uniquely isolated disposable schemas."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from starlette.requests import Request

from app.api.v1.intakes import IntakeBulkInventoryUpdate, bulk_update_intake_inventory
from app.api.v1.scans import list_scans
from app.core.migrations import upgrade_connection
from app.core.time import now_manila
from app.models import Intake, Scan, ScanClassification, UserAccount
from app.services import dashboard
from app.services.inventory_policy import eligible_stock, inventory_facts
from tests.test_scan_records_postgresql import pytestmark, station  # noqa: F401


@pytest.mark.asyncio
async def test_pg_provenance_migration_and_deleted_parent_remain_distinguishable(station):  # noqa: F811 - pytest fixture injection
    x = station
    async with x.sessions() as db:
        unlinked = Scan(operator_id=x.operator)
        db.add(unlinked)
        await db.flush()
        unlinked_id = unlinked.id
        await db.execute(
            text("ALTER TABLE scan DROP COLUMN intake_origin_id, DROP COLUMN intake_provenance")
        )
        connection = await db.connection()
        await connection.run_sync(upgrade_connection)
        await db.commit()
    async with x.sessions() as db:
        linked = await db.get(Scan, x.scan)
        unknown = await db.get(Scan, unlinked_id)
        assert linked.intake_origin_id == x.intake and linked.intake_provenance == "linked"
        assert unknown.intake_origin_id is None and unknown.intake_provenance == "unverified"
        genuine = Scan(operator_id=x.operator)
        db.add(genuine)
        await db.flush()
        genuine_id = genuine.id
        await db.execute(delete(Intake).where(Intake.id == x.intake))
        await db.commit()
    async with x.sessions() as db:
        actor = await db.get(UserAccount, x.actors[0])
        records = (await db.execute(select(Scan))).scalars().all()
        now = now_manila()
        for row in records:
            assert inventory_facts(row, "In Stock", now)["inventory_eligible"] == (
                row.id == genuine_id
            )
        deleted = next(row for row in records if row.id == x.scan)
        assert deleted.intake_id is None and deleted.intake_origin_id == x.intake
        projection = dashboard._scoped_projection(actor, now)
        assert (
            await db.execute(select(projection.c.id).where(eligible_stock(projection)))
        ).scalars().all() == [genuine_id]


@pytest.mark.asyncio
async def test_pg_history_snapshot_locks_like_bulk_and_freezes_accepted_values(station):  # noqa: F811 - pytest fixture injection
    x = station
    async with x.sessions() as db:
        second = Scan(operator_id=x.operator, intake_id=x.intake)
        db.add(second)
        await db.flush()
        ids = sorted([x.scan, second.id])
        for i, identifier in enumerate(ids):
            row = await db.get(Scan, identifier)
            row.date_time = now_manila() + timedelta(seconds=i)
        await db.commit()

    async def capture():
        async with x.sessions() as db:
            await db.execute(text("SET LOCAL application_name = 'bv_snapshot_lock_probe'"))
            actor = await db.get(UserAccount, x.actors[0])
            result = await list_scans(db, actor, page=1, page_size=1, stable=True, snapshot_id=None)
            await db.commit()
            return result

    pending = None
    async with x.sessions() as blocker:
        try:
            await blocker.execute(select(Scan.id).where(Scan.id == ids[0]).with_for_update())
            pending = asyncio.create_task(capture())
            for _ in range(100):
                async with x.sessions() as observer:
                    waiting = await observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE application_name='bv_snapshot_lock_probe' "
                            "AND wait_event_type='Lock'"
                        )
                    )
                if waiting:
                    break
                await asyncio.sleep(0.02)
            assert waiting, "Reader did not reach its conflicting row lock"
            # If history locked descending, it already holds the higher ID and
            # this raises instead of completing. Same-ID-order locking avoids it.
            await blocker.execute(
                select(Scan.id).where(Scan.id == ids[1]).with_for_update(nowait=True)
            )
            actor = await blocker.get(UserAccount, x.actors[1])
            body = IntakeBulkInventoryUpdate(
                request_id=uuid4(),
                expected_revisions={i: 1 for i in ids},
                inventory_status="Sold",
                reason="Generated fixture shipment",
            )
            await bulk_update_intake_inventory(
                x.intake, body, blocker, actor, Request({"type": "http"})
            )
            await blocker.commit()
            first = await asyncio.wait_for(pending, 5)
        finally:
            await blocker.rollback()
            if pending and not pending.done():
                pending.cancel()
            if pending:
                await asyncio.gather(pending, return_exceptions=True)
    assert first.total == 2 and first.items[0].id == ids[1]
    assert first.items[0].inventory_status == "Sold" and first.items[0].revision == 2
    async with x.sessions() as db:
        actor = await db.get(UserAccount, x.actors[0])
        second = await list_scans(
            db, actor, page=2, page_size=1, stable=True, snapshot_id=first.snapshot_id
        )
        assert second.items[0].id == ids[0] and second.items[0].inventory_status == "Sold"


@pytest.mark.asyncio
async def test_pg_policy_and_remaining_life_match_hydrated_records(station):  # noqa: F811 - pytest fixture injection
    from app.models import ScanStatusLog

    x = station
    now = now_manila()
    cases = [
        ("In Stock", "unlinked", None, "1", True),
        ("In Stock", "unlinked", None, "Unknown", True),
        ("In Stock", "unlinked", None, "5-3", True),
        ("In Stock", "unlinked", None, "\u20033\u2003", True),
        ("Sold", "unlinked", None, "1", False),
        ("Spoiled", "unlinked", None, "1", False),
        ("In Stock", "unverified", None, "1", False),
        ("In Stock", "excluded", None, "1", False),
        ("In Stock", "linked", "Depleted", "1", False),
        ("In Stock", "linked", "Active", " 3 - 5 ", True),
    ]
    expected = {}
    async with x.sessions() as db:
        for status, provenance, intake_status, prediction, eligible in cases:
            parent = (
                Intake(source="Fixture", intake_date=now.date(), status=intake_status)
                if intake_status
                else None
            )
            if parent:
                db.add(parent)
                await db.flush()
            row = Scan(
                operator_id=x.operator,
                date_time=now - timedelta(days=2),
                intake_id=parent.id if parent else None,
                intake_provenance=provenance,
            )
            db.add(row)
            await db.flush()
            db.add(ScanClassification(scan_id=row.id, spoilage_days=prediction, finger_count=1))
            db.add(ScanStatusLog(scan_id=row.id, inventory_status=status, updated_at=now))
            expected[row.id] = (status, eligible)
        await db.commit()
    async with x.sessions() as db:
        actor = await db.get(UserAccount, x.actors[0])
        projection = dashboard._scoped_projection(actor, now)
        sql_rows = (
            await db.execute(
                select(
                    projection.c.id,
                    projection.c.remaining_days,
                    eligible_stock(projection).label("eligible"),
                )
            )
        ).all()
        for projected in sql_rows:
            if projected.id not in expected:
                continue
            row = await db.get(Scan, projected.id)
            status, eligible = expected[row.id]
            facts = inventory_facts(row, status, now)
            assert bool(projected.eligible) == eligible == facts["inventory_eligible"]
            if projected.remaining_days is None:
                assert facts["remaining_days"] is None
            else:
                assert float(projected.remaining_days) == pytest.approx(facts["remaining_days"])
