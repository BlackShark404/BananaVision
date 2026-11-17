"""Activity Log read side: paging is pinned to an ``as_of`` boundary.

Rows that arrive while an administrator pages through the log must not shift later pages:
the first page reports the boundary it used and later pages pass it back. Tests use the
isolated SQLite fixture (and a disposable PostgreSQL schema when
``BANANAVISION_TEST_DATABASE_URL`` is set); no live station database is touched.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.api.v1.activity import list_activity
from app.core.database import Base
from app.core.time import MANILA, now_manila
from app.models import ActivityLog, UserAccount, UserRole
from app.services import audit
from tests.test_time_and_writes import application as application_fixture

application = application_fixture


def add_rows(app, count, start, action=audit.AuditAction.LOGIN, step=timedelta(minutes=1)):
    """Insert rows with fixed timestamps (start, start + step, ...); returns their ids."""
    rows = [ActivityLog(timestamp=start + step * index, user_id=app.ids.admin, action=str(action),
                        details=f"Seeded {action} #{index}")
            for index in range(count)]
    with Session(app.engine) as db:
        db.add_all(rows)
        db.commit()
        return [str(row.id) for row in rows]


def page(app, number, size, **params):
    response = app.client.get("/api/v1/activity",
                              params={"page": number, "page_size": size, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_as_of_pins_paging_while_newer_rows_arrive(application):
    app = application
    base = now_manila() - timedelta(hours=2)
    original = add_rows(app, 7, base)

    first = page(app, 1, 3)
    assert first["total"] == 7
    boundary = first["as_of"]
    assert datetime.fromisoformat(boundary) >= base + timedelta(minutes=6)

    # New activity lands while the administrator is still paging.
    add_rows(app, 4, datetime.fromisoformat(boundary) + timedelta(seconds=1))

    second = page(app, 2, 3, as_of=boundary)
    third = page(app, 3, 3, as_of=boundary)
    for later in (second, third):
        assert later["total"] == 7
        assert later["as_of"] == boundary

    ids = [item["id"] for item in first["items"] + second["items"] + third["items"]]
    assert len(ids) == len(set(ids)) == 7
    assert set(ids) == set(original)

    # A later boundary (a fresh load) sees the newer rows again.
    later = (datetime.fromisoformat(boundary) + timedelta(minutes=10)).isoformat()
    assert page(app, 1, 3, as_of=later)["total"] == 11


def test_as_of_round_trips_and_defaults_to_now(application):
    app = application
    before = now_manila()
    first = page(app, 1, 10)
    after = now_manila()
    used = datetime.fromisoformat(first["as_of"])
    assert used.utcoffset() == timedelta(hours=8)
    assert before <= used <= after

    # The exact string returned is accepted back and echoed unchanged.
    assert page(app, 1, 10, as_of=first["as_of"])["as_of"] == first["as_of"]

    # A zone-less boundary is Manila wall time; an explicit offset keeps its instant.
    assert page(app, 1, 10, as_of="2026-11-17T10:00:00")["as_of"] == "2026-11-17T10:00:00+08:00"
    utc = page(app, 1, 10, as_of="2026-11-17T02:00:00.250000Z")["as_of"]
    assert utc == "2026-11-17T10:00:00.250000+08:00"

    assert app.client.get("/api/v1/activity", params={"as_of": "yesterday"}).status_code == 422


def test_rows_stamped_after_the_server_clock_are_still_listed(application):
    """A restored backup from a station whose clock ran ahead, or a clock stepped back by NTP,
    must not hide rows: without as_of the boundary is the later of now and the newest row."""
    app = application
    ahead = now_manila() + timedelta(days=2)
    [future] = add_rows(app, 1, ahead)
    first = page(app, 1, 10)
    assert future in [item["id"] for item in first["items"]]
    assert datetime.fromisoformat(first["as_of"]) >= ahead
    # The returned boundary keeps that row on later pages too.
    assert future in [item["id"] for item in page(app, 1, 10, as_of=first["as_of"])["items"]]


def test_as_of_includes_rows_at_the_boundary_and_applies_with_filters(application):
    app = application
    base = datetime(2026, 11, 1, 9, 0, tzinfo=MANILA)
    add_rows(app, 3, base, action=audit.AuditAction.LOGIN)
    add_rows(app, 3, base, action=audit.AuditAction.LOGOUT)

    at_second = (base + timedelta(minutes=1)).isoformat()
    assert page(app, 1, 50, as_of=at_second)["total"] == 4  # two of each, boundary included
    filtered = page(app, 1, 50, as_of=at_second, action="logout")
    assert filtered["total"] == 2 and len(filtered["items"]) == 2
    assert {item["action"] for item in filtered["items"]} == {"logout"}
    searched = page(app, 1, 50, as_of=at_second, search="Seeded")
    assert searched["total"] == 4

    # The same instant written in UTC selects the same rows.
    utc = (base + timedelta(minutes=1)).astimezone(UTC).isoformat()
    assert page(app, 1, 50, as_of=utc)["total"] == 4


def test_activity_log_displays_actor_name_snapshot_after_user_rename(application):
    app = application
    with Session(app.engine) as db:
        row = ActivityLog(user_id=app.ids.admin, action="user_updated",
                          details="Name changed", actor_name="Snapshot Name",
                          timestamp=now_manila())
        db.add(row)
        user = db.get(UserAccount, app.ids.admin)
        user.full_name = "New Live Name"
        db.commit()

    p = page(app, 1, 10, action="user_updated")
    item = next(it for it in p["items"] if it["details"] == "Name changed")
    assert item["user_name"] == "Snapshot Name"


# ── PostgreSQL ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def pg_station():
    url = os.environ["BANANAVISION_TEST_DATABASE_URL"]
    schema = "qa_audit_read_" + uuid4().hex
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
            role = UserRole(name="Admin")
            db.add(role)
            await db.flush()
            admin = UserAccount(username="admin", full_name="Admin User", role_id=role.id,
                                password_hash="test-only")
            db.add(admin)
            await db.commit()
            yield SimpleNamespace(sessions=sessions, admin=admin)
    finally:
        await engine.dispose()
        async with control.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


async def pg_page(station, number, size, as_of=None):
    async with station.sessions() as db:
        response = await list_activity(db, station.admin, page=number, page_size=size,
                                       action=None, user_name=None, search=None, as_of=as_of)
    return response.model_dump(mode="json")


@pytest.mark.skipif(not os.environ.get("BANANAVISION_TEST_DATABASE_URL"),
                    reason="Disposable PostgreSQL required")
@pytest.mark.asyncio
async def test_postgresql_as_of_paging_is_stable_while_rows_are_inserted(pg_station):
    base = now_manila() - timedelta(hours=1)
    async with pg_station.sessions() as db:
        for index in range(5):
            await audit.record(db, audit.AuditAction.LOGIN, f"Original {index}",
                               actor=pg_station.admin, timestamp=base + timedelta(minutes=index))
        await db.commit()
        rows = (await db.execute(text("SELECT id FROM activity_log ORDER BY details"))).all()
        original = {str(row.id) for row in rows}

    first = await pg_page(pg_station, 1, 2)
    assert first["total"] == 5
    boundary = datetime.fromisoformat(first["as_of"])

    async with pg_station.sessions() as db:
        for index in range(3):
            await audit.record(db, audit.AuditAction.LOGOUT, f"Newer {index}",
                               actor=pg_station.admin)
        await db.commit()

    later = [await pg_page(pg_station, number, 2, as_of=boundary) for number in (2, 3)]
    for response in later:
        assert response["total"] == 5
        assert response["as_of"] == first["as_of"]
    ids = [item["id"] for item in first["items"] + later[0]["items"] + later[1]["items"]]
    assert len(ids) == len(set(ids)) == 5
    assert set(ids) == original
    assert (await pg_page(pg_station, 1, 2))["total"] == 8
