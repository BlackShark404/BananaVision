"""
System startup / boot sequence.

Handles all initialization that must happen before the app accepts requests:
  Phase 1: Configuration validation
  Phase 2: Database connection + seed
  Phase 3: ML model loading + warmup
  Phase 4: Camera initialization
  Phase 5: Sensor initialization
  Phase 6: Ready broadcast
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import async_session_factory, engine
from app.core.migrations import initialize_schema
from app.core.security import hash_password, hash_pin
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from app.models.device import Device
from app.models.system_config import SystemConfig
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
import uuid
import random
from datetime import timedelta
from app.services.camera_manager import camera_manager
from app.services.runtime_operations import station_lock, coordinator, run_blocking
from app.services import configuration, maintenance_state, maintenance_database
from app.services.backup_restore import get_service
from app.services.power_control import reconcile_power
from app.services.classification import banana_classifier
from app.services.banana_detector import banana_pre_detector
from app.services.spoilage import spoilage_predictor
from app.services.sensor_reader import freshness_window_seconds, sensor_reader
from app.ws.manager import ws_manager
from app.ws import events
from app.schemas.enums import RoleEnum, ActiveStatusEnum, DeviceStatusEnum, PasswordSetupReasonEnum

logger = logging.getLogger(__name__)
settings = get_settings()
_runtime_ready = False
_background_tasks: list[asyncio.Task] = []


async def run_startup():
    """
    Execute the full system boot sequence.
    Called from FastAPI lifespan handler.
    """
    logger.info("=" * 60)
    logger.info("  BananaVision Backend — Starting Up")
    logger.info("=" * 60)

    # ── Phase 1: Configuration ───────────────────────────────────────────
    logger.info("[Phase 1] Configuration validated")
    logger.info(f"  Environment: {settings.app_env}")
    logger.info(f"  Debug: {settings.app_debug}")
    logger.info(f"  Cameras: {settings.camera_device_ids}")

    global _runtime_ready
    _runtime_ready = False
    coordinator.runtime_resume = None
    await maintenance_database.acquire_station_owner(engine)
    coordinator.database_barrier = lambda: maintenance_database.database_barrier(engine)

    # ── Phase 2: Database ────────────────────────────────────────────────
    logger.info("[Phase 2] Connecting to database...")
    await initialize_schema(engine)
    logger.info("  Database tables initialized and versioned migrations applied")

    service = get_service()
    await run_blocking(service.prepare)
    try:
        await service.recover()
    except Exception:
        coordinator.block('recovery-required')
        logger.exception('Recovery required; hardware and public data access remain blocked')
        return
    finally:
        coordinator.runtime_resume = resume_runtime
    await reconcile_power()
    if coordinator.state != 'ready':
        return
    await _initialize_runtime()
    _runtime_ready = True


async def resume_runtime():
    global _runtime_ready
    if not _runtime_ready:
        await _initialize_runtime()
        await start_background_tasks(allow_blocked=True)
        _runtime_ready = True


async def _initialize_runtime():
    service = get_service()
    settings.capture_path.mkdir(parents=True, exist_ok=True)
    async with async_session_factory() as db:
        await _seed_default_data(db)
        config = await configuration.get_config(db)
        state = await maintenance_state.get_state(db)
        maintenance_state.publish_generation(state.auth_generation)
        await db.commit()

    # ── Phase 3: ML Models ───────────────────────────────────────────────
    logger.info("[Phase 3] Loading ML models...")
    logger.info(f"  Pre-detector: {banana_pre_detector._COCO_MODEL}")
    logger.info(f"  Classifier:   {settings.yolo_model_path}")
    logger.info(f"  Spoilage:     {settings.rfr_model_path}")
    banana_pre_detector.load()
    banana_pre_detector.warmup()
    banana_classifier.load()
    banana_classifier.warmup()
    spoilage_predictor.load()
    if not banana_pre_detector.is_loaded and not settings.ood_gate_fail_open:
        logger.error(
            "  Banana verifier is not loaded: scans will be refused until the backend "
            "restarts with a loadable verifier (the out-of-distribution gate fails closed)"
        )
    logger.info("  All ML models ready")

    # ── Phase 4: Camera Initialization ───────────────────────────────────
    logger.info("[Phase 4] Initializing cameras...")
    await configuration.apply_camera_config(config)
    camera_results = dict(camera_manager._health)

    # Register camera status in DB
    async with async_session_factory() as db:
        await _register_cameras(db, camera_results)

    async def refresh_hardware():
        async with async_session_factory() as db:
            restored = await configuration.get_config(db)
            await db.commit()
            await configuration.apply_camera_config(restored)
            await _register_cameras(db, dict(camera_manager._health))
            return configuration.config_response(restored)
    service.hardware_refresh = refresh_hardware

    online = camera_manager.online_cameras
    logger.info(f"  Cameras online: {len(online)}/{len(camera_manager._device_ids)}")

    # ── Phase 5: Sensor Initialization ───────────────────────────────────
    logger.info("[Phase 5] Initializing DHT22 sensor...")
    sensor_connected = sensor_reader.connect()
    logger.info(f"  Sensor connected: {sensor_connected}")

    # ── Phase 6: Ready ───────────────────────────────────────────────────
    logger.info("[Phase 6] System ready!")
    logger.info("=" * 60)
    logger.info(f"  API: http://{settings.app_host}:{settings.app_port}")
    logger.info(f"  Docs: http://{settings.app_host}:{settings.app_port}/docs")
    logger.info("=" * 60)


async def run_shutdown():
    """
    Clean shutdown sequence.
    Called from FastAPI lifespan handler.
    """
    logger.info("Shutting down BananaVision Backend...")

    coordinator.block('draining')
    await asyncio.wait_for(coordinator._empty.wait(), timeout=coordinator.drain_timeout)
    await run_blocking(camera_manager.release_all)

    # Close sensor
    sensor_reader.disconnect()

    # Close DB connection pool
    await maintenance_database.release_station_owner()
    await engine.dispose()

    _background_tasks.clear()
    logger.info("Shutdown complete.")


async def start_background_tasks(*, allow_blocked=False):
    """
    Start long-running background tasks (called after startup).
    Returns list of tasks for cancellation on shutdown.
    """
    tasks = _background_tasks
    if tasks or (coordinator.state != "ready" and not allow_blocked):
        return tasks

    # Retention worker
    from app.services.data_retention import data_retention_worker
    retention_task = asyncio.create_task(data_retention_worker())
    tasks.append(retention_task)

    # Sensor polling task
    async def on_sensor_reading(data):
        """Callback for each sensor reading — persist and broadcast."""
        from app.models.sensor_reading import SensorReading

        async with coordinator.operation():
            # Persist to DB
            async with async_session_factory() as db:
                db.add(SensorReading(
                    temperature=data.temperature,
                    humidity=data.humidity,
                    recorded_at=data.recorded_at,
                ))
                await db.commit()

            # Broadcast via WebSocket
            freshness = {
                "server_time": now_manila().isoformat(),
                "stale_after_seconds": freshness_window_seconds(),
            }
            await ws_manager.send_to_room(events.ROOM_KIOSK, events.SENSOR_UPDATE, {
                "temperature": data.temperature,
                "humidity": data.humidity,
                "recorded_at": data.recorded_at.isoformat(),
                **freshness,
            })
            await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.SENSOR_UPDATE, {
                "temperature": data.temperature,
                "humidity": data.humidity,
                "recorded_at": data.recorded_at.isoformat(),
                **freshness,
            })

    sensor_task = asyncio.create_task(sensor_reader.start_polling(on_sensor_reading))
    tasks.append(sensor_task)

    # Camera health monitor — polls every 10s, updates DB + broadcasts on change
    async def camera_health_monitor():
        """Periodically check which cameras are truly online (producing real
        images, not black/blank feeds) and sync changes to DB + WS."""
        # The first probe must use the same retry path as later probes: startup
        # retention and deferred recovery may still own station admission.
        last_known: dict[int, bool] = {}
        last_mapping = None

        while True:
            await asyncio.sleep(10)
            try:
                if station_lock.locked():
                    continue
                async with coordinator.operation(), station_lock:
                    # probe_all validates each camera's feed (reads frame + mean/stddev check)
                    # Run in executor to avoid blocking the event loop
                    current_probe = await run_blocking(camera_manager.probe_all)
                    mapping = tuple((dev_id, camera_manager._get_camera_id(dev_id)) for dev_id in current_probe)
                    if mapping != last_mapping:
                        last_known = {}
                        last_mapping = mapping
                    changes: list[tuple[int, bool]] = []

                    for dev_id, is_online in current_probe.items():
                        was_online = last_known.get(dev_id)
                        if is_online != was_online:
                            changes.append((dev_id, is_online))

                    if not changes:
                        continue

                    # Apply DB updates and broadcast WS events
                    async with async_session_factory() as db:
                        for dev_id, is_online in changes:
                            idx = camera_manager._device_ids.index(dev_id)
                            camera_id = camera_manager._get_camera_id(dev_id)
                            label = (
                                settings.camera_labels[idx]
                                if idx < len(settings.camera_labels)
                                else f"Camera {idx + 1}"
                            )
                            new_status = DeviceStatusEnum.ONLINE if is_online else DeviceStatusEnum.OFFLINE
                            now = now_manila()

                            # Update DB
                            result = await db.execute(select(Device).where(Device.camera_id == camera_id))
                            device = result.scalar_one_or_none()
                            if device:
                                device.status = new_status
                                if is_online:
                                    device.last_seen = now
                            else:
                                db.add(Device(
                                    camera_id=camera_id,
                                    slot_index=idx,
                                    device_index=dev_id,
                                    label=label,
                                    status=new_status,
                                    last_seen=now if is_online else None,
                                ))

                            # Do not announce a state that the database rejected.
                            await db.commit()
                            last_known[dev_id] = is_online
                            logger.info(f"Camera {camera_id} status changed: {'Online' if is_online else 'Offline'}")

                            # Broadcast to WS rooms
                            ws_data = {
                                "camera_id": camera_id,
                                "status": new_status.value,
                                "last_seen": now.isoformat() if is_online else None,
                            }
                            await ws_manager.send_to_room(events.ROOM_DEVICES, events.DEVICE_STATUS, ws_data)
                            await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.DEVICE_STATUS, ws_data)

            except Exception as exc:
                logger.warning(f"Camera health monitor error: {exc}")

    camera_task = asyncio.create_task(camera_health_monitor())
    tasks.append(camera_task)

    return tasks


# ── Seed Helpers ─────────────────────────────────────────────────────────────

async def _seed_default_data(db: AsyncSession):
    """Seed default admin user if the users table is empty."""
    result = await db.execute(select(UserAccount).limit(1))
    if result.scalar_one_or_none() is not None:
        logger.info("  Users already exist — skipping seed")
        return

    bootstrap = get_settings()
    if bootstrap.bootstrap_admin_password is None:
        raise RuntimeError(
            "Empty database: set BOOTSTRAP_ADMIN_PASSWORD to a unique temporary password "
            "of at least 12 bytes before starting BananaVision. See backend/README.md."
        )
    logger.info("  Creating roles and bootstrap administrator...")
    admin_role = UserRole(name=RoleEnum.ADMIN.value, description="Full system access")
    operator_role = UserRole(name=RoleEnum.OPERATOR.value, description="Standard scan pipeline access")
    for role in (admin_role, operator_role):
        existing = await db.scalar(select(UserRole).where(UserRole.name == role.name))
        if existing:
            if role.name == RoleEnum.ADMIN.value:
                admin_role = existing
        else:
            db.add(role)
    await db.flush()

    admin_account = UserAccount(
        username=bootstrap.bootstrap_admin_username,
        full_name="Admin User",
        password_hash=hash_password(bootstrap.bootstrap_admin_password.get_secret_value()),
        role_id=admin_role.id,
        status=ActiveStatusEnum.ACTIVE,
        requires_password_change=True,
        password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT,
    )
    admin_account.admin_profile = AdminProfile()
    db.add(admin_account)
    await db.commit()
    logger.info("  Bootstrap administrator created; credential replacement required")


async def _register_cameras(db: AsyncSession, results: dict[int, bool]):
    """Register or update camera devices in the DB based on init results."""
    for idx, (dev_id, success) in enumerate(results.items()):
        camera_id = camera_manager._get_camera_id(dev_id)
        label = (
            settings.camera_labels[idx]
            if idx < len(settings.camera_labels)
            else f"Camera {idx + 1}"
        )
        measured = camera_manager.get_resolution(dev_id) if success else None
        resolution = f"{measured[0]}x{measured[1]}" if measured else None

        # Upsert device record
        existing = await db.execute(select(Device).where(Device.camera_id == camera_id))
        device = existing.scalar_one_or_none()

        slot_index = (camera_manager._device_ids.index(dev_id)
                      if dev_id in camera_manager._device_ids else idx)
        if device:
            device.status = DeviceStatusEnum.ONLINE if success else DeviceStatusEnum.OFFLINE
            device.resolution = resolution
            device.last_seen = now_manila() if success else device.last_seen
            if device.slot_index is None:
                device.slot_index = slot_index
            if device.device_index is None:
                device.device_index = dev_id
        else:
            db.add(Device(
                camera_id=camera_id,
                slot_index=slot_index,
                device_index=dev_id,
                label=label,
                status=DeviceStatusEnum.ONLINE if success else DeviceStatusEnum.OFFLINE,
                resolution=resolution,
                last_seen=now_manila() if success else None,
            ))

    await db.commit()

