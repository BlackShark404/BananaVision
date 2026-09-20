"""
Scan routes — trigger scans, CRUD, flagging, notes, overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.operator_profile import OperatorProfile
from app.models.scan_status_log import ScanStatusLog
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.scan_note import ScanNote
from app.models.activity_log import ActivityLog
from app.core.exceptions import NotFoundException, ModelInferenceError
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
    ScanImageRef,
    ScanNoteResponse,
    ScanStatusUpdate,
)
from app.services.scan_service import execute_scan_pipeline
from app.schemas.enums import InventoryStatusEnum

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.post("/trigger", response_model=ScanResponse)
async def trigger_scan(body: ScanTriggerRequest, db: DbSession, user: CurrentUser):
    """Trigger a full scan pipeline (capture → detect → fuse → predict)."""
    if not user.operator_profile:
        raise NotFoundException("OperatorProfile")

    try:
        scan = await execute_scan_pipeline(
            db=db,
            operator_id=user.operator_profile.id,
            account_id=user.id,
            operator_name=user.full_name,
            intake_id=body.intake_id,
            supplier_name=body.source_text,  # Use source_text from request
        )
    except ModelInferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return ScanResponse(
        id=scan.id,
        date_time=scan.date_time,
        cultivar=scan.classification.cultivar,
        ripeness=scan.classification.ripeness,
        confidence=scan.classification.confidence,
        temperature=scan.classification.temperature,
        humidity=scan.classification.humidity,
        dew_point=float(scan.classification.dew_point) if scan.classification.dew_point else None,
        vpd=float(scan.classification.vpd) if scan.classification.vpd else None,
        heat_index=float(scan.classification.heat_index) if scan.classification.heat_index else None,
        treatment=scan.classification.treatment.value if scan.classification.treatment else None,
        spoilage_days=scan.classification.spoilage_days,
        finger_count=scan.classification.finger_count,
        operator_name=user.full_name,
        source_text=scan.source_text,
        intake_id=scan.intake_id,
        inventory_status=scan.status_logs[-1].inventory_status if scan.status_logs else InventoryStatusEnum.IN_STOCK,
        status_updated_at=scan.status_logs[-1].updated_at if scan.status_logs else None,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result=None,
        thumbnail_url=scan.classification.thumbnail_url,
        has_notes=False,
        images=[ScanImageRef(camera_id=img.camera_id, file_path=img.file_path) for img in (scan.images or [])],
        updated_at=scan.updated_at,
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
    query = select(Scan).outerjoin(Scan.classification).options(
        selectinload(Scan.classification),
        selectinload(Scan.status_logs),
        selectinload(Scan.original_ai_result),
        selectinload(Scan.notes),
        selectinload(Scan.images),
        selectinload(Scan.operator).selectinload(OperatorProfile.account),
    ).order_by(desc(Scan.date_time))

    if cultivar:
        query = query.where(ScanClassification.cultivar == cultivar)
    if ripeness:
        query = query.where(ScanClassification.ripeness == ripeness)
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
                date_time=s.date_time,
                cultivar=s.classification.cultivar if s.classification else "Unknown",
                ripeness=s.classification.ripeness if s.classification else "Unknown",
                confidence=float(s.classification.confidence) if s.classification else 0.0,
                temperature=float(s.classification.temperature) if s.classification and s.classification.temperature else None,
                humidity=float(s.classification.humidity) if s.classification and s.classification.humidity else None,
                dew_point=float(s.classification.dew_point) if s.classification and s.classification.dew_point else None,
                vpd=float(s.classification.vpd) if s.classification and s.classification.vpd else None,
                heat_index=float(s.classification.heat_index) if s.classification and s.classification.heat_index else None,
                treatment=s.classification.treatment.value if s.classification and s.classification.treatment else None,
                spoilage_days=s.classification.spoilage_days if s.classification else "Unknown",
                finger_count=s.classification.finger_count if s.classification else 0,
                operator_name=s.operator.account.full_name if s.operator and s.operator.account else "Unknown",
                source_text=s.source_text,
                intake_id=s.intake_id,
                inventory_status=s.status_logs[-1].inventory_status if s.status_logs else "Unknown",
                status_updated_at=s.status_logs[-1].updated_at if s.status_logs else None,
                flagged=s.flagged,
                is_overridden=s.is_overridden,
                original_ai_result={
                    "cultivar": s.original_ai_result.cultivar,
                    "ripeness": s.original_ai_result.ripeness,
                    "confidence": float(s.original_ai_result.confidence),
                    "finger_count": s.original_ai_result.finger_count,
                } if s.original_ai_result else None,
                thumbnail_url=s.classification.thumbnail_url if s.classification else None,
                has_notes=len(s.notes) > 0 if hasattr(s, 'notes') and s.notes else False,
                images=[ScanImageRef(camera_id=img.camera_id, file_path=img.file_path) for img in (s.images or [])],
                updated_at=s.updated_at,
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
            selectinload(Scan.classification),
            selectinload(Scan.status_logs),
            selectinload(Scan.original_ai_result),
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
        date_time=scan.date_time,
        cultivar=scan.classification.cultivar if scan.classification else "Unknown",
        ripeness=scan.classification.ripeness if scan.classification else "Unknown",
        confidence=float(scan.classification.confidence) if scan.classification else 0.0,
        temperature=float(scan.classification.temperature) if scan.classification and scan.classification.temperature else None,
        humidity=float(scan.classification.humidity) if scan.classification and scan.classification.humidity else None,
        dew_point=float(scan.classification.dew_point) if scan.classification and scan.classification.dew_point else None,
        vpd=float(scan.classification.vpd) if scan.classification and scan.classification.vpd else None,
        heat_index=float(scan.classification.heat_index) if scan.classification and scan.classification.heat_index else None,
        treatment=scan.classification.treatment.value if scan.classification and scan.classification.treatment else None,
        spoilage_days=scan.classification.spoilage_days if scan.classification else "Unknown",
        finger_count=scan.classification.finger_count if scan.classification else 0,
        operator_name=scan.operator.full_name if scan.operator else "Unknown",
        source_text=scan.source_text,
        intake_id=scan.intake_id,
        inventory_status=scan.status_logs[-1].inventory_status if scan.status_logs else "Unknown",
        status_updated_at=scan.status_logs[-1].updated_at if scan.status_logs else None,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result={
            "cultivar": scan.original_ai_result.cultivar,
            "ripeness": scan.original_ai_result.ripeness,
            "confidence": float(scan.original_ai_result.confidence),
            "finger_count": scan.original_ai_result.finger_count,
        } if scan.original_ai_result else None,
        thumbnail_url=scan.classification.thumbnail_url if scan.classification else None,
        has_notes=len(scan.notes) > 0 if scan.notes else False,
        updated_at=scan.updated_at,
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
                text=n.text,
                author_name=n.author_name,
                timestamp=n.timestamp,
            )
            for n in scan.notes
        ],
    )


@router.patch("/{scan_id}/flag")
async def flag_scan(scan_id: uuid.UUID, body: ScanFlagRequest, db: DbSession, user: CurrentUser, request: Request):
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
        ip_address=request.client.host if request.client else None,
    ))
    return {"message": f"Scan {'flagged' if body.flagged else 'unflagged'}"}


@router.patch("/{scan_id}", response_model=ScanResponse)
async def override_scan(
    scan_id: uuid.UUID, body: ScanOverrideRequest, db: DbSession, admin: AdminUser, request: Request
):
    """Admin override of scan classification."""
    result = await db.execute(
        select(Scan)
        .where(Scan.id == scan_id)
        .options(
            selectinload(Scan.classification),
            selectinload(Scan.status_logs),
            selectinload(Scan.original_ai_result),
            selectinload(Scan.notes),
            selectinload(Scan.operator),
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundException("Scan")

    # Store original AI result before override
    if not scan.is_overridden and scan.classification:
        if not scan.original_ai_result:
            scan.original_ai_result = ScanOriginalAiResult(
                scan_id=scan.id,
                cultivar=scan.classification.cultivar,
                ripeness=scan.classification.ripeness,
                confidence=scan.classification.confidence,
                finger_count=scan.classification.finger_count,
            )
            db.add(scan.original_ai_result)

    if scan.classification:
        if body.cultivar:
            scan.classification.cultivar = body.cultivar
        if body.ripeness:
            scan.classification.ripeness = body.ripeness
        if body.finger_count is not None:
            scan.classification.finger_count = body.finger_count

    scan.is_overridden = True

    db.add(ActivityLog(
        user_id=admin.id,
        action="scan_edited",
        details=f"Override scan {scan_id}: {body.model_dump(exclude_none=True)}",
        ip_address=request.client.host if request.client else None,
    ))

    await db.flush()

    return ScanResponse(
        id=scan.id,
        date_time=scan.date_time,
        cultivar=scan.classification.cultivar if scan.classification else "Unknown",
        ripeness=scan.classification.ripeness if scan.classification else "Unknown",
        confidence=float(scan.classification.confidence) if scan.classification else 0.0,
        temperature=float(scan.classification.temperature) if scan.classification and scan.classification.temperature else None,
        humidity=float(scan.classification.humidity) if scan.classification and scan.classification.humidity else None,
        spoilage_days=scan.classification.spoilage_days if scan.classification else "Unknown",
        finger_count=scan.classification.finger_count if scan.classification else 0,
        operator_name=scan.operator.full_name if scan.operator else "Unknown",
        source_text=scan.source_text,
        intake_id=scan.intake_id,
        inventory_status=scan.status_logs[-1].inventory_status if scan.status_logs else "Unknown",
        status_updated_at=scan.status_logs[-1].updated_at if scan.status_logs else None,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result={
            "cultivar": scan.original_ai_result.cultivar,
            "ripeness": scan.original_ai_result.ripeness,
            "confidence": float(scan.original_ai_result.confidence),
            "finger_count": scan.original_ai_result.finger_count,
        } if scan.original_ai_result else None,
        thumbnail_url=scan.classification.thumbnail_url if scan.classification else None,
        has_notes=len(scan.notes) > 0 if hasattr(scan, 'notes') and scan.notes else False,
        updated_at=scan.updated_at,
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

    new_log = ScanStatusLog(
        scan_id=scan.id,
        inventory_status=body.inventory_status
    )
    db.add(new_log)
    scan.updated_at = func.now()
    return {"message": "Status updated"}


@router.post("/{scan_id}/notes", response_model=ScanNoteResponse)
async def add_note(
    scan_id: uuid.UUID, body: ScanNoteCreate, db: DbSession, user: CurrentUser
):
    """Add a note to a scan."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    if not result.scalar_one_or_none():
        raise NotFoundException("Scan")

    note = ScanNote(scan_id=scan_id, author_name=user.full_name, text=body.note)
    db.add(note)
    await db.flush()

    return ScanNoteResponse(
        id=note.id,
        scan_id=note.scan_id,
        text=note.text,
        author_name=note.author_name,
        timestamp=note.timestamp,
    )


@router.get("/{scan_id}/notes", response_model=list[ScanNoteResponse])
async def get_notes(scan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Get all notes for a scan."""
    result = await db.execute(
        select(ScanNote)
        .where(ScanNote.scan_id == scan_id)
        .order_by(ScanNote.timestamp)
    )
    notes = result.scalars().all()
    return [
        ScanNoteResponse(
            id=n.id,
            scan_id=n.scan_id,
            text=n.text,
            author_name=n.author_name,
            timestamp=n.timestamp,
        )
        for n in notes
    ]
