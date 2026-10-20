"""One SQL filter pipeline for Scan Logs, full-result metrics and streamed CSV."""

from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
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
from app.services.scan_evidence import evidence_url
from app.services.scan_snapshots import (
    MAX_ROWS,
    binding,
    load_snapshot,
    save_snapshot,
    slice_snapshot,
)


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
    if query.flagged_only and query.attention != "review":
        conditions.append(scans.c.flagged.is_(True))
    if query.attention == "at-risk":
        conditions.append(dashboard._expiring(scans))
    elif query.attention == "review":
        conditions.append(dashboard._review(scans, threshold))
    elif query.attention == "success":
        conditions.append(dashboard._successful(scans, threshold))
    if query.search and query.search.strip():
        text = query.search.strip().lower()
        try:
            exact_uuid = UUID(text)
            conditions.append(scans.c.id == exact_uuid)
        except ValueError:
            fields = [
                cast(scans.c.id, String), scans.c.operator_name, scans.c.username,
                scans.c.source_name,
                func.replace(cast(scans.c.cultivar, String), "_", " "),
                func.replace(cast(scans.c.ripeness, String), "_", " "),
                func.replace(cast(scans.c.inventory_status, String), "_", " "),
            ]
            matches = [func.lower(field).contains(text, autoescape=True) for field in fields]
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
        revision=row.revision,
        temperature=None if row.temperature is None else float(row.temperature),
        humidity=None if row.humidity is None else float(row.humidity),
        vpd=None if row.vpd is None else float(row.vpd),
        finger_count=row.finger_count if row.finger_count is not None else 0,
        thumbnail_url=evidence_url(row.thumbnail_url),
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


def _snapshot_key(query):
    # Page size changes only the slice, never the authorized record set.
    return binding("logs", query.model_dump(
        mode="json", exclude={"page", "page_size", "snapshot_id", "stable", "limit"},
    ))


async def _snapshot(db, user, query):
    """Allow only an at-risk subset of the same authorized, frozen result."""
    try:
        return await load_snapshot(db, user, query.snapshot_id, _snapshot_key(query))
    except HTTPException as error:
        if error.status_code != 409 or query.attention != "at-risk":
            raise
    for attention in ("all", "review", "success"):
        try:
            saved = await load_snapshot(
                db, user, query.snapshot_id,
                _snapshot_key(query.model_copy(update={"attention": attention})),
            )
        except HTTPException as error:
            if error.status_code != 409:
                raise
            continue
        # Private snapshot bookkeeping, never a DB column or API schema field.
        # Older snapshots need refreshing rather than guessing from rounded values.
        if any("_at_risk" not in row for row in saved.payload["items"]):
            raise HTTPException(410, "Refresh to obtain an updated browse snapshot.")
        rows = [row for row in saved.payload["items"] if row["_at_risk"]]
        scores = [row["confidence"] for row in rows if row["confidence"] is not None]
        meta = saved.payload["meta"]
        return SimpleNamespace(id=saved.id, expires_at=saved.expires_at, payload={
            "items": rows,
            "meta": {
                **meta,
                "at_risk_count": len(rows),
                "avg_confidence": dashboard._mean(sum(scores) / len(scores)) if scores else None,
                "review_count": sum(
                    row["flagged"] or (
                        row["confidence"] is not None
                        and row["confidence"] < meta["confidence_threshold"]
                    ) for row in rows
                ),
                "flagged_count": sum(row["flagged"] for row in rows),
            },
        })
    raise HTTPException(409, "Browse filters changed. Refresh to start a new snapshot.")


async def list_scan_logs(
    db: AsyncSession, user: UserAccount, query: ScanLogQuery,
) -> ScanLogList:
    key = _snapshot_key(query)
    if query.snapshot_id:
        saved = await _snapshot(db, user, query)
        return ScanLogList(**slice_snapshot(saved, query.page, query.page_size))
    if query.stable:
        from app.services.auth_service import lock_current_account
        user = await lock_current_account(db, user)
    now = dashboard.now_manila()
    scans = dashboard._scoped_projection(user, now)
    threshold = await dashboard._threshold(db)
    conditions = _conditions(scans, query, threshold)
    if query.stable:
        raw = (
            await db.execute(
                select(scans, dashboard._expiring(scans).label("at_risk"))
                .where(*conditions)
                .order_by(*_ordering(scans, query))
                .limit(MAX_ROWS + 1)
            )
        ).all()
        rows = [_row(row) for row in raw]
        scores = [row.confidence for row in rows if row.confidence is not None]
        # Capture the same unrounded stock/risk decision used by filters and metrics.
        # Never reclassify from rounded remaining days or the displayed range.
        # No history/notes or credentials are included in browse payloads.
        saved = await save_snapshot(
            db,
            user,
            key,
            {
                "items": [
                    {**row.model_dump(mode="json"), "username": source.username,
                     "_at_risk": bool(source.at_risk)}
                    for row, source in zip(rows, raw, strict=True)
                ],
                "meta": {
                    "generated_at": now.isoformat(),
                    "confidence_threshold": threshold,
                    "avg_confidence": dashboard._mean(sum(scores) / len(scores))
                    if scores
                    else None,
                    "at_risk_count": sum(bool(row.at_risk) for row in raw),
                    "review_count": sum(
                        row.flagged or (row.confidence is not None and row.confidence < threshold)
                        for row in rows
                    ),
                    "flagged_count": sum(row.flagged for row in rows),
                    "options": (await _options(db, scans)).model_dump(mode="json"),
                },
            },
        )
        return ScanLogList(**slice_snapshot(saved, query.page, query.page_size))
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
        select(scans)
        .where(*conditions).order_by(*_ordering(scans, query))
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
        select(scans)
        .where(*_conditions(scans, query, threshold))
        .order_by(*_ordering(scans, query)).execution_options(yield_per=200)
    )
    # Start the query before HTTP headers are sent, so initial DB failures propagate.
    if query.snapshot_id:
        saved = await _snapshot(db, user, query)

        class SnapshotRows:
            async def partitions(self, size):
                for start in range(0, len(saved.payload["items"]), size):
                    yield saved.payload["items"][start:start + size]

            async def close(self):
                pass

        result = SnapshotRows()
    else:
        result = await db.stream(statement)

    async def contents():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Scan ID", "Scanned At (UTC+08:00)", "Operator", "Operator Username", "Source",
            "Cultivar", "Ripeness", "Confidence (%)", "Inventory Status", "Flagged",
            "Original Shelf Life (days)", "Remaining Shelf Life (days)", "Finger Count",
            "Temperature (C)", "Humidity (%)", "Intake ID", "Overridden", "Status Updated At (UTC+08:00)",
            "VPD (kPa)",
        ])
        try:
            yield "\ufeff" + output.getvalue()
            async for batch in result.partitions(200):
                output.seek(0)
                output.truncate(0)
                for raw in batch:
                    row = ScanLogRow.model_validate(raw) if query.snapshot_id else _row(raw)
                    username = raw["username"] if query.snapshot_id else raw.username
                    writer.writerow([_safe_cell(cell) for cell in [
                        str(row.id), row.date_time.isoformat(), row.operator_name, username,
                        row.source_name, row.cultivar, row.ripeness, row.confidence,
                        row.inventory_status, row.flagged, row.spoilage_days, row.remaining_days,
                        row.finger_count, row.temperature, row.humidity,
                        str(row.intake_id) if row.intake_id else None, row.is_overridden,
                        row.status_updated_at.isoformat() if row.status_updated_at else None,
                        None if row.vpd is None else f"{row.vpd:.3f}",
                    ]])
                yield output.getvalue()
        finally:
            await result.close()

    return contents()
