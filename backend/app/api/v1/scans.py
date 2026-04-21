"""
Scan routes — trigger scans, CRUD, flagging, notes, overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.models.scan import Scan
from app.models.scan_note import ScanNote
from app.models.activity_log import ActivityLog
from app.core.exceptions import NotFoundException
from app.schemas.scan import (
    ScanTriggerRequest,
    ScanFlagRequest,
    ScanNoteCreate,
    ScanOverrideRequest,
    ScanResponse,
    ScanDetailResponse,
    ScanListResponse,
    ScanDetectionResponse,
    ScanImageResponse,
    ScanNoteResponse,
    ScanStatusUpdate,
)
from app.services.scan_service import execute_scan_pipeline

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.post("/trigger", response_model=ScanResponse)
async def trigger_scan(body: ScanTriggerRequest, db: DbSession, user: CurrentUser):
    """Trigger a full scan pipeline (capture → detect → fuse → predict)."""
    scan = await execute_scan_pipeline(
        db=db,
        operator_id=user.id,
        operator_name=user.full_name,
        intake_id=body.intake_id,
        supplier_name=None,  # Resolved from intake if needed
    )

    return ScanResponse(
        id=scan.id,
        scanned_at=scan.scanned_at,
        cultivar=scan.cultivar,
        ripeness=scan.ripeness,
        confidence=scan.confidence,
        temperature=scan.temperature,
        humidity=scan.humidity,
        spoilage_days=scan.spoilage_days,
        finger_count=scan.finger_count,
        operator_name=user.full_name,
        intake_id=scan.intake_id,
        inventory_status=scan.inventory_status,
        status_updated_at=scan.status_updated_at,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        created_at=scan.created_at,
    )


@router.get("", response_model=ScanListResponse)
async def list_scans(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cultivar: str | None = None,
    ripeness: str | None = None,
    flagged: bool | None = None,
):
    """List scans with pagination and filtering."""
    query = select(Scan).order_by(desc(Scan.scanned_at))

    if cultivar:
        query = query.where(Scan.cultivar == cultivar)
    if ripeness:
        query = query.where(Scan.ripeness == ripeness)
    if flagged is not None:
        query = query.where(Scan.flagged == flagged)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    scans = result.scalars().all()

    return ScanListResponse(
        items=[
            ScanResponse(
                id=s.id,
                scanned_at=s.scanned_at,
                cultivar=s.cultivar,
                ripeness=s.ripeness,
                confidence=s.confidence,
                temperature=s.temperature,
                humidity=s.humidity,
                spoilage_days=s.spoilage_days,
                finger_count=s.finger_count,
                operator_name=s.operator.full_name if s.operator else "Unknown",
                supplier_name=(
                    s.intake.supplier.name
                    if s.intake and s.intake.supplier
                    else None
                ),
                intake_id=s.intake_id,
                inventory_status=s.inventory_status,
                status_updated_at=s.status_updated_at,
                flagged=s.flagged,
                is_overridden=s.is_overridden,
                original_ai_result=s.original_ai_result,
                created_at=s.created_at,
            )
            for s in scans
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan(scan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Get a single scan with detections, images, and notes."""
    result = await db.execute(
        select(Scan)
        .where(Scan.id == scan_id)
        .options(
            selectinload(Scan.detections),
            selectinload(Scan.images),
            selectinload(Scan.notes),
            selectinload(Scan.operator),
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundException("Scan")

    return ScanDetailResponse(
        id=scan.id,
        scanned_at=scan.scanned_at,
        cultivar=scan.cultivar,
        ripeness=scan.ripeness,
        confidence=scan.confidence,
        temperature=scan.temperature,
        humidity=scan.humidity,
        spoilage_days=scan.spoilage_days,
        finger_count=scan.finger_count,
        operator_name=scan.operator.full_name if scan.operator else "Unknown",
        intake_id=scan.intake_id,
        inventory_status=scan.inventory_status,
        status_updated_at=scan.status_updated_at,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result=scan.original_ai_result,
        created_at=scan.created_at,
        detections=[
            ScanDetectionResponse.model_validate(d) for d in scan.detections
        ],
        images=[
            ScanImageResponse.model_validate(i) for i in scan.images
        ],
        notes=[
            ScanNoteResponse(
                id=n.id,
                scan_id=n.scan_id,
                note=n.note,
                author_name=n.author.full_name if n.author else "Unknown",
                created_at=n.created_at,
            )
            for n in scan.notes
        ],
    )


@router.patch("/{scan_id}/flag")
async def flag_scan(scan_id: uuid.UUID, body: ScanFlagRequest, db: DbSession, user: CurrentUser):
    """Flag or unflag a scan for review."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundException("Scan")

    scan.flagged = body.flagged
    db.add(ActivityLog(
        user_id=user.id,
        action="scan_flagged",
        details=f"{'Flagged' if body.flagged else 'Unflagged'} scan {scan_id}",
    ))
    return {"message": f"Scan {'flagged' if body.flagged else 'unflagged'}"}


@router.patch("/{scan_id}", response_model=ScanResponse)
async def override_scan(
    scan_id: uuid.UUID, body: ScanOverrideRequest, db: DbSession, admin: AdminUser
):
    """Admin override of scan classification."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundException("Scan")

    # Store original AI result before override
    if not scan.is_overridden:
        scan.original_ai_result = {
            "cultivar": scan.cultivar,
            "ripeness": scan.ripeness,
            "confidence": scan.confidence,
            "finger_count": scan.finger_count,
        }

    if body.cultivar:
        scan.cultivar = body.cultivar
    if body.ripeness:
        scan.ripeness = body.ripeness
    if body.finger_count is not None:
        scan.finger_count = body.finger_count

    scan.is_overridden = True

    db.add(ActivityLog(
        user_id=admin.id,
        action="scan_edited",
        details=f"Override scan {scan_id}: {body.model_dump(exclude_none=True)}",
    ))

    return ScanResponse(
        id=scan.id,
        scanned_at=scan.scanned_at,
        cultivar=scan.cultivar,
        ripeness=scan.ripeness,
        confidence=scan.confidence,
        temperature=scan.temperature,
        humidity=scan.humidity,
        spoilage_days=scan.spoilage_days,
        finger_count=scan.finger_count,
        operator_name=scan.operator.full_name if scan.operator else "Unknown",
        intake_id=scan.intake_id,
        inventory_status=scan.inventory_status,
        status_updated_at=scan.status_updated_at,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result=scan.original_ai_result,
        created_at=scan.created_at,
    )


@router.patch("/{scan_id}/status")
async def update_scan_status(
    scan_id: uuid.UUID, body: ScanStatusUpdate, db: DbSession, user: CurrentUser
):
    """Update scan inventory status."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundException("Scan")

    from datetime import datetime, timezone
    scan.inventory_status = body.inventory_status
    scan.status_updated_at = datetime.now(timezone.utc)
    return {"message": "Status updated"}


@router.post("/{scan_id}/notes", response_model=ScanNoteResponse)
async def add_note(
    scan_id: uuid.UUID, body: ScanNoteCreate, db: DbSession, user: CurrentUser
):
    """Add a note to a scan."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    if not result.scalar_one_or_none():
        raise NotFoundException("Scan")

    note = ScanNote(scan_id=scan_id, author_id=user.id, note=body.note)
    db.add(note)
    await db.flush()

    return ScanNoteResponse(
        id=note.id,
        scan_id=note.scan_id,
        note=note.note,
        author_name=user.full_name,
        created_at=note.created_at,
    )


@router.get("/{scan_id}/notes", response_model=list[ScanNoteResponse])
async def get_notes(scan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Get all notes for a scan."""
    result = await db.execute(
        select(ScanNote)
        .where(ScanNote.scan_id == scan_id)
        .options(selectinload(ScanNote.author))
        .order_by(ScanNote.created_at)
    )
    notes = result.scalars().all()
    return [
        ScanNoteResponse(
            id=n.id,
            scan_id=n.scan_id,
            note=n.note,
            author_name=n.author.full_name if n.author else "Unknown",
            created_at=n.created_at,
        )
        for n in notes
    ]
