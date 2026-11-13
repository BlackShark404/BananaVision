"""
High-performance, dependency-free XLSX generator using standard library zipfile.
Adheres strictly to OpenXML SpreadsheetML standards:
- text wrapping enabled in styles
- auto-calculated column widths (clamped between 12 and 81)
- dynamic row heights for multiline and wrapped text
- inlineStr escaping to protect against formula injection
- precise number, boolean, and string typing
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
import xml.sax.saxutils as saxutils
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from app.core.time import now_manila

NS_SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
MAX_ROW_HEIGHT = 409.0


def col_letter(col_idx: int) -> str:
    """Convert 1-based column index to Excel column letters (1 -> A, 27 -> AA)."""
    result = []
    while col_idx > 0:
        col_idx, rem = divmod(col_idx - 1, 26)
        result.append(chr(65 + rem))
    return "".join(reversed(result))


def clean_xml_text(value: str) -> str:
    """Remove characters that are invalid in XML 1.0 (except tab, CR, LF)."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", "", value)


def escape_xml(value: str) -> str:
    return saxutils.escape(clean_xml_text(value))


def display_width(value: str) -> int:
    """Approximate visible cell width, counting wide CJK characters as two."""
    width = 0
    for char in value:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def wrapped_line_count(value: str, column_width: float) -> int:
    """Estimate how many wrapped lines a value occupies in a column."""
    available = max(1, int(column_width) - 2)
    return sum(
        max(1, math.ceil(display_width(line) / available))
        for line in value.split("\n")
    )


def number_text(value: Any) -> str | None:
    """Render a finite number without losing precision or adding trailing zeros."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    # Keep exact integer/Decimal text instead of routing it through a float.
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        return str(int(value)) if value == value.to_integral_value() else str(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    if not math.isfinite(numeric):
        return str(value)
    return str(int(numeric)) if numeric.is_integer() else str(value)


def build_xlsx(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_name: str = "sheet1",
) -> bytes:
    """Generate an OpenXML (.xlsx) file as bytes."""
    num_cols = len(headers)

    # 1. Compute column widths and analyze row heights
    col_widths = []
    for c_idx in range(num_cols):
        max_c = display_width(str(headers[c_idx]))
        for row in rows:
            if c_idx < len(row):
                cell = row[c_idx]
                if isinstance(cell, tuple):
                    val = cell[0]
                elif isinstance(cell, dict):
                    val = cell.get("value")
                else:
                    val = cell

                if val is not None:
                    for line in str(val).split("\n"):
                        max_c = max(max_c, display_width(line))

        # Clamp between 12 and 81 so wide values wrap instead of hiding the sheet.
        width = min(81.0, max(12.0, float(max_c + 3)))
        col_widths.append(width)

    # 2. Build worksheet XML
    cols_xml = []
    for i, w in enumerate(col_widths, start=1):
        cols_xml.append(f'<col min="{i}" max="{i}" width="{w:.1f}" customWidth="1"/>')

    sheet_rows_xml = []

    # Header row (row 1)
    header_cells = []
    header_lines = 1
    for c_idx, h in enumerate(headers, start=1):
        text = str(h)
        header_lines = max(header_lines, wrapped_line_count(text, col_widths[c_idx - 1]))
        cell_ref = f"{col_letter(c_idx)}1"
        header_cells.append(
            f'<c r="{cell_ref}" t="inlineStr" s="2">'
            f'<is><t xml:space="preserve">{escape_xml(text)}</t></is></c>'
        )
    header_ht = min(MAX_ROW_HEIGHT, max(24.0, float(header_lines * 18)))
    sheet_rows_xml.append(
        f'<row r="1" ht="{header_ht:.1f}" customHeight="1">{"".join(header_cells)}</row>'
    )

    # Data rows (rows 2..N+1)
    for r_idx, row in enumerate(rows, start=2):
        row_cells = []
        visual_lines = 1

        for c_idx in range(num_cols):
            cell_ref = f"{col_letter(c_idx + 1)}{r_idx}"
            cell = row[c_idx] if c_idx < len(row) else None

            if isinstance(cell, tuple):
                val, cell_type = cell
            elif isinstance(cell, dict):
                val = cell.get("value")
                cell_type = cell.get("type")
            elif cell is None:
                val, cell_type = None, None
            elif isinstance(cell, bool):
                val, cell_type = ("1" if cell else "0"), "b"
            elif isinstance(cell, (int, float)):
                val, cell_type = str(cell), "n"
            else:
                val, cell_type = str(cell), "inlineStr"

            if cell_type == "n":
                try:
                    if not math.isfinite(float(val)):
                        cell_type = "inlineStr"
                except (TypeError, ValueError):
                    cell_type = "inlineStr"

            if val is not None:
                visual_lines = max(
                    visual_lines, wrapped_line_count(str(val), col_widths[c_idx])
                )

            if val is None or cell_type is None:
                row_cells.append(f'<c r="{cell_ref}" s="1"/>')
            elif cell_type == "b":
                row_cells.append(f'<c r="{cell_ref}" t="b" s="1"><v>{val}</v></c>')
            elif cell_type == "n":
                row_cells.append(f'<c r="{cell_ref}" t="n" s="1"><v>{val}</v></c>')
            else:
                # String / inlineStr - safe from formula execution and preserves spaces.
                row_cells.append(
                    f'<c r="{cell_ref}" t="inlineStr" s="1"><is>'
                    f'<t xml:space="preserve">{escape_xml(str(val))}</t></is></c>'
                )

        row_ht = min(MAX_ROW_HEIGHT, max(16.0, float(visual_lines * 18)))
        sheet_rows_xml.append(
            f'<row r="{r_idx}" ht="{row_ht:.1f}" customHeight="1">{"".join(row_cells)}</row>'
        )

    worksheet_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<worksheet xmlns="{NS_SPREADSHEET}">\n'
        f'  <cols>\n    {"".join(cols_xml)}\n  </cols>\n'
        f'  <sheetData>\n    {"".join(sheet_rows_xml)}\n  </sheetData>\n'
        f'</worksheet>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/xl/workbook.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        f'  <Override PartName="/xl/worksheets/{sheet_name}.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
        '  <Override PartName="/xl/styles.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\n'
        '</Types>'
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
        '</Relationships>'
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <sheets>\n'
        '    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>\n'
        '  </sheets>\n'
        '</workbook>'
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/worksheet" Target="worksheets/{sheet_name}.xml"/>\n'
        '  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
        '</Relationships>'
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <fonts count="2">\n'
        '    <font><sz val="11"/><name val="Calibri"/></font>\n'
        '    <font><b/><sz val="11"/><name val="Calibri"/></font>\n'
        '  </fonts>\n'
        '  <fills count="2">\n'
        '    <fill><patternFill patternType="none"/></fill>\n'
        '    <fill><patternFill patternType="gray125"/></fill>\n'
        '  </fills>\n'
        '  <borders count="1">\n'
        '    <border><left/><right/><top/><bottom/><diagonal/></border>\n'
        '  </borders>\n'
        '  <cellStyleXfs count="1">\n'
        '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>\n'
        '  </cellStyleXfs>\n'
        '  <cellXfs count="3">\n'
        '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
        '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">\n'
        '      <alignment wrapText="1" vertical="top"/>\n'
        '    </xf>\n'
        '    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1">\n'
        '      <alignment wrapText="1" vertical="center"/>\n'
        '    </xf>\n'
        '  </cellXfs>\n'
        '</styleSheet>'
    )

    # Zip members carry a modification time; stamp it with the Manila clock rather than
    # the server's local zone.
    stamp = now_manila().timetuple()[:6]

    def part(name: str) -> ZipInfo:
        info = ZipInfo(name, date_time=stamp)
        info.compress_type = ZIP_DEFLATED
        return info

    buf = io.BytesIO()
    with ZipFile(buf, mode="w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(part("[Content_Types].xml"), content_types_xml)
        zf.writestr(part("_rels/.rels"), rels_xml)
        zf.writestr(part("xl/workbook.xml"), workbook_xml)
        zf.writestr(part("xl/_rels/workbook.xml.rels"), workbook_rels_xml)
        zf.writestr(part("xl/styles.xml"), styles_xml)
        zf.writestr(part(f"xl/worksheets/{sheet_name}.xml"), worksheet_xml)

    return buf.getvalue()
