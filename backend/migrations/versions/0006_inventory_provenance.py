"""Preserve known intake provenance; quarantine ambiguous legacy unlinked stock."""

import sqlalchemy as sa
from alembic import op

from app.models.scan_snapshot import ScanSnapshot

revision = "0006_inventory_provenance"
down_revision = "0005_scan_record_history"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    ScanSnapshot.__table__.create(bind, checkfirst=True)
    if "scan" not in sa.inspect(bind).get_table_names():
        return
    columns = {c["name"] for c in sa.inspect(bind).get_columns("scan")}
    if "intake_origin_id" not in columns:
        op.add_column("scan", sa.Column("intake_origin_id", sa.Uuid(), nullable=True))
    if "intake_provenance" not in columns:
        op.add_column(
            "scan",
            sa.Column(
                "intake_provenance", sa.String(20), nullable=False, server_default="unverified"
            ),
        )
        if "intake_id" in columns:
            bind.execute(
                sa.text(
                    "UPDATE scan SET intake_origin_id = intake_id, "
                    "intake_provenance = 'linked' WHERE intake_id IS NOT NULL"
                )
            )
    # Adoption of a schema already created from current models must not relabel
    # new unlinked records or erase recorded reconciliation decisions.


def downgrade():
    raise RuntimeError("Inventory provenance cannot be discarded automatically")
