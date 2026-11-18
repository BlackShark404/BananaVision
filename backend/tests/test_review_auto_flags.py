"""Cleanup of old system flags: preview by default, changes only with --apply.

Before 2026-11-18 the system flagged scans for reasons other than low confidence. The
review_auto_flags command removes those old flags under the current rule (a scan is flagged
only when its confidence is below the saved threshold). Tests use the isolated SQLite
fixture and a disposable PostgreSQL schema; never a live station database.
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.time import now_manila
from app.models import (
    ActivityLog,
    Intake,
    OperatorProfile,
    Scan,
    ScanClassification,
    ScanEvent,
    ScanNote,
    SystemConfig,
    UserAccount,
    UserRole,
)
from app.schemas.enums import ActiveStatusEnum, CultivarEnum, RipenessEnum
from app.services.scan_creation import create_scan_record
from scripts import review_auto_flags as cleanup
from tests.test_time_and_writes import SessionAdapter
from tests.test_time_and_writes import application as application_fixture

application = application_fixture


def sessions(app):
    return lambda: SessionAdapter(app.engine, app.state)


def add_scan(app, confidence, *, flagged=True, flag_reason=None, minutes=0):
    """A stored scan as the kiosk saved it; returns its id."""
    async def create():
        async with SessionAdapter(app.engine, app.state) as db:
            scan = await create_scan_record(
                db, operator_id=app.ids.profile, operator_name="Original Name",
                classification=ScanClassification(
                    cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.RIPE,
                    confidence=confidence, spoilage_days="3", finger_count=9,
                ),
                date_time=now_manila() - timedelta(minutes=minutes), actor_id=app.ids.operator,
                actor_name="Original Name", flagged=flagged, flag_reason=flag_reason,
            )
            await db.commit()
            return scan.id

    return asyncio.run(create())


def add_event(app, scan_id, kind, revision=2, **values):
    with Session(app.engine) as db:
        db.add(ScanEvent(scan_id=scan_id, revision=revision, kind=kind, actor_id=app.ids.admin,
                         actor_name="Admin User", new_values=values or {"flagged": True}))
        db.get(Scan, scan_id).revision = revision
        db.commit()


def state(app):
    """Everything the command may change, for before/after comparisons."""
    with Session(app.engine) as db:
        return (
            sorted((str(s.id), s.flagged, s.revision) for s in db.scalars(select(Scan))),
            db.scalar(select(func.count()).select_from(ScanEvent)),
            db.scalar(select(func.count()).select_from(ActivityLog)),
        )


def run(app, **options):
    return asyncio.run(cleanup.review(sessions(app), **options))


def decisions(report):
    return {str(item.scan_id): (item.action, item.reason) for item in report.decisions}


@pytest.fixture
def stored(application):
    app = application
    ids = SimpleNamespace(
        confident=add_scan(app, 92.0, minutes=5),
        low=add_scan(app, 70.0, minutes=4),
        person_flag=add_scan(app, 93.0, minutes=3),
        noted=add_scan(app, 94.0, minutes=2),
        unknown=add_scan(app, None, minutes=1),
        unflagged=add_scan(app, 95.0, flagged=False),
    )
    add_event(app, ids.person_flag, "flag", flagged=True)
    add_event(app, ids.noted, "note", text="Checked the crown")
    return app, ids


def test_preview_lists_every_decision_and_changes_nothing(stored):
    app, ids = stored
    before = state(app)
    report = run(app)
    assert report.applied is False and report.threshold == 85
    assert decisions(report) == {
        str(ids.confident): ("remove", "Confidence 92% is not below the 85% threshold"),
        str(ids.low): ("keep", "Confidence 70% is below the 85% threshold"),
        str(ids.person_flag): ("keep", "A person flagged, corrected or noted this scan"),
        str(ids.noted): ("keep", "A person flagged, corrected or noted this scan"),
        str(ids.unknown): ("keep", "No confidence is stored for this scan"),
    }
    assert report.removed == 0
    assert state(app) == before
    text_out = cleanup.render(report)
    assert "PREVIEW" in text_out and "nothing was changed" in text_out
    assert "remove flag: 1" in text_out and "keep flag: 4" in text_out
    assert str(ids.confident) in text_out
    assert "postgresql" not in text_out.lower() and "password" not in text_out.lower()


def test_apply_needs_a_named_active_administrator(stored):
    app, _ = stored
    before = state(app)
    with Session(app.engine) as db:
        db.add(UserAccount(id=uuid4(), role_id=1, username="retired", full_name="Retired Admin",
                           password_hash="unused", status=ActiveStatusEnum.INACTIVE))
        db.commit()
    for username, message in [
        (None, "--apply needs --admin"),
        ("nobody", "No active administrator"),
        ("operator", "No active administrator"),
        ("retired", "No active administrator"),
    ]:
        with pytest.raises(cleanup.CleanupError, match=message):
            run(app, apply=True, admin_username=username)
    with Session(app.engine) as db:
        db.delete(db.scalars(select(UserAccount).where(UserAccount.username == "retired")).one())
        db.commit()
    assert state(app) == before


def test_apply_removes_only_flags_the_rule_would_not_set_and_records_each_change(stored):
    app, ids = stored
    report = run(app, apply=True, admin_username="admin")
    assert report.applied is True and report.removed == 1
    with Session(app.engine) as db:
        flags = {str(s.id): s.flagged for s in db.scalars(select(Scan))}
        assert flags[str(ids.confident)] is False
        assert all(flags[str(scan)] is True
                   for scan in (ids.low, ids.person_flag, ids.noted, ids.unknown))
        assert db.get(Scan, ids.confident).revision == 2
        [event] = db.scalars(select(ScanEvent).where(
            ScanEvent.scan_id == ids.confident, ScanEvent.kind == "flag")).all()
        assert event.previous_values == {"flagged": True}
        assert event.new_values == {"flagged": False}
        assert (event.actor_id, event.actor_name) == (app.ids.admin, "Admin User")
        assert event.reason == (
            "Auto-flag rule corrected: only a confidence below the threshold flags a scan "
            "(92% is not below 85%)"
        )
        [audit_row] = db.scalars(select(ActivityLog).where(
            ActivityLog.action == "scan_flag")).all()
        assert audit_row.user_id == app.ids.admin and str(ids.confident) in audit_row.details
    assert "1 flag removed" in cleanup.render(report)

    # Running it again finds nothing left to change.
    after = state(app)
    again = run(app, apply=True, admin_username="admin")
    assert again.removed == 0 and str(ids.confident) not in decisions(again)
    assert state(app) == after


def test_the_saved_threshold_decides(stored):
    app, ids = stored
    with Session(app.engine) as db:
        db.scalars(select(SystemConfig)).one().confidence_threshold = 95
        db.commit()
    report = run(app)
    assert report.threshold == 95
    assert decisions(report)[str(ids.confident)] == (
        "keep", "Confidence 92% is below the 95% threshold")


def test_a_flag_the_system_set_under_the_current_rule_is_judged_the_same_way(application):
    app = application
    scan_id = add_scan(app, 60.0, flag_reason="Confidence 60% is below the 85% threshold")
    assert decisions(run(app))[str(scan_id)][0] == "keep"
    with Session(app.engine) as db:
        db.scalars(select(SystemConfig)).one().confidence_threshold = 50
        db.commit()
    # A lower threshold does not un-flag by itself; the admin decides with --apply.
    assert decisions(run(app))[str(scan_id)] == (
        "remove", "Confidence 60% is not below the 50% threshold")


def test_a_scan_a_person_handles_before_the_change_is_left_alone(stored, monkeypatch):
    app, ids = stored
    original = cleanup._remove_flag

    async def flagged_meanwhile(db, scan_id, admin, threshold):
        # A reviewer adds a note after the preview list was built and before the change.
        add_event(app, scan_id, "note", text="Looking at this one")
        return await original(db, scan_id, admin, threshold)

    monkeypatch.setattr(cleanup, "_remove_flag", flagged_meanwhile)
    report = run(app, apply=True, admin_username="admin")
    assert report.removed == 0
    with Session(app.engine) as db:
        assert db.get(Scan, ids.confident).flagged is True


def test_command_line_preview_and_missing_admin(stored, capsys, monkeypatch):
    app, _ = stored
    monkeypatch.setattr(cleanup, "default_sessions", lambda: sessions(app))
    assert cleanup.main([]) == 0
    assert "PREVIEW" in capsys.readouterr().out
    assert cleanup.main(["--apply"]) == 2
    assert "--apply needs --admin" in capsys.readouterr().err


def as_user(app, account_id, role, **extra):
    from app.api.deps import get_current_user

    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=account_id, token_version=1, full_name="Original Name" if role == "Operator"
        else "Admin User", role=SimpleNamespace(name=role), **extra,
    )


def request(revision=1, **fields):
    return {"request_id": str(uuid4()), "expected_revision": revision, **fields}


def test_an_operator_flag_on_an_already_flagged_scan_is_kept(application):
    """Kiosk "Flag for Review" on a scan the system had already flagged changes nothing, so
    it leaves no history entry. The request receipt is the only trace of the person's flag."""
    app = application
    scan_id = add_scan(app, 92.0)
    as_user(app, app.ids.operator, "Operator")
    response = app.client.patch(f"/api/v1/scans/{scan_id}/flag",
                                json=request(flagged=True, reason="Crown looks damaged"))
    assert response.status_code == 200, response.text
    with Session(app.engine) as db:
        kinds = db.scalars(select(ScanEvent.kind).where(ScanEvent.scan_id == scan_id)).all()
    assert kinds == ["created"]  # the flag request recorded nothing
    assert decisions(run(app))[str(scan_id)] == ("keep", cleanup.UNRECORDED)
    report = run(app, apply=True, admin_username="admin")
    assert report.removed == 0
    with Session(app.engine) as db:
        assert db.get(Scan, scan_id).flagged is True


def test_a_status_change_is_not_a_flag_decision(application):
    app = application
    scan_id = add_scan(app, 92.0)
    as_user(app, app.ids.admin, "Admin")
    response = app.client.patch(f"/api/v1/scans/{scan_id}/status",
                                json=request(inventory_status="Sold", reason="Dispatched"))
    assert response.status_code == 200, response.text
    assert decisions(run(app))[str(scan_id)] == (
        "remove", "Confidence 92% is not below the 85% threshold")


def test_scans_from_before_scan_history_are_left_to_people(application):
    app = application
    corrected = add_scan(app, 92.0, minutes=3)
    noted = add_scan(app, 93.0, minutes=2)
    no_record = add_scan(app, 94.0, minutes=1)
    with Session(app.engine) as db:
        # Older stations: corrections and notes have no history entry, and scans restored
        # from an old archive have no creation entry at all.
        db.get(Scan, corrected).is_overridden = True
        db.add(ScanNote(scan_id=noted, text="Checked", author_name="Admin User"))
        for event in db.scalars(select(ScanEvent).where(ScanEvent.scan_id == no_record)):
            db.delete(event)
        db.commit()
    found = decisions(run(app))
    assert found[str(corrected)] == ("keep", cleanup.HANDLED)
    assert found[str(noted)] == ("keep", cleanup.HANDLED)
    assert found[str(no_record)] == ("keep", cleanup.UNKNOWN_ORIGIN)
    assert run(app, apply=True, admin_username="admin").removed == 0


def test_a_failure_on_one_scan_does_not_stop_the_others(application, monkeypatch):
    app = application
    first = add_scan(app, 92.0, minutes=2)
    second = add_scan(app, 93.0, minutes=1)
    original = cleanup.scan_records.apply_scan_change

    async def fail_for_first(db, scan, *args, **kwargs):
        if scan.id == first:
            raise RuntimeError("simulated database error")
        return await original(db, scan, *args, **kwargs)

    monkeypatch.setattr(cleanup.scan_records, "apply_scan_change", fail_for_first)
    report = run(app, apply=True, admin_username="admin")
    assert (report.removed, report.skipped) == (1, 1)
    with Session(app.engine) as db:
        assert db.get(Scan, first).flagged is True
        assert db.get(Scan, second).flagged is False
    assert "1 scan could not be changed" in cleanup.render(report)


def test_an_administrator_deactivated_during_the_run_stops_it(application, monkeypatch):
    app = application
    scan_id = add_scan(app, 92.0)
    original = cleanup._remove_flag

    async def deactivate_first(db, target, admin, threshold):
        with Session(app.engine) as other:
            other.get(UserAccount, app.ids.admin).status = ActiveStatusEnum.INACTIVE
            other.commit()
        return await original(db, target, admin, threshold)

    monkeypatch.setattr(cleanup, "_remove_flag", deactivate_first)
    with pytest.raises(cleanup.CleanupError, match="no longer an active administrator"):
        run(app, apply=True, admin_username="admin")
    with Session(app.engine) as db:
        assert db.get(Scan, scan_id).flagged is True


def test_the_command_refuses_to_guess_the_database_from_another_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(cleanup.CleanupError, match="from the backend folder"):
        cleanup.default_sessions()


# ── PostgreSQL: real row locks and transactions ───────────────────────────────

@pytest_asyncio.fixture
async def pg():
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = "qa_flags_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema, "timezone": "Asia/Manila"}}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        async with factory() as db:
            role = UserRole(name="Admin")
            db.add(role)
            await db.flush()
            admin = UserAccount(username="admin", full_name="Admin User", role_id=role.id,
                                password_hash="test-only")
            db.add_all([admin, SystemConfig(canonical_key=1, revision=1, confidence_threshold=80,
                                            data_retention_enabled=True)])
            await db.flush()
            profile = OperatorProfile(account_id=admin.id)
            intake = Intake(source="Supplier", intake_date=now_manila().date())
            db.add_all([profile, intake])
            await db.flush()
            scans = {}
            for name, confidence in (("confident", 91.5), ("low", 62.0)):
                scan = await create_scan_record(
                    db, operator_id=profile.id, operator_name="Admin User", intake=intake,
                    classification=ScanClassification(
                        cultivar=CultivarEnum.LAKATAN, ripeness=RipenessEnum.RIPE,
                        confidence=confidence, spoilage_days="3", finger_count=9,
                    ),
                    date_time=now_manila(), actor_id=admin.id, actor_name="Admin User",
                    flagged=True,
                )
                scans[name] = scan.id
            await db.commit()
        yield SimpleNamespace(sessions=factory, admin=admin.id, **scans)
    finally:
        await engine.dispose()
        async with control.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required",
)
@pytest.mark.asyncio
async def test_postgresql_apply_removes_the_flag_once_under_row_locks(pg):
    preview = await cleanup.review(pg.sessions)
    assert preview.threshold == 80 and preview.removed == 0
    report = await cleanup.review(pg.sessions, apply=True, admin_username="admin")
    assert report.removed == 1
    async with pg.sessions() as db:
        confident = await db.get(Scan, pg.confident)
        low = await db.get(Scan, pg.low)
        assert (confident.flagged, confident.revision) == (False, 2)
        assert (low.flagged, low.revision) == (True, 1)
        events = (await db.execute(
            select(ScanEvent).where(ScanEvent.kind == "flag"))).scalars().all()
        assert [(e.scan_id, e.actor_id) for e in events] == [(pg.confident, pg.admin)]
        rows = (await db.execute(select(ActivityLog).where(
            ActivityLog.action == "scan_flag"))).scalars().all()
        assert len(rows) == 1 and rows[0].user_id == pg.admin
    again = await cleanup.review(pg.sessions, apply=True, admin_username="admin")
    assert again.removed == 0
