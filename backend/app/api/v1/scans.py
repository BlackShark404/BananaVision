"""
Scan routes — trigger scans, CRUD, flagging, notes, overrides.
"""

from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select
from app.core.http import get_client_ip
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.exceptions import ModelInferenceError, NotFoundException, ScanRejectedError
from app.core.time import now_manila
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_note import ScanNote
from app.schemas.scan import (
    PublicScanResponse,
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
from app.services.inventory_policy import (
    remaining_shelf_life,
    ripeness_projection,
    shelf_life_window,
)
from app.services.ood_gate import REJECTION_CODE
from app.services.scan_service import execute_scan_pipeline, rejection_payload
from app.config import get_settings
from app.services.print_jobs import queue_automatic_label

router = APIRouter(prefix="/scans", tags=["Scans"])
logger = logging.getLogger(__name__)


@router.post("/trigger", response_model=ScanResponse)
async def trigger_scan(
    body: ScanTriggerRequest, db: DbSession, user: CurrentUser,
    request: Request, background_tasks: BackgroundTasks,
):
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
    except ScanRejectedError as exc:
        # `detail` stays a string for existing clients; the other fields are additive.
        status_code = 422 if exc.code == REJECTION_CODE else 503
        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.message, **rejection_payload(exc)},
        )
    except ModelInferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    response = serialize_scan(scan, user)
    if get_settings().bananavision_auto_print:
        try:
            response.print_job = await queue_automatic_label(db, scan, user, background_tasks)
        except Exception:
            # The prediction has already committed. Printing cannot invalidate it.
            await db.rollback()
            logger.exception("Could not queue automatic label for scan %s", response.id)
            response.print_error = (
                "Prediction saved, but its label could not be queued. "
                "Check the server log and print status before printing from Scan Logs."
            )
    return response


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


@router.get("/{scan_id}/track", response_model=PublicScanResponse)
async def public_scan_track(scan_id: uuid.UUID, db: DbSession):
    """Public read-only scan summary for QR code tracking — no auth required."""
    scan = (await db.execute(
        select(Scan).where(Scan.id == scan_id).options(
            selectinload(Scan.classification),
            selectinload(Scan.status_logs),
        )
    )).scalar_one_or_none()
    if scan is None:
        raise NotFoundException("Scan")
    classification = scan.classification
    latest = scan.status_logs[-1] if scan.status_logs else None
    now = now_manila()
    return PublicScanResponse(
        id=scan.id,
        date_time=scan.date_time,
        cultivar=classification.cultivar if classification else None,
        ripeness=classification.ripeness if classification else None,
        confidence=classification.confidence if classification else None,
        spoilage_days=classification.spoilage_days if classification else None,
        remaining_days=remaining_shelf_life(
            classification.spoilage_days if classification else None, scan.date_time, now
        ),
        risk_as_of=now,
        shelf_life_window=shelf_life_window(
            classification.spoilage_days if classification else None, scan.date_time, now
        ),
        ripeness_projection=ripeness_projection(
            classification.ripeness if classification else None,
            classification.cultivar if classification else None,
            classification.spoilage_days if classification else None,
            scan.date_time,
            now,
            temperature=classification.temperature if classification else None,
            humidity=classification.humidity if classification else None,
            vpd=classification.vpd if classification else None,
            treatment=classification.treatment if classification else None,
            respect_closed_status=False,
        ),
        finger_count=classification.finger_count if classification else 0,
        temperature=classification.temperature if classification else None,
        humidity=classification.humidity if classification else None,
        vpd=classification.vpd if classification else None,
        treatment=classification.treatment if classification else None,
        source_text=scan.source_text,
        inventory_status=latest.inventory_status if latest else "In Stock",
        flagged=scan.flagged,
        # Anyone with the QR link reads this; capture paths and camera IDs stay staff-only.
        images=[],
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
