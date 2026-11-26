"""Record expected received bunches per intake and variety."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models.intake_expected_stock import IntakeExpectedStock

revision = "0014_expected_stock"
down_revision = "0013_threshold_default"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "intake_expected_stock" in tables or "delivery_intake" not in tables:
        return
    columns = {column["name"]: column for column in sa.inspect(bind).get_columns("delivery_intake")}
    # The synthetic legacy fixture uses integer intake ids; real stations use UUIDs.
    if not isinstance(columns["id"]["type"], sa.Uuid):
        return
    IntakeExpectedStock.__table__.create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    if "intake_expected_stock" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("intake_expected_stock")