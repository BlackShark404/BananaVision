"""Independent account sessions against an explicitly disposable PostgreSQL schema."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.models import OperatorProfile, Scan, ScanClassification, UserAccount, UserRole
from app.schemas.scan import ScanFlagRequest
from app.schemas.scan_logs import ScanLogQuery
from app.services.scan_logs import list_scan_logs, reconcile_scan_logs
from app.services.scan_records import mutate_scan
from tests.test_scan_records_postgresql import station  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required",
)]


@pytest.mark.usefixtures("station")
async def test_committed_mutation_reconciles_three_accounts_and_removed_rows(request):
    x = request.getfixturevalue("station")
    async with x.sessions() as db:
        role = UserRole(name="Operator")
        db.add(role)
        await db.flush()
        owner = await db.get(UserAccount, x.actors[0])
        owner.role_id = role.id
        other = UserAccount(username="other", full_name="Other Operator", role_id=role.id,
                            password_hash="test-only")
        db.add(other)
        await db.flush()
        db.add(OperatorProfile(account_id=other.id))
        db.add(ScanClassification(scan_id=x.scan, cultivar="Lakatan", ripeness="Ripe",
                                  confidence=95, spoilage_days="11.00982880647441", finger_count=7))
        await db.commit()
        accounts = [x.actors[1], owner.id, other.id]

    snapshots = []
    for account in accounts:
        async with x.sessions() as db:
            user = await db.get(UserAccount, account)
            saved = await list_scan_logs(db, user, ScanLogQuery(stable=True))
            snapshots.append(saved)
            await db.commit()

    async with x.sessions() as db:
        user = await db.get(UserAccount, accounts[1])
        await mutate_scan(db, x.scan, user, "flag", ScanFlagRequest(
            request_id=uuid4(), expected_revision=1, flagged=True,
        ))

    for account, saved, expected in zip(accounts, snapshots, [1, 1, 0], strict=True):
        async with x.sessions() as db:
            user = await db.get(UserAccount, account)
            query = ScanLogQuery(snapshot_id=saved.snapshot_id, stable=True)
            live = await reconcile_scan_logs(db, user, query)
            assert live.total == live.flagged_count == live.review_count == expected
            assert len(live.items) == expected
            if expected:
                assert live.items[0].revision == 2 and live.items[0].flagged
                assert live.items[0].spoilage_days == "11.00982880647441"
            assert (await list_scan_logs(db, user, query)) == saved

    # No delete UI is invented: externally removed rows must vanish on next read.
    async with x.sessions() as db:
        await db.execute(delete(Scan).where(Scan.id == x.scan))
        await db.commit()
    for account, saved in zip(accounts, snapshots, strict=True):
        async with x.sessions() as db:
            user = await db.get(UserAccount, account)
            live = await reconcile_scan_logs(db, user, ScanLogQuery(snapshot_id=saved.snapshot_id))
            assert live.total == 0 and live.items == [] and live.at_risk_ids == []
