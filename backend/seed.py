import asyncio
import logging
import uuid
import random
import io
import base64
import json
import sqlalchemy
import qrcode
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.schema import MetaData

from app.core.database import async_session_factory, engine, Base
from app.core.security import hash_password, hash_pin
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from app.models.device import Device
from app.models.sensor_reading import SensorReading
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.schemas.enums import RoleEnum, ActiveStatusEnum, DeviceStatusEnum, IntakeStatusEnum, InventoryStatusEnum, CultivarEnum, RipenessEnum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seeder")

async def clear_database():
    """Drop and recreate all tables."""
    logger.info("Dropping all tables...")
    
    # We must issue separate transactions if one fails and aborts the block
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table.name} CASCADE"))
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created.")

async def seed_data():
    async with async_session_factory() as db:
        logger.info("Seeding data...")
        now = datetime.now(timezone.utc)

        # 1. Roles
        admin_role = UserRole(name=RoleEnum.ADMIN.value, description="Full system access")
        operator_role = UserRole(name=RoleEnum.OPERATOR.value, description="Standard scan pipeline access")
        db.add_all([admin_role, operator_role])
        await db.flush()

        # 2. Admin User
        admin_user = UserAccount(
            username="admin",
            full_name="Admin User",
            password_hash=hash_password("admin"),
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
            full_name="Kiosk Operator",
            password_hash=hash_password("operator"),
            role_id=operator_role.id,
            status=ActiveStatusEnum.ACTIVE,
        )
        db.add(operator_user)
        await db.flush()

        # Operator profile — pin_hash goes here; no `assigned_station` field in the model
        operator_prof = OperatorProfile(
            account_id=operator_user.id,
            pin_hash=hash_pin("1234"),
        )
        db.add(operator_prof)
        await db.flush()
        
        # 4. Devices (Cameras)
<<<<<<< HEAD
        cam1 = Device(camera_id="CAM-001", label="Top Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
        cam2 = Device(camera_id="CAM-002", label="Left Camera", status=DeviceStatusEnum.OFFLINE, resolution="1920x1080", last_seen=now - timedelta(days=1))
        cam3 = Device(camera_id="CAM-003", label="Right Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
        cam4 = Device(camera_id="CAM-004", label="Rear Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
=======
        cam1 = Device(camera_id="CAM-001", label="Front Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
        cam2 = Device(camera_id="CAM-002", label="Left Camera", status=DeviceStatusEnum.OFFLINE, resolution="1920x1080", last_seen=now - timedelta(days=1))
        cam3 = Device(camera_id="CAM-003", label="Right Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
        cam4 = Device(camera_id="CAM-004", label="Top Camera", status=DeviceStatusEnum.ONLINE, resolution="1920x1080", last_seen=now)
>>>>>>> 5662a0308495e115cd29e745eaee6001b16ba045
        db.add_all([cam1, cam2, cam3, cam4])
        
        # 5. Sensor Readings
        for i in range(10):
            sr = SensorReading(
                temperature=random.uniform(22.0, 25.0),
                humidity=random.uniform(55.0, 65.0),
                recorded_at=now - timedelta(minutes=i*10)
            )
            db.add(sr)
        
        # 6. Suppliers
        s1 = Supplier(name="Dole Foods", contact_person="John Doe", contact_phone="555-0100", status=ActiveStatusEnum.ACTIVE)
        s2 = Supplier(name="Del Monte", contact_person="Jane Smith", contact_phone="555-0200", status=ActiveStatusEnum.ACTIVE)
        s3 = Supplier(name="Local Farm Coop", contact_person="Bob Builder", contact_phone="555-0300", status=ActiveStatusEnum.INACTIVE)
        db.add_all([s1, s2, s3])
        await db.flush()

        # 7. Intakes (with QR codes — same format as create_intake API)
        i1 = Intake(
            supplier_id=s1.id,
            batch_number="BCH-1A2B3C",
            source="Kiosk",
            intake_date=now.date(),
            status=IntakeStatusEnum.ACTIVE,
            created_at=now,
            updated_at=now
        )
        db.add(i1)
        await db.flush()

        i2 = Intake(
            supplier_id=s2.id,
            batch_number="BCH-9X8Y7Z",
            source="Kiosk",
            intake_date=(now - timedelta(days=1)).date(),
            status=IntakeStatusEnum.DEPLETED,
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1)
        )
        db.add(i2)
        await db.flush()

        # Generate QR codes for both intakes
        for intake, supplier in [(i1, s1), (i2, s2)]:
            qr_data = {
                "intake_id": str(intake.id),
                "supplier_id": str(intake.supplier_id),
                "batch_number": intake.batch_number,
                "date": intake.intake_date.isoformat()
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
            scan_time = now - timedelta(minutes=random.randint(1, 60)) if is_i1 else now - timedelta(days=1, minutes=random.randint(1, 60))
            
            scan = Scan(
                operator_id=operator_prof.id,
                intake_id=i1.id if is_i1 else i2.id,
                date_time=scan_time,
                source_text=s1.name if is_i1 else s2.name
            )
            db.add(scan)
            await db.flush()

            cultivar = random.choice(cultivars)
            ripeness = random.choice(ripeness_levels)
            
            classification = ScanClassification(
                scan_id=scan.id,
                cultivar=cultivar,
                ripeness=ripeness,
                confidence=random.uniform(85.0, 99.9),
                temperature=random.uniform(22.0, 24.0),
                humidity=random.uniform(50.0, 60.0),
                # spoilage_days is String(20) in the model, not Integer
                spoilage_days=str(random.randint(1, 10)),
                finger_count=random.randint(5, 12),
            )
            db.add(classification)
            
            status_log = ScanStatusLog(
                scan_id=scan.id,
                inventory_status=InventoryStatusEnum.IN_STOCK if is_i1 else InventoryStatusEnum.SOLD,
                updated_at=scan_time
            )
            db.add(status_log)

        await db.commit()
        logger.info("Database seeding completed successfully.")

async def main():
    await clear_database()
    await seed_data()

if __name__ == "__main__":
    asyncio.run(main())