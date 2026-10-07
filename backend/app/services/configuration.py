"""Canonical saved configuration and explicit post-commit camera application."""
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.core.time import now_manila
from app.models.device import Device
from app.models.system_config import SystemConfig
from app.schemas.common import SystemConfigUpdate
from app.services.camera_manager import camera_manager


def _validated_values(camera_ids, physical_ids, threshold, retention):
    value = SystemConfigUpdate(expected_revision=1, camera_ids=camera_ids,
        camera_device_ids=physical_ids, confidence_threshold=threshold,
        data_retention_enabled=retention)
    if len(value.camera_ids.split(',')) != len(value.camera_device_ids):
        raise ValueError('Provide one logical camera ID for every physical camera slot')
    return value.model_dump(exclude={'expected_revision'})


async def get_config(db) -> SystemConfig:
    """Select one valid legacy row, preserving all history and unique canonical ownership.

    The unique nullable canonical marker arbitrates concurrent first access. A losing
    initializer rolls back and reads the winner; initialization belongs before writes.
    """
    canonical = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1))
    if canonical is not None:
        try:
            _validated_values(canonical.camera_ids, canonical.camera_device_ids,
                              canonical.confidence_threshold, canonical.data_retention_enabled)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(503, 'Saved configuration is invalid; administrator repair is required') from exc
        return canonical
    rows = (await db.execute(select(SystemConfig).order_by(
        SystemConfig.updated_at.desc(), SystemConfig.id.desc()))).scalars().all()
    physical_ids = list(get_settings().camera_device_ids)
    valid = []
    for row in rows:
        try:
            values = _validated_values(row.camera_ids, row.camera_device_ids or physical_ids,
                row.confidence_threshold, row.data_retention_enabled)
            valid.append((row, values))
        except (ValueError, ValidationError):
            continue
    if rows and not valid:
        raise HTTPException(503, 'No valid saved configuration; administrator repair is required. Legacy rows were preserved.')
    if valid:
        canonical, values = valid[0]
        canonical.camera_device_ids = values['camera_device_ids']
        canonical.legacy_conflict = len(rows) > 1 and (
            len(valid) != len(rows) or any(values != other for _, other in valid[1:]))
        canonical.canonical_key = 1
    else:
        canonical = SystemConfig(canonical_key=1, revision=1, camera_device_ids=physical_ids,
            camera_ids=', '.join(f'CAM-{index + 1:03d}' for index in range(len(physical_ids))),
            confidence_threshold=85, data_retention_enabled=True, legacy_conflict=False)
        db.add(canonical)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        canonical = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1))
        if canonical is None:
            raise
    return canonical


def config_response(config) -> dict:
    applied_ids = list(camera_manager._logical_ids)
    physical_ids = list(camera_manager._device_ids) if camera_manager.is_initialized else []
    matches = applied_ids == [value.strip() for value in config.camera_ids.split(',')] and physical_ids == config.camera_device_ids
    online = set(camera_manager.online_cameras)
    all_online = matches and all(value in online for value in physical_ids)
    error = camera_manager.application_error
    status = 'applied' if all_online else ('partial' if matches and online else 'failed' if matches else 'pending')
    return {
        'camera_ids': config.camera_ids, 'camera_device_ids': config.camera_device_ids,
        'confidence_threshold': config.confidence_threshold,
        'data_retention_enabled': config.data_retention_enabled, 'revision': config.revision,
        'legacy_conflict': config.legacy_conflict,
        'applied_camera_ids': ', '.join(applied_ids) if camera_manager.is_initialized else None,
        'applied_camera_device_ids': physical_ids,
        'applied_revision': config.revision if all_online else None,
        'application_status': status,
        'application_error': error or (None if all_online else 'Saved cameras have not all produced usable frames'),
        'restart_required': False,
        'retention_days': get_settings().max_captures_retention_days,
        'retention_policy': 'orphan_captures_only',
    }


async def update_config(db, changes, expected_revision, admin_id) -> SystemConfig:
    config = await get_config(db)
    values = dict(camera_ids=config.camera_ids, camera_device_ids=config.camera_device_ids,
        confidence_threshold=config.confidence_threshold, data_retention_enabled=config.data_retention_enabled)
    unknown = set(changes) - set(values)
    if unknown:
        raise HTTPException(422, 'Unknown configuration fields')
    values.update(changes)
    try:
        values = _validated_values(values['camera_ids'], values['camera_device_ids'],
            values['confidence_threshold'], values['data_retention_enabled'])
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    previous_ids = [part.strip() for part in config.camera_ids.split(',')]
    changed = await db.execute(update(SystemConfig).where(
        SystemConfig.id == config.id, SystemConfig.canonical_key == 1,
        SystemConfig.revision == expected_revision).values(**values,
            revision=SystemConfig.revision + 1, updated_by_admin=admin_id, updated_at=now_manila())
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        current = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
            .execution_options(populate_existing=True))
        raise HTTPException(409, {'message': 'Configuration changed; reload before saving', 'current': config_response(current)})
    if 'camera_ids' in changes:
        devices = (await db.execute(select(Device))).scalars().all()
        by_name = {device.camera_id: device for device in devices}
        slots = [by_name.get(name) for name in previous_ids]
        for device in devices:
            device.camera_id = f'pending-{device.id}'
        await db.flush()
        kept = set()
        for index, name in enumerate(values['camera_ids'].split(', ')):
            device = slots[index] if index < len(slots) else None
            if device is None:
                db.add(Device(camera_id=name, label=f'Scanner {index + 1}', status='Offline', resolution=None))
            else:
                device.camera_id = name
                kept.add(device.id)
        for device in devices:
            if device.id not in kept:
                await db.delete(device)
    if 'camera_ids' in changes or 'camera_device_ids' in changes:
        await db.execute(update(Device).values(status='Offline', resolution=None))
    await db.flush()
    return await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
        .execution_options(populate_existing=True))


async def apply_camera_config(config) -> None:
    """Call only after saved configuration and its audit have committed."""
    from app.services.runtime_operations import run_blocking
    await run_blocking(camera_manager.configure, [part.strip() for part in config.camera_ids.split(',')],
        list(config.camera_device_ids))


async def sync_devices(db):
    """Publish only frame-verified current mappings after physical application."""
    mapping = dict(zip(camera_manager._logical_ids, camera_manager._device_ids))
    online = set(camera_manager.online_cameras)
    for device in (await db.execute(select(Device))).scalars():
        ok = mapping.get(device.camera_id) in online
        device.status = 'Online' if ok else 'Offline'
        device.resolution = f'{get_settings().camera_resolution_w}x{get_settings().camera_resolution_h}' if ok else None
        if ok:
            device.last_seen = now_manila()
    await db.commit()
