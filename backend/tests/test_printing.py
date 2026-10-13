"""Isolated label routes and fake GDI: never create a physical print job."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import printing
from app.models import PrintJob, Scan
from app.services import print_jobs, windows_printer
from app.services.prediction_label import PredictionData
from tests.test_time_and_writes import application as application


@pytest.fixture
def station(application, monkeypatch):
    application.app.include_router(printing.router, prefix="/api/v1")
    submit = MagicMock(return_value=712)
    monkeypatch.setattr(print_jobs, "print_prediction_label", submit)
    application.submit = submit
    return application


def test_saved_values_preview_and_idempotent_quantity(station):
    app = station
    url = f"/api/v1/scans/{app.ids.scan}"
    preview = app.client.get(url + "/label")
    assert preview.status_code == 200
    payload = preview.json()["payload"]
    assert f"ID={app.ids.scan}" in payload
    assert "RIPENESS=Ripe" in payload and "SPOILAGE_DAYS=3" in payload
    assert "CONFIDENCE=90%" in payload and "TEMP=" not in payload
    assert "HUMIDITY=" not in payload
    body = {"request_id": str(uuid4()), "quantity": 3}
    first = app.client.post(url + "/print", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "QUEUED"
    again = app.client.post(url + "/print", json=body)
    assert again.json()["status"] == "SUBMITTED"
    assert again.json()["windows_job_id"] == 712
    assert again.json()["attempt_count"] == 1
    assert app.submit.call_count == 1 and app.submit.call_args.kwargs == {"quantity": 3}
    assert app.submit.call_args.args[1].payload() == payload
    assert app.client.post(url + "/print", json={**body, "quantity": 2}).status_code == 409
    asyncio.run(print_jobs.submit_job(uuid4()))
    asyncio.run(print_jobs.submit_job(UUID(body["request_id"])))
    assert app.submit.call_count == 1
    with Session(app.engine) as db:
        assert db.scalar(select(func.count()).select_from(PrintJob)) == 1
        assert db.scalar(select(func.count()).select_from(Scan)) == 1


def test_offline_preserves_scan_and_retry_reuses_job(station):
    app = station
    app.submit.side_effect = windows_printer.PrinterServiceError("TP870 S is OFFLINE")
    url = f"/api/v1/scans/{app.ids.scan}"
    job_id = str(uuid4())
    assert app.client.post(url + "/print", json={"request_id": job_id}).status_code == 200
    status_url = url + f"/print-jobs/{job_id}"
    failed = app.client.get(status_url).json()
    assert failed["status"] == "FAILED" and "OFFLINE" in failed["error"]
    assert app.client.get(url).status_code == 200
    app.submit.side_effect = None
    retried = app.client.post(status_url + "/retry", json={"expected_attempt": 1})
    assert retried.status_code == 200, retried.text
    submitted = app.client.get(status_url).json()
    assert submitted["id"] == job_id and submitted["status"] == "SUBMITTED"
    assert submitted["attempt_count"] == 2 and submitted["error"] is None
    assert app.client.post(status_url + "/retry", json={"expected_attempt": 1}).status_code == 409
    assert app.submit.call_count == 2


@pytest.mark.parametrize("quantity", [0, 11, -1, 1.5, True, "2"])
def test_quantity_boundaries(station, quantity):
    response = station.client.post(f"/api/v1/scans/{station.ids.scan}/print", json={
        "request_id": str(uuid4()), "quantity": quantity,
    })
    assert response.status_code == 422
    station.submit.assert_not_called()


def test_authorization_missing_scan_and_commit_failure(station):
    app = station
    url = f"/api/v1/scans/{app.ids.scan}"
    body = {"request_id": str(uuid4()), "quantity": 1}
    assert app.client.post(f"/api/v1/scans/{uuid4()}/print", json=body).status_code == 404
    app.state.fail_commit = True
    assert app.client.post(url + "/print", json=body).status_code == 500
    app.state.fail_commit = False
    app.submit.assert_not_called()
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role=SimpleNamespace(name="Operator"),
    )
    assert app.client.get(url + "/label").status_code == 403
    assert app.client.post(url + "/print", json=body).status_code == 403
    assert app.client.get(url + f"/print-jobs/{uuid4()}").status_code == 403
    app.submit.assert_not_called()


def prediction():
    return PredictionData(str(uuid4()), "Semi Ripe", "3-5", 95.25, 28, 75)


def test_qr_quiet_zone_and_whole_pixel_layout():
    data = prediction()
    assert "TEMP=28C\nHUMIDITY=75%\nTEST=LIVE" in data.payload()
    matrix = windows_printer._qr_matrix(data)
    assert all(not any(row) for row in matrix[:4] + matrix[-4:])
    assert all(not any(row[:4] + row[-4:]) for row in matrix)
    dc = MagicMock()
    dc.GetDeviceCaps.side_effect = lambda cap: 320 if cap == 8 else 240
    font = object()  # Deliberately has no DeleteObject method.
    ui = SimpleNamespace(CreateFont=lambda _: font)
    windows_printer._draw_label(dc, ui, SimpleNamespace(), data)
    for call in dc.FillSolidRect.call_args_list:
        left, top, right, bottom = call.args[0]
        assert all(isinstance(x, int) for x in (left, top, right, bottom))
        assert 0 <= left < right <= 320 and 0 <= top < bottom <= 240
    assert dc.SelectObject.call_count == 2
    assert [call.args[0] for call in dc.DrawText.call_args_list] == list(data.panel())


def test_gdi_three_argument_createdc_quantity_and_abort(monkeypatch):
    # Only remove the physical-print guard AFTER substituting every Windows module.
    printer = SimpleNamespace(name="TP870 S")
    gui, ui, dc = MagicMock(), MagicMock(), MagicMock()
    ui.CreateDCFromHandle.return_value = dc
    dc.StartDoc.return_value = 42
    modules = (MagicMock(), ui, gui, SimpleNamespace(), SimpleNamespace())
    monkeypatch.setattr(windows_printer, "_require_windows_modules", lambda: modules)
    monkeypatch.setattr(windows_printer, "_get_installed_printer", lambda _: printer)
    devmode = object()
    monkeypatch.setattr(windows_printer, "_configured_devmode", lambda *args: devmode)
    draw = MagicMock()
    monkeypatch.setattr(windows_printer, "_draw_label", draw)
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert windows_printer.print_prediction_label("TP870 S", prediction(), quantity=3) == 42
    gui.CreateDC.assert_called_once_with("WINSPOOL", "TP870 S", devmode)
    assert dc.StartPage.call_count == dc.EndPage.call_count == draw.call_count == 3
    dc.EndDoc.assert_called_once()
    dc.DeleteDC.assert_called_once()
    draw.side_effect = RuntimeError("GDI failed")
    with pytest.raises(windows_printer.PrinterServiceError, match="GDI failed"):
        windows_printer.print_prediction_label("TP870 S", prediction())
    dc.AbortDoc.assert_called_once()


def test_automated_tests_cannot_load_real_windows_driver():
    with pytest.raises(windows_printer.PrinterServiceError, match="disabled in automated tests"):
        windows_printer.print_prediction_label("TP870 S", prediction())


def test_inaccessible_printer_is_not_reported_ready():
    assert not windows_printer._printer_info("TP870 S", None).is_ready
    assert not windows_printer._printer_info("TP870 S", {"Status": 0x80}).is_ready


def test_driver_dimensions_and_copy_count_are_validated():
    spooler = MagicMock()
    devmode = SimpleNamespace(Fields=0)
    spooler.GetPrinter.return_value = {"pDevMode": devmode}
    spooler.DocumentProperties.return_value = 1
    result = windows_printer._configured_devmode(spooler, SimpleNamespace(), "TP870 S", 40, 30)
    assert result is devmode
    assert (devmode.PaperWidth, devmode.PaperLength, devmode.Copies) == (400, 300, 1)
    assert devmode.Fields & 0x100
    spooler.ClosePrinter.assert_called_once()

    def wrong_paper(*_args):
        devmode.PaperWidth = 800
        return 1

    spooler.DocumentProperties.side_effect = wrong_paper
    with pytest.raises(windows_printer.PrinterServiceError, match="driver replaced"):
        windows_printer._configured_devmode(spooler, SimpleNamespace(), "TP870 S", 40, 30)


def test_missing_and_offline_printers_are_rejected(monkeypatch):
    monkeypatch.setattr(windows_printer, "list_printers", lambda: [])
    with pytest.raises(windows_printer.PrinterServiceError, match="not installed"):
        windows_printer._get_installed_printer("TP870 S")
    monkeypatch.setattr(windows_printer, "list_printers", lambda: [
        windows_printer._printer_info("TP870 S", {"Status": 0x80}),
    ])
    with pytest.raises(windows_printer.PrinterServiceError, match="OFFLINE"):
        windows_printer._get_installed_printer("TP870 S")
