"""Real concurrent claims on a disposable PostgreSQL schema; GDI remains mocked."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import func, select

from app.core import database
from app.models import PrintJob, Scan, ScanClassification
from app.schemas.printing import LabelPrintRequest
from app.services import print_jobs
from tests.test_scan_records_postgresql import station as station

pytestmark = pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required",
)


async def test_concurrent_manual_delivery_and_workers_print_once(station, monkeypatch):
    x = station
    async with x.sessions() as db:
        db.add(ScanClassification(
            scan_id=x.scan, cultivar="Lakatan", ripeness="Ripe", confidence=95,
            spoilage_days="3-5", finger_count=7,
        ))
        await db.commit()
    body = LabelPrintRequest(request_id=uuid4(), quantity=4)

    async def enqueue():
        async with x.sessions() as db:
            scan = await db.get(Scan, x.scan)
            job, created = await print_jobs.create_job(
                db, scan, SimpleNamespace(id=x.actors[0]), body,
            )
            return job.id, created

    results = await asyncio.gather(enqueue(), enqueue(), enqueue())
    assert sum(created for _, created in results) == 1
    submit = MagicMock(return_value=456)
    monkeypatch.setattr(print_jobs, "print_prediction_label", submit)
    monkeypatch.setattr(database, "async_session_factory", x.sessions)
    await asyncio.gather(*(print_jobs.submit_job(body.request_id) for _ in range(3)))
    assert submit.call_count == 1 and submit.call_args.kwargs == {"quantity": 4}
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PrintJob)) == 1
        job = await db.get(PrintJob, body.request_id)
        assert job.status == "SUBMITTED" and job.windows_job_id == 456
        assert job.attempt_count == 1


async def test_automatic_slot_is_unique_under_concurrent_requests(station):
    x = station
    async with x.sessions() as db:
        db.add(ScanClassification(
            scan_id=x.scan, cultivar="Lakatan", ripeness="Ripe", confidence=95,
            spoilage_days="3-5", finger_count=7,
        ))
        await db.commit()

    async def enqueue():
        async with x.sessions() as db:
            scan = await db.get(Scan, x.scan)
            tasks = BackgroundTasks()
            job = await print_jobs.queue_automatic_label(
                db, scan, SimpleNamespace(id=x.actors[0]), tasks,
            )
            return job.id, len(tasks.tasks)

    results = await asyncio.gather(enqueue(), enqueue(), enqueue())
    assert len({job_id for job_id, _ in results}) == 1
    assert sum(task_count for _, task_count in results) == 1
