from __future__ import annotations

import platform
from contextlib import suppress
from typing import Any

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.schemas.printing import PrinterInfo
from app.services.prediction_label import PredictionData


class PrinterServiceError(RuntimeError):
    """An actionable Windows printing error."""


STATUS_FLAGS = {
    0x00000001: "PAUSED",
    0x00000002: "ERROR",
    0x00000004: "PENDING DELETION",
    0x00000008: "PAPER JAM",
    0x00000010: "PAPER OUT",
    0x00000020: "MANUAL FEED",
    0x00000040: "PAPER PROBLEM",
    0x00000080: "OFFLINE",
    0x00000200: "BUSY",
    0x00000400: "PRINTING",
    0x00000800: "OUTPUT BIN FULL",
    0x00001000: "NOT AVAILABLE",
    0x00002000: "WAITING",
    0x00004000: "PROCESSING",
    0x00008000: "INITIALIZING",
    0x00010000: "WARMING UP",
    0x00020000: "TONER LOW",
    0x00040000: "NO TONER",
    0x00080000: "PAGE PUNT",
    0x00100000: "USER INTERVENTION",
    0x00200000: "OUT OF MEMORY",
    0x00400000: "DOOR OPEN",
    0x00800000: "SERVER UNKNOWN",
    0x01000000: "POWER SAVE",
}

NOT_READY_FLAGS = (
    0x00000001
    | 0x00000002
    | 0x00000004
    | 0x00000008
    | 0x00000010
    | 0x00000020
    | 0x00000040
    | 0x00000080
    | 0x00000800
    | 0x00001000
    | 0x00100000
    | 0x00040000
    | 0x00080000
    | 0x00200000
    | 0x00400000
    | 0x00800000
)


def _require_windows_modules() -> tuple[Any, Any, Any, Any, Any]:
    if platform.system() != "Windows":
        raise PrinterServiceError("Printing requires Windows and the official printer driver.")
    try:
        import win32con
        import win32gui
        import win32print
        import win32ui
        from win32.lib import win32con as lib_win32con
    except ImportError as exc:
        raise PrinterServiceError(
            "pywin32 is not installed. Run: pip install -r requirements.txt"
        ) from exc
    return win32print, win32ui, win32gui, win32con, lib_win32con


def _status_text(status: int) -> str:
    if status == 0:
        return "READY"
    return ", ".join(label for flag, label in STATUS_FLAGS.items() if status & flag) or "UNKNOWN"


def _printer_info(name: str, data: dict[str, Any] | None) -> PrinterInfo:
    data = data or {}
    status_value = int(data.get("Status") or 0)
    port_name = str(data.get("pPortName") or "")
    combined = f"{name} {data.get('pDriverName') or ''}".lower()
    ports = [port.strip().upper() for port in port_name.split(",")]
    return PrinterInfo(
        name=name,
        driver_name=data.get("pDriverName") or None,
        port_name=port_name or None,
        status=_status_text(status_value) if data else "UNAVAILABLE",
        is_ready=bool(data) and (status_value & NOT_READY_FLAGS) == 0,
        is_grozziie="grozziie" in combined or "tp870" in combined,
        is_usb=any(port.startswith("USB") for port in ports),
    )


def list_printers() -> list[PrinterInfo]:
    win32print, _, _, _, _ = _require_windows_modules()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    try:
        entries = win32print.EnumPrinters(flags, None, 4)
    except Exception as exc:
        raise PrinterServiceError(f"Windows could not enumerate printers: {exc}") from exc

    printers: list[PrinterInfo] = []
    seen: set[str] = set()
    for entry in entries:
        name = str(entry.get("pPrinterName") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        handle = None
        details = None
        try:
            handle = win32print.OpenPrinter(name)
            details = win32print.GetPrinter(handle, 2)
        except Exception:
            # The name is still useful even if Windows denies detailed status access.
            pass
        finally:
            if handle is not None:
                win32print.ClosePrinter(handle)
        printers.append(_printer_info(name, details))

    return sorted(printers, key=lambda item: (not item.is_grozziie, item.name.casefold()))


def _get_installed_printer(printer_name: str) -> PrinterInfo:
    match = next(
        (printer for printer in list_printers()
         if printer.name.casefold() == printer_name.casefold()),
        None,
    )
    if match is None:
        raise PrinterServiceError(
            f'Printer "{printer_name}" is not installed. Check USB and the official driver.'
        )
    if not match.is_ready:
        detail = (
            "Windows reports a driver/spooler error without a specific paper or connection status. "
            if match.status == "ERROR" else ""
        )
        raise PrinterServiceError(
            f'Printer "{match.name}" reports {match.status}. '
            f"{detail}No new label document was submitted. "
            "Check power, USB, labels, and the Windows print queue. "
            "Confirm a Windows test page works before retrying this label."
        )
    return match


def _configured_devmode(
    win32print: Any, win32con: Any, printer_name: str, width_mm: float, height_mm: float,
) -> Any:
    handle = None
    try:
        handle = win32print.OpenPrinter(printer_name)
        details = win32print.GetPrinter(handle, 2)
        devmode = details.get("pDevMode")
        if devmode is None:
            raise PrinterServiceError(
                "The driver did not provide settings (DEVMODE). Reinstall the official driver."
            )

        dm_paperwidth = getattr(win32con, "DM_PAPERWIDTH", 0x00000008)
        dm_paperlength = getattr(win32con, "DM_PAPERLENGTH", 0x00000004)
        dm_papersize = getattr(win32con, "DM_PAPERSIZE", 0x00000002)
        dm_orientation = getattr(win32con, "DM_ORIENTATION", 0x00000001)
        devmode.Fields |= dm_paperwidth | dm_paperlength | dm_papersize | dm_orientation
        devmode.PaperSize = getattr(win32con, "DMPAPER_USER", 256)
        # Windows DEVMODE custom paper dimensions use tenths of a millimetre.
        devmode.PaperWidth = round(width_mm * 10)
        devmode.PaperLength = round(height_mm * 10)
        devmode.Orientation = getattr(win32con, "DMORIENT_PORTRAIT", 1)
        devmode.Fields |= getattr(win32con, "DM_COPIES", 0x00000100)
        devmode.Copies = 1  # Quantity is implemented as pages, never multiplied by driver copies.

        # Ask the official driver to validate/merge the requested custom settings.
        dm_in_buffer = getattr(win32con, "DM_IN_BUFFER", 8)
        dm_out_buffer = getattr(win32con, "DM_OUT_BUFFER", 2)
        result = win32print.DocumentProperties(
            None,
            handle,
            printer_name,
            devmode,
            devmode,
            dm_in_buffer | dm_out_buffer,
        )
        if isinstance(result, int) and result < 0:
            raise PrinterServiceError("The installed driver rejected the custom label dimensions.")
        if devmode.Copies != 1:
            raise PrinterServiceError("Set Windows driver copies to one before printing labels.")
        actual_width_mm = float(devmode.PaperWidth) / 10
        actual_height_mm = float(devmode.PaperLength) / 10
        if abs(actual_width_mm - width_mm) > 1 or abs(actual_height_mm - height_mm) > 1:
            raise PrinterServiceError(
                "The driver replaced the requested "
                f"{width_mm:g} x {height_mm:g} mm label with "
                f"{actual_width_mm:g} x {actual_height_mm:g} mm. "
                "Select the correct stock in Windows Printing preferences, then retry."
            )
        return devmode
    except PrinterServiceError:
        raise
    except Exception as exc:
        raise PrinterServiceError(f"The Windows driver rejected the label size: {exc}") from exc
    finally:
        if handle is not None:
            win32print.ClosePrinter(handle)


def _qr_matrix(prediction: PredictionData) -> list[list[bool]]:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(prediction.payload())
    qr.make(fit=True)
    return qr.get_matrix()


def _draw_label(dc: Any, win32ui: Any, win32con: Any, prediction: PredictionData) -> None:
    page_width = dc.GetDeviceCaps(getattr(win32con, "HORZRES", 8))
    page_height = dc.GetDeviceCaps(getattr(win32con, "VERTRES", 10))
    if page_width <= 0 or page_height <= 0:
        raise PrinterServiceError("The driver returned an invalid printable label area.")

    matrix = _qr_matrix(prediction)
    dc.FillSolidRect((0, 0, page_width, page_height), 0xFFFFFF)
    module_count = len(matrix)
    margin = max(2, round(min(page_width, page_height) * 0.025))
    gap = max(4, round(page_width * 0.018))

    # A 40 x 30 mm label is landscape: reserve about one third for a short
    # human-readable identifier and use the full printable height for the QR.
    has_text_panel = page_width >= round(page_height * 1.15)
    text_width = round(page_width * 0.31) if has_text_panel else 0
    max_qr_width = page_width - (2 * margin) - text_width - (gap if has_text_panel else 0)
    max_qr_size = min(page_height - (2 * margin), max_qr_width)
    module_px = max_qr_size // module_count
    if module_px < 2:
        raise PrinterServiceError(
            "Printable area too small for a scannable QR. Check the 40 x 30 mm paper size."
        )

    qr_size = module_px * module_count
    qr_x = margin if has_text_panel else max(margin, (page_width - qr_size) // 2)
    qr_y = max(margin, (page_height - qr_size) // 2)

    # Draw consecutive black modules as one rectangle to keep GDI calls small.
    for row_index, row in enumerate(matrix):
        run_start: int | None = None
        for column_index, is_black in enumerate([*row, False]):
            if is_black and run_start is None:
                run_start = column_index
            elif not is_black and run_start is not None:
                dc.FillSolidRect(
                    (
                        qr_x + (run_start * module_px),
                        qr_y + (row_index * module_px),
                        qr_x + (column_index * module_px),
                        qr_y + ((row_index + 1) * module_px),
                    ),
                    0x000000,
                )
                run_start = None

    if not has_text_panel:
        return

    panel_left = qr_x + qr_size + gap
    panel_right = page_width - margin
    panel_width = panel_right - panel_left
    labels = prediction.panel()
    row_height = max(8, (page_height - (2 * margin)) // len(labels))
    font_px = max(7, min(round(row_height * 0.48), max(7, panel_width // 7)))
    font = win32ui.CreateFont({"name": "Arial", "height": -font_px, "weight": 700})
    old_font = dc.SelectObject(font)
    try:
        dc.SetBkMode(getattr(win32con, "TRANSPARENT", 1))
        dc.SetTextColor(0x000000)
        flags = (
            getattr(win32con, "DT_CENTER", 1)
            | getattr(win32con, "DT_SINGLELINE", 0x20)
            | getattr(win32con, "DT_VCENTER", 4)
        )
        for index, label in enumerate(labels):
            top = margin + (index * row_height)
            dc.DrawText(label, (panel_left, top, panel_right, top + row_height), flags)
    finally:
        dc.SelectObject(old_font)
        del font


def print_prediction_label(
    printer_name: str, prediction: PredictionData,
    width_mm: float = 40, height_mm: float = 30,
    *, quantity: int = 1,
) -> int | None:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
        raise PrinterServiceError("Choose between 1 and 10 labels.")
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise PrinterServiceError("Physical printing is disabled in automated tests.")
    win32print, win32ui, win32gui, win32con, lib_win32con = _require_windows_modules()
    printer = _get_installed_printer(printer_name)
    devmode = _configured_devmode(win32print, lib_win32con, printer.name, width_mm, height_mm)

    hdc = None
    dc = None
    document_started = False
    try:
        # Create the GDI printer context with the official driver's validated DEVMODE.
        # This applies label dimensions without raw/ESC-POS commands.
        hdc = win32gui.CreateDC("WINSPOOL", printer.name, devmode)
        dc = win32ui.CreateDCFromHandle(hdc)
        job_id = dc.StartDoc(f"BananaVision {prediction.prediction_id}")
        document_started = True
        for _ in range(quantity):
            dc.StartPage()
            _draw_label(dc, win32ui, win32con, prediction)
            dc.EndPage()
        dc.EndDoc()
        document_started = False
        return int(job_id) if job_id else None
    except PrinterServiceError:
        if document_started and dc is not None:
            with suppress(Exception):
                dc.AbortDoc()
        raise
    except Exception as exc:
        if document_started and dc is not None:
            with suppress(Exception):
                dc.AbortDoc()
        hint = " Check the official Grozziie driver and its label size setting."
        raise PrinterServiceError(f"Windows could not submit the print job: {exc}.{hint}") from exc
    finally:
        if dc is not None:
            dc.DeleteDC()
