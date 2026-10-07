"""Add versioned canonical configuration without deleting legacy settings."""
from alembic import op
import sqlalchemy as sa

revision = '0003_system_configuration'
down_revision = '0002_feature_engineering'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('system_config'):
        # Empty/partial legacy schemas are completed by initialize_schema/create_all.
        return
    columns = {c['name'] for c in sa.inspect(bind).get_columns('system_config')}
    additions = [sa.Column('canonical_key', sa.Integer(), nullable=True),
                 sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
                 sa.Column('camera_device_ids', sa.JSON(), nullable=True),
                 sa.Column('legacy_conflict', sa.Boolean(), nullable=False, server_default=sa.false())]
    for column in additions:
        if column.name not in columns:
            op.add_column('system_config', column)
    inspector = sa.inspect(bind)
    if not any(c['column_names'] == ['canonical_key'] for c in inspector.get_unique_constraints('system_config')):
        if not any(i['name'] == 'uq_config_canonical_key' for i in inspector.get_indexes('system_config')):
            op.create_index('uq_config_canonical_key', 'system_config', ['canonical_key'], unique=True)
    if not any(c['name'] == 'ck_config_canonical_key' for c in inspector.get_check_constraints('system_config')):
        with op.batch_alter_table('system_config') as batch:
            batch.create_check_constraint('ck_config_canonical_key', 'canonical_key IS NULL OR canonical_key = 1')


def downgrade():
    raise RuntimeError('Saved configuration revisions must not be discarded automatically')
