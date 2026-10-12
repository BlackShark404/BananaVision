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
from app.models.activity_log import ActivityLog
from app.core.http import get_client_ip
from app.schemas.common import SupplierCreate, SupplierUpdate, SupplierResponse


router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


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
    db.add(ActivityLog(
        user_id=admin.id,
        action="supplier_created",
        details=f"Added supplier '{body.name}'",
        ip_address=get_client_ip(request),
    ))
    await db.flush()
    return SupplierResponse.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession, admin: AdminUser, request: Request
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
        ip_address=get_client_ip(request),
    ))

    await db.flush()
    return SupplierResponse.model_validate(supplier)
