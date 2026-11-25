import argparse
import asyncio
import base64
import io
import json
import logging
import random
from datetime import timedelta

import qrcode
from sqlalchemy import inspect, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import Base, engine
from app.core.migrations import upgrade_connection
from app.core.security import hash_password
from app.core.temporary_credentials import temporary_password
from app.core.time import now_manila
from app.models.admin_profile import AdminProfile
from app.models.device import Device
from app.models.intake import Intake
from app.models.operator_profile import OperatorProfile
from app.models.scan_classification import ScanClassification
from app.models.scan_history import ScanEvent
from app.models.scan_status_log import ScanStatusLog
from app.models.sensor_reading import SensorReading
from app.models.supplier import Supplier
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.schemas.enums import (
    ActiveStatusEnum,
    CultivarEnum,
    DeviceStatusEnum,
    IntakeStatusEnum,
    InventoryStatusEnum,
    RipenessEnum,
    RoleEnum,
    TreatmentEnum,
)
from app.services.feature_engineering import calc_vpd
from app.services.scan_creation import create_scan_record
from app.services.spoilage import SpoilagePredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seeder")
# Plain invocation refuses existing data; ordinary Python invocation errors use 2.
DATABASE_NOT_EMPTY_EXIT = 20


class DatabaseNotEmptyError(RuntimeError):
    """Expected refusal: demo data must never replace existing records."""


def prepare_empty_database(connection):
    """Refuse all existing data before applying even schema changes. Never reset tables."""
    for name in inspect(connection).get_table_names():
        if name == "alembic_version":
            continue
        if connection.execute(select(1).select_from(table(name)).limit(1)).first():
            raise DatabaseNotEmptyError(
                "Demo seeding requires an empty database; existing data was not changed"
            )
    Base.metadata.create_all(connection)
    upgrade_connection(connection)


def reset_demo_database(connection):
    """Explicit demo reset; DDL and new records share the caller's transaction."""
    Base.metadata.drop_all(connection)
    # Reapply maintained migrations to recreated tables, including their constraints.
    connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(connection)
    upgrade_connection(connection)


async def seed_data(db):
    logger.info("Seeding data...")
    now = now_manila()
    current_intake_time = now - timedelta(hours=2)
    previous_intake_time = current_intake_time - timedelta(days=1)
    # Same configured RFR and encoders as Kiosk, evaluated on simulated inputs.
    predictor = SpoilagePredictor()
    predictor.load()

    # 1. Roles
    admin_role = UserRole(name=RoleEnum.ADMIN.value, description="Full system access")
    operator_role = UserRole(
        name=RoleEnum.OPERATOR.value, description="Standard scan pipeline access"
    )
    db.add_all([admin_role, operator_role])
    await db.flush()

    # 2. Admin User
    admin_user = UserAccount(
        username=get_settings().bootstrap_admin_username,
        full_name="Admin User",
        password_hash=hash_password(get_settings().bootstrap_admin_password.get_secret_value()),
        requires_password_change=True,
        password_setup_reason="new_account",
        role_id=admin_role.id,
        status=ActiveStatusEnum.ACTIVE,
    )
    db.add(admin_user)
    await db.flush()

    # Admin profile — the FK column is `account_id`, not `user_id`
    admin_prof = AdminProfile(account_id=admin_user.id)
    db.add(admin_prof)
    await db.flush()

    # 3. Operator User — pin_hash lives on OperatorProfile, NOT UserAccount
    operator_user = UserAccount(
        username="operator",
        full_name="Demo Kiosk Operator",
        password_hash=hash_password(temporary_password()),
        requires_password_change=True,
        password_setup_reason="new_account",
        role_id=operator_role.id,
        status=ActiveStatusEnum.INACTIVE,
    )
    db.add(operator_user)
    await db.flush()

    # Operator profile — pin_hash goes here; no `assigned_station` field in the model
    operator_prof = OperatorProfile(
        account_id=operator_user.id,
        pin_hash=None,
    )
    db.add(operator_prof)
    await db.flush()

    # 4. Devices (Cameras) — one row per saved camera slot.
    camera_labels = ("Top Camera", "Left Camera", "Right Camera", "Rear Camera")
    for index, device_index in enumerate(get_settings().camera_device_ids):
        online = index != 1
        db.add(Device(
            camera_id=f"CAM-{index + 1:03}",
            slot_index=index,
            device_index=device_index,
            label=camera_labels[index],
            status=DeviceStatusEnum.ONLINE if online else DeviceStatusEnum.OFFLINE,
            resolution="1920x1080",
            last_seen=now if online else now - timedelta(days=1),
        ))

    # 5. Sensor Readings
    for i in range(10):
        sr = SensorReading(
            temperature=random.uniform(22.0, 25.0),
            humidity=random.uniform(55.0, 65.0),
            recorded_at=now - timedelta(minutes=i * 10),
        )
        db.add(sr)

    # 6. Suppliers
    s1 = Supplier(
        name="Demo Dole Foods",
        contact_person="John Doe",
        contact_phone="555-0100",
        status=ActiveStatusEnum.ACTIVE,
    )
    s2 = Supplier(
        name="Demo Del Monte",
        contact_person="Jane Smith",
        contact_phone="555-0200",
        status=ActiveStatusEnum.ACTIVE,
    )
    s3 = Supplier(
        name="Demo Local Farm Coop",
        contact_person="Bob Builder",
        contact_phone="555-0300",
        status=ActiveStatusEnum.INACTIVE,
    )
    db.add_all([s1, s2, s3])
    await db.flush()

    # 7. Intakes (with QR codes — same format as create_intake API)
    i1 = Intake(
        supplier_id=s1.id,
        batch_number="BCH-1A2B3C",
        source="Kiosk",
        intake_date=current_intake_time.date(),
        status=IntakeStatusEnum.ACTIVE,
        created_at=current_intake_time,
        updated_at=current_intake_time,
        treatment=TreatmentEnum.NATURAL,
    )
    db.add(i1)
    await db.flush()

    i2 = Intake(
        supplier_id=s2.id,
        batch_number="BCH-9X8Y7Z",
        source="Kiosk",
        intake_date=previous_intake_time.date(),
        status=IntakeStatusEnum.DEPLETED,
        created_at=previous_intake_time,
        updated_at=now - timedelta(days=1),
        treatment=TreatmentEnum.ETHEPHON,
        treated_at=previous_intake_time,
    )
    db.add(i2)
    await db.flush()

    # 7b. Near-expiry stock for Spoilage Alerts pagination: an open ethephon intake
    # from yesterday puts five cultivar/ripeness groups inside the two-day window.
    i3 = Intake(
        supplier_id=s1.id,
        batch_number="BCH-SPOIL1",
        source="Kiosk",
        intake_date=previous_intake_time.date(),
        status=IntakeStatusEnum.ACTIVE,
        created_at=previous_intake_time,
        updated_at=now - timedelta(days=1),
        treatment=TreatmentEnum.ETHEPHON,
        treated_at=previous_intake_time,
    )
    db.add(i3)
    await db.flush()

    # Generate QR codes for the intakes
    for intake in (i1, i2, i3):
        qr_data = {
            "intake_id": str(intake.id),
            "supplier_id": str(intake.supplier_id),
            "batch_number": intake.batch_number,
            "date": intake.intake_date.isoformat(),
        }
        img = qrcode.make(json.dumps(qr_data))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        intake.qr_code = f"data:image/png;base64,{b64}"
    await db.flush()
    logger.info("  QR codes generated for intakes")

    # 8. Scans & Classifications
    cultivars = [e.value for e in CultivarEnum]
    ripeness_levels = [e.value for e in RipenessEnum]

    for i in range(25):
        is_i1 = i < 15
        scan_time = (
            now - timedelta(minutes=random.randint(1, 60))
            if is_i1
            else now - timedelta(days=1, minutes=random.randint(1, 60))
        )

        cultivar = random.choice(cultivars)
        ripeness = random.choice(ripeness_levels)

        # Round the inputs to their stored precision BEFORE deriving VPD.
        temperature = round(random.uniform(22.0, 24.0), 2)
        humidity = round(random.uniform(50.0, 60.0), 2)
        vpd = calc_vpd(temperature, humidity)
        treatment = i1.treatment if is_i1 else i2.treatment
        spoilage_days = predictor.predict(
            cultivar,
            ripeness,
            temperature,
            humidity,
            vpd=vpd,
            treatment=treatment.value,
        )
        classification = ScanClassification(
            cultivar=cultivar,
            ripeness=ripeness,
            confidence=round(random.uniform(85.0, 99.9), 2),
            temperature=temperature,
            humidity=humidity,
            vpd=vpd,
            treatment=treatment,
            # spoilage_days is String(20) in the model, not Integer
            spoilage_days=spoilage_days,
            finger_count=random.randint(5, 12),
        )
        scan = await create_scan_record(
            db, operator_id=operator_prof.id, operator_name=operator_user.full_name,
            intake=i1 if is_i1 else i2, source_text=s1.name if is_i1 else s2.name,
            date_time=scan_time, classification=classification,
            actor_id=None, actor_name="Demo Seeder",
            reason=(
                "Synthetic demo scan: simulated classification, confidence, finger count and "
                "sensor readings; no YOLO image inference. Spoilage uses the shared Kiosk predictor."
            ),
        )
        if not is_i1:
            sold_time = scan_time + timedelta(minutes=1)
            sold = ScanStatusLog(
                scan_id=scan.id,
                inventory_status=InventoryStatusEnum.SOLD,
                updated_at=sold_time,
            )
            db.add(sold)
            scan.revision = 2
            scan.updated_at = sold_time
            await db.flush()
            db.add(
                ScanEvent(
                    scan_id=scan.id,
                    revision=2,
                    kind="status",
                    timestamp=sold_time,
                    actor_name="Demo Seeder",
                    actor_id=None,
                    reason="Synthetic sale for the depleted demo intake.",
                    previous_values={"inventory_status": "In Stock"},
                    new_values={"inventory_status": "Sold"},
                    evidence_id=f"status:{sold.id}",
                )
            )

    # 9. Deterministic spoilage alerts (five groups, so Inventory paginates 3 + 2).
    spoilage_groups = (
        (CultivarEnum.LAKATAN, RipenessEnum.OVERRIPE),
        (CultivarEnum.LATUNDAN, RipenessEnum.OVERRIPE),
        (CultivarEnum.CARDABA, RipenessEnum.OVERRIPE),
        (CultivarEnum.LAKATAN, RipenessEnum.RIPE),
        (CultivarEnum.LATUNDAN, RipenessEnum.RIPE),
    )
    for index, (cultivar, ripeness) in enumerate(spoilage_groups):
        scan_time = previous_intake_time + timedelta(hours=1, minutes=index * 5)
        temperature = round(random.uniform(22.0, 24.0), 2)
        humidity = round(random.uniform(50.0, 60.0), 2)
        vpd = calc_vpd(temperature, humidity)
        classification = ScanClassification(
            cultivar=cultivar.value,
            ripeness=ripeness.value,
            confidence=round(random.uniform(85.0, 99.9), 2),
            temperature=temperature,
            humidity=humidity,
            vpd=vpd,
            treatment=i3.treatment,
            spoilage_days=predictor.predict(
                cultivar.value,
                ripeness.value,
                temperature,
                humidity,
                vpd=vpd,
                treatment=i3.treatment.value,
            ),
            finger_count=random.randint(5, 12),
        )
        await create_scan_record(
            db, operator_id=operator_prof.id, operator_name=operator_user.full_name,
            intake=i3, source_text=s1.name, date_time=scan_time,
            classification=classification,
            actor_id=None, actor_name="Demo Seeder",
            reason=(
                "Synthetic demo scan: simulated classification, confidence, finger count and "
                "sensor readings; no YOLO image inference. Spoilage uses the shared Kiosk predictor."
            ),
        )

    await db.flush()


async def main(*, reset_demo=False):
    settings = get_settings()
    if settings.is_production or settings.bootstrap_admin_password is None:
        raise RuntimeError(
            "Demo seeding requires a non-production environment and BOOTSTRAP_ADMIN_PASSWORD"
        )
    try:
        async with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                # Share startup's schema lock; serialize concurrent seed attempts too.
                await connection.execute(text("SELECT pg_advisory_xact_lock(786124903)"))
            if reset_demo:
                logger.warning("Resetting application database records for demo seeding.")
                await connection.run_sync(reset_demo_database)
            else:
                await connection.run_sync(prepare_empty_database)
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                await seed_data(db)
        logger.info("Database seeding completed successfully.")
    finally:
        await engine.dispose()


def run_cli(argv=None):
    parser = argparse.ArgumentParser(description="Create BananaVision demo data.")
    parser.add_argument(
        "--reset-demo", action="store_true",
        help="Delete and recreate application tables before seeding. Development only.",
    )
    arguments = parser.parse_args(argv)
    try:
        asyncio.run(main(reset_demo=arguments.reset_demo))
    except DatabaseNotEmptyError:
        logger.warning(
            "Demo seeding skipped: the database already contains records; "
            "existing data was not changed. Use the current database normally, "
            "or configure a separate empty development database for demo data."
        )
        return DATABASE_NOT_EMPTY_EXIT
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
