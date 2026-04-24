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
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import async_session_factory, engine, Base
from app.core.security import hash_password, hash_pin
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from app.models.device import Device
from app.services.camera_manager import camera_manager
from app.services.classification import banana_classifier
from app.services.spoilage import spoilage_predictor
from app.services.sensor_reader import sensor_reader
from app.ws.manager import ws_manager
from app.ws import events

logger = logging.getLogger(__name__)
settings = get_settings()


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

    # Ensure captures directory exists
    settings.capture_path.mkdir(parents=True, exist_ok=True)

    # ── Phase 2: Database ────────────────────────────────────────────────
    logger.info("[Phase 2] Connecting to database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("  Database tables created/verified")

    # Seed default admin user if no users exist
    async with async_session_factory() as db:
        await _seed_default_data(db)

    # ── Phase 3: ML Models ───────────────────────────────────────────────
    logger.info("[Phase 3] Loading ML models...")
    banana_classifier.load()
    banana_classifier.warmup()
    spoilage_predictor.load()
    logger.info("  ML models ready")

    # ── Phase 4: Camera Initialization ───────────────────────────────────
    logger.info("[Phase 4] Initializing cameras...")
    camera_results = camera_manager.initialize()

    # Register camera status in DB
    async with async_session_factory() as db:
        await _register_cameras(db, camera_results)

    online = camera_manager.online_cameras
    logger.info(f"  Cameras online: {len(online)}/{len(settings.camera_device_ids)}")

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

    # Release cameras
    camera_manager.release_all()

    # Close sensor
    sensor_reader.disconnect()

    # Close DB connection pool
    await engine.dispose()

    logger.info("Shutdown complete.")


async def start_background_tasks():
    """
    Start long-running background tasks (called after startup).
    Returns list of tasks for cancellation on shutdown.
    """
    tasks: list[asyncio.Task] = []

    # Sensor polling task
    async def on_sensor_reading(data):
        """Callback for each sensor reading — persist and broadcast."""
        from app.models.sensor_reading import SensorReading

        # Persist to DB
        async with async_session_factory() as db:
            db.add(SensorReading(
                temperature=data.temperature,
                humidity=data.humidity,
                recorded_at=data.recorded_at,
            ))
            await db.commit()

        # Broadcast via WebSocket
        await ws_manager.send_to_room(events.ROOM_KIOSK, events.SENSOR_UPDATE, {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "recorded_at": data.recorded_at.isoformat(),
        })
        await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.SENSOR_UPDATE, {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "recorded_at": data.recorded_at.isoformat(),
        })

    sensor_task = asyncio.create_task(sensor_reader.start_polling(on_sensor_reading))
    tasks.append(sensor_task)

    return tasks


# ── Seed Helpers ─────────────────────────────────────────────────────────────

async def _seed_default_data(db: AsyncSession):
    """Seed default admin user if the users table is empty."""
    result = await db.execute(select(UserAccount).limit(1))
    if result.scalar_one_or_none() is not None:
        logger.info("  Users already exist — skipping seed")
        return

    logger.info("  Seeding default roles & admin user...")
    admin_role = UserRole(name="Admin", description="Full system access")
    operator_role = UserRole(name="Operator", description="Standard scan pipeline access")
    db.add_all([admin_role, operator_role])
    await db.commit()
    await db.refresh(admin_role)

    admin_account = UserAccount(
        username="admin",
        full_name="Admin User",
        password_hash=hash_password("admin"),
        role_id=admin_role.id,
        status="Active",
    )
    admin_account.admin_profile = AdminProfile()
    db.add(admin_account)
    await db.commit()
    logger.info("  Default admin created (admin / admin)")


async def _register_cameras(db: AsyncSession, results: dict[int, bool]):
    """Register or update camera devices in the DB based on init results."""
    for idx, (dev_id, success) in enumerate(results.items()):
        camera_id = f"CAM-{idx + 1:03d}"
        label = (
            settings.camera_labels[idx]
            if idx < len(settings.camera_labels)
            else f"Camera {idx + 1}"
        )
        resolution = (
            f"{settings.camera_resolution_w}x{settings.camera_resolution_h}"
            if success
            else None
        )

        # Upsert device record
        existing = await db.execute(select(Device).where(Device.camera_id == camera_id))
        device = existing.scalar_one_or_none()

        if device:
            device.status = "Online" if success else "Offline"
            device.resolution = resolution
            device.last_seen = datetime.now(timezone.utc) if success else device.last_seen
        else:
            db.add(Device(
                camera_id=camera_id,
                label=label,
                status="Online" if success else "Offline",
                resolution=resolution,
                last_seen=datetime.now(timezone.utc) if success else None,
            ))

    await db.commit()
