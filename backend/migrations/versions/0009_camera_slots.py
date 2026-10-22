"""Normalize saved camera slots and drop derived operator counters.

Camera mappings move from repeated values on system_config to one device row per
slot. Existing archives remain readable through the versioned archive adapters.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

from app.core.time import now_manila

revision = '0009_camera_slots'
down_revision = '0008_windows_label_jobs'
branch_labels = None
depends_on = None


def _parse_camera_mapping(camera_ids, device_ids):
    if not isinstance(camera_ids, str) or not camera_ids.strip():
        return None
    names = [part.strip() for part in camera_ids.split(',')]
    if not 1 <= len(names) <= 4 or len(set(names)) != len(names):
        return None
    if any(not name or len(name) > 50 or ',' in name for name in names):
        return None
    if device_ids is None:
        from app.config import get_settings
        configured = list(get_settings().camera_device_ids)
        if len(configured) < len(names):
            return None
        device_ids = configured[:len(names)]
    if isinstance(device_ids, str):
        try:
            device_ids = json.loads(device_ids)
        except ValueError:
            return None
    if (not isinstance(device_ids, list) or len(device_ids) != len(names)
            or any(type(value) is not int or value < 0 for value in device_ids)
            or len(set(device_ids)) != len(device_ids)):
        return None
    return names, list(device_ids)


def _camera_mapping(bind, config_table):
    rows = bind.execute(
        sa.select(
            config_table.c.id,
            config_table.c.canonical_key,
            config_table.c.camera_ids,
            config_table.c.camera_device_ids,
        ).order_by(
            config_table.c.canonical_key.desc().nulls_last(),
            config_table.c.updated_at.desc(),
            config_table.c.id.desc(),
        )
    ).mappings().all()
    valid = []
    for row in rows:
        parsed = _parse_camera_mapping(row['camera_ids'], row['camera_device_ids'])
        if parsed is not None:
            valid.append((row['id'], *parsed))
    if not valid:
        bind.execute(config_table.update().values(legacy_conflict=True))
        return None
    chosen_id, names, device_ids = valid[0]
    if len(valid) > 1 and any((names, device_ids) != (other[1], other[2]) for other in valid[1:]):
        bind.execute(config_table.update().where(config_table.c.id == chosen_id)
                     .values(legacy_conflict=True))
    return names, device_ids


def _apply_camera_mapping(bind, names, device_ids):
    device_table = sa.Table('device', sa.MetaData(), autoload_with=bind)
    now = now_manila()
    for index, (name, device_index) in enumerate(zip(names, device_ids, strict=True)):
        existing = bind.execute(
            sa.select(device_table.c.id).where(device_table.c.camera_id == name)
        ).first()
        if existing is not None:
            bind.execute(device_table.update().where(device_table.c.id == existing.id).values(
                slot_index=index, device_index=device_index,
                updated_at=now,
            ))
        else:
            bind.execute(device_table.insert().values(
                id=str(uuid.uuid4()),
                camera_id=name,
                slot_index=index,
                device_index=device_index,
                label=f'Scanner {index + 1}',
                status='Offline',
                resolution=None,
                last_seen=None,
                created_at=now,
                updated_at=now,
            ))


def _camera_id_is_unique():
    inspector = sa.inspect(op.get_bind())
    return (
        any(
            index.get('unique') and index.get('column_names') == ['camera_id']
            for index in inspector.get_indexes('device')
        )
        or any(
            constraint.get('column_names') == ['camera_id']
            for constraint in inspector.get_unique_constraints('device')
        )
    )


def _ensure_camera_id_unique():
    """Promote an inline SQLite UNIQUE to a named index before batch recreation.

    SQLite reports inline UNIQUE constraints as neither indexes nor unique
    constraints, so a reflected batch table recreation silently drops them.
    Named indexes survive the recreation.
    """
    if not _camera_id_is_unique():
        op.create_index('ix_device_camera_id', 'device', ['camera_id'], unique=True)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'device' in tables:
        columns = {column['name'] for column in inspector.get_columns('device')}
        added_slots = 'slot_index' not in columns
        if added_slots:
            op.add_column('device', sa.Column('slot_index', sa.Integer(), nullable=True))
        if 'device_index' not in columns:
            op.add_column('device', sa.Column('device_index', sa.Integer(), nullable=True))

    if 'system_config' in tables:
        columns = {column['name'] for column in inspector.get_columns('system_config')}
        has_camera_columns = {'camera_ids', 'camera_device_ids'} <= columns
        if has_camera_columns and 'device' in tables:
            config_table = sa.Table('system_config', sa.MetaData(), autoload_with=bind)
            mapping = _camera_mapping(bind, config_table)
            if mapping is not None:
                _apply_camera_mapping(bind, *mapping)
        elif has_camera_columns:
            config_table = sa.Table('system_config', sa.MetaData(), autoload_with=bind)
            bind.execute(config_table.update().values(legacy_conflict=True))

    if 'device' in tables:
        device_inspector = sa.inspect(bind)
        device_columns = {
            column['name'] for column in device_inspector.get_columns('device')
        }
        if 'camera_id' in device_columns:
            _ensure_camera_id_unique()
        names = {index['name'] for index in device_inspector.get_indexes('device')}
        names.update(constraint['name'] for constraint in
                     device_inspector.get_unique_constraints('device'))
        if 'uq_device_slot_index' not in names:
            op.create_index('uq_device_slot_index', 'device', ['slot_index'], unique=True)
        if 'uq_device_device_index' not in names:
            op.create_index('uq_device_device_index', 'device', ['device_index'], unique=True)
        checks = {
            constraint['name']
            for constraint in device_inspector.get_check_constraints('device')
        }
        missing_checks = {
            'ck_device_slot_index_range':
                'slot_index IS NULL OR (slot_index >= 0 AND slot_index < 4)',
            'ck_device_device_index_nonnegative':
                'device_index IS NULL OR device_index >= 0',
        }
        missing_checks = {
            name: condition for name, condition in missing_checks.items()
            if name not in checks
        }
        if missing_checks:
            with op.batch_alter_table('device') as batch:
                for name, condition in missing_checks.items():
                    batch.create_check_constraint(name, condition)
            if 'camera_id' in device_columns and not _camera_id_is_unique():
                op.create_index('ix_device_camera_id', 'device', ['camera_id'], unique=True)

    if 'system_config' in tables:
        columns = {column['name'] for column in sa.inspect(bind).get_columns('system_config')}
        if 'camera_ids' in columns:
            op.drop_column('system_config', 'camera_ids')
        if 'camera_device_ids' in columns:
            op.drop_column('system_config', 'camera_device_ids')

    if 'operator_profile' in tables:
        columns = {column['name'] for column in sa.inspect(bind).get_columns('operator_profile')}
        if 'total_scans' in columns:
            op.drop_column('operator_profile', 'total_scans')
        if 'flagged_scans' in columns:
            op.drop_column('operator_profile', 'flagged_scans')


def downgrade():
    raise RuntimeError('Saved camera slots and scan history must not be discarded automatically')
