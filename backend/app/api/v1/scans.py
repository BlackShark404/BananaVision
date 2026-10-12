"""
Scan routes — trigger scans, CRUD, flagging, notes, overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import desc, func, select
from app.core.http import get_client_ip
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.exceptions import ModelInferenceError, NotFoundException
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_note import ScanNote
from app.schemas.scan import (
    ScanDetailResponse,
    ScanFlagRequest,
    ScanHistoryResponse,
    ScanListResponse,
    ScanNoteCreate,
    ScanNoteResponse,
    ScanNoteWriteResponse,
    ScanOverrideRequest,
    ScanProvenanceReview,
    ScanResponse,
    ScanStatusUpdate,
    ScanTriggerRequest,
)
from app.services.scan_records import (
    load_authorized_scan,
    mutate_scan,
    scan_history,
    scan_scope,
    serialize_detail,
    serialize_scan,
)
from app.services.scan_service import execute_scan_pipeline

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.post("/trigger", response_model=ScanResponse)
async def trigger_scan(body: ScanTriggerRequest, db: DbSession, user: CurrentUser, request: Request):
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
            client_ip=get_client_ip(request),
        )
    except ModelInferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return serialize_scan(scan, user)


@router.get("", response_model=ScanListResponse)
async def list_scans(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cultivar: str | None = None,
    ripeness: str | None = None,
    flagged: bool | None = None,
    stable: bool = False,
    snapshot_id: uuid.UUID | None = None,
):
    """List scans with pagination and filtering."""
    from app.services.scan_snapshots import (
        MAX_ROWS,
        binding,
        load_snapshot,
        save_snapshot,
        slice_snapshot,
    )

    key = binding(
        "history", dict(page_size=page_size, cultivar=cultivar, ripeness=ripeness, flagged=flagged)
    )
    if snapshot_id:
        saved = await load_snapshot(db, user, snapshot_id, key)
        return ScanListResponse(**slice_snapshot(saved, page, page_size))
    if stable:
        from app.services.auth_service import lock_current_account
        user = await lock_current_account(db, user)
    query = select(Scan).where(scan_scope(user)).outerjoin(Scan.classification).options(
        selectinload(Scan.classification),
        selectinload(Scan.status_logs),
        selectinload(Scan.original_ai_result),
        selectinload(Scan.notes),
        selectinload(Scan.images),
        selectinload(Scan.operator).selectinload(OperatorProfile.account),
    ).order_by(desc(Scan.date_time), desc(Scan.id))

    if cultivar:
        query = query.where(ScanClassification.cultivar == cultivar)
    if ripeness:
        query = query.where(ScanClassification.ripeness == ripeness)
    if flagged is not None:
        query = query.where(Scan.flagged == flagged)

    if stable:
        # Hold scan read locks while select-in relationships are hydrated. All
        # supported scan writers lock this parent before changing its children.
        scans = (
            (
                await db.execute(
                    query.execution_options(populate_existing=True)
                    .order_by(None)
                    .order_by(Scan.id)
                    .limit(MAX_ROWS + 1)
                    .with_for_update(read=True, of=Scan)
                )
            )
            .scalars()
            .all()
        )
        # Use the same lock order as bulk intake writes; sort only after locks.
        scans.sort(key=lambda scan: (scan.date_time, scan.id), reverse=True)
        saved = await save_snapshot(db, user, key, {
            "items": [serialize_scan(scan, user).model_dump(mode="json") for scan in scans],
        })
        return ScanListResponse(**slice_snapshot(saved, page, page_size))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    scans = result.scalars().all()

    return ScanListResponse(
        items=[serialize_scan(s, user) for s in scans],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan(scan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Get a single scan with detections, images, and notes."""
    scan = await load_authorized_scan(db, scan_id, user)
    return await serialize_detail(db, scan, user)


@router.patch("/{scan_id}/flag", response_model=ScanDetailResponse)
async def flag_scan(scan_id: uuid.UUID, body: ScanFlagRequest, db: DbSession, user: CurrentUser, request: Request):
    return await mutate_scan(db, scan_id, user, "flag", body, client_ip=get_client_ip(request))


@router.patch("/{scan_id}", response_model=ScanDetailResponse)
async def override_scan(
    scan_id: uuid.UUID, body: ScanOverrideRequest, db: DbSession, admin: AdminUser, request: Request
):
    return await mutate_scan(db, scan_id, admin, "correction", body, client_ip=get_client_ip(request))


@router.patch("/{scan_id}/status", response_model=ScanDetailResponse)
async def update_scan_status(
    scan_id: uuid.UUID, body: ScanStatusUpdate, db: DbSession, user: CurrentUser, request: Request
):
    return await mutate_scan(db, scan_id, user, "status", body, client_ip=get_client_ip(request))


@router.post("/{scan_id}/notes", response_model=ScanNoteWriteResponse)
async def add_note(scan_id: uuid.UUID, body: ScanNoteCreate, db: DbSession, user: AdminUser, request: Request):
    return await mutate_scan(db, scan_id, user, "note", body, client_ip=get_client_ip(request))


@router.patch("/{scan_id}/provenance", response_model=ScanDetailResponse)
async def review_provenance(
    scan_id: uuid.UUID, body: ScanProvenanceReview, db: DbSession, user: AdminUser, request: Request
):
    return await mutate_scan(db, scan_id, user, "provenance", body, client_ip=get_client_ip(request))


@router.get("/{scan_id}/history", response_model=list[ScanHistoryResponse])
async def get_history(scan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    scan = await load_authorized_scan(db, scan_id, user)
    return await scan_history(db, scan, user)


@router.get("/{scan_id}/notes", response_model=list[ScanNoteResponse])
async def get_notes(scan_id: uuid.UUID, db: DbSession, user: AdminUser):
    """Get all notes for a scan."""
    await load_authorized_scan(db, scan_id, user)
    result = await db.execute(
        select(ScanNote)
        .where(ScanNote.scan_id == scan_id)
        .order_by(ScanNote.timestamp, ScanNote.id)
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
