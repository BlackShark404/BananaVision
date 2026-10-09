"""Add revisions and immutable evidence without reconstructing historical facts."""
from alembic import op
import sqlalchemy as sa

from app.models.scan_history import ScanEvent, ScanMutation, ScanTombstone

revision = "0005_scan_record_history"
down_revision = "0004_maintenance_state"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "scan" in tables:
        columns = {c["name"] for c in sa.inspect(bind).get_columns("scan")}
        for column in (
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("operator_name_snapshot", sa.String(100), nullable=True),
            sa.Column("source_name_snapshot", sa.String(100), nullable=True),
        ):
            if column.name not in columns:
                op.add_column("scan", column)
    if "scan_original_ai_result" in tables:
        columns = {c["name"]: c for c in sa.inspect(bind).get_columns("scan_original_ai_result")}
        with op.batch_alter_table("scan_original_ai_result") as batch:
            if "spoilage_days" not in columns:
                batch.add_column(sa.Column("spoilage_days", sa.String(50), nullable=True))
            for name in ("cultivar", "ripeness", "confidence"):
                if not columns[name]["nullable"]:
                    batch.alter_column(name, existing_type=columns[name]["type"], nullable=True)
    for model in (ScanEvent, ScanMutation, ScanTombstone):
        model.__table__.create(bind, checkfirst=True)


def downgrade():
    raise RuntimeError("Scan history cannot be discarded automatically")
