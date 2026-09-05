"""
Delivery intake routes.
"""

from __future__ import annotations

import uuid
import qrcode
import io
import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_status_log import ScanStatusLog
from app.models.activity_log import ActivityLog
from app.schemas.common import (
    IntakeCreate,
    IntakeResponse,
    IntakeStatusUpdate,
    IntakeBulkInventoryUpdate,
)
from app.schemas.enums import IntakeStatusEnum, InventoryStatusEnum, TreatmentEnum


router = APIRouter(prefix="/intakes", tags=["Intakes"])


@router.post("", response_model=IntakeResponse)
async def create_intake(body: IntakeCreate, db: DbSession, user: CurrentUser, request: Request):
    """Create a new delivery intake."""
    now = datetime.now(timezone.utc)

    # Parse treatment enum
    treatment_val = None
    if body.treatment:
        try:
            treatment_val = TreatmentEnum(body.treatment)
        except ValueError:
            treatment_val = TreatmentEnum.NATURAL

    new_intake = Intake(
        supplier_id=body.supplier_id,
        batch_number=body.batch_number,
        source=body.source,
        intake_date=now.date(),
        status=IntakeStatusEnum.ACTIVE,
        treatment=treatment_val,
        harvested_at=body.harvested_at,
        treated_at=body.treated_at,
        created_at=now,
        updated_at=now,
    )
    db.add(new_intake)
    await db.flush()

    # Generate QR Code
    qr_data = {
        "intake_id": str(new_intake.id),
        "supplier_id": str(new_intake.supplier_id),
        "batch_number": new_intake.batch_number,
        "date": new_intake.intake_date.isoformat()
    }
    img = qrcode.make(json.dumps(qr_data))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    new_intake.qr_code = f"data:image/png;base64,{b64}"

    await db.flush()

    # Fetch supplier name
    sup_result = await db.execute(select(Supplier).where(Supplier.id == new_intake.supplier_id))
    sup = sup_result.scalar_one_or_none()

    db.add(ActivityLog(
        user_id=user.id,
        action="intake_created",
        details=f"Created intake {new_intake.id}",
        ip_address=request.client.host if request.client else None,
    ))

    return IntakeResponse(
        id=new_intake.id,
        supplier_id=new_intake.supplier_id,
        supplier_name=sup.name if sup else None,
        batch_number=new_intake.batch_number,
        qr_code=new_intake.qr_code,
        intake_date=new_intake.intake_date,
        status=new_intake.status,
        treatment=new_intake.treatment.value if new_intake.treatment else None,
        harvested_at=new_intake.harvested_at,
        treated_at=new_intake.treated_at,
        spoiled_at=new_intake.spoiled_at,
        scan_count=0,
        created_at=new_intake.created_at,
    )


@router.get("", response_model=list[IntakeResponse])
async def list_intakes(db: DbSession, user: CurrentUser):
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
            batch_number=intake.batch_number,
            qr_code=intake.qr_code,
            intake_date=intake.intake_date,
            status=intake.status,
            treatment=intake.treatment.value if intake.treatment else None,
            harvested_at=intake.harvested_at,
            treated_at=intake.treated_at,
            spoiled_at=intake.spoiled_at,
            scan_count=scan_count,
            created_at=intake.created_at,
        ))

    return responses


@router.patch("/{intake_id}/status")
async def update_intake_status(
    intake_id: uuid.UUID, body: IntakeStatusUpdate, db: DbSession, admin: AdminUser, request: Request
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
        ip_address=request.client.host if request.client else None,
    ))
    return {"message": "Intake status updated"}


@router.patch("/{intake_id}/bulk-inventory")
async def bulk_update_intake_inventory(
    intake_id: uuid.UUID, body: IntakeBulkInventoryUpdate, db: DbSession, admin: AdminUser, request: Request
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
        current_status = scan.status_logs[-1].inventory_status if scan.status_logs else InventoryStatusEnum.IN_STOCK
        if current_status not in (InventoryStatusEnum.SOLD, InventoryStatusEnum.SPOILED):
            db.add(ScanStatusLog(scan_id=scan.id, inventory_status=body.inventory_status))
            scan.updated_at = now
            updated += 1

    # Update intake status based on inventory
    intake.status = IntakeStatusEnum.ACTIVE if body.inventory_status == InventoryStatusEnum.IN_STOCK else IntakeStatusEnum.DEPLETED

    db.add(ActivityLog(
        user_id=admin.id,
        action="intake_status_changed",
        details=f"Bulk updated {updated} scans in intake {intake_id} → {body.inventory_status}",
        ip_address=request.client.host if request.client else None,
    ))

    return {"message": f"Updated {updated} scans", "updated_count": updated}
