"""
Supplier routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException
from app.models.supplier import Supplier
from app.core.http import get_client_ip
from app.services import audit
from app.schemas.common import SupplierCreate, SupplierUpdate, SupplierResponse
from app.ws.mutations import publish_supplier_event, supplier_event


router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

# Contact fields are personal data: the audit log notes that they changed, never the value.
AUDITED_FIELDS = ("name", "contact_person", "contact_phone", "status")


def _audit_snapshot(supplier: Supplier) -> dict:
    return {field: getattr(supplier, field) for field in AUDITED_FIELDS}


@router.get("", response_model=list[SupplierResponse])
async def list_suppliers(db: DbSession, user: CurrentUser):
    """List all suppliers."""
    result = await db.execute(select(Supplier).order_by(Supplier.date_added))
    return [SupplierResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SupplierResponse, status_code=201)
async def create_supplier(body: SupplierCreate, db: DbSession, admin: AdminUser, request: Request):
    """Create a new supplier."""
    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    await db.flush()
    await audit.record(
        db, audit.AuditAction.SUPPLIER_CREATED,
        f"Created supplier {audit.quoted(supplier.name)} ({supplier.id}), "
        f"status {audit.clean(supplier.status)}",
        actor=admin, ip=get_client_ip(request),
    )
    await db.flush()
    response = SupplierResponse.model_validate(supplier)
    await db.commit()
    await publish_supplier_event(
        supplier_event(
            supplier_id=supplier.id,
            kind="created",
            actor_id=admin.id,
            supplier=response.model_dump(mode="json"),
        )
    )
    return response


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession, admin: AdminUser, request: Request
):
    """Update a supplier."""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise NotFoundException("Supplier")

    before = _audit_snapshot(supplier)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(supplier, field, value)

    changes = audit.describe_changes(before, _audit_snapshot(supplier))
    if changes:  # Saving unchanged values is not an event.
        await audit.record(
            db, audit.AuditAction.SUPPLIER_UPDATED,
            f"Updated supplier {audit.quoted(before['name'])} ({supplier.id}): {changes}",
            actor=admin, ip=get_client_ip(request),
        )

    await db.flush()
    response = SupplierResponse.model_validate(supplier)
    await db.commit()
    await publish_supplier_event(
        supplier_event(
            supplier_id=supplier.id,
            kind="updated",
            actor_id=admin.id,
            supplier=response.model_dump(mode="json"),
        )
    )
    return response
