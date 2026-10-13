"""Record the prediction print-job migration head.

The print-job model is not part of this checkout.  Keep this revision
dependency-free so databases that already recorded it can still start and
fresh databases can advance through the same migration history.
"""

from alembic import op


revision = "0007_prediction_print_jobs"
down_revision = "0006_inventory_provenance"
branch_labels = None
depends_on = None


def upgrade():
    # The application schema is created from the current SQLAlchemy metadata.
    # This revision exists to preserve compatibility with databases stamped
    # with the previously published migration head.
    pass


def downgrade():
    raise RuntimeError("Print history cannot be discarded automatically")
