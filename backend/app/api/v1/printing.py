"""Manual printing of authorized, already-saved predictions."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models.print_job import PrintJob
from app.schemas.enums import RipenessEnum
from app.schemas.printing import (
    KioskDemoRequest,
    LabelPreviewResponse,
    LabelPrintRequest,
    PrintJobResponse,
    RetryPrintRequest,
)
from app.schemas.scan import KioskDemoResponse
from app.services import print_jobs
from app.services.prediction_label import PredictionData
from app.services.runtime_operations import run_blocking
from app.services.scan_records import load_authorized_scan, scan_scope, serialize_detail
from app.services.windows_printer import PrinterServiceError, list_printers

router = APIRouter(tags=["Printing"])


def label_preview(data):
    settings = get_settings()
    return LabelPreviewResponse(
        payload=data.payload(), panel=data.panel(),
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


@router.post("/scans/{scan_id}/kiosk-demo", response_model=KioskDemoResponse)
async def kiosk_demo(
    scan_id: UUID, body: KioskDemoRequest, db: DbSession,
    user: CurrentUser, background_tasks: BackgroundTasks,
):
    """Replay a saved prediction and print one DEMO label; never create a scan."""
    scan = await load_authorized_scan(db, scan_id, user)
    detail = await serialize_detail(db, scan, user)
    job, created = await print_jobs.create_job(
        db, scan, user, LabelPrintRequest(request_id=body.request_id, quantity=1), demo=True,
    )
    if created:
        background_tasks.add_task(print_jobs.submit_job, job.id)
    # Replayed requests must display the same values as their immutable printed label.
    data = PredictionData(**job.label_data)
    detail = detail.model_copy(update={
        "ripeness": RipenessEnum(data.ripeness), "confidence": data.confidence,
        "spoilage_days": data.spoilage_days,
        "temperature": data.temperature, "humidity": data.humidity,
    })
    return KioskDemoResponse(
        scan=detail, label=label_preview(data),
        print_job=print_jobs.serialize_job(job),
    )


@router.post("/scans/{scan_id}/print", response_model=PrintJobResponse)
async def print_saved_scan(
    scan_id: UUID, body: LabelPrintRequest, db: DbSession,
    user: CurrentUser, background_tasks: BackgroundTasks,
):
    scan = await load_authorized_scan(db, scan_id, user)
    job, created = await print_jobs.create_job(db, scan, user, body)
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
    user: CurrentUser, background_tasks: BackgroundTasks,
):
    job = await authorized_job(scan_id, job_id, db, user)
    job = await print_jobs.retry_job(db, job, body.expected_attempt)
    background_tasks.add_task(print_jobs.submit_job, job.id)
    return print_jobs.serialize_job(job)
