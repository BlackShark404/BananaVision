"""Add actor_name snapshot to activity_log and append-only trigger.

The actor_name column preserves the actor's display name at the time an event
was recorded, so renaming or deleting the account does not rewrite history.

The append-only trigger prevents UPDATE and DELETE on activity_log rows,
enforcing audit immutability at the database level.  The trigger is installed
on PostgreSQL only; SQLite test fixtures are not affected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_audit_integrity"
down_revision = "0011_device_scan_links"
branch_labels = None
depends_on = None

# Backfill batch size — small enough to avoid lock contention on busy stations.
_BATCH = 500


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if bind.dialect.name == "postgresql" and "activity_log" in tables:
        op.execute(sa.text("SET LOCAL bananavision.audit_restore = 'on'"))

    # -- actor_name column ----------------------------------------------------
    if "activity_log" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("activity_log")}
        if "actor_name" not in existing_cols:
            op.add_column(
                "activity_log",
                sa.Column("actor_name", sa.String(100), nullable=True),
            )
            # Backfill from the user_account table so existing rows get a snapshot.
            if bind.dialect.name == "postgresql" and "user_account" in tables:
                op.execute(
                    sa.text(
                        """
                        UPDATE activity_log al
                        SET actor_name = ua.full_name
                        FROM user_account ua
                        WHERE al.user_id = ua.id
                          AND al.actor_name IS NULL
                        """
                    )
                )

    # -- PostgreSQL append-only trigger ---------------------------------------
    if bind.dialect.name == "postgresql" and "activity_log" in tables:
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION audit_log_append_only()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Allow the migration's own backfill (session_replication_role = 'replica')
                    -- and controlled restore operations that SET LOCAL bananavision.audit_restore
                    IF current_setting('session_replication_role', true) = 'replica' THEN
                        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD
                                          WHEN 'UPDATE' THEN NEW
                                          ELSE NULL END;
                    END IF;
                    IF current_setting('bananavision.audit_restore', true) = 'on' THEN
                        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD
                                          WHEN 'UPDATE' THEN NEW
                                          ELSE NULL END;
                    END IF;
                    RAISE EXCEPTION 'activity_log is append-only: % is not allowed', TG_OP;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        op.execute(sa.text("DROP TRIGGER IF EXISTS activity_log_append_only ON activity_log"))
        op.execute(
            sa.text(
                """
                CREATE TRIGGER activity_log_append_only
                BEFORE UPDATE OR DELETE ON activity_log
                FOR EACH ROW
                EXECUTE FUNCTION audit_log_append_only()
                """
            )
        )
        op.execute(sa.text("DROP TRIGGER IF EXISTS activity_log_truncate ON activity_log"))
        op.execute(
            sa.text(
                """
                CREATE TRIGGER activity_log_truncate
                BEFORE TRUNCATE ON activity_log
                FOR EACH STATEMENT
                EXECUTE FUNCTION audit_log_append_only()
                """
            )
        )
        op.execute(sa.text("SET LOCAL bananavision.audit_restore = 'off'"))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if bind.dialect.name == "postgresql" and "activity_log" in tables:
        op.execute(sa.text("DROP TRIGGER IF EXISTS activity_log_truncate ON activity_log"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS activity_log_append_only ON activity_log"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS audit_log_append_only()"))

    if "activity_log" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("activity_log")}
        if "actor_name" in existing_cols:
            op.drop_column("activity_log", "actor_name")
