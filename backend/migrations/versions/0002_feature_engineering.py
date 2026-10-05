"""Version the previously manual batch lifecycle and engineered-feature columns."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

revision = "0002_feature_engineering"
down_revision = "0001_session_revocation"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    treatment = sa.String(20)
    if connection.dialect.name == "postgresql":
        treatment = ENUM("Natural", "Ethephon", name="treatmentenum", create_type=False)
        treatment.create(connection, checkfirst=True)
    additions = {
        "delivery_intake": [
            sa.Column("treatment", treatment, nullable=True, server_default=sa.text("'Natural'")),
            sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("treated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("spoiled_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "scan_classification": [
            sa.Column("dew_point", sa.Numeric(6, 3), nullable=True),
            sa.Column("vpd", sa.Numeric(6, 3), nullable=True),
            sa.Column("heat_index", sa.Numeric(5, 2), nullable=True),
            sa.Column("treatment", treatment, nullable=True),
        ],
    }
    for table, columns in additions.items():
        inspector = sa.inspect(connection)
        if not inspector.has_table(table):
            raise RuntimeError(f"Missing base table {table}; initialize the base schema first")
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade():
    raise RuntimeError("This migration preserves historical data; use a reviewed backup for rollback")
