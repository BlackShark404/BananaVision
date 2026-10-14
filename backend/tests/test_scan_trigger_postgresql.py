"""New scan serialization on real async PostgreSQL; all hardware remains mocked."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import event, func, select
from starlette.requests import Request

from app.api.v1 import scans
from app.core import database
from app.models import PrintJob, Scan, ScanDetection
from app.schemas.scan import ScanTriggerRequest
from app.services import print_jobs, scan_service
from app.services.runtime_operations import StationCoordinator
from app.services.scan_records import serialize_scan
from tests.test_scan_records_postgresql import station as station

pytestmark = pytest.mark.skipif(
    not os.environ.get("BANANAVISION_TEST_DATABASE_URL"), reason="Disposable PostgreSQL required",
)


@pytest.fixture
def mocked_pipeline(monkeypatch):
    captures = [
        SimpleNamespace(camera_id=f"CAM-{i + 1:03}", camera_label=label,
                        frame=None, file_path=None)
        for i, label in enumerate(["Top", "Left", "Right", "Rear"])
    ]
    result = SimpleNamespace(
        cultivar="Lakatan", ripeness="Ripe", confidence=98, finger_count=7,
        detections=[], inference_time_ms=1, auto_flagged=False,
        conflict_detected=False, camera_count=4,
    )

    async def capture_all():
        return captures

    async def send(*_args, **_kwargs):
        pass

    async def config(_db):
        return SimpleNamespace(confidence_threshold=85)

    monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(
        online_cameras=[0, 1, 3, 2], capture_all=capture_all,
        save_captures=lambda frames, _: frames,
    ))
    monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
        detect=lambda _: SimpleNamespace(banana_detected=True),
    ))
    monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(
        predict=lambda _, **kwargs: result,
    ))
    monkeypatch.setattr(scan_service, "fusion_engine", SimpleNamespace(fuse=lambda _: result))
    monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(
        predict=lambda **_: "3-6",
    ))
    monkeypatch.setattr(scan_service, "sensor_reader", SimpleNamespace(latest=None))
    monkeypatch.setattr(scan_service, "get_config", config)
    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", send)
    monkeypatch.setattr(scan_service, "station_lock", asyncio.Lock())
    coordinator = StationCoordinator()
    monkeypatch.setattr(scan_service, "coordinator", coordinator)
    monkeypatch.setattr(print_jobs, "coordinator", coordinator)
    monkeypatch.setattr(scans, "get_settings", lambda: SimpleNamespace(
        bananavision_auto_print=True,
    ))
    monkeypatch.setattr(print_jobs, "get_settings", lambda: SimpleNamespace(
        bananavision_printer_name="Fixture Printer", bananavision_label_width_mm=40,
        bananavision_label_height_mm=30,
    ))
    submit = MagicMock(return_value=713)
    monkeypatch.setattr(print_jobs, "print_prediction_label", submit)
    return submit


@pytest.mark.parametrize("role", ["Admin", "Operator"])
@pytest.mark.parametrize("linked", [True, False])
async def test_fresh_async_trigger_serializes_without_sql_and_prints_once(
    station, mocked_pipeline, monkeypatch, role, linked,
):
    x = station
    user = SimpleNamespace(
        id=x.actors[0], full_name="Fixture Operator", role=SimpleNamespace(name=role),
        operator_profile=SimpleNamespace(id=x.operator),
    )
    captured = []
    async with x.sessions() as db:
        statements = []

        def observe_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        def checked_serialize(scan, current_user):
            event.listen(db.bind.sync_engine, "before_cursor_execute", observe_sql)
            try:
                response = serialize_scan(scan, current_user)
            finally:
                event.remove(db.bind.sync_engine, "before_cursor_execute", observe_sql)
            assert statements == [], "Response serialization attempted implicit SQL"
            captured.append(scan)
            return response

        monkeypatch.setattr(scans, "serialize_scan", checked_serialize)
        tasks = BackgroundTasks()
        response = await scans.trigger_scan(
            ScanTriggerRequest(
                intake_id=x.intake if linked else None, source_text="Fixture Supplier",
            ), db, user, Request({
                "type": "http", "client": ("127.0.0.1", 1), "headers": [],
            }), tasks,
        )
        assert response.cultivar.value == "Lakatan" and response.spoilage_days == "3-6"
        assert response.intake_id == (x.intake if linked else None)
        assert response.intake_provenance == ("linked" if linked else "unlinked")
        assert response.inventory_eligible is True and response.has_notes is False
        assert response.print_error is None and response.print_job.status == "QUEUED"
        assert len(tasks.tasks) == 1
        # Confirm the complete saved graph also remains usable after detachment.
        db.expunge_all()
        assert serialize_scan(captured[0], user).id == response.id

    monkeypatch.setattr(database, "async_session_factory", x.sessions)
    await tasks()
    assert mocked_pipeline.call_count == 1
    async with x.sessions() as db:
        job = await db.get(PrintJob, response.print_job.id)
        assert job.status == "SUBMITTED" and job.windows_job_id == 713
        assert await db.scalar(select(func.count()).select_from(PrintJob)) == 1
        assert await db.scalar(
            select(func.count()).select_from(ScanDetection)
            .where(ScanDetection.scan_id == response.id)
        ) == 4


async def test_unknown_requested_intake_cannot_be_silently_saved_as_unlinked(
    station, mocked_pipeline,
):
    x = station
    async with x.sessions() as db:
        with pytest.raises(HTTPException) as error:
            await scan_service.execute_scan_pipeline(
                db=db, operator_id=x.operator, account_id=x.actors[0],
                operator_name="Fixture Operator", intake_id=uuid4(),
            )
        assert error.value.status_code == 404
        assert await db.scalar(select(func.count()).select_from(Scan)) == 1
        assert await db.scalar(select(func.count()).select_from(PrintJob)) == 0
    assert mocked_pipeline.call_count == 0
