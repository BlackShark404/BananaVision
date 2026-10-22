"""Notification visibility and per-user read-receipt contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v1.notifications import router
from app.core.database import get_db
from app.models.app_notification import AppNotification
from app.models.app_notification_read import AppNotificationRead
from tests.test_dashboard import account, db  # noqa: F401

NOW = datetime(2026, 10, 2, 4, tzinfo=UTC)


@pytest.fixture
def notifications_db(db):  # noqa: F811
    AppNotification.__table__.create(db.session.get_bind(), checkfirst=True)
    AppNotificationRead.__table__.create(db.session.get_bind(), checkfirst=True)
    return db


def add_notification(database, user=None):
    notification_id = uuid.uuid4()
    database.add(
        AppNotification,
        id=notification_id,
        type="scan_flagged",
        title="Scan Auto-Flagged",
        message="Review this scan",
        timestamp=NOW,
        href="/scans/example",
        user_id=user.id if user else None,
    )
    return notification_id


def notification_app(database, current):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database_session():
        yield database

    app.dependency_overrides[get_db] = database_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return app


def test_broadcast_read_state_is_per_user_and_idempotent(notifications_db):
    first = account(notifications_db)
    second = account(notifications_db, name="Bea Cruz", role="Admin")
    notification_id = add_notification(notifications_db)
    current = {"user": first}

    with TestClient(notification_app(notifications_db, current)) as client:
        first_list = client.get("/api/v1/notifications").json()["items"]
        assert [(row["id"], row["read"]) for row in first_list] == [
            (str(notification_id), False)
        ]

        first_read = client.patch(f"/api/v1/notifications/{notification_id}/read")
        assert first_read.status_code == 200
        first_read_again = client.patch(f"/api/v1/notifications/{notification_id}/read")
        assert first_read_again.status_code == 200

        first_list = client.get("/api/v1/notifications").json()["items"]
        assert first_list[0]["read"] is True

        current["user"] = second
        second_list = client.get("/api/v1/notifications").json()["items"]
        assert second_list[0]["read"] is False

    receipts = notifications_db.session.execute(
        select(AppNotificationRead)
    ).scalars().all()
    assert len(receipts) == 1
    assert receipts[0].notification_id == notification_id
    assert receipts[0].user_id == first.id
    assert receipts[0].read_at is not None


def test_private_notification_reads_are_recipient_scoped(notifications_db):
    user = account(notifications_db)
    other = account(notifications_db, name="Bea Cruz")
    own_notification = add_notification(notifications_db, user)
    other_notification = add_notification(notifications_db, other)
    broadcast_notification = add_notification(notifications_db)
    current = {"user": user}

    with TestClient(notification_app(notifications_db, current)) as client:
        listed = client.get("/api/v1/notifications")
        assert listed.status_code == 200
        listed_ids = {row["id"] for row in listed.json()["items"]}
        assert listed_ids == {
            str(own_notification),
            str(broadcast_notification),
        }
        assert str(other_notification) not in listed_ids

        denied = client.patch(
            f"/api/v1/notifications/{other_notification}/read"
        )
        assert denied.status_code == 404
        assert notifications_db.session.get(
            AppNotificationRead, (other_notification, user.id)
        ) is None

        marked = client.patch(f"/api/v1/notifications/{own_notification}/read")
        assert marked.status_code == 200
        assert notifications_db.session.get(
            AppNotificationRead, (own_notification, user.id)
        ) is not None

        broadcast = client.patch(
            f"/api/v1/notifications/{broadcast_notification}/read"
        )
        assert broadcast.status_code == 200
        assert notifications_db.session.get(
            AppNotificationRead, (broadcast_notification, user.id)
        ) is not None


def test_read_all_only_creates_receipts_for_the_current_user(notifications_db):
    user = account(notifications_db)
    other = account(notifications_db, name="Bea Cruz")
    own_notification = add_notification(notifications_db, user)
    other_notification = add_notification(notifications_db, other)
    broadcast_notification = add_notification(notifications_db)
    current = {"user": user}

    with TestClient(notification_app(notifications_db, current)) as client:
        response = client.post("/api/v1/notifications/read-all")
        assert response.status_code == 200

        receipts = notifications_db.session.execute(
            select(AppNotificationRead)
        ).scalars().all()
        assert {
            (receipt.notification_id, receipt.user_id) for receipt in receipts
        } == {
            (own_notification, user.id),
            (broadcast_notification, user.id),
        }
        assert all(receipt.read_at is not None for receipt in receipts)

        current["user"] = other
        other_list = client.get("/api/v1/notifications").json()["items"]
        read_state = {row["id"]: row["read"] for row in other_list}
        assert read_state == {
            str(other_notification): False,
            str(broadcast_notification): False,
        }
