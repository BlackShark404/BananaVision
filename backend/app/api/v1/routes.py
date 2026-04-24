"""
Device, sensor, user, supplier, intake, analytics, activity, config, and quality routes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select, func, desc

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException, ConflictException
from app.core.security import hash_password, hash_pin
from app.models.device import Device
from app.models.sensor_reading import SensorReading
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from sqlalchemy.orm import selectinload
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.models.activity_log import ActivityLog
from app.models.system_config import SystemConfig
from app.schemas.common import (
    DeviceResponse,
    SensorReadingResponse,
    SensorHistoryResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    IntakeResponse,
    IntakeStatusUpdate,
    IntakeBulkInventoryUpdate,
    AnalyticsSummary,
    RipenessDistribution,
    CultivarCount,
    ScanTrend,
    ActivityLogResponse,
    ActivityLogListResponse,
    SystemConfigResponse,
    SystemConfigUpdate,
)
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserPasswordReset,
    UserPinReset,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════════════════════════

devices_router = APIRouter(prefix="/devices", tags=["Devices"])


@devices_router.get("", response_model=list[DeviceResponse])
async def list_devices(db: DbSession, user: CurrentUser):
    """List all camera devices and their status."""
    result = await db.execute(select(Device).order_by(Device.camera_id))
    return [DeviceResponse.model_validate(d) for d in result.scalars().all()]


# ═══════════════════════════════════════════════════════════════════════════════
# SENSORS
# ═══════════════════════════════════════════════════════════════════════════════

sensors_router = APIRouter(prefix="/sensors", tags=["Sensors"])


@sensors_router.get("/latest", response_model=SensorReadingResponse | None)
async def latest_sensor(db: DbSession, user: CurrentUser):
    """Get the latest DHT22 sensor reading."""
    result = await db.execute(
        select(SensorReading).order_by(desc(SensorReading.recorded_at)).limit(1)
    )
    reading = result.scalar_one_or_none()
    if not reading:
        # Return mock data from sensor_reader if no DB records
        from app.services.sensor_reader import sensor_reader
        data = sensor_reader.latest
        if data:
            return SensorReadingResponse(
                temperature=data.temperature,
                humidity=data.humidity,
                recorded_at=data.recorded_at,
            )
        return None
    return SensorReadingResponse.model_validate(reading)


@sensors_router.get("/history", response_model=SensorHistoryResponse)
async def sensor_history(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get sensor reading history."""
    result = await db.execute(
        select(SensorReading).order_by(desc(SensorReading.recorded_at)).limit(limit)
    )
    readings = result.scalars().all()
    return SensorHistoryResponse(
        items=[SensorReadingResponse.model_validate(r) for r in readings],
        total=len(readings),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════════

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("", response_model=UserListResponse)
async def list_users(db: DbSession, admin: AdminUser):
    """List all users (admin only)."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .order_by(UserAccount.created_at)
    )
    users = result.scalars().all()
    return UserListResponse(
        items=[UserResponse.from_db_model(u) for u in users],
        total=len(users),
    )


@users_router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, db: DbSession, admin: AdminUser):
    """Create a new user (admin only)."""
    existing = await db.execute(select(UserAccount).where(UserAccount.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Username '{body.username}' already exists")

    role_res = await db.execute(select(UserRole).where(UserRole.name == body.role))
    user_role = role_res.scalar_one_or_none()
    if not user_role:
        raise NotFoundException(f"Role '{body.role}' not found")

    user = UserAccount(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role_id=user_role.id,
        requires_password_change=True,
        password_setup_reason="new_account",
    )
    user.role = user_role  # Explicitly load for from_db_model

    if body.role == "Admin":
        user.admin_profile = AdminProfile()
    elif body.role == "Operator":
        user.operator_profile = OperatorProfile(
            pin_hash=hash_pin(body.pin) if body.pin else None,
            requires_pin_change=True if body.pin else False,
            pin_setup_reason="new_account" if body.pin else None,
        )

    db.add(user)

    db.add(ActivityLog(
        user_id=admin.id,
        action="user_created",
        details=f"Created user '{body.username}' with role {body.role}",
    ))

    await db.flush()
    return UserResponse.from_db_model(user)


@users_router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, admin: AdminUser):
    """Update a user (admin only)."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field in ["requires_pin_change", "pin_setup_reason"]:
            if user.operator_profile:
                setattr(user.operator_profile, field, value)
        elif field == "role":
            role_res = await db.execute(select(UserRole).where(UserRole.name == value))
            user_role = role_res.scalar_one_or_none()
            if user_role:
                user.role_id = user_role.id
                user.role = user_role
        else:
            setattr(user, field, value)

    db.add(ActivityLog(
        user_id=admin.id,
        action="user_updated",
        details=f"Updated user '{user.username}': {list(update_data.keys())}",
    ))

    await db.flush()
    return UserResponse.from_db_model(user)


@users_router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: uuid.UUID, body: UserPasswordReset, db: DbSession, admin: AdminUser
):
    """Reset a user's password (admin only)."""
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    user.password_hash = hash_password(body.new_password)
    user.requires_password_change = True
    user.password_setup_reason = body.password_setup_reason
    return {"message": "Password reset successfully"}


@users_router.post("/{user_id}/reset-pin")
async def reset_user_pin(
    user_id: uuid.UUID, body: UserPinReset, db: DbSession, admin: AdminUser
):
    """Reset a user's PIN (admin only)."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user or not user.operator_profile:
        raise NotFoundException("User Operator Profile")

    user.operator_profile.pin_hash = hash_pin(body.new_pin)
    user.operator_profile.requires_pin_change = True
    user.operator_profile.pin_setup_reason = body.pin_setup_reason
    return {"message": "PIN reset successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPLIERS
# ═══════════════════════════════════════════════════════════════════════════════

suppliers_router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@suppliers_router.get("", response_model=list[SupplierResponse])
async def list_suppliers(db: DbSession, admin: AdminUser):
    """List all suppliers."""
    result = await db.execute(select(Supplier).order_by(Supplier.date_added))
    return [SupplierResponse.model_validate(s) for s in result.scalars().all()]


@suppliers_router.post("", response_model=SupplierResponse, status_code=201)
async def create_supplier(body: SupplierCreate, db: DbSession, admin: AdminUser):
    """Create a new supplier."""
    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    db.add(ActivityLog(
        user_id=admin.id,
        action="supplier_created",
        details=f"Added supplier '{body.name}'",
    ))
    await db.flush()
    return SupplierResponse.model_validate(supplier)


@suppliers_router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession, admin: AdminUser
):
    """Update a supplier."""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise NotFoundException("Supplier")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(supplier, field, value)

    db.add(ActivityLog(
        user_id=admin.id,
        action="supplier_updated",
        details=f"Updated supplier '{supplier.name}'",
    ))

    await db.flush()
    return SupplierResponse.model_validate(supplier)


# ═══════════════════════════════════════════════════════════════════════════════
# INTAKES
# ═══════════════════════════════════════════════════════════════════════════════

intakes_router = APIRouter(prefix="/intakes", tags=["Intakes"])


@intakes_router.get("", response_model=list[IntakeResponse])
async def list_intakes(db: DbSession, admin: AdminUser):
    """List all intakes with scan counts."""
    result = await db.execute(
        select(Intake).order_by(desc(Intake.intake_date))
    )
    intakes = result.scalars().all()

    responses = []
    for intake in intakes:
        scan_count_result = await db.execute(
            select(func.count()).where(Scan.intake_id == intake.id)
        )
        scan_count = scan_count_result.scalar() or 0

        responses.append(IntakeResponse(
            id=intake.id,
            supplier_id=intake.supplier_id,
            supplier_name=intake.supplier.name if intake.supplier else None,
            intake_date=intake.intake_date,
            status=intake.status,
            scan_count=scan_count,
            created_at=intake.created_at,
        ))

    return responses


@intakes_router.patch("/{intake_id}/status")
async def update_intake_status(
    intake_id: uuid.UUID, body: IntakeStatusUpdate, db: DbSession, admin: AdminUser
):
    """Update intake status (Active/Depleted)."""
    result = await db.execute(select(Intake).where(Intake.id == intake_id))
    intake = result.scalar_one_or_none()
    if not intake:
        raise NotFoundException("Intake")

    intake.status = body.status
    db.add(ActivityLog(
        user_id=admin.id,
        action="intake_status_changed",
        details=f"Intake {intake_id} status → {body.status}",
    ))
    return {"message": "Intake status updated"}


@intakes_router.patch("/{intake_id}/bulk-inventory")
async def bulk_update_intake_inventory(
    intake_id: uuid.UUID, body: IntakeBulkInventoryUpdate, db: DbSession, admin: AdminUser
):
    """Bulk update inventory status for all scans in an intake."""
    result = await db.execute(select(Intake).where(Intake.id == intake_id))
    intake = result.scalar_one_or_none()
    if not intake:
        raise NotFoundException("Intake")

    # Update all scans in this intake
    scans_result = await db.execute(
        select(Scan)
        .where(Scan.intake_id == intake_id)
        .options(selectinload(Scan.status_logs))
    )
    scans = scans_result.scalars().all()

    now = datetime.now(timezone.utc)
    updated = 0
    for scan in scans:
        current_status = scan.status_logs[-1].inventory_status if scan.status_logs else "In Stock"
        if current_status not in ("Sold", "Spoiled"):
            db.add(ScanStatusLog(scan_id=scan.id, inventory_status=body.inventory_status))
            scan.updated_at = now
            updated += 1

    # Update intake status based on inventory
    intake.status = "Active" if body.inventory_status == "In Stock" else "Depleted"

    db.add(ActivityLog(
        user_id=admin.id,
        action="intake_status_changed",
        details=f"Bulk updated {updated} scans in intake {intake_id} → {body.inventory_status}",
    ))

    return {"message": f"Updated {updated} scans", "updated_count": updated}


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@analytics_router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(db: DbSession, user: CurrentUser):
    """Get aggregated analytics data for the dashboard."""
    # Total scans
    total_result = await db.execute(select(func.count()).select_from(Scan))
    total_scans = total_result.scalar() or 0

    # Average confidence
    avg_result = await db.execute(select(func.avg(ScanClassification.confidence)))
    avg_confidence = round(float(avg_result.scalar() or 0), 1)

    # Ripeness distribution
    ripeness_dist = []
    for ripeness in ["Unripe", "Ripe", "Overripe", "Rotten"]:
        count_result = await db.execute(
            select(func.count()).where(ScanClassification.ripeness == ripeness)
        )
        ripeness_dist.append(RipenessDistribution(
            name=ripeness,
            value=count_result.scalar() or 0,
        ))

    # Cultivar counts
    cultivar_counts = []
    most_common = "N/A"
    max_count = 0
    for cultivar in ["Lakatan", "Latundan", "Saba"]:
        count_result = await db.execute(
            select(func.count()).where(ScanClassification.cultivar == cultivar)
        )
        count = count_result.scalar() or 0
        cultivar_counts.append(CultivarCount(name=cultivar, count=count))
        if count > max_count:
            max_count = count
            most_common = cultivar

    # Scan trend (last 14 days)
    scan_trend: list[ScanTrend] = []
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        count_result = await db.execute(
            select(func.count()).where(
                func.date(Scan.date_time) == day
            )
        )
        scan_trend.append(ScanTrend(
            date=day.strftime("%b %d"),
            count=count_result.scalar() or 0,
        ))

    return AnalyticsSummary(
        total_scans=total_scans,
        avg_confidence=avg_confidence,
        most_common_cultivar=most_common,
        ripeness_distribution=ripeness_dist,
        cultivar_counts=cultivar_counts,
        scan_trend=scan_trend,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════════════════════════

activity_router = APIRouter(prefix="/activity", tags=["Activity"])


@activity_router.get("", response_model=ActivityLogListResponse)
async def list_activity(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
):
    """List activity logs with pagination (admin only)."""
    query = select(ActivityLog).order_by(desc(ActivityLog.created_at))

    if action:
        query = query.where(ActivityLog.action == action)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return ActivityLogListResponse(
        items=[
            ActivityLogResponse(
                id=log.id,
                user_name=log.user.full_name if log.user else None,
                action=log.action,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

config_router = APIRouter(prefix="/config", tags=["Config"])


@config_router.get("", response_model=SystemConfigResponse)
async def get_config(db: DbSession, admin: AdminUser):
    """Get system configuration."""
    camera_ids = await _get_config_value(db, "camera_ids", "CAM-001, CAM-002")
    threshold = await _get_config_value(db, "confidence_threshold", "85")

    return SystemConfigResponse(
        camera_ids=camera_ids,
        confidence_threshold=float(threshold),
    )


@config_router.patch("", response_model=SystemConfigResponse)
async def update_config(body: SystemConfigUpdate, db: DbSession, admin: AdminUser):
    """Update system configuration."""
    if body.camera_ids is not None:
        await _set_config_value(db, "camera_ids", body.camera_ids)
    if body.confidence_threshold is not None:
        await _set_config_value(db, "confidence_threshold", str(body.confidence_threshold))

    db.add(ActivityLog(
        user_id=admin.id,
        action="config_changed",
        details=f"Updated config: {body.model_dump(exclude_none=True)}",
    ))

    return await get_config(db, admin)


async def _get_config_value(db: DbSession, key: str, default: str) -> str:
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    return config.value if config else default


async def _set_config_value(db: DbSession, key: str, value: str):
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if config:
        config.value = value
    else:
        db.add(SystemConfig(key=key, value=value))


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

quality_router = APIRouter(prefix="/quality", tags=["Quality"])


@quality_router.get("/flagged")
async def get_flagged_scans(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get all flagged scans for quality review."""
    query = (
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.operator))
        .where(Scan.flagged == True)  # noqa: E712
        .order_by(desc(Scan.date_time))
    )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    scans = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "scanned_at": s.date_time.isoformat(),
                "cultivar": s.classification.cultivar if s.classification else "Unknown",
                "ripeness": s.classification.ripeness if s.classification else "Unknown",
                "confidence": float(s.classification.confidence) if s.classification else 0.0,
                "finger_count": s.classification.finger_count if s.classification else 0,
                "operator_name": s.operator.full_name if s.operator else "Unknown",
                "flagged": s.flagged,
            }
            for s in scans
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
