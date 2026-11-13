"""Lossless export contracts using isolated SQL fixtures and workbook XML."""

# Imported pytest fixtures intentionally share names with test parameters.
# ruff: noqa: F811

import csv
import io
import xml.etree.ElementTree as ET
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
from app.core.xlsx import number_text
from app.models.scan_classification import ScanClassification
from app.schemas.scan_logs import ScanLogQuery
from app.services import auth_service, scan_logs
from tests.test_dashboard import NOW, account, db, scan  # noqa: F401
from tests.test_scan_logs import logs_db  # noqa: F401

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


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


def test_scan_excel_all_rows_filters_permissions_and_full_text(
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

    async def load(_db, _user, token, key):
        saved = snapshots[token]
        if key != saved.binding:
            raise HTTPException(409, "Browse filters changed")
        return saved

    monkeypatch.setattr(auth_service, "lock_current_account", lock)
    monkeypatch.setattr(scan_logs, "save_snapshot", save)
    monkeypatch.setattr(scan_logs, "load_snapshot", load)
    prediction = "1.123456789012345678"
    source = '日本語, "Saging"\n' + "source " * 20
    expected = [scan(logs_db, own, at=NOW - timedelta(seconds=i),
                     source=source, prediction=prediction, confidence=0) for i in range(205)]
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
        assert len(rows) == 206
        assert [row[f"A{i + 2}"][0] for i, row in enumerate(rows[1:])] == [
            str(identifier) for identifier in expected
        ]
        assert rows[1]["C2"] == ("=SUM(1,2)", "inlineStr")
        assert rows[1]["E2"] == (source.strip(), "inlineStr")
        assert rows[1]["K2"] == (prediction, "inlineStr")
        assert rows[1]["B2"][0].endswith("+08:00")
        assert rows[1]["B2"][1] == "inlineStr"
        assert rows[1]["H2"] == rows[1]["M2"] == rows[1]["N2"] == ("0", "n")
        assert rows[1]["J2"] == ("0", "b")
        assert rows[1]["P2"][0] is None
        columns = root.findall("m:cols/m:col", NS)
        assert all(12 <= float(column.attrib["width"]) <= 81 for column in columns)
        assert max(float(column.attrib["width"]) for column in columns) >= 80
        assert float(root.findall("m:sheetData/m:row", NS)[1].attrib["ht"]) > 36
        with ZipFile(io.BytesIO(result.content)) as archive:
            styles = ET.fromstring(archive.read("xl/styles.xml"))
            assert styles.findall('.//m:alignment[@wrapText="1"]', NS)
            assert not any("hyperlink" in name for name in archive.namelist())
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            assert all(
                text.attrib.get(XML_SPACE) == "preserve"
                for text in sheet.findall(".//m:t", NS)
            )

        listing = client.get("/api/v1/scan-logs", params={
            "stable": True, "page_size": 1, "source": source,
        })
        assert listing.status_code == 200, listing.text
        token = listing.json()["snapshot_id"]
        snapshot = client.get("/api/v1/scan-logs/export", params={
            "format": "xlsx", "snapshot_id": token, "source": source,
            "page": 99, "limit": 1,
        })
        assert snapshot.status_code == 200, snapshot.text
        assert len(workbook_rows(snapshot.content)[1]) == 206
        denied = client.get("/api/v1/scan-logs/export", params={
            "format": "xlsx", "operator_id": str(other.operator_id),
        })
        assert len(workbook_rows(denied.content)[1]) == 1
        assert client.get("/api/v1/scan-logs/export", params={"format": "pdf"}).status_code == 422
        assert client.get("/api/v1/scan-logs/export", params={
            "format": "xlsx", "page_size": 101,
        }).status_code == 422


def test_config_excel_and_csv_same_complete_summary_and_admin_scope(export_app, logs_db):
    admin, operator = account(logs_db, role="Admin"), account(logs_db)
    for i in range(205):
        scan(logs_db, operator, at=NOW + timedelta(seconds=i), confidence=0)
    export_app.dependency_overrides[get_current_user] = lambda: operator
    with TestClient(export_app) as client:
        for kind in ("csv", "xlsx"):
            assert client.get("/api/v1/config/export", params={"format": kind}).status_code == 403
        export_app.dependency_overrides[get_current_user] = lambda: admin
        csv_result = client.get("/api/v1/config/export")
        assert csv_result.status_code == 200
        csv_data = list(csv.reader(io.StringIO(csv_result.text)))
        assert len(csv_data) == 206
        excel_result = client.get("/api/v1/config/export", params={"format": "xlsx"})
        assert excel_result.status_code == 200
        _, rows = workbook_rows(excel_result.content)
        assert len(rows) == len(csv_data)
        assert rows[0]["A1"][0] == csv_data[0][0] == "Scan ID"
        assert [row[f"A{i + 2}"][0] for i, row in enumerate(rows[1:])] == [
            row[0] for row in csv_data[1:]
        ]
        assert rows[1]["E2"] == ("0", "n")
        assert rows[1]["F2"] == ("N/A", "inlineStr")
        assert client.get("/api/v1/config/export", params={"format": "pdf"}).status_code == 422


@pytest.mark.asyncio
async def test_csv_full_precision_and_special_values_remain_unchanged(logs_db):
    own = account(logs_db, name='=HYPERLINK("https://example.test")')
    prediction = "1.123456789012345678"
    source = '日本語, "banana"\n' + "long " * 60
    identifier = scan(logs_db, own, prediction=prediction, source=source, confidence=0)
    chunks = await scan_logs.export_scan_logs(logs_db, own, ScanLogQuery())
    rows = list(csv.DictReader(io.StringIO("".join([c async for c in chunks]).lstrip("\ufeff"))))
    assert rows[0]["Scan ID"] == str(identifier)
    assert rows[0]["Source"] == source.strip()
    assert rows[0]["Est. Original Shelf Life (days)"] == prediction
    assert rows[0]["Confidence (%)"] == "0.0"
    assert rows[0]["Operator"] == '\'=HYPERLINK("https://example.test")'


def test_xlsx_preserves_whitespace_precision_ranges_and_config_values(export_app, logs_db):
    admin = account(logs_db, role="Admin")
    owner = account(logs_db, name="  00123  ")
    identifier = scan(
        logs_db, owner, confidence=92.123456789, prediction="3-4",
        source="  Farm 001  ",
    )
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == identifier,
    ).values(temperature=22.29, humidity=53.37, vpd=1.555))
    export_app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(export_app) as client:
        result = client.get("/api/v1/scan-logs/export", params={"format": "xlsx"})
        assert result.status_code == 200, result.text
        root, rows = workbook_rows(result.content)
        assert rows[1]["C2"] == ("  00123  ", "inlineStr")
        assert rows[1]["E2"] == ("Farm 001", "inlineStr")
        # Confidence is DECIMAL(5,2); the export must not truncate it further.
        assert rows[1]["H2"] == ("92.12", "n")
        assert rows[1]["K2"] == ("3-4", "inlineStr")
        assert rows[1]["L2"][1] == "n"
        assert rows[1]["N2"] == ("22.29", "n")
        assert rows[1]["O2"] == ("53.37", "n")
        assert rows[1]["S2"] == ("1.555", "n")
        assert root.findall("m:sheetData/m:row", NS)[1].find(
            "m:c[@r='C2']/m:is/m:t", NS,
        ).attrib[XML_SPACE] == "preserve"

        export_app.dependency_overrides[get_current_user] = lambda: admin
        config_result = client.get("/api/v1/config/export", params={"format": "xlsx"})
        assert config_result.status_code == 200, config_result.text
        _, config_rows = workbook_rows(config_result.content)
        row = next(row for row in config_rows if row.get("A2") is not None
                   and row["A2"][0] == str(identifier))
        assert row["E2"] == ("92.12", "n")


def test_xlsx_null_optional_values_are_blank_like_csv(export_app, logs_db):
    admin = account(logs_db, role="Admin")
    owner = account(logs_db)
    identifier = scan(logs_db, owner, confidence=90, prediction="5-7")
    logs_db.session.execute(update(ScanClassification).where(
        ScanClassification.scan_id == identifier,
    ).values(cultivar=None, ripeness=None, confidence=None, spoilage_days=None))
    export_app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(export_app) as client:
        csv_result = client.get("/api/v1/scan-logs/export")
        assert csv_result.status_code == 200
        csv_row = next(csv.DictReader(
            io.StringIO(csv_result.text.lstrip("\ufeff")),
        ))
        assert csv_row["Cultivar"] == ""
        assert csv_row["Ripeness"] == ""
        assert csv_row["Confidence (%)"] == ""
        assert csv_row["Est. Original Shelf Life (days)"] == ""

        xlsx_result = client.get(
            "/api/v1/scan-logs/export", params={"format": "xlsx"},
        )
        assert xlsx_result.status_code == 200, xlsx_result.text
        _, rows = workbook_rows(xlsx_result.content)
        for reference in ("F2", "G2", "H2", "K2"):
            assert rows[1][reference][0] is None, (reference, rows[1][reference])

        export_app.dependency_overrides[get_current_user] = lambda: admin
        config_csv = client.get("/api/v1/config/export")
        assert config_csv.status_code == 200
        config_csv_row = list(csv.reader(io.StringIO(config_csv.text)))[1]
        assert config_csv_row[2:5] == ["", "", ""]

        config_xlsx = client.get(
            "/api/v1/config/export", params={"format": "xlsx"},
        )
        assert config_xlsx.status_code == 200, config_xlsx.text
        _, config_rows = workbook_rows(config_xlsx.content)
        config_row = next(
            row for row in config_rows[1:]
            if row.get("A2") and row["A2"][0] == str(identifier)
        )
        for reference in ("C2", "D2", "E2"):
            assert config_row[reference][0] is None, (
                reference, config_row[reference],
            )


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
        csv_result = client.get("/api/v1/scan-logs/export")
        assert csv_result.status_code == 200
        assert len(list(csv.reader(io.StringIO(csv_result.text.lstrip("\ufeff"))))) == 1
        xlsx_result = client.get("/api/v1/scan-logs/export", params={"format": "xlsx"})
        assert xlsx_result.status_code == 200
        _, rows = workbook_rows(xlsx_result.content)
        assert len(rows) == 1
        assert rows[0]["A1"] == ("Scan ID", "inlineStr")
