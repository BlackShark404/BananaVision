"""Update default confidence threshold from 85 to 80.

Replaces the legacy 85% confidence threshold default with 80%. This runs once, at upgrade:
a saved 85 becomes 80. A value an admin saves afterwards is kept, 85 included.

The revision id must fit alembic_version.version_num, VARCHAR(32). The first id of this
migration had 33 characters, so PostgreSQL rejected the upgrade and the backend did not
start.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_threshold_default"
down_revision = "0012_audit_integrity"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "system_config" in tables:
        op.execute(
            sa.text(
                "UPDATE system_config SET confidence_threshold = 80 WHERE confidence_threshold = 85"
            )
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "system_config" in tables:
        op.execute(
            sa.text(
                "UPDATE system_config SET confidence_threshold = 85 WHERE confidence_threshold = 80"
            )
        )
