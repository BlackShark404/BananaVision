"""Idempotent manual/demo batches and one automatic label per committed prediction."""

import logging
from dataclasses import asdict
from uuid import uuid5

from fastapi import HTTPException
from sqlalchemy import select, update

from app.config import get_settings
from app.core import database
from app.models.print_job import PrintJob
from app.schemas.printing import LabelPrintRequest, PrintJobResponse
from app.services import audit
from app.services.prediction_label import PredictionData
from app.services.printer_service import print_prediction_label
from app.services.runtime_operations import coordinator, run_blocking

logger = logging.getLogger(__name__)


def _labels(job) -> str:
    return (
        f"{job.quantity} label{'' if job.quantity == 1 else 's'} on printer "
        f"{audit.quoted(job.printer_name)}"
    )


def serialize_job(job):
    return PrintJobResponse(
        id=job.id, status=job.status, printer_name=job.printer_name,
        windows_job_id=job.windows_job_id, error=job.error_message,
        attempt_count=job.attempt_count, quantity=job.quantity,
    )


async def create_job(db, scan, user, body, *, demo=False, manual=False, client_ip=None):
    """Queue a label once per request ID. A person's request (``manual``) is audited once."""
    try:
        data = PredictionData.from_scan(scan, demo=demo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    settings = get_settings()
    # ON CONFLICT serializes concurrent delivery of the same deliberate action.
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    inserted = await db.execute(insert(PrintJob).values(
        id=body.request_id, prediction_id=scan.id, owner_id=user.id,
        printer_name=settings.bananavision_printer_name,
        quantity=body.quantity, label_data=asdict(data),
        width_mm=settings.bananavision_label_width_mm,
        height_mm=settings.bananavision_label_height_mm,
        status="QUEUED", claimed=False, attempt_count=0,
    ).on_conflict_do_nothing(index_elements=[PrintJob.id]).returning(PrintJob.id))
    created = inserted.scalar_one_or_none() is not None
    job = (await db.execute(select(PrintJob).where(PrintJob.id == body.request_id))).scalar_one()
    if (job.owner_id != user.id or job.prediction_id != scan.id
            or job.quantity != body.quantity
            or bool(job.label_data.get("demo", False)) != demo):
        raise HTTPException(409, "This print request ID was already used for another action.")
    if created and manual:
        await audit.record(
            db, audit.AuditAction.LABEL_PRINT_REQUESTED,
            f"Print job {job.id} for scan {scan.id}: {_labels(job)}",
            actor=user, ip=client_ip,
        )
    await db.commit()
    return job, created


async def queue_automatic_label(db, scan, user, background_tasks):
    """Called by the trigger route only after the successful pipeline commit."""
    request = LabelPrintRequest(
        request_id=uuid5(scan.id, "bananavision:automatic-label:v1"), quantity=1,
    )
    job, created = await create_job(db, scan, user, request)
    if created:
        background_tasks.add_task(submit_job, job.id)
    return serialize_job(job)


async def retry_job(db, job, expected_attempt, *, actor=None, client_ip=None):
    result = await db.execute(update(PrintJob).where(
        PrintJob.id == job.id, PrintJob.status == "FAILED",
        PrintJob.attempt_count == expected_attempt,
    ).values(status="QUEUED", claimed=False, error_message=None, windows_job_id=None))
    if result.rowcount != 1:
        raise HTTPException(409, "This job has changed. Refresh its print status before retrying.")
    await audit.record(
        db, audit.AuditAction.LABEL_PRINT_RETRIED,
        f"Retried print job {job.id} for scan {job.prediction_id}: {_labels(job)} "
        f"(attempt {expected_attempt + 1})",
        actor=actor, ip=client_ip,
    )
    await db.commit()
    return (await db.execute(select(PrintJob).where(PrintJob.id == job.id)
                            .execution_options(populate_existing=True))).scalar_one()


async def submit_job(job_id):
    """Claim before GDI; never replay uncertain submissions after a process restart."""
    try:
        async with coordinator.operation(), database.async_session_factory() as db:
            claim = await db.execute(update(PrintJob).where(
                PrintJob.id == job_id, PrintJob.status == "QUEUED",
                PrintJob.claimed.is_(False),
            ).values(claimed=True, attempt_count=PrintJob.attempt_count + 1))
            await db.commit()
            if claim.rowcount != 1:
                return
            job = (await db.execute(select(PrintJob).where(PrintJob.id == job_id))).scalar_one()
            try:
                windows_id = await run_blocking(
                    print_prediction_label, job.printer_name,
                    PredictionData(**job.label_data), job.width_mm, job.height_mm,
                    quantity=job.quantity,
                )
                job.status, job.windows_job_id = "SUBMITTED", windows_id
                job.error_message = None
            except Exception as exc:
                job.status = "FAILED"
                job.error_message = f"{type(exc).__name__}: {exc}"
                logger.exception("Label submission failed for job %s", job_id)
            await db.commit()
    except Exception:
        # The saved prediction and receipt survive even when final status cannot be written.
        logger.exception("Could not complete label job %s; inspect the print queue", job_id)
