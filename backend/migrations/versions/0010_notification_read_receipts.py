"""Replace shared notification flags with per-user read receipts."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

from app.core.time import now_manila

revision = "0010_notification_read_receipts"
down_revision = "0009_camera_slots"
branch_labels = None
depends_on = None


def _as_uuid(value):
    return uuid.UUID(str(value)) if value is not None else None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if (
        "app_notification" in tables
        and "user_account" in tables
        and "app_notification_read" not in tables
    ):
        op.create_table(
            "app_notification_read",
            sa.Column("notification_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["notification_id"],
                ["app_notification.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["user_account.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("notification_id", "user_id"),
        )
        op.create_index(
            "ix_app_notification_read_user_id",
            "app_notification_read",
            ["user_id"],
        )
        tables = set(sa.inspect(bind).get_table_names())

    if "app_notification" not in tables or "app_notification_read" not in tables:
        return

    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("app_notification")
    }
    if "is_read" not in columns:
        return

    notification = sa.Table(
        "app_notification", sa.MetaData(), autoload_with=bind
    )
    # Explicit UUID types keep SQLite and PostgreSQL inserts consistent with ORM
    # storage instead of relying on reflected column types.
    read_table = sa.table(
        "app_notification_read",
        sa.column("notification_id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("read_at", sa.DateTime(timezone=True)),
    )
    account = sa.Table("user_account", sa.MetaData(), autoload_with=bind)

    read_rows = bind.execute(
        sa.select(
            notification.c.id,
            notification.c.user_id,
            notification.c.is_read,
        ).where(notification.c.is_read.is_(True))
    ).all()
    account_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("user_account")
    }
    active_account_ids = []
    if "status" in account_columns:
        active_account_ids = [
            row[0]
            for row in bind.execute(
                sa.select(account.c.id).where(account.c.status == "ACTIVE")
            ).all()
        ]
    read_at = now_manila()
    receipts = []
    for notification_id, user_id, _ in read_rows:
        notification_uuid = _as_uuid(notification_id)
        if user_id is not None:
            receipts.append({
                "notification_id": notification_uuid,
                "user_id": _as_uuid(user_id),
                "read_at": read_at,
            })
            continue
        receipts.extend({
            "notification_id": notification_uuid,
            "user_id": _as_uuid(active_account_id),
            "read_at": read_at,
        } for active_account_id in active_account_ids)
    if receipts:
        bind.execute(read_table.insert(), receipts)

    op.drop_column("app_notification", "is_read")


def downgrade():
    raise RuntimeError(
        "Notification read receipts cannot be discarded automatically"
    )
