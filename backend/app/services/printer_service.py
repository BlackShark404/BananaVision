"""Platform-aware printer dispatch: Windows GDI or macOS CUPS."""

from __future__ import annotations

import platform

from app.schemas.printing import PrinterInfo
from app.services.prediction_label import PredictionData


class PrinterServiceError(RuntimeError):
    """An actionable printing error (platform-independent)."""


def _backend():
    """Return the platform-specific printer module."""
    system = platform.system()
    if system == "Windows":
        from app.services import windows_printer
        return windows_printer
    if system == "Darwin":
        from app.services import cups_printer
        return cups_printer
    raise PrinterServiceError(
        f"Printing is not supported on {system}. "
        "BananaVision requires Windows (GDI) or macOS (CUPS)."
    )


def list_printers() -> list[PrinterInfo]:
    """Enumerate installed printers using the platform-specific backend."""
    return _backend().list_printers()


def print_prediction_label(
    printer_name: str, prediction: PredictionData,
    width_mm: float = 40, height_mm: float = 30,
    *, quantity: int = 1,
) -> int | None:
    """Submit a prediction label to the named printer.

    On Windows, uses GDI via pywin32.
    On macOS, renders to PNG via Pillow and submits via ``lp``.

    Returns a job ID (Windows spooler or CUPS) on success, or None.
    """
    return _backend().print_prediction_label(
        printer_name, prediction, width_mm, height_mm, quantity=quantity,
    )
