"""macOS CUPS label printing via Pillow rendering and `lp` submission."""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.schemas.printing import PrinterInfo
from app.services.prediction_label import PredictionData

logger = logging.getLogger(__name__)


class PrinterServiceError(RuntimeError):
    """An actionable CUPS printing error."""


# ── CUPS status helpers ──────────────────────────────────────────────────────

_NOT_READY_KEYWORDS = frozenset({
    "disabled", "paused", "stopped", "offline", "error",
    "not-accepting-jobs", "media-needed", "toner-empty",
    "door-open", "jammed", "cups-reject",
})


def _require_cups() -> None:
    if platform.system() != "Darwin":
        raise PrinterServiceError("CUPS printing is only available on macOS.")
    if shutil.which("lpstat") is None:
        raise PrinterServiceError("CUPS tools (lpstat/lp) are not installed.")


def _cups_status_text(raw: str) -> str:
    """Normalize the lpstat status line into a short label."""
    lower = raw.lower()
    if "idle" in lower:
        return "READY"
    if "printing" in lower:
        return "PRINTING"
    for keyword in _NOT_READY_KEYWORDS:
        if keyword in lower:
            return keyword.upper().replace("-", " ")
    return raw.strip() or "UNKNOWN"


def _is_ready(raw: str) -> bool:
    lower = raw.lower()
    return not any(kw in lower for kw in _NOT_READY_KEYWORDS)


def _is_grozziie(name: str, info: str) -> bool:
    combined = f"{name} {info}".lower()
    return "grozziie" in combined or "tp870" in combined


def list_printers() -> list[PrinterInfo]:
    """Enumerate installed CUPS printers via lpstat -p -l."""
    _require_cups()
    try:
        result = subprocess.run(
            ["lpstat", "-p", "-l"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        raise PrinterServiceError(f"Could not enumerate CUPS printers: {exc}") from exc

    printers: list[PrinterInfo] = []
    # lpstat -p output: "printer NAME is idle.  enabled since ..."
    # Each printer entry may span multiple lines; parse the printer header lines.
    current_name = ""
    current_status = ""
    for line in result.stdout.splitlines():
        match = re.match(r"^printer\s+(\S+)\s+(.*)", line)
        if match:
            if current_name:
                printers.append(_build_info(current_name, current_status))
            current_name = match.group(1)
            current_status = match.group(2)
        elif current_name and line.strip():
            # Continuation line with additional status info.
            current_status += " " + line.strip()
    if current_name:
        printers.append(_build_info(current_name, current_status))

    return sorted(printers, key=lambda p: (not p.is_grozziie, p.name.casefold()))


def _build_info(name: str, raw_status: str) -> PrinterInfo:
    return PrinterInfo(
        name=name,
        driver_name=None,  # CUPS does not expose the driver name in lpstat -p.
        port_name=None,
        status=_cups_status_text(raw_status),
        is_ready=_is_ready(raw_status),
        is_grozziie=_is_grozziie(name, raw_status),
        is_usb="usb" in raw_status.lower(),
    )


def _get_installed_printer(printer_name: str) -> PrinterInfo:
    """Find the named CUPS queue; raise if absent or not ready."""
    match = next(
        (p for p in list_printers()
         if p.name.casefold() == printer_name.casefold()),
        None,
    )
    if match is None:
        raise PrinterServiceError(
            f'Printer "{printer_name}" is not installed. '
            "Check USB connection and run `lpstat -p` to verify the queue name."
        )
    if not match.is_ready:
        raise PrinterServiceError(
            f'Printer "{match.name}" reports {match.status}. '
            "No label was submitted. Check power, USB, labels, and the CUPS queue. "
            "Confirm a CUPS test page works before retrying this label."
        )
    return match


# ── Label rendering with Pillow ──────────────────────────────────────────────

def _qr_matrix(prediction: PredictionData) -> list[list[bool]]:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(prediction.qr_data())
    qr.make(fit=True)
    return qr.get_matrix()


def _render_label_image(
    prediction: PredictionData, width_mm: float, height_mm: float,
) -> bytes:
    """Render a QR + text-panel label to PNG bytes at 203 DPI (common thermal)."""
    from PIL import Image, ImageDraw, ImageFont

    dpi = 203  # Standard thermal printer DPI (8 dots/mm).
    page_w = round(width_mm * dpi / 25.4)
    page_h = round(height_mm * dpi / 25.4)
    if page_w <= 0 or page_h <= 0:
        raise PrinterServiceError("Invalid label dimensions.")

    img = Image.new("1", (page_w, page_h), color=1)  # 1-bit white background.
    draw = ImageDraw.Draw(img)

    matrix = _qr_matrix(prediction)
    module_count = len(matrix)
    margin = max(2, round(min(page_w, page_h) * 0.025))
    gap = max(4, round(page_w * 0.018))

    # Landscape: reserve ~31% for the text panel if wide enough.
    has_text_panel = page_w >= round(page_h * 1.15)
    text_width = round(page_w * 0.31) if has_text_panel else 0
    max_qr_width = page_w - (2 * margin) - text_width - (gap if has_text_panel else 0)
    max_qr_size = min(page_h - (2 * margin), max_qr_width)
    module_px = max_qr_size // module_count
    if module_px < 2:
        raise PrinterServiceError(
            "Printable area too small for a scannable QR. Check the label paper size."
        )

    qr_size = module_px * module_count
    qr_x = margin if has_text_panel else max(margin, (page_w - qr_size) // 2)
    qr_y = max(margin, (page_h - qr_size) // 2)

    # Draw QR modules.
    for row_index, row in enumerate(matrix):
        run_start: int | None = None
        for column_index, is_black in enumerate([*row, False]):
            if is_black and run_start is None:
                run_start = column_index
            elif not is_black and run_start is not None:
                draw.rectangle(
                    [
                        qr_x + (run_start * module_px),
                        qr_y + (row_index * module_px),
                        qr_x + (column_index * module_px) - 1,
                        qr_y + ((row_index + 1) * module_px) - 1,
                    ],
                    fill=0,
                )
                run_start = None

    if has_text_panel:
        panel_left = qr_x + qr_size + gap
        labels = prediction.panel()
        row_height = max(8, (page_h - (2 * margin)) // len(labels))
        font_px = max(7, min(round(row_height * 0.48), max(7, (page_w - panel_left - margin) // 7)))
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_px)
        except OSError:
            font = ImageFont.load_default()
        for index, label in enumerate(labels):
            top = margin + (index * row_height)
            draw.text((panel_left, top), label, fill=0, font=font)

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── CUPS submission ──────────────────────────────────────────────────────────

def print_prediction_label(
    printer_name: str, prediction: PredictionData,
    width_mm: float = 40, height_mm: float = 30,
    *, quantity: int = 1,
) -> int | None:
    """Render and submit a prediction label to the named CUPS printer.

    Returns the CUPS job ID on success, or None if it could not be parsed.
    """
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
        raise PrinterServiceError("Choose between 1 and 10 labels.")

    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise PrinterServiceError("Physical printing is disabled in automated tests.")

    _require_cups()
    printer = _get_installed_printer(printer_name)
    png_data = _render_label_image(prediction, width_mm, height_mm)

    # Write the rendered label to a temporary file and submit via `lp`.
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="bv-label-")
        label_path = Path(tmp_dir) / "label.png"
        label_path.write_bytes(png_data)

        # Submit one copy per page; quantity is number of copies.
        cmd = [
            "lp",
            "-d", printer.name,
            "-n", str(quantity),
            "-o", f"media=Custom.{width_mm:.0f}x{height_mm:.0f}mm",
            "-o", "fit-to-page",
            "-t", f"BananaVision {prediction.prediction_id}",
            str(label_path),
        ]
        logger.info("Submitting label: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            raise PrinterServiceError(
                f"CUPS rejected the print job (exit {result.returncode}): {error_text}"
            )

        # Parse the CUPS job ID from stdout: "request id is PRINTER-123 (1 file(s))"
        job_match = re.search(r"request id is \S+-(\d+)", result.stdout)
        job_id = int(job_match.group(1)) if job_match else None
        logger.info("Label submitted to %s, CUPS job %s", printer.name, job_id)
        return job_id

    except PrinterServiceError:
        raise
    except Exception as exc:
        raise PrinterServiceError(
            f"Could not submit the print job via CUPS: {exc}. "
            "Check the printer connection and CUPS configuration."
        ) from exc
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
