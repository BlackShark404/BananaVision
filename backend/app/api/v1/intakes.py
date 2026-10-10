"""
Delivery intake routes.
"""

from __future__ import annotations

import uuid
import qrcode
import io
import base64
import json
from app.core.time import now_manila

from fastapi import APIRouter, Request
from sqlalchemy import select, func, desc

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException, ConflictException, ForbiddenException
from app.services.auth_service import lock_current_account
from app.services.scan_records import (
    lock_mutation,
    mutation_fingerprint,
    mutation_replay,
    save_receipt,
    apply_scan_change,
    is_admin,
)
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
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
    now = now_manila()

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
        source=new_intake.source,
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
            source=intake.source,
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


@router.get("/{intake_id}/scan-revisions")
async def intake_scan_revisions(intake_id: uuid.UUID, db: DbSession, admin: AdminUser):
    if not await db.scalar(select(Intake.id).where(Intake.id == intake_id)):
        raise NotFoundException("Intake")
    rows = (
        await db.execute(select(Scan.id, Scan.revision).where(Scan.intake_id == intake_id))
    ).all()
    return {"revisions": {str(row.id): row.revision for row in rows}}


@router.patch("/{intake_id}/bulk-inventory")
async def bulk_update_intake_inventory(
    intake_id: uuid.UUID, body: IntakeBulkInventoryUpdate, db: DbSession, admin: AdminUser, request: Request
):
    await lock_mutation(db, body.request_id)
    admin = await lock_current_account(db, admin)
    if not is_admin(admin):
        raise ForbiddenException("Admin access required")
    intake = (await db.execute(select(Intake).where(Intake.id == intake_id).with_for_update()
                               .execution_options(populate_existing=True))).scalar_one_or_none()
    if not intake:
        raise NotFoundException("Intake")
    fingerprint = mutation_fingerprint(admin, intake_id, "bulk-inventory", body)
    replay = await mutation_replay(db, admin, body, fingerprint)
    if replay is not None:
        return replay
    scans = (await db.execute(select(Scan).where(Scan.intake_id == intake_id).order_by(Scan.id)
                              .with_for_update().execution_options(populate_existing=True))).scalars().all()
    if body.expected_revisions != {scan.id: scan.revision for scan in scans}:
        raise ConflictException(
            "Intake scans changed. Reload the intake before applying this action."
        )
    updated_ids = []
    for scan in scans:
        current = (
            scan.status_logs[-1].inventory_status
            if scan.status_logs
            else InventoryStatusEnum.IN_STOCK
        )
        if (
            current not in (InventoryStatusEnum.SOLD, InventoryStatusEnum.SPOILED)
            and current != body.inventory_status
        ):
            await apply_scan_change(
                db, scan, admin, "status", {"inventory_status": body.inventory_status}, body.reason
            )
            updated_ids.append(str(scan.id))
    intake.status = IntakeStatusEnum.ACTIVE if body.inventory_status == InventoryStatusEnum.IN_STOCK else IntakeStatusEnum.DEPLETED
    db.add(
        ActivityLog(
            user_id=admin.id,
            action="intake_status_changed",
            details=f"Bulk updated {len(updated_ids)} scans in intake {intake_id}: {body.reason}",
            ip_address=request.client.host if request.client else None,
        )
    )
    response = {
        "message": f"Updated {len(updated_ids)} scans",
        "updated_count": len(updated_ids),
        "updated_scan_ids": updated_ids,
        "status_updated_at": now_manila().isoformat(),
        "intake_status": intake.status,
        "revisions": {str(scan.id): scan.revision for scan in scans},
    }
    save_receipt(db, admin, body, fingerprint, response)
    return response
