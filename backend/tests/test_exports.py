"""Human-friendly Excel (.xlsx) and PDF (.pdf) export contracts, traceability, and parity tests."""

# Imported pytest fixtures intentionally share names with test parameters.
# ruff: noqa: F811

import io
import re
import xml.etree.ElementTree as ET
import zlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.api.deps import get_current_user
from app.api.v1 import config
from app.api.v1 import scan_logs as logs_api
from app.core.database import Base, get_db, get_stream_db
from app.core.export_format import SCAN_EXPORT_HEADERS, format_scan_ref
from app.core.xlsx import number_text
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum
from app.services import auth_service, scan_logs
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_scan_logs import logs_db  # noqa: F401

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

EXCLUDED_HEADERS = {
    "Scan ID", "Intake ID", "Operator Username",
    "Overridden", "Status Updated At", "Status Updated At (UTC+08:00)", "VPD (kPa)",
}


def workbook_rows(content, sheet="sheet1"):
    with ZipFile(io.BytesIO(content)) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/{sheet}.xml"))
        rows = []
        for row in root.findall("m:sheetData/m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                text = cell.find("m:is/m:t", NS)
                number = cell.find("m:v", NS)
                cells[cell.attrib["r"]] = (
                    text.text if text is not None else number.text if number is not None else None,
                    cell.attrib.get("t", "n"),
                )
                assert cell.find("m:f", NS) is None
            rows.append(cells)
        return root, rows


def workbook_table(content, sheet="sheet1") -> tuple[list[str], list[list[str]]]:
    _, raw_rows = workbook_rows(content, sheet=sheet)
    col_count = len(raw_rows[0])
    letters = [chr(65 + idx) for idx in range(col_count)]
    headers = [raw_rows[0][f"{col}1"][0] or "" for col in letters]
    data = [
        [row[f"{col}{r_idx + 2}"][0] or "" for col in letters]
        for r_idx, row in enumerate(raw_rows[1:])
    ]
    return headers, data


def decode_pdf_literal(raw: str) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt in ("(", ")", "\\"):
                out.append(ord(nxt))
                i += 2
                continue
            if i + 3 < len(raw) and all(c in "01234567" for c in raw[i + 1:i + 4]):
                out.append(int(raw[i + 1:i + 4], 8))
                i += 4
                continue
        out.append(ord(raw[i]))
        i += 1
    return out.decode("cp1252")


def extract_pdf_text(pdf_bytes: bytes) -> tuple[list[str], str]:
    assert pdf_bytes.startswith(b"%PDF-1.4\n")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
    pages: list[str] = []
    for match in re.finditer(rb"stream\n(.*?)\nendstream", pdf_bytes, flags=re.S):
        raw_stream = match.group(1)
        try:
            decoded = zlib.decompress(raw_stream).decode("ascii")
        except zlib.error:
            decoded = raw_stream.decode("ascii", errors="replace")
        tokens = [
            decode_pdf_literal(tok.group(1))
            for tok in re.finditer(r"\(((?:\\.|[^\\()])*)\)\s*Tj", decoded)
        ]
        pages.append(" ".join(tokens))
    return pages, "\n".join(pages)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def export_app(logs_db):
    Base.metadata.create_all(logs_db.session.get_bind(), checkfirst=True)
    app = FastAPI()
    app.include_router(logs_api.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")

    async def database():
        yield logs_db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_stream_db] = database
    return app


def test_scan_excel_and_pdf_filters_permissions_parity_and_csv_removal(
    export_app, logs_db, monkeypatch,
):
    own, other = account(logs_db, name='=SUM(1,2)'), account(logs_db)
    snapshots = {}

    async def lock(_db, user):
        return user

    async def save(_db, _user, key, payload):
        saved = SimpleNamespace(
            id=uuid4(), payload=payload, binding=key,
            expires_at=NOW + timedelta(minutes=10),
        )
        snapshots[saved.id] = saved
        return saved

    async def load(_db, _user, token, key, lock=True):
        saved = snapshots[token]
        if key != saved.binding:
            raise HTTPException(409, "Browse filters changed")
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    prediction = "14.560613439297734"
    source = 'Peñafrancia Farm, "Saging"\n' + "source " * 15
    expected = [
        scan(
            logs_db, own, at=NOW - timedelta(seconds=i),
            source=source, prediction=prediction, confidence=0,
        )
        for i in range(205)
    ]
    scan(logs_db, own, source="Excluded", confidence=0)
    scan(logs_db, other, source=source, confidence=0)
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == expected[0],
    ).values(temperature=0, humidity=0, finger_count=0, vpd=0))
    export_app.dependency_overrides[get_current_user] = lambda: own
    with TestClient(export_app) as client:
        params = {"format": "xlsx", "source": source, "page": 99, "limit": 1}
        result = client.get("/api/v1/scan-logs/export", params=params)
        assert result.status_code == 200, result.text
        assert result.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert result.headers["content-disposition"].endswith('.xlsx"')
        root, rows = workbook_rows(result.content)
        headers, data = workbook_table(result.content)
        assert headers == SCAN_EXPORT_HEADERS
        assert headers[0] == "Scan Ref"
        assert not EXCLUDED_HEADERS.intersection(headers)
        assert len(data) == 205
        # Deterministic SCAN-XXXXXXXX ref first, never raw 36-char UUID.
        first_ref = format_scan_ref(expected[0])
        assert re.fullmatch(r"SCAN-[0-9A-F]{8}", first_ref)
        assert [row[0] for row in data] == [format_scan_ref(sid) for sid in expected]
        # Readable Asia/Manila timestamp with seconds (NOW = 2026-10-02 12:00:00 +08:00).
        assert data[0][1] == "Oct 2, 2026, 12:00:00 PM"
        assert data[1][1] == "Oct 2, 2026, 11:59:59 AM"
        assert "T" not in data[0][1] and "+08:00" not in data[0][1]
        assert data[0][2] == source.strip()
        assert data[0][3] == "Lakatan"
        assert data[0][4] == "Ripe"
        assert data[0][5] == "Est. 0 fingers"
        assert data[0][6] == "14–15 days"
        assert data[0][7] == "14–15 days left"
        assert data[0][8] == "In Stock"
        assert data[0][9] == "Approved"
        assert data[0][10] == "0.0"
        assert data[0][11] == "0.0"
        assert data[0][12] == "0.0"
        assert data[0][13] == "=SUM(1,2)"
        # Numeric spreadsheet cells for Confidence, Temperature, and Humidity (with 0.0 format).
        assert rows[1]["K2"] == ("0.0", "n")
        assert rows[1]["L2"] == ("0.0", "n")
        assert rows[1]["M2"] == ("0.0", "n")
        # Formula text stays safe inlineStr without Excel formula elements.
        assert rows[1]["N2"] == ("=SUM(1,2)", "inlineStr")
        columns = root.findall("m:cols/m:col", NS)
        assert all(12 <= float(column.attrib["width"]) <= 81 for column in columns)
        assert max(float(column.attrib["width"]) for column in columns) >= 80
        assert float(root.findall("m:sheetData/m:row", NS)[1].attrib["ht"]) > 36
        with ZipFile(io.BytesIO(result.content)) as archive:
            styles = ET.fromstring(archive.read("xl/styles.xml"))
            assert styles.findall('.//m:alignment[@wrapText="1"]', NS)
            assert styles.findall('.//m:numFmt[@formatCode="0.0"]', NS)
            assert not any("hyperlink" in name for name in archive.namelist())
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            assert all(
                text.attrib.get(XML_SPACE) == "preserve"
                for text in sheet.findall(".//m:t", NS)
            )

        # PDF export matches the exact same headers, record count, Scan Ref, and formatted values.
        pdf_result = client.get("/api/v1/scan-logs/export", params={**params, "format": "pdf"})
        assert pdf_result.status_code == 200, pdf_result.text
        assert pdf_result.headers["content-type"] == "application/pdf"
        assert pdf_result.headers["content-disposition"].endswith('.pdf"')
        assert b"/MediaBox [0 0 792 612]" in pdf_result.content  # Landscape orientation
        pages, pdf_text = extract_pdf_text(pdf_result.content)
        assert len(pages) > 1
        assert "BananaVision — Scan Logs Report" in pages[0]
        assert "Exported: Oct 2, 2026, 12:00:00 PM (Asia/Manila)" in pages[0]
        assert "Total records: 205" in pages[0]
        assert "Filters: Source:" in pages[0]
        assert f"Page 1 of {len(pages)}" in pages[0]
        assert f"Page {len(pages)} of {len(pages)}" in pages[-1]
        for header in SCAN_EXPORT_HEADERS:
            for token in header.split():
                assert token in pages[0] and token in pages[1]
        for cell in (first_ref, "Oct 2, 2026, 12:00:00 PM", "Est. 0 fingers", "14–15 days",
                     "14–15 days left", "0.0", "=SUM(1,2)", "Peñafrancia"):
            assert cell in pdf_text
        assert str(expected[0]) not in pdf_text

        # Snapshot serves both XLSX and PDF cleanly with identical row counts and refs.
        listing = client.get("/api/v1/scan-logs", params={
            "stable": True, "page_size": 1, "source": source,
        })
        assert listing.status_code == 200, listing.text
        token = listing.json()["snapshot_id"]
        for fmt in ("xlsx", "pdf"):
            snap_resp = client.get("/api/v1/scan-logs/export", params={
                "format": fmt, "snapshot_id": token, "source": source,
                "page": 99, "limit": 1,
            })
            assert snap_resp.status_code == 200, snap_resp.text
            if fmt == "xlsx":
                snap_data = workbook_table(snap_resp.content)[1]
                assert len(snap_data) == 205
                assert snap_data[0][0] == first_ref
            else:
                _, snap_pdf_text = extract_pdf_text(snap_resp.content)
                assert "Total records: 205" in snap_pdf_text
                assert first_ref in snap_pdf_text

        # Account scope still enforced; CSV rejected with 422.
        denied = client.get("/api/v1/scan-logs/export", params={
            "format": "xlsx", "operator_id": str(other.operator_id),
        })
        assert len(workbook_table(denied.content)[1]) == 0
        assert client.get("/api/v1/scan-logs/export", params={"format": "csv"}).status_code == 422
        assert client.get("/api/v1/scan-logs/export", params={
            "format": "xlsx", "page_size": 101,
        }).status_code == 422


def test_human_friendly_freshness_review_and_finger_count_rules(export_app, logs_db):
    owner = account(logs_db, name="Maria Santos")
    # 1. Active in-stock scan with AI-estimated finger count and decimal shelf life.
    active_id = scan(
        logs_db, owner, at=NOW - timedelta(days=2), source="Davao Farm",
        prediction="10.4321987654321", confidence=89.84, flagged=False,
    )
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == active_id,
    ).values(finger_count=14, temperature=26.44, humidity=72.56))

    # 2. Final day scan with human-corrected finger count (must NOT say "Est.").
    final_id = scan(
        logs_db, owner, at=NOW - timedelta(days=3), source="Bukidnon Growers",
        prediction="2-3", confidence=74.2, flagged=True,
    )
    logs_db.session.execute(update(Scan).where(Scan.id == final_id).values(is_overridden=True))
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == final_id,
    ).values(
        cultivar=CultivarEnum.LATUNDAN, ripeness=RipenessEnum.SEMI_RIPE,
        finger_count=12, temperature=25.0, humidity=68.0,
    ))
    logs_db.add(
        ScanOriginalAiResult, scan_id=final_id, cultivar=CultivarEnum.LATUNDAN,
        ripeness=RipenessEnum.SEMI_RIPE, confidence=74.2, spoilage_days="2-3", finger_count=10,
    )

    # 3. Overdue by 1 day scan where cultivar was overridden, NOT finger count (stays "Est.").
    overdue_id = scan(
        logs_db, owner, at=NOW - timedelta(days=4), source="Cebu Co-op",
        prediction="3", confidence=91.0,
    )
    logs_db.session.execute(update(Scan).where(Scan.id == overdue_id).values(is_overridden=True))
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == overdue_id,
    ).values(cultivar=CultivarEnum.CARDABA, ripeness=RipenessEnum.OVERRIPE, finger_count=1))
    logs_db.add(
        ScanOriginalAiResult, scan_id=overdue_id, cultivar=CultivarEnum.LAKATAN,
        ripeness=RipenessEnum.OVERRIPE, confidence=91.0, spoilage_days="3", finger_count=1,
    )

    # 4. Closed-stock scans (Sold, For Processing, Spoiled).
    for offset, status in enumerate(
        (InventoryStatusEnum.SOLD, InventoryStatusEnum.FOR_PROCESSING, InventoryStatusEnum.SPOILED),
        start=5,
    ):
        scan(
            logs_db, owner, at=NOW - timedelta(days=offset), source=f"Closed {status.value}",
            prediction="4", confidence=88.0, statuses=[(NOW, status)],
        )

    export_app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(export_app) as client:
        xlsx_resp = client.get("/api/v1/scan-logs/export", params={"format": "xlsx"})
        pdf_resp = client.get("/api/v1/scan-logs/export", params={"format": "pdf"})
        assert xlsx_resp.status_code == 200 and pdf_resp.status_code == 200
        headers, rows = workbook_table(xlsx_resp.content)
        assert headers == SCAN_EXPORT_HEADERS
        assert len(rows) == 6

        by_source = {row[2]: row for row in rows}
        # Active scan: Scan Ref, Est. 14 fingers, 10–11 days, 8–9 days left, Approved, numeric 89.8/26.4/72.6.
        assert by_source["Davao Farm"][0] == format_scan_ref(active_id)
        assert by_source["Davao Farm"][5:14] == [
            "Est. 14 fingers", "10–11 days", "8–9 days left", "In Stock", "Approved",
            "89.8", "26.4", "72.6", "Maria Santos",
        ]
        # Final day scan: human-corrected count -> "12 fingers" (no Est.), Needs Review.
        assert by_source["Bukidnon Growers"][0] == format_scan_ref(final_id)
        assert by_source["Bukidnon Growers"][3:11] == [
            "Latundan", "Semi Ripe", "12 fingers", "2–3 days", "Final day",
            "In Stock", "Needs Review", "74.2",
        ]
        # Overdue by 1 day: count unchanged from AI baseline -> "Est. 1 finger".
        assert by_source["Cebu Co-op"][0] == format_scan_ref(overdue_id)
        assert by_source["Cebu Co-op"][3:10] == [
            "Cardaba", "Overripe", "Est. 1 finger", "3 days", "Overdue by 1 day",
            "In Stock", "Approved",
        ]
        # Closed stock shows outcome, never countdown or raw floats.
        assert by_source["Closed Sold"][7:9] == ["Sold", "Sold"]
        assert by_source["Closed For Processing"][7:9] == ["For Processing", "For Processing"]
        assert by_source["Closed Spoiled"][7:9] == ["Spoiled", "Spoiled"]

        # PDF parity: every formatted value from XLSX (including Scan Ref) is present in the PDF output.
        _, pdf_text = extract_pdf_text(pdf_resp.content)
        for row in rows:
            for value in row:
                if value:
                    assert value in pdf_text


def test_config_excel_and_pdf_same_complete_summary_and_admin_scope(export_app, logs_db):
    admin, operator = account(logs_db, role="Admin"), account(logs_db, name="Juan Dela Cruz")
    ids = []
    for i in range(15):
        ids.append(scan(
            logs_db, operator, at=NOW - timedelta(minutes=15 - i), confidence=85.5,
            prediction="4.6", source=f"Farm {i:02d}",
        ))
    export_app.dependency_overrides[get_current_user] = lambda: operator
    with TestClient(export_app) as client:
        for kind in ("xlsx", "pdf"):
            assert client.get("/api/v1/config/export", params={"format": kind}).status_code == 403
        export_app.dependency_overrides[get_current_user] = lambda: admin
        assert client.get("/api/v1/config/export", params={"format": "csv"}).status_code == 422
        excel_result = client.get("/api/v1/config/export")
        assert excel_result.status_code == 200
        assert excel_result.headers["content-disposition"].endswith(".xlsx\"")
        headers, rows = workbook_table(excel_result.content)
        assert headers == SCAN_EXPORT_HEADERS
        assert len(rows) == 15
        assert rows[0][0] == format_scan_ref(ids[0])
        assert rows[0][2] == "Farm 00"
        assert rows[0][6] == "4–5 days"
        assert rows[0][10] == "85.5"
        assert rows[0][13] == "Juan Dela Cruz"

        pdf_result = client.get("/api/v1/config/export", params={"format": "pdf"})
        assert pdf_result.status_code == 200
        assert pdf_result.headers["content-type"] == "application/pdf"
        assert pdf_result.headers["content-disposition"].endswith(".pdf\"")
        pages, pdf_text = extract_pdf_text(pdf_result.content)
        assert "BananaVision — Inventory Scan Summary" in pages[0]
        assert "Total records: 15" in pages[0]
        assert format_scan_ref(ids[0]) in pdf_text and format_scan_ref(ids[-1]) in pdf_text
        assert "Farm 00" in pdf_text and "Farm 14" in pdf_text
        assert "4–5 days" in pdf_text and "85.5" in pdf_text and "Juan Dela Cruz" in pdf_text


def test_xlsx_preserves_whitespace_and_null_optional_values_are_blank(export_app, logs_db):
    admin = account(logs_db, role="Admin")
    owner = account(logs_db, name="  00123  ")
    identifier = scan(logs_db, owner, confidence=90, prediction="5-7", source=None)
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == identifier,
    ).values(
        cultivar=None, ripeness=None, confidence=None,
        spoilage_days=None, temperature=None, humidity=None,
    ))
    export_app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(export_app) as client:
        xlsx_result = client.get("/api/v1/scan-logs/export", params={"format": "xlsx"})
        assert xlsx_result.status_code == 200, xlsx_result.text
        root, rows = workbook_rows(xlsx_result.content)
        assert rows[1]["A2"] == (format_scan_ref(identifier), "inlineStr")
        assert rows[1]["N2"] == ("  00123  ", "inlineStr")
        assert root.findall("m:sheetData/m:row", NS)[1].find(
            "m:c[@r='N2']/m:is/m:t", NS,
        ).attrib[XML_SPACE] == "preserve"
        # Optional fields (Source, Cultivar, Ripeness, Shelf Life, Freshness, Confidence, Temp, Humidity) are blank.
        for ref in ("C2", "D2", "E2", "G2", "H2", "K2", "L2", "M2"):
            assert rows[1][ref][0] is None, (ref, rows[1][ref])

        export_app.dependency_overrides[get_current_user] = lambda: admin
        config_xlsx = client.get("/api/v1/config/export", params={"format": "xlsx"})
        assert config_xlsx.status_code == 200, config_xlsx.text
        _, config_rows = workbook_rows(config_xlsx.content)
        for ref in ("C2", "D2", "E2", "G2", "H2", "K2", "L2", "M2"):
            assert config_rows[1][ref][0] is None, (ref, config_rows[1][ref])


def test_number_text_keeps_exact_integer_and_decimal_values():
    huge = 10 ** 400
    assert number_text(huge) == str(huge)
    assert number_text(Decimal("1.123456789012345678")) == "1.123456789012345678"
    assert number_text(Decimal("2.00")) == "2"
    assert number_text(None) is None


def test_empty_exports_keep_headers_and_media_contract(export_app, logs_db):
    empty = account(logs_db)
    export_app.dependency_overrides[get_current_user] = lambda: empty
    with TestClient(export_app) as client:
        xlsx_result = client.get("/api/v1/scan-logs/export")
        assert xlsx_result.status_code == 200
        assert xlsx_result.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        headers, rows = workbook_table(xlsx_result.content)
        assert headers == SCAN_EXPORT_HEADERS
        assert rows == []

        pdf_result = client.get("/api/v1/scan-logs/export", params={"format": "pdf"})
        assert pdf_result.status_code == 200
        assert pdf_result.headers["content-type"] == "application/pdf"
        pages, text = extract_pdf_text(pdf_result.content)
        assert len(pages) == 1
        assert "Total records: 0" in text
        assert "No matching records." in text
        assert "Scan" in text and "Ref" in text and "Operator" in text
