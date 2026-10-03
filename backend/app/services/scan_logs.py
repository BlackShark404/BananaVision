"""One SQL filter pipeline for Scan Logs, full-result metrics and streamed CSV."""

from __future__ import annotations

import csv
import io
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_account import UserAccount
from app.schemas.scan_logs import (
    OperatorOption,
    ScanLogList,
    ScanLogOptions,
    ScanLogQuery,
    ScanLogRow,
    SourceOption,
)
from app.services import dashboard


def _conditions(scans, query: ScanLogQuery, threshold: float):
    conditions = []
    if query.business_date is not None:
        conditions.append(dashboard._day(scans, query.business_date))
    if query.source_key is not None:
        conditions.append(dashboard._source_filter(scans, query.source_key))
    elif query.source is not None:
        # Compatibility for old name-based links. Stable keys remain authoritative.
        name = query.source.strip()
        conditions.append(or_(
            scans.c.source_name == name,
            func.btrim(scans.c.original_source_text, dashboard.WHITESPACE) == name,
            func.btrim(scans.c.legacy_intake_source, dashboard.WHITESPACE) == name,
        ))
    for name in ("operator_id", "intake_id", "cultivar", "ripeness", "inventory_status"):
        value = getattr(query, name)
        if value is not None:
            conditions.append(getattr(scans.c, name) == value)
    if query.flagged_only:
        conditions.append(scans.c.flagged.is_(True))
    if query.attention == "at-risk":
        conditions.append(dashboard._expiring(scans))
    elif query.attention == "review":
        conditions.append(dashboard._review(scans, threshold))
    if query.search and query.search.strip():
        text = query.search.strip().lower()
        fields = [
            cast(scans.c.id, String), scans.c.operator_name, scans.c.username,
            scans.c.source_name,
            func.replace(cast(scans.c.cultivar, String), "_", " "),
            func.replace(cast(scans.c.ripeness, String), "_", " "),
            func.replace(cast(scans.c.inventory_status, String), "_", " "),
        ]
        matches = [func.lower(field).contains(text, autoescape=True) for field in fields]
        try:
            matches.append(scans.c.id == UUID(text))
        except ValueError:
            pass
        conditions.append(or_(*matches))
    return conditions


def _ordering(scans, query: ScanLogQuery):
    columns = {
        "date_time": scans.c.date_time,
        "cultivar": cast(scans.c.cultivar, String),
        "confidence": scans.c.confidence,
        "spoilage_days": scans.c.predicted_days,
        "finger_count": scans.c.finger_count,
    }
    column = columns[query.sort]
    primary = column.asc() if query.direction == "asc" else column.desc()
    # A stable ID tiebreak prevents rows moving between pages with equal values.
    return [primary.nulls_last(), scans.c.date_time.desc(), scans.c.id.desc()]


def _row(row) -> ScanLogRow:
    return ScanLogRow(
        **dashboard._scan(row).model_dump(),
        temperature=None if row.temperature is None else float(row.temperature),
        humidity=None if row.humidity is None else float(row.humidity),
        finger_count=row.finger_count if row.finger_count is not None else 0,
        thumbnail_url=row.thumbnail_url,
        intake_id=row.intake_id,
        is_overridden=bool(row.is_overridden),
        status_updated_at=(
            None if row.status_updated_at is None else dashboard.as_manila(row.status_updated_at)
        ),
    )


async def _options(db: AsyncSession, scans) -> ScanLogOptions:
    source_rows = (await db.execute(
        select(scans.c.supplier_id, scans.c.source_text, scans.c.source_name)
        .distinct().order_by(scans.c.source_name, scans.c.supplier_id, scans.c.source_text)
    )).all()
    operator_rows = (await db.execute(
        select(scans.c.operator_id, scans.c.operator_name, scans.c.username)
        .distinct().order_by(scans.c.operator_name, scans.c.username, scans.c.operator_id)
    )).all()
    return ScanLogOptions(
        sources=[SourceOption(key=dashboard._source(r)[0], name=r.source_name) for r in source_rows],
        operators=[OperatorOption(
            operator_id=r.operator_id, name=r.operator_name, username=r.username,
        ) for r in operator_rows],
    )


async def list_scan_logs(
    db: AsyncSession, user: UserAccount, query: ScanLogQuery,
) -> ScanLogList:
    now = dashboard.now_manila()
    scans = dashboard._scoped_projection(user, now)
    threshold = await dashboard._threshold(db)
    conditions = _conditions(scans, query, threshold)
    metrics = (await db.execute(
        select(
            func.count().label("total"),
            func.avg(scans.c.confidence).label("avg_confidence"),
            func.count().filter(dashboard._expiring(scans)).label("at_risk"),
            func.count().filter(dashboard._review(scans, threshold)).label("review"),
            func.count().filter(scans.c.flagged.is_(True)).label("flagged"),
        ).select_from(scans).where(*conditions)
    )).one()
    rows = (await db.execute(
        select(scans).where(*conditions).order_by(*_ordering(scans, query))
        .offset((query.page - 1) * query.page_size).limit(query.page_size)
    )).all()
    return ScanLogList(
        items=[_row(row) for row in rows], total=metrics.total,
        page=query.page, page_size=query.page_size,
        avg_confidence=dashboard._mean(metrics.avg_confidence),
        at_risk_count=metrics.at_risk, review_count=metrics.review, flagged_count=metrics.flagged,
        generated_at=now, confidence_threshold=threshold,
        options=await _options(db, scans),
    )


def _safe_cell(value):
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


async def export_scan_logs(db: AsyncSession, user: UserAccount, query: ScanLogQuery):
    """Return a stream over ALL matching records, with bounded fetch/output buffers."""
    now = dashboard.now_manila()
    scans = dashboard._scoped_projection(user, now)
    threshold = await dashboard._threshold(db)
    statement = (
        select(scans).where(*_conditions(scans, query, threshold))
        .order_by(*_ordering(scans, query)).execution_options(yield_per=200)
    )
    # Start the query before HTTP headers are sent, so initial DB failures propagate.
    result = await db.stream(statement)

    async def contents():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Scan ID", "Scanned At (UTC+08:00)", "Operator", "Operator Username", "Source",
            "Cultivar", "Ripeness", "Confidence (%)", "Inventory Status", "Flagged",
            "Original Shelf Life (days)", "Remaining Shelf Life (days)", "Finger Count",
            "Temperature (C)", "Humidity (%)", "Intake ID", "Overridden", "Status Updated At (UTC+08:00)",
        ])
        try:
            yield "\ufeff" + output.getvalue()
            async for batch in result.partitions(200):
                output.seek(0)
                output.truncate(0)
                for raw in batch:
                    row = _row(raw)
                    writer.writerow([_safe_cell(cell) for cell in [
                        str(row.id), row.date_time.isoformat(), row.operator_name, raw.username,
                        row.source_name, row.cultivar, row.ripeness, row.confidence,
                        row.inventory_status, row.flagged, row.spoilage_days, row.remaining_days,
                        row.finger_count, row.temperature, row.humidity,
                        str(row.intake_id) if row.intake_id else None, row.is_overridden,
                        row.status_updated_at.isoformat() if row.status_updated_at else None,
                    ]])
                yield output.getvalue()
        finally:
            await result.close()

    return contents()
