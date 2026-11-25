"""Asia/Manila is the only clock: log lines, zip member times and source rules.

The station and its users are in Manila. A server, container or laptop set to another
zone must still log, stamp and date everything in Asia/Manila. The data paths already
use app/core/time.py; these tests pin the remaining clock reads and keep new code on it.
"""
import io
import logging
import os
import re
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.time import MANILA
from tests.test_backup_archive import archive_module, backup, station  # noqa: F401

# 00:30 on 2 October in Manila; still 1 October in UTC and in Los Angeles.
INSTANT = datetime(2026, 10, 1, 16, 30, tzinfo=UTC)
MANILA_STAMP = (2026, 10, 2, 0, 30, 0)
BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


@pytest.fixture
def los_angeles():
    """Run with the process clock in Los Angeles to prove nothing reads it."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_log_lines_carry_manila_time_and_say_so(los_angeles):
    import app.main as main

    record = logging.LogRecord("bananavision", logging.INFO, __file__, 1, "ready", None, None)
    record.created = INSTANT.timestamp()
    formatter = logging.Formatter("%(asctime)s", datefmt=main.LOG_DATE_FORMAT)
    assert formatter.format(record) == "2026-10-02 00:30:00 +08:00"
    # Every installed handler reads the same Manila clock (16:30 UTC, 09:30 in Los Angeles).
    for handler in logging.getLogger().handlers:
        if handler.formatter is not None:
            assert "00:30:00" in handler.formatter.formatTime(record, handler.formatter.datefmt)


def test_xlsx_parts_are_stamped_with_the_manila_clock(monkeypatch, los_angeles):
    from app.core import xlsx

    monkeypatch.setattr(xlsx, "now_manila", lambda: INSTANT.astimezone(MANILA))
    with zipfile.ZipFile(io.BytesIO(xlsx.build_xlsx(["Cultivar"], [["Lakatan"]]))) as workbook:
        members = workbook.infolist()
    assert members
    assert {member.date_time for member in members} == {MANILA_STAMP}
    assert {member.compress_type for member in members} == {zipfile.ZIP_DEFLATED}


def test_pdf_metadata_and_header_use_the_manila_clock(monkeypatch, los_angeles):
    from app.core import pdf

    monkeypatch.setattr(pdf, "now_manila", lambda: INSTANT.astimezone(MANILA))
    doc = pdf.build_pdf(["Cultivar"], [["Lakatan"]], title="Clock Test")
    assert b"/CreationDate (D:20261002003000+08'00')" in doc


def test_backup_manifest_is_stamped_with_the_manila_clock(
    archive_module, station, tmp_path, monkeypatch, los_angeles  # noqa: F811
):
    monkeypatch.setattr(archive_module, "now_manila", lambda: INSTANT.astimezone(MANILA))
    with zipfile.ZipFile(backup(archive_module, station, tmp_path)) as archive:
        manifest = archive.getinfo("manifest.json")
    assert manifest.date_time == MANILA_STAMP
    assert manifest.compress_type == zipfile.ZIP_DEFLATED


# ── Source rules: any new clock read must go through app/core/time.py ──

FORBIDDEN = [
    (re.compile(r"datetime\.now\(\s*\)"), "datetime.now() without a zone; use now_manila()"),
    (re.compile(r"datetime\.utcnow\("), "datetime.utcnow(); use now_manila()"),
    (re.compile(r"\b(?:date|datetime)\.today\("), "today() reads the machine zone"),
    (re.compile(r"\btime\.(?:localtime|strftime|ctime|asctime)\("), "process-local clock"),
    (re.compile(r"fromtimestamp\((?![^)]*(?:MANILA|tz))"), "fromtimestamp() without a zone"),
    (re.compile(r"\.writestr\(\s*f?[\"']"), "zip member stamped with the process-local clock"),
]


def _python_sources():
    roots = [BACKEND / "app", BACKEND / "scripts"]
    files = [path for root in roots for path in root.rglob("*.py")]
    files += sorted(BACKEND.glob("*.py")) + sorted(REPO.glob("*.py"))
    return [path for path in files if "__pycache__" not in path.parts]


def test_no_code_reads_a_clock_outside_asia_manila():
    problems = []
    for path in _python_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for pattern, reason in FORBIDDEN:
                if pattern.search(code):
                    problems.append(f"{path.relative_to(REPO)}:{number} {reason}")
    assert problems == []
