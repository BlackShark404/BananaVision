"""Create durable Windows label jobs without changing the compatibility revision."""

from alembic import op

from app.models.print_job import PrintJob

revision = "0008_windows_label_jobs"
down_revision = "0007_prediction_print_jobs"
branch_labels = None
depends_on = None


def upgrade():
    PrintJob.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Print history cannot be discarded automatically")
