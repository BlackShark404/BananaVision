"""One SQL filter pipeline for Scan Logs, full-result metrics and Excel/PDF exports."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, cast, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.export_format import (
    SCAN_EXPORT_HEADERS,
    ExportCell,
    format_manila_date,
    format_scan_export_cells,
    to_pdf_rows,
    to_xlsx_rows,
)
from app.core.pdf import build_pdf
from app.core.time import as_manila
from app.core.xlsx import build_xlsx
from app.models.intake import Intake
from app.models.operator_profile import OperatorProfile
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.supplier import Supplier
from app.models.user_account import UserAccount
from app.schemas.scan_logs import (
    OperatorOption,
    ScanLogList,
    ScanLogOptions,
    ScanLogPending,
    ScanLogQuery,
    ScanLogReconciliation,
    ScanLogRow,
    SourceOption,
)
from app.services import dashboard
from app.services.inventory_policy import eligible_stock, shelf_life_window
from app.services.scan_evidence import thumbnail_url
from app.services.scan_snapshots import (
    MAX_ROWS,
    binding,
    load_snapshot,
    save_snapshot,
    slice_snapshot,
)

EXPORT_HEADERS = SCAN_EXPORT_HEADERS


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
    if query.stock_eligible:
        conditions.append(eligible_stock(scans))
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
        ref_candidate = text.removeprefix("scan-").strip() if text.startswith("scan-") else text
        try:
            exact_uuid = UUID(ref_candidate)
            conditions.append(scans.c.id == exact_uuid)
        except ValueError:
            compact_id = func.replace(func.lower(cast(scans.c.id, String)), "-", "")
            fields = [
                cast(scans.c.id, String), scans.c.operator_name, scans.c.username,
                scans.c.source_name,
                func.replace(cast(scans.c.cultivar, String), "_", " "),
                func.replace(cast(scans.c.ripeness, String), "_", " "),
                func.replace(cast(scans.c.inventory_status, String), "_", " "),
            ]
            matches = [func.lower(field).contains(text, autoescape=True) for field in fields]
            compact_query = text.replace("-", "")
            if compact_query:
                matches.append(compact_id.contains(compact_query, autoescape=True))
            if text.startswith("scan-") and ref_candidate:
                compact_ref = ref_candidate.replace("-", "")
                if compact_ref:
                    matches.append(compact_id.startswith(compact_ref, autoescape=True))
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


def _row(row, now: datetime) -> ScanLogRow:
    return ScanLogRow(
        **dashboard._scan(row, now).model_dump(),
        revision=row.revision,
        temperature=None if row.temperature is None else float(row.temperature),
        humidity=None if row.humidity is None else float(row.humidity),
        vpd=None if row.vpd is None else float(row.vpd),
        finger_count=row.finger_count if row.finger_count is not None else 0,
        thumbnail_url=thumbnail_url(row.thumbnail_url),
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
        mode="json", exclude={"page", "page_size", "snapshot_id", "stable", "limit", "format"},
    ))


async def _snapshot(db, user, query, *, lock=True):
    """Allow only an at-risk subset of the same authorized, frozen result."""
    try:
        return await load_snapshot(db, user, query.snapshot_id, _snapshot_key(query), lock=lock)
    except HTTPException as error:
        if error.status_code != 409 or query.attention != "at-risk":
            raise
    for attention in ("all", "review", "success"):
        try:
            saved = await load_snapshot(
                db, user, query.snapshot_id,
                _snapshot_key(query.model_copy(update={"attention": attention})), lock=lock,
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
                # The review queue is the flagged scans (dashboard._review).
                "review_count": sum(bool(row["flagged"]) for row in rows),
                "flagged_count": sum(row["flagged"] for row in rows),
            },
        })
    raise HTTPException(409, "Browse filters changed. Refresh to start a new snapshot.")


def _snapshot_watermark(snapshot) -> tuple[datetime, str | None]:
    """Return the newest row included in the frozen filtered result.

    Older snapshots only carry ``generated_at``; they remain readable and fall
    back to that boundary until their short lifetime installs a new snapshot.
    """
    meta = snapshot.payload.get("meta", {})
    marker = meta.get("watermark") or {}
    raw = marker.get("date_time") or meta.get("generated_at")
    if not raw:
        raise HTTPException(409, "Refresh to start a new browse snapshot.")
    return as_manila(datetime.fromisoformat(raw)), marker.get("id")


async def _new_scan_count(
    db: AsyncSession, user: UserAccount, snapshot, query: ScanLogQuery,
) -> int:
    """Count only committed scans newer than this snapshot's watermark.

    The query reuses the exact account scope and filter predicates that built
    the snapshot. Therefore scans outside the operator scope, tied to another
    filter, or not matching the selected attention card never raise the notice.
    """
    meta = snapshot.payload.get("meta", {})
    scans = dashboard._scoped_projection(user, dashboard.now_manila())
    threshold = (
        float(meta["confidence_threshold"])
        if meta.get("confidence_threshold") is not None
        else await dashboard._threshold(db)
    )
    since, watermark_id = _snapshot_watermark(snapshot)
    boundary = scans.c.date_time > since
    if watermark_id:
        # A same-instant tie is ordered by UUID value, matching the
        # deterministic ID tiebreak used by the snapshot query. Compare the
        # native UUID type: casting to text differs between PostgreSQL (dashed)
        # and SQLite (32 hex characters).
        boundary = or_(
            boundary,
            and_(scans.c.date_time == since, scans.c.id > UUID(watermark_id)),
        )
    total = await db.scalar(
        select(func.count()).select_from(scans)
        .where(*_conditions(scans, query, threshold), boundary)
    )
    return int(total or 0)


async def pending_scan_count(
    db: AsyncSession, user: UserAccount, query: ScanLogQuery,
) -> ScanLogPending:
    """Authoritative count for the live update prompt; the snapshot stays frozen."""
    saved = await _snapshot(db, user, query)
    meta = saved.payload.get("meta", {})
    return ScanLogPending(
        snapshot_id=saved.id,
        new_count=await _new_scan_count(db, user, saved, query),
        generated_at=meta.get("generated_at") or dashboard.now_manila(),
    )


async def reconcile_scan_logs(
    db: AsyncSession, user: UserAccount, query: ScanLogQuery,
) -> ScanLogReconciliation:
    """Overlay a frozen page with current values without mutating its snapshot.

    Membership and order come only from the authorized snapshot slice. Current
    account scope and filters can remove rows, but never backfill the page.
    Metrics deliberately cover the entire current authorized filtered result.
    """
    saved = await _snapshot(db, user, query)
    frozen = slice_snapshot(saved, query.page, query.page_size)["items"]
    identifiers = [UUID(row["id"]) for row in frozen]
    now = dashboard.now_manila()
    scans = dashboard._scoped_projection(user, now)
    threshold = await dashboard._threshold(db)
    conditions = _conditions(scans, query, threshold)
    metrics_query = (
        select(
            func.count().label("live_total"),
            func.avg(scans.c.confidence).label("live_avg_confidence"),
            func.count().filter(dashboard._expiring(scans)).label("live_at_risk"),
            func.count().filter(dashboard._review(scans, threshold)).label("live_review"),
            func.count().filter(scans.c.flagged.is_(True)).label("live_flagged"),
        ).select_from(scans).where(*conditions)
    ).subquery("live_metrics")
    page_query = (
        select(scans, dashboard._expiring(scans).label("at_risk"))
        .where(*conditions, scans.c.id.in_(identifiers))
    ).subquery("live_page")
    # One SQL statement gives page values and whole-filter metrics the same
    # PostgreSQL read view even when another session commits during this read.
    rows = (await db.execute(
        select(metrics_query, page_query)
        .select_from(metrics_query.outerjoin(page_query, true()))
    )).all()
    metrics = rows[0]
    current = {row.id: row for row in rows if row.id is not None}
    ordered = [current[identifier] for identifier in identifiers if identifier in current]
    return ScanLogReconciliation(
        snapshot_id=saved.id, items=[_row(row, now) for row in ordered],
        at_risk_ids=[row.id for row in ordered if row.at_risk],
        total=metrics.live_total, avg_confidence=dashboard._mean(metrics.live_avg_confidence),
        at_risk_count=metrics.live_at_risk, review_count=metrics.live_review,
        flagged_count=metrics.live_flagged,
        confidence_threshold=threshold, generated_at=now,
    )


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
        rows = [_row(row, now) for row in raw]
        scores = [row.confidence for row in rows if row.confidence is not None]
        watermark_row = max(
            raw, key=lambda row: (as_manila(row.date_time), row.id.int), default=None
        )
        overridden_ids = [source.id for source in raw if source.is_overridden]
        original_counts = await _original_finger_counts(db, overridden_ids)
        # Capture the same unrounded stock/risk decision used by filters and metrics.
        # Never reclassify from rounded remaining days or the displayed range.
        # No history/notes or credentials are included in browse payloads.
        saved = await save_snapshot(
            db,
            user,
            key,
            {
                "items": [
                    {
                        **row.model_dump(mode="json"),
                        "username": source.username,
                        "_at_risk": bool(source.at_risk),
                        "_has_finger_count": source.finger_count is not None,
                        **(
                            {"_original_finger_count": original_counts[source.id]}
                            if source.id in original_counts
                            else {}
                        ),
                    }
                    for row, source in zip(rows, raw, strict=True)
                ],
                "meta": {
                    "generated_at": now.isoformat(),
                    # New-scan detection starts after the newest frozen row,
                    # never before the query, so a concurrent commit cannot be
                    # both displayed in this snapshot and announced as new.
                    **({"watermark": {
                        "date_time": as_manila(watermark_row.date_time).isoformat(),
                        "id": str(watermark_row.id),
                    }} if watermark_row else {}),
                    "confidence_threshold": threshold,
                    "avg_confidence": dashboard._mean(sum(scores) / len(scores))
                    if scores
                    else None,
                    "at_risk_count": sum(bool(row.at_risk) for row in raw),
                    "review_count": sum(bool(row.flagged) for row in rows),
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
        items=[_row(row, now) for row in rows], total=metrics.total,
        page=query.page, page_size=query.page_size,
        avg_confidence=dashboard._mean(metrics.avg_confidence),
        at_risk_count=metrics.at_risk, review_count=metrics.review, flagged_count=metrics.flagged,
        generated_at=now, confidence_threshold=threshold,
        options=await _options(db, scans),
    )


async def _original_finger_counts(
    db: AsyncSession, scan_ids: list[UUID],
) -> dict[UUID, int]:
    """Load pre-override AI finger counts for overridden scans only."""
    if not scan_ids:
        return {}
    rows = (await db.execute(
        select(ScanOriginalAiResult.scan_id, ScanOriginalAiResult.finger_count)
        .where(ScanOriginalAiResult.scan_id.in_(scan_ids))
    )).all()
    return {row.scan_id: int(row.finger_count) for row in rows if row.finger_count is not None}


async def _export_filter_summary(db: AsyncSession, query: ScanLogQuery) -> list[str]:
    """Build plain-language filter chips for PDF report headers (no raw UUIDs)."""
    parts: list[str] = []
    if query.business_date is not None:
        parts.append(f"Date: {format_manila_date(query.business_date)}")
    if query.source_key is not None:
        if query.source_key.startswith("supplier:"):
            try:
                supplier_id = UUID(query.source_key.removeprefix("supplier:"))
                supplier_name = await db.scalar(
                    select(Supplier.name).where(Supplier.id == supplier_id)
                )
            except ValueError:
                supplier_name = None
            parts.append(f"Source: {supplier_name or 'Selected supplier'}")
        elif query.source_key.startswith("text:"):
            parts.append(f"Source: {query.source_key[5:]}")
        elif query.source_key == "unknown":
            parts.append("Source: Unknown")
    elif query.source is not None and query.source.strip():
        parts.append(f"Source: {query.source.strip()}")
    if query.operator_id is not None:
        op_name = await db.scalar(
            select(UserAccount.full_name)
            .join(OperatorProfile, OperatorProfile.account_id == UserAccount.id)
            .where(OperatorProfile.id == query.operator_id)
        )
        parts.append(f"Operator: {op_name or 'Selected operator'}")
    if query.intake_id is not None:
        intake = (await db.execute(
            select(Intake.batch_number, Intake.intake_date, Supplier.name)
            .outerjoin(Supplier, Supplier.id == Intake.supplier_id)
            .where(Intake.id == query.intake_id)
        )).first()
        if intake and intake.batch_number:
            parts.append(f"Delivery Batch: {intake.batch_number}")
        elif intake and intake.name:
            parts.append(f"Delivery: {intake.name} ({format_manila_date(intake.intake_date)})")
        else:
            parts.append("Delivery Intake: Filtered")
    if query.cultivar is not None:
        parts.append(f"Cultivar: {query.cultivar.value}")
    if query.ripeness is not None:
        parts.append(f"Ripeness: {query.ripeness.value}")
    if query.inventory_status is not None:
        parts.append(f"Status: {query.inventory_status.value}")
    if query.stock_eligible:
        parts.append("Eligible Stock Only")
    attention_labels = {
        "at-risk": "At-Risk",
        "review": "Needs Review",
        "success": "Approved",
    }
    if query.attention in attention_labels:
        parts.append(f"View: {attention_labels[query.attention]}")
    elif query.flagged_only:
        parts.append("Review: Needs Review")
    if query.search and query.search.strip():
        parts.append(f'Search: "{query.search.strip()}"')
    return parts


async def check_export_snapshot(db: AsyncSession, user: UserAccount, query: ScanLogQuery):
    """Refuse an expired, foreign or changed snapshot before the export is audited.

    The check reads without locking the account row, because the audit insert that follows
    would wait on that lock. The export repeats the locked check when it reads the snapshot.
    """
    if query.snapshot_id:
        await _snapshot(db, user, query, lock=False)


async def _collect_export_data(
    db: AsyncSession, user: UserAccount, query: ScanLogQuery,
) -> tuple[list[list[ExportCell]], datetime, list[str]]:
    """Collect the canonical formatted rows shared by both Excel and PDF exports."""
    now = dashboard.now_manila()
    as_of = now
    scans = dashboard._scoped_projection(user, now)
    threshold = await dashboard._threshold(db)
    statement = (
        select(scans)
        .where(*_conditions(scans, query, threshold))
        .order_by(*_ordering(scans, query)).execution_options(yield_per=200)
    )
    if query.snapshot_id:
        saved = await _snapshot(db, user, query)
        generated_raw = saved.payload.get("meta", {}).get("generated_at")
        if isinstance(generated_raw, str):
            try:
                as_of = as_manila(datetime.fromisoformat(generated_raw))
            except ValueError:
                as_of = now

        class SnapshotRows:
            async def partitions(self, size):
                for start in range(0, len(saved.payload["items"]), size):
                    yield saved.payload["items"][start:start + size]

            async def close(self):
                pass

        result = SnapshotRows()
    else:
        result = await db.stream(statement)

    collected: list[tuple[ScanLogRow, int | None, int | None, dict | None]] = []
    overridden_ids: list[UUID] = []
    try:
        async for batch in result.partitions(200):
            for raw in batch:
                if query.snapshot_id:
                    row = ScanLogRow.model_validate(raw)
                    has_finger_count = raw.get("_has_finger_count", True)
                    finger_count = row.finger_count if has_finger_count else None
                    original_finger_count = raw.get("_original_finger_count")
                    window = shelf_life_window(row.spoilage_days, row.date_time, as_of)
                    collected.append((row, finger_count, original_finger_count, window))
                else:
                    row = _row(raw, as_of)
                    window = (
                        row.shelf_life_window.model_dump()
                        if row.shelf_life_window is not None
                        else None
                    )
                    if row.is_overridden:
                        overridden_ids.append(row.id)
                    collected.append((row, raw.finger_count, None, window))
    finally:
        await result.close()

    original_counts: dict[UUID, int] = {}
    if not query.snapshot_id and overridden_ids:
        for start in range(0, len(overridden_ids), 500):
            original_counts.update(
                await _original_finger_counts(db, overridden_ids[start:start + 500])
            )

    formatted_rows: list[list[ExportCell]] = []
    for row, finger_count, snapshot_original, window in collected:
        source = "" if row.source_key == "unknown" else row.source_name
        original_finger_count = (
            snapshot_original if query.snapshot_id else original_counts.get(row.id)
        )
        formatted_rows.append(format_scan_export_cells(
            scan_id=row.id,
            date_time=row.date_time,
            source_name=source,
            cultivar=row.cultivar,
            ripeness=row.ripeness,
            finger_count=finger_count,
            is_overridden=row.is_overridden,
            original_finger_count=original_finger_count,
            spoilage_days=row.spoilage_days,
            inventory_status=row.inventory_status,
            flagged=row.flagged,
            confidence=row.confidence,
            temperature=row.temperature,
            humidity=row.humidity,
            operator_name=row.operator_name,
            as_of=as_of,
            shelf_life=window,
        ))

    filters = await _export_filter_summary(db, query)
    return formatted_rows, as_of, filters


async def export_scan_logs_xlsx(db: AsyncSession, user: UserAccount, query: ScanLogQuery) -> bytes:
    rows, as_of, _ = await _collect_export_data(db, user, query)
    return build_xlsx(EXPORT_HEADERS, to_xlsx_rows(rows), sheet_name="sheet1", timestamp=as_of)


async def export_scan_logs_pdf(db: AsyncSession, user: UserAccount, query: ScanLogQuery) -> bytes:
    rows, as_of, filters = await _collect_export_data(db, user, query)
    return build_pdf(
        EXPORT_HEADERS,
        to_pdf_rows(rows),
        title="BananaVision — Scan Logs Report",
        filters=filters,
        exported_at=as_of,
        orientation="landscape",
    )
