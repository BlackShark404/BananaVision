"""Dependency-free tabular PDF 1.4 report generator using standard library zlib.

Produces clean, printable landscape/portrait reports with:
- Report title, Asia/Manila export timestamp, record count, and optional filter summary
- Proportional Helvetica font metrics for accurate column widths and text wrapping
- WinAnsi encoding (degree symbol, en dash, bullet, middle dot, accented Latin chars)
- Repeated table headers on continuation pages and 'Page X of Y' footers
"""

from __future__ import annotations

import unicodedata
import zlib
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from app.core.export_format import format_manila_datetime
from app.core.time import as_manila, now_manila

# Standard Adobe AFM Helvetica glyph widths in 1/1000 em units (ASCII 32..126).
_HELVETICA_ASCII_WIDTHS: dict[int, int] = {
    32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
    40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
    48: 556, 49: 556, 50: 556, 51: 556, 52: 556, 53: 556, 54: 556, 55: 556,
    56: 556, 57: 556, 58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556,
    64: 1015, 65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778,
    72: 722, 73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778,
    80: 667, 81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944,
    88: 667, 89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556,
    96: 333, 97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556,
    104: 556, 105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556,
    111: 556, 112: 556, 113: 556, 114: 333, 115: 500, 116: 278, 117: 556,
    118: 500, 119: 722, 120: 500, 121: 500, 122: 500, 123: 334, 124: 260,
    125: 334, 126: 584,
}

_WINANSI_EXTRA_WIDTHS: dict[int, int] = {
    0x85: 1000,  # ellipsis
    0x91: 222,   # lsquo
    0x92: 222,   # rsquo
    0x93: 333,   # ldquo
    0x94: 333,   # rdquo
    0x95: 350,   # bullet
    0x96: 556,   # endash
    0x97: 1000,  # emdash
    0xB0: 400,   # degree
    0xB7: 278,   # periodcentered
    0xD1: 722,   # Ntilde
    0xF1: 556,   # ntilde
}

_CHAR_FALLBACKS = {
    "\u00a0": " ",
    "\u202f": " ",
    "\u2009": " ",
    "\u2192": "->",
    "\u2190": "<-",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2212": "-",
}


def _normalize_winansi_bytes(text: str) -> bytes:
    """Convert Unicode text to WinAnsi (cp1252) bytes for PDF Type 1 Helvetica."""
    out = bytearray()
    for ch in text:
        mapped = _CHAR_FALLBACKS.get(ch)
        if mapped is not None:
            out.extend(mapped.encode("ascii"))
            continue
        code = ord(ch)
        if code < 32:
            out.append(32)
            continue
        try:
            out.extend(ch.encode("cp1252"))
            continue
        except UnicodeEncodeError:
            pass
        decomposed = unicodedata.normalize("NFKD", ch)
        ascii_only = "".join(c for c in decomposed if 32 <= ord(c) < 127)
        if ascii_only:
            out.extend(ascii_only.encode("ascii"))
        else:
            out.append(ord("?"))
    return bytes(out)


def _pdf_escape(text: str) -> str:
    """Encode text as an ASCII PDF string literal payload using WinAnsi octal escapes."""
    raw = _normalize_winansi_bytes(text)
    parts: list[str] = []
    for b in raw:
        if b in (0x28, 0x29, 0x5C):  # (, ), \
            parts.append("\\" + chr(b))
        elif 32 <= b <= 126:
            parts.append(chr(b))
        else:
            parts.append(f"\\{b:03o}")
    return "".join(parts)


def _measure_text(text: str, font_size: float, *, bold: bool = False) -> float:
    raw = _normalize_winansi_bytes(text)
    total = 0
    for b in raw:
        if b in _HELVETICA_ASCII_WIDTHS:
            total += _HELVETICA_ASCII_WIDTHS[b]
        elif b in _WINANSI_EXTRA_WIDTHS:
            total += _WINANSI_EXTRA_WIDTHS[b]
        else:
            total += 556
    scale = 1.06 if bold else 1.0
    return (total / 1000.0) * font_size * scale


def _wrap_text(text: str, max_width: float, font_size: float, *, bold: bool = False) -> list[str]:
    """Word-wrap text to fit within max_width points, breaking long tokens cleanly."""
    if not text:
        return [""]
    usable = max(font_size, max_width)
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            if not word:
                continue
            candidate = word if not current else f"{current} {word}"
            if _measure_text(candidate, font_size, bold=bold) <= usable:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if _measure_text(word, font_size, bold=bold) <= usable:
                current = word
                continue
            # Single token wider than column: split cleanly at character boundaries.
            chunk = ""
            for ch in word:
                next_chunk = chunk + ch
                if chunk and _measure_text(next_chunk, font_size, bold=bold) > usable:
                    lines.append(chunk)
                    chunk = ch
                else:
                    chunk = next_chunk
            current = chunk
        if current:
            lines.append(current)
    return lines or [""]


def _compute_column_widths(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    usable_width: float,
    header_font_size: float,
    body_font_size: float,
    pad_x: float,
) -> list[float]:
    num_cols = len(headers)
    if num_cols == 0:
        return []
    sample_rows = rows[:200]
    min_floor = 32.0 if num_cols >= 10 else 44.0
    max_share = 0.22 if num_cols >= 10 else 0.44 if num_cols <= 5 else 0.30
    max_cap = usable_width * max_share

    mins: list[float] = []
    ideals: list[float] = []
    for c in range(num_cols):
        header_text = headers[c]
        header_words = header_text.split() or [header_text]
        longest_header_word = max(
            _measure_text(w, header_font_size, bold=True) for w in header_words
        )
        header_full = _measure_text(header_text, header_font_size, bold=True)
        min_w = max(min_floor, min(max_cap, longest_header_word + 2 * pad_x + 2.0))

        cell_widths: list[float] = []
        for row in sample_rows:
            val = row[c] if c < len(row) else ""
            if val:
                longest_line = max(
                    _measure_text(part, body_font_size) for part in val.split("\n")
                )
                cell_widths.append(longest_line + 2 * pad_x + 2.0)

        if cell_widths:
            cell_widths.sort()
            p90 = cell_widths[min(len(cell_widths) - 1, int(len(cell_widths) * 0.90))]
            ideal_w = max(min_w, min(max_cap, max(header_full + 2 * pad_x + 2.0, p90)))
        else:
            ideal_w = max(min_w, min(max_cap, header_full + 2 * pad_x + 2.0))

        mins.append(min_w)
        ideals.append(ideal_w)

    total_ideal = sum(ideals)
    if total_ideal <= 0:
        return [usable_width / num_cols] * num_cols

    if total_ideal <= usable_width:
        # Distribute remaining room proportionally so the table spans the full width cleanly.
        scale = usable_width / total_ideal
        return [w * scale for w in ideals]

    # Fit within usable_width while respecting minimums where possible.
    total_min = sum(mins)
    if total_min >= usable_width:
        scale = usable_width / total_min
        return [m * scale for m in mins]

    extra_budget = usable_width - total_min
    extra_demand = sum(max(0.0, ideal - mn) for ideal, mn in zip(ideals, mins, strict=True))
    if extra_demand <= 0:
        return list(mins)
    return [
        mn + extra_budget * (max(0.0, ideal - mn) / extra_demand)
        for ideal, mn in zip(ideals, mins, strict=True)
    ]


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple):
        value = value[0]
    elif isinstance(value, dict):
        value = value.get("value")
    return "" if value is None else str(value)


def build_pdf(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    title: str = "BananaVision Report",
    filters: Sequence[str] | None = None,
    exported_at: datetime | None = None,
    orientation: Literal["auto", "landscape", "portrait"] = "auto",
) -> bytes:
    """Generate a clean, printable tabular PDF 1.4 document as bytes."""
    header_list = [str(h) for h in headers]
    num_cols = len(header_list)
    row_list: list[list[str]] = [
        [_cell_text(row[c]) if c < len(row) else "" for c in range(num_cols)]
        for row in rows
    ]

    use_landscape = (
        orientation == "landscape"
        or (orientation == "auto" and num_cols >= 5)
    )
    page_w, page_h = (792.0, 612.0) if use_landscape else (612.0, 792.0)
    margin_x = 28.0
    margin_top = 30.0
    margin_bottom = 30.0
    footer_h = 16.0
    usable_w = page_w - 2 * margin_x

    # Adaptive compact typography for wide 13-column reports vs narrower tables.
    header_font = 7.5 if num_cols >= 10 else 8.5
    body_font = 7.2 if num_cols >= 10 else 8.2
    header_line_h = header_font + 2.5
    body_line_h = body_font + 2.6
    pad_x = 3.5 if num_cols >= 10 else 5.0
    pad_y = 4.0

    timestamp = as_manila(exported_at) if exported_at is not None else now_manila()
    exported_label = f"Exported: {format_manila_datetime(timestamp)} (Asia/Manila)"
    count_label = f"Total records: {len(row_list)}"
    meta_line = f"{exported_label}   |   {count_label}"

    filter_items = [item.strip() for item in (filters or []) if item and item.strip()]
    filter_lines = (
        _wrap_text("Filters: " + " · ".join(filter_items), usable_w, 8.0)
        if filter_items
        else []
    )

    col_widths = _compute_column_widths(
        header_list, row_list, usable_w, header_font, body_font, pad_x,
    )
    wrapped_headers = [
        _wrap_text(header_list[c], max(8.0, col_widths[c] - 2 * pad_x), header_font, bold=True)
        for c in range(num_cols)
    ]
    header_row_h = max(1, *(len(lines) for lines in wrapped_headers)) * header_line_h + 2 * pad_y

    # Pre-wrap all data rows and split any pathologically tall row safely across pages.
    first_page_banner_h = 34.0 + (len(filter_lines) * 10.5 + 4.0 if filter_lines else 0.0)
    cont_page_banner_h = 20.0
    max_body_h_cont = (
        page_h - margin_top - margin_bottom - footer_h - cont_page_banner_h - header_row_h
    )
    max_lines_per_cell = max(1, int((max_body_h_cont - 2 * pad_y) // body_line_h))

    wrapped_rows: list[tuple[list[list[str]], float, int]] = []
    for row_idx, row in enumerate(row_list):
        cells = [
            _wrap_text(row[c], max(8.0, col_widths[c] - 2 * pad_x), body_font)
            for c in range(num_cols)
        ]
        tallest = max(1, *(len(lines) for lines in cells))
        if tallest <= max_lines_per_cell:
            wrapped_rows.append((cells, tallest * body_line_h + 2 * pad_y, row_idx))
        else:
            for offset in range(0, tallest, max_lines_per_cell):
                chunk = [lines[offset:offset + max_lines_per_cell] or [""] for lines in cells]
                chunk_lines = max(1, *(len(lines) for lines in chunk))
                wrapped_rows.append((chunk, chunk_lines * body_line_h + 2 * pad_y, row_idx))

    # Paginate rows into pages.
    pages: list[list[tuple[list[list[str]], float, int]]] = []
    current_page: list[tuple[list[list[str]], float, int]] = []
    available_h = (
        page_h - margin_top - margin_bottom - footer_h - first_page_banner_h - header_row_h
    )
    used_h = 0.0
    for item in wrapped_rows:
        row_h = item[1]
        if current_page and used_h + row_h > available_h:
            pages.append(current_page)
            current_page = []
            available_h = max_body_h_cont
            used_h = 0.0
        current_page.append(item)
        used_h += row_h
    pages.append(current_page)

    total_pages = len(pages)
    page_streams: list[bytes] = []

    for page_num, page_rows in enumerate(pages, start=1):
        ops: list[str] = []
        y = page_h - margin_top

        # Page header banner.
        if page_num == 1:
            ops.append("0.08 0.12 0.18 rg")
            ops.append(f"BT /F2 13.5 Tf {margin_x:.2f} {y - 11:.2f} Td ({_pdf_escape(title)}) Tj ET")
            y -= 18.0
            ops.append("0.30 0.36 0.44 rg")
            ops.append(
                f"BT /F1 8.2 Tf {margin_x:.2f} {y - 7:.2f} Td ({_pdf_escape(meta_line)}) Tj ET"
            )
            y -= 13.0
            if filter_lines:
                for line in filter_lines:
                    ops.append(
                        f"BT /F1 7.8 Tf {margin_x:.2f} {y - 7:.2f} Td ({_pdf_escape(line)}) Tj ET"
                    )
                    y -= 10.5
                y -= 2.0
            ops.append("0.80 0.84 0.89 RG 0.7 w")
            ops.append(f"{margin_x:.2f} {y:.2f} m {page_w - margin_x:.2f} {y:.2f} l S")
            y -= 6.0
        else:
            ops.append("0.30 0.36 0.44 rg")
            ops.append(f"BT /F2 8.5 Tf {margin_x:.2f} {y - 8:.2f} Td ({_pdf_escape(title)}) Tj ET")
            right_w = _measure_text(exported_label, 7.8)
            right_x = max(margin_x + 120.0, page_w - margin_x - right_w)
            ops.append(
                f"BT /F1 7.8 Tf {right_x:.2f} {y - 8:.2f} Td ({_pdf_escape(exported_label)}) Tj ET"
            )
            y -= 14.0
            ops.append("0.80 0.84 0.89 RG 0.6 w")
            ops.append(f"{margin_x:.2f} {y:.2f} m {page_w - margin_x:.2f} {y:.2f} l S")
            y -= 6.0

        # Table header row.
        table_top = y
        header_bottom = y - header_row_h
        ops.append("0.93 0.95 0.97 rg")
        ops.append(f"{margin_x:.2f} {header_bottom:.2f} {usable_w:.2f} {header_row_h:.2f} re f")

        ops.append("0.08 0.12 0.18 rg")
        x = margin_x
        for c in range(num_cols):
            lines = wrapped_headers[c]
            text_y = table_top - pad_y - header_font + 1.0
            for line in lines:
                if line:
                    ops.append(
                        f"BT /F2 {header_font:.2f} Tf {x + pad_x:.2f} {text_y:.2f} Td "
                        f"({_pdf_escape(line)}) Tj ET"
                    )
                text_y -= header_line_h
            x += col_widths[c]

        # Header border.
        ops.append("0.68 0.73 0.80 RG 0.6 w")
        ops.append(f"{margin_x:.2f} {header_bottom:.2f} {usable_w:.2f} {header_row_h:.2f} re S")
        x = margin_x
        for c in range(num_cols - 1):
            x += col_widths[c]
            ops.append(f"{x:.2f} {table_top:.2f} m {x:.2f} {header_bottom:.2f} l S")

        y = header_bottom

        # Data rows (or polite empty notice).
        if not page_rows:
            empty_h = 22.0
            empty_bottom = y - empty_h
            ops.append("0.86 0.89 0.93 RG 0.5 w")
            ops.append(f"{margin_x:.2f} {empty_bottom:.2f} {usable_w:.2f} {empty_h:.2f} re S")
            notice = "No matching records."
            notice_w = _measure_text(notice, body_font)
            notice_x = margin_x + max(pad_x, (usable_w - notice_w) / 2.0)
            ops.append("0.40 0.46 0.54 rg")
            ops.append(
                f"BT /F1 {body_font:.2f} Tf {notice_x:.2f} {y - 14:.2f} Td "
                f"({_pdf_escape(notice)}) Tj ET"
            )
        else:
            for cells, row_h, orig_idx in page_rows:
                row_bottom = y - row_h
                if orig_idx % 2 == 1:
                    ops.append("0.975 0.982 0.99 rg")
                    ops.append(f"{margin_x:.2f} {row_bottom:.2f} {usable_w:.2f} {row_h:.2f} re f")

                ops.append("0.12 0.16 0.22 rg")
                x = margin_x
                for c in range(num_cols):
                    text_y = y - pad_y - body_font + 1.0
                    for line in cells[c]:
                        if line:
                            ops.append(
                                f"BT /F1 {body_font:.2f} Tf {x + pad_x:.2f} {text_y:.2f} Td "
                                f"({_pdf_escape(line)}) Tj ET"
                            )
                        text_y -= body_line_h
                    x += col_widths[c]

                ops.append("0.86 0.89 0.93 RG 0.45 w")
                ops.append(f"{margin_x:.2f} {row_bottom:.2f} {usable_w:.2f} {row_h:.2f} re S")
                x = margin_x
                for c in range(num_cols - 1):
                    x += col_widths[c]
                    ops.append(f"{x:.2f} {y:.2f} m {x:.2f} {row_bottom:.2f} l S")
                y = row_bottom

        # Page footer.
        footer_y = margin_bottom - 10.0
        ops.append("0.45 0.50 0.58 rg")
        ops.append(
            f"BT /F1 7.5 Tf {margin_x:.2f} {footer_y:.2f} Td "
            f"(BananaVision Export Report) Tj ET"
        )
        page_label = f"Page {page_num} of {total_pages}"
        page_label_w = _measure_text(page_label, 7.5)
        ops.append(
            f"BT /F1 7.5 Tf {page_w - margin_x - page_label_w:.2f} {footer_y:.2f} Td "
            f"({_pdf_escape(page_label)}) Tj ET"
        )

        page_streams.append(("\n".join(ops) + "\n").encode("ascii"))

    # Assemble PDF 1.4 objects with exact xref table.
    creation_date = timestamp.strftime("D:%Y%m%d%H%M%S+08'00'")
    objects: list[bytes] = []

    # 1: Catalog, 2: Pages (placeholder filled after kids known), 3: F1, 4: F2, 5: Info
    page_obj_ids = [6 + i * 2 for i in range(total_pages)]
    kids_ref = " ".join(f"{pid} 0 R" for pid in page_obj_ids)

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids_ref}] /Count {total_pages} >>".encode("ascii"))
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    objects.append(
        (
            f"<< /Title ({_pdf_escape(title)}) /Creator (BananaVision) "
            f"/Producer (BananaVision Export) /CreationDate ({creation_date}) >>"
        ).encode("ascii")
    )

    for idx, stream_data in enumerate(page_streams):
        stream_obj_id = 7 + idx * 2
        compressed = zlib.compress(stream_data)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.0f} {page_h:.0f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {stream_obj_id} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            f"<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            + compressed
            + b"\nendstream"
        )

    buf = bytearray()
    buf.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]
    for obj_num, body in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        buf.extend(body)
        buf.extend(b"\nendobj\n")

    xref_offset = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 5 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(buf)
