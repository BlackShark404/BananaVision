"""Station control state must survive application-data restoration."""
from alembic import op
from app.models.maintenance_state import MaintenanceState

revision = "0004_maintenance_state"
down_revision = "0003_system_configuration"
branch_labels = None
depends_on = None


def upgrade():
    MaintenanceState.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Maintenance recovery state cannot be safely discarded automatically")
