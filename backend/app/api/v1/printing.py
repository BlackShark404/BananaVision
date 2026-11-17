"""Manual printing of authorized, already-saved predictions."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.http import get_client_ip
from app.models.print_job import PrintJob
from app.schemas.printing import (
    LabelPreviewResponse,
    LabelPrintRequest,
    PrintJobResponse,
    RetryPrintRequest,
)
from app.services import print_jobs
from app.services.prediction_label import PredictionData
from app.services.runtime_operations import run_blocking
from app.services.scan_records import load_authorized_scan, scan_scope
from app.services.printer_service import PrinterServiceError, list_printers

router = APIRouter(tags=["Printing"])


def label_preview(data):
    settings = get_settings()
    return LabelPreviewResponse(
        payload=data.payload(), qr_data=data.qr_data(), panel=data.panel(),
        printer_name=settings.bananavision_printer_name, max_quantity=10,
        width_mm=settings.bananavision_label_width_mm,
        height_mm=settings.bananavision_label_height_mm,
    )


@router.get("/printers")
async def printers(user: CurrentUser):
    scan_scope(user)
    try:
        return await run_blocking(list_printers)
    except PrinterServiceError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/scans/{scan_id}/label")
async def label(scan_id: UUID, db: DbSession, user: CurrentUser):
    scan = await load_authorized_scan(db, scan_id, user)
    try:
        data = PredictionData.from_scan(scan)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return label_preview(data)


@router.post("/scans/{scan_id}/print", response_model=PrintJobResponse)
async def print_saved_scan(
    scan_id: UUID, body: LabelPrintRequest, db: DbSession,
    user: CurrentUser, background_tasks: BackgroundTasks, request: Request,
):
    scan = await load_authorized_scan(db, scan_id, user)
    job, created = await print_jobs.create_job(
        db, scan, user, body, manual=True, client_ip=get_client_ip(request),
    )
    if created:
        background_tasks.add_task(print_jobs.submit_job, job.id)
    return print_jobs.serialize_job(job)


async def authorized_job(scan_id, job_id, db, user):
    await load_authorized_scan(db, scan_id, user)
    job = (await db.execute(select(PrintJob).where(
        PrintJob.id == job_id, PrintJob.prediction_id == scan_id,
    ))).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Print job not found")
    return job


@router.get("/scans/{scan_id}/print-jobs/{job_id}", response_model=PrintJobResponse)
async def print_status(scan_id: UUID, job_id: UUID, db: DbSession, user: CurrentUser):
    return print_jobs.serialize_job(await authorized_job(scan_id, job_id, db, user))


@router.post("/scans/{scan_id}/print-jobs/{job_id}/retry", response_model=PrintJobResponse)
async def retry_print(
    scan_id: UUID, job_id: UUID, body: RetryPrintRequest, db: DbSession,
    user: CurrentUser, background_tasks: BackgroundTasks, request: Request,
):
    job = await authorized_job(scan_id, job_id, db, user)
    job = await print_jobs.retry_job(
        db, job, body.expected_attempt, actor=user, client_ip=get_client_ip(request),
    )
    background_tasks.add_task(print_jobs.submit_job, job.id)
    return print_jobs.serialize_job(job)
