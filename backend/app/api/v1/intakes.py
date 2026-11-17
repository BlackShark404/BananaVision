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
from sqlalchemy.orm import noload, selectinload

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
    partial_scan_event_payload,
    scan_scope,
)
from app.core.http import get_client_ip
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.services import audit
from app.ws.mutations import (
    intake_event,
    publish_intake_event,
    publish_scan_event,
    scan_event,
)
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

    supplier_text = audit.quoted(sup.name) if sup else "unknown"
    batch_text = audit.quoted(new_intake.batch_number) if new_intake.batch_number else "none"
    source_text = audit.quoted(new_intake.source) if new_intake.source else "none"
    await audit.record(
        db, audit.AuditAction.INTAKE_CREATED,
        f"Created intake {new_intake.id} for supplier {supplier_text} "
        f"({new_intake.supplier_id}): batch {batch_text}, source {source_text}, "
        f"treatment {audit.clean(new_intake.treatment) or 'none'}",
        actor=user, ip=get_client_ip(request),
    )

    response = IntakeResponse(
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
        updated_at=new_intake.updated_at,
    )
    payload = response.model_dump(mode="json")
    payload.pop("qr_code", None)
    await db.commit()
    await publish_intake_event(
        intake_event(
            intake_id=new_intake.id,
            kind="created",
            actor_id=user.id,
            intake=payload,
            status=new_intake.status,
        )
    )
    return response


@router.get("", response_model=list[IntakeResponse])
async def list_intakes(db: DbSession, user: CurrentUser):
    """Shared registry; counts include only the caller's authorized scans."""
    scope = scan_scope(user)
    counts = (
        select(Scan.intake_id, func.count().label("scan_count"))
        .where(scope, Scan.intake_id.is_not(None))
        .group_by(Scan.intake_id)
        .subquery()
    )
    rows = (await db.execute(
        select(Intake, func.coalesce(counts.c.scan_count, 0))
        .outerjoin(counts, counts.c.intake_id == Intake.id)
        .options(noload(Intake.scans), selectinload(Intake.supplier))
        .order_by(desc(Intake.intake_date), desc(Intake.created_at))
    )).all()

    return [
        IntakeResponse(
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
            updated_at=intake.updated_at,
        )
        for intake, scan_count in rows
    ]


@router.patch("/{intake_id}/status")
async def update_intake_status(
    intake_id: uuid.UUID, body: IntakeStatusUpdate, db: DbSession, admin: AdminUser, request: Request
):
    """Update intake status (Active/Depleted)."""
    result = await db.execute(select(Intake).where(Intake.id == intake_id))
    intake = result.scalar_one_or_none()
    if not intake:
        raise NotFoundException("Intake")

    old_status = intake.status
    intake.status = body.status
    if old_status != body.status:  # Saving the same status is not an event.
        await audit.record(
            db, audit.AuditAction.INTAKE_STATUS_CHANGED,
            f"Intake {intake_id} status {audit.clean(old_status)} → {audit.clean(body.status)}",
            actor=admin, ip=get_client_ip(request),
        )
    await db.commit()
    await publish_intake_event(
        intake_event(
            intake_id=intake.id,
            kind="status",
            actor_id=admin.id,
            intake={"id": str(intake.id), "status": intake.status.value,
                    "updated_at": intake.updated_at.isoformat()},
            status=intake.status,
        )
    )
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
    pending_events = []
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
            change = await apply_scan_change(
                db, scan, admin, "status", {"inventory_status": body.inventory_status}, body.reason,
                client_ip=get_client_ip(request),
            )
            if change.changed:
                updated_ids.append(str(scan.id))
                pending_events.append((
                    scan_event(
                        scan_id=scan.id,
                        revision=scan.revision,
                        kind="status",
                        changed=change.changed,
                        actor_id=admin.id,
                        scan=partial_scan_event_payload(scan),
                        partial=True,
                    ),
                    scan.operator.account_id if scan.operator else None,
                ))
    final_in_stock = (
        body.inventory_status == InventoryStatusEnum.IN_STOCK
        if not scans
        else any(
            (
                scan.status_logs[-1].inventory_status
                if scan.status_logs
                else InventoryStatusEnum.IN_STOCK
            ) == InventoryStatusEnum.IN_STOCK
            for scan in scans
        )
    )
    old_intake_status = intake.status
    intake.status = IntakeStatusEnum.ACTIVE if final_in_stock else IntakeStatusEnum.DEPLETED
    if updated_ids or intake.status != old_intake_status:  # Nothing changed: no event.
        intake_change = (
            f"intake status {audit.clean(old_intake_status)} → {audit.clean(intake.status)}"
            if intake.status != old_intake_status
            else f"intake status {audit.clean(intake.status)} unchanged"
        )
        await audit.record(
            db, audit.AuditAction.INTAKE_STATUS_CHANGED,
            f"Bulk inventory for intake {intake_id}: {len(updated_ids)} of {len(scans)} scans "
            f"set to {audit.clean(body.inventory_status)}; "
            f"reason {audit.quoted(body.reason, 200)}; {intake_change}",
            actor=admin, ip=get_client_ip(request),
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
    await db.commit()
    for event, owner_account_id in pending_events:
        await publish_scan_event(event, owner_account_id=owner_account_id)
    await publish_intake_event(
        intake_event(
            intake_id=intake.id,
            kind="bulk-inventory",
            actor_id=admin.id,
            intake={"id": str(intake.id), "status": intake.status.value,
                    "updated_at": intake.updated_at.isoformat()},
            status=intake.status,
        )
    )
    return response
