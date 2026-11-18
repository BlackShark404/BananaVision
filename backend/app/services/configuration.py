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
    names = [part.strip() for part in value.camera_ids.split(',')]
    if len(names) != len(value.camera_device_ids):
        raise ValueError('Provide one logical camera ID for every physical camera slot')
    return {
        'camera_ids': ', '.join(names),
        'camera_device_ids': list(value.camera_device_ids),
        'confidence_threshold': value.confidence_threshold,
        'data_retention_enabled': value.data_retention_enabled,
    }


def ordered_camera_slots(slots):
    return sorted(slots, key=lambda slot: slot.slot_index)


def camera_slot_values(slots):
    ordered = ordered_camera_slots(slots)
    return ', '.join(slot.camera_id for slot in ordered), [slot.device_index for slot in ordered]


def _valid_saved_scalars(config):
    try:
        SystemConfigUpdate(
            expected_revision=1,
            confidence_threshold=config.confidence_threshold,
            data_retention_enabled=config.data_retention_enabled,
        )
    except ValidationError:
        return False
    return True


def _validate_camera_slots(slots):
    ordered = ordered_camera_slots(slots)
    if not 1 <= len(ordered) <= 4:
        raise ValueError('Saved camera configuration must contain one to four slots')
    if any(type(slot.slot_index) is not int for slot in ordered):
        raise ValueError('Saved camera slot positions are invalid')
    if [slot.slot_index for slot in ordered] != list(range(len(ordered))):
        raise ValueError('Saved camera slot positions are not contiguous')
    names = [slot.camera_id for slot in ordered]
    if any(not name or len(name) > 50 or ',' in name for name in names):
        raise ValueError('Saved camera IDs are invalid')
    if len(names) != len(set(names)):
        raise ValueError('Saved camera IDs must be unique')
    device_ids = [slot.device_index for slot in ordered]
    if any(type(value) is not int or value < 0 for value in device_ids):
        raise ValueError('Saved physical camera indices are invalid')
    if len(device_ids) != len(set(device_ids)):
        raise ValueError('Saved physical camera indices must be unique')
    return ordered


async def _load_camera_slots(db):
    return list((await db.execute(
        select(Device).where(Device.slot_index.is_not(None)).order_by(Device.slot_index)
    )).scalars())


async def _initialize_camera_slots(db):
    settings = get_settings()
    devices = (await db.execute(select(Device))).scalars().all()
    by_name = {device.camera_id: device for device in devices}
    for index, device_index in enumerate(settings.camera_device_ids):
        name = f'CAM-{index + 1:03d}'
        device = by_name.get(name)
        if device is None:
            device = Device(
                camera_id=name,
                label=settings.camera_labels[index]
                if index < len(settings.camera_labels) else f'Scanner {index + 1}',
                status='Offline',
                resolution=None,
            )
            db.add(device)
        device.slot_index = index
        device.device_index = device_index
    await db.flush()


async def _ensure_camera_slots(db, config):
    slots = await _load_camera_slots(db)
    if not slots:
        if config.legacy_conflict:
            raise HTTPException(
                503, 'Saved configuration is invalid; administrator repair is required',
            )
        await _initialize_camera_slots(db)
        slots = await _load_camera_slots(db)
    try:
        slots = _validate_camera_slots(slots)
    except ValueError as exc:
        raise HTTPException(
            503, 'Saved configuration is invalid; administrator repair is required',
        ) from exc
    config.camera_slots = slots
    return slots


async def get_config(db) -> SystemConfig:
    """Select one valid configuration while preserving legacy rows as history.

    Camera slots live in the device table. The canonical nullable marker still
    arbitrates concurrent first access to the singleton configuration row.
    """
    canonical = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1))
    if canonical is not None:
        if not _valid_saved_scalars(canonical):
            raise HTTPException(
                503, 'Saved configuration is invalid; administrator repair is required',
            )
        # Migrate the old bootstrap default (85) to the current default (80).
        # Only auto-migrate when no admin has explicitly saved the threshold.
        if canonical.confidence_threshold == 85 and canonical.updated_by_admin is None:
            canonical.confidence_threshold = 80
            await db.flush()
        return await _with_camera_slots(db, canonical)
    rows = (await db.execute(select(SystemConfig).order_by(
        SystemConfig.updated_at.desc(), SystemConfig.id.desc()))).scalars().all()
    valid = [row for row in rows if _valid_saved_scalars(row)]
    if rows and not valid:
        raise HTTPException(
            503, 'No valid saved configuration; administrator repair is required. '
                 'Legacy rows were preserved.',
        )
    if valid:
        canonical = valid[0]
        canonical.legacy_conflict = canonical.legacy_conflict or (
            len(valid) != len(rows) or any(
                (row.confidence_threshold, row.data_retention_enabled)
                != (canonical.confidence_threshold, canonical.data_retention_enabled)
                for row in valid[1:]
            )
        )
        canonical.canonical_key = 1
        # Migrate the old bootstrap default (85) to the current default (80).
        if canonical.confidence_threshold == 85 and canonical.updated_by_admin is None:
            canonical.confidence_threshold = 80
    else:
        canonical = SystemConfig(canonical_key=1, revision=1,
            confidence_threshold=80, data_retention_enabled=True, legacy_conflict=False)
        db.add(canonical)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        canonical = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1))
        if canonical is None:
            raise
    return await _with_camera_slots(db, canonical)


async def _with_camera_slots(db, config):
    await _ensure_camera_slots(db, config)
    return config


def config_response(config) -> dict:
    camera_ids, device_ids = camera_slot_values(config.camera_slots)
    applied_ids = list(camera_manager._logical_ids)
    physical_ids = list(camera_manager._device_ids) if camera_manager.is_initialized else []
    matches = applied_ids == camera_ids.split(', ') and physical_ids == device_ids
    online = set(camera_manager.online_cameras)
    all_online = matches and all(value in online for value in device_ids)
    error = camera_manager.application_error
    status = 'applied' if all_online else ('partial' if matches and online else 'failed' if matches else 'pending')
    return {
        'camera_ids': camera_ids, 'camera_device_ids': device_ids,
        'confidence_threshold': config.confidence_threshold,
        'detection_confidence_threshold': min(
            config.confidence_threshold, get_settings().yolo_confidence_threshold * 100,
        ),
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


async def _replace_camera_slots(db, current_slots, camera_ids, device_ids):
    """Rewrite slot rows in place, preserving each existing slot's device UUID.

    Unassigned rows are retained unless a reused slot needs the same camera name.
    """
    names = [part.strip() for part in camera_ids.split(',')]
    devices = (await db.execute(select(Device))).scalars().all()
    slot_rows = {device.slot_index: device for device in
                 ordered_camera_slots(current_slots) if device.slot_index is not None}
    unassigned = {device.camera_id: device for device in devices if device.slot_index is None}

    # Release every unique name/index before assigning the new arrangement.
    for device in slot_rows.values():
        device.camera_id = f'pending-{device.id}'
        device.slot_index = None
        device.device_index = None
    # An unassigned duplicate cannot keep a name that a reused slot now owns.
    for index, name in enumerate(names):
        device = unassigned.get(name)
        if device is not None and index in slot_rows:
            await db.delete(device)
    await db.flush()

    for index, (name, device_index) in enumerate(zip(names, device_ids, strict=True)):
        device = slot_rows.get(index)
        if device is None:
            device = unassigned.get(name)
        if device is None:
            device = Device(
                camera_id=name, label=f'Scanner {index + 1}',
                status='Offline', resolution=None,
            )
            db.add(device)
        device.camera_id = name
        device.slot_index = index
        device.device_index = device_index

    for index, device in slot_rows.items():
        if index >= len(names):
            await db.delete(device)

    await db.execute(update(Device).where(Device.slot_index.is_not(None)).values(
        status='Offline', resolution=None,
    ))


async def update_config(db, changes, expected_revision, admin_id) -> SystemConfig:
    config = await get_config(db)
    camera_ids, device_ids = camera_slot_values(config.camera_slots)
    values = dict(camera_ids=camera_ids, camera_device_ids=device_ids,
        confidence_threshold=config.confidence_threshold,
        data_retention_enabled=config.data_retention_enabled)
    unknown = set(changes) - set(values)
    if unknown:
        raise HTTPException(422, 'Unknown configuration fields')
    camera_changed = 'camera_ids' in changes or 'camera_device_ids' in changes
    values.update(changes)
    try:
        values = _validated_values(values['camera_ids'], values['camera_device_ids'],
            values['confidence_threshold'], values['data_retention_enabled'])
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    changed = await db.execute(update(SystemConfig).where(
        SystemConfig.id == config.id, SystemConfig.canonical_key == 1,
        SystemConfig.revision == expected_revision).values(
            confidence_threshold=values['confidence_threshold'],
            data_retention_enabled=values['data_retention_enabled'],
            revision=SystemConfig.revision + 1,
            updated_by_admin=admin_id,
            updated_at=now_manila(),
        ).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        current = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
            .execution_options(populate_existing=True))
        if current is not None:
            await _ensure_camera_slots(db, current)
        raise HTTPException(409, {'message': 'Configuration changed; reload before saving',
                                  'current': config_response(current)})
    if camera_changed:
        await _replace_camera_slots(
            db, config.camera_slots, values['camera_ids'], values['camera_device_ids'],
        )
    await db.flush()
    saved = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
        .execution_options(populate_existing=True))
    return await _with_camera_slots(db, saved)


async def apply_camera_config(config) -> None:
    """Call only after saved configuration and its audit have committed."""
    from app.services.runtime_operations import run_blocking
    names, device_ids = camera_slot_values(config.camera_slots)
    await run_blocking(camera_manager.configure, names.split(', '), device_ids)


async def sync_devices(db):
    """Publish only frame-verified current mappings after physical application."""
    mapping = dict(zip(camera_manager._logical_ids, camera_manager._device_ids))
    online = set(camera_manager.online_cameras)
    for device in (await db.execute(select(Device))).scalars():
        ok = mapping.get(device.camera_id) in online
        device.status = 'Online' if ok else 'Offline'
        measured = camera_manager.get_resolution(mapping[device.camera_id]) if ok else None
        device.resolution = f'{measured[0]}x{measured[1]}' if measured else None
        if ok:
            device.last_seen = now_manila()
    await db.commit()
