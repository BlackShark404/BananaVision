"""Add session generation to existing accounts without changing credentials."""
import sqlalchemy as sa
from alembic import op

revision = "0001_session_revocation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("user_account"):
        raise RuntimeError("Initialize the base schema with python -m app.core.migrations first")
    columns = {column["name"] for column in inspector.get_columns("user_account")}
    if "token_version" not in columns:
        op.add_column("user_account", sa.Column(
            "token_version", sa.Integer(), nullable=False, server_default=sa.text("1"),
        ))


def downgrade():
    raise RuntimeError("Removing session revocation is unsafe; restore a reviewed database backup instead")
