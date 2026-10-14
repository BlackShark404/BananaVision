"""Windows readiness gates use fake queues and never submit physical documents."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services import windows_printer
from app.services.prediction_label import PredictionData


@pytest.fixture
def printer_queue(monkeypatch):
    spooler, ui, gui = MagicMock(), MagicMock(), MagicMock()
    spooler.EnumPrinters.return_value = [{'pPrinterName': 'TP870 S'}]
    spooler.GetPrinter.return_value = {
        'Status': 0, 'pDriverName': 'Grozziie TP870 S', 'pPortName': 'USB001',
    }
    modules = (spooler, ui, gui, SimpleNamespace(), SimpleNamespace())
    monkeypatch.setattr(windows_printer, '_require_windows_modules', lambda: modules)
    return SimpleNamespace(spooler=spooler, ui=ui, gui=gui)


@pytest.mark.parametrize('status, label', [
    (0x00000002, 'ERROR'), (0x00000001, 'PAUSED'),
    (0x00000008, 'PAPER JAM'), (0x00000010, 'PAPER OUT'),
    (0x00000040, 'PAPER PROBLEM'), (0x00000080, 'OFFLINE'),
    (0x00100000, 'USER INTERVENTION'), (0x00400000, 'DOOR OPEN'),
    (0x00000082, 'ERROR, OFFLINE'),
])
def test_driver_faults_stop_before_gdi_document_submission(
    printer_queue, monkeypatch, status, label,
):
    printer_queue.spooler.GetPrinter.return_value['Status'] = status
    # Every Windows module is substituted before removing the physical-print guard.
    monkeypatch.delenv('PYTEST_CURRENT_TEST')
    prediction = PredictionData(str(uuid4()), 'Ripe', '3', 90, None, None)
    with pytest.raises(windows_printer.PrinterServiceError, match=label):
        windows_printer.print_prediction_label('TP870 S', prediction)
    printer_queue.gui.CreateDC.assert_not_called()
    printer_queue.ui.CreateDCFromHandle.assert_not_called()
    printer_queue.spooler.DocumentProperties.assert_not_called()
    printer_queue.spooler.ClosePrinter.assert_called_once()


def test_generic_error_explains_windows_fault_and_recovery_step(printer_queue):
    printer_queue.spooler.GetPrinter.return_value['Status'] = 0x00000002
    with pytest.raises(windows_printer.PrinterServiceError) as error:
        windows_printer._get_installed_printer('TP870 S')
    detail = str(error.value)
    assert 'driver/spooler' in detail
    assert 'No new label document was submitted' in detail
    assert 'Windows test page' in detail
    assert 'retry' in detail.lower()
    assert not windows_printer.list_printers()[0].is_ready


@pytest.mark.parametrize('status', [0, 0x00000200, 0x00000400, 0x00004000])
def test_healthy_or_busy_queue_remains_available_for_submission(printer_queue, status):
    printer_queue.spooler.GetPrinter.return_value['Status'] = status
    assert windows_printer._get_installed_printer('TP870 S').is_ready
