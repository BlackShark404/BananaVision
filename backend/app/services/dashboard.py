"""Scoped Dashboard projections and aggregates, without loading ORM graphs.

Review is the set of flagged scans. New scans below the confidence threshold are
flagged when they are saved (fusion_engine), and removing the flag after a check takes a
scan out of the queue; there is no separate persisted human-review state.
Expiry ages the original prediction from scan time and includes overdue stock.
Intake status does not change a scan's inventory status.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import Float, String, and_, case, cast, extract, false, func, literal, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.core.time import MANILA, as_manila, business_day_bounds, now_manila
from app.models.intake import Intake
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_status_log import ScanStatusLog
from app.models.supplier import Supplier
from app.models.system_config import SystemConfig
from app.models.user_account import UserAccount
from app.schemas.dashboard import (
    DashboardFifoRecommendation,
    DashboardOperator,
    DashboardScan,
    DashboardScanList,
    DashboardSort,
    DashboardSource,
    DashboardSummary,
    DashboardView,
)
from app.schemas.enums import InventoryStatusEnum, RoleEnum
from app.services.inventory_policy import (
    PREDICTION_PATTERN,
    WHITESPACE,
    eligible_stock,
    ripeness_projection,
    shelf_life_window,
)
from app.services.sensor_exposure import (
    effective_remaining_days,
    load_buckets_for_query,
    row_exposure,
)

DEFAULT_CONFIDENCE_THRESHOLD = 80.0
FIFO_LIMIT = 5


def _mean(value) -> float | None:
    return None if value is None else round(float(value), 1)


def _prediction_days():
    """Guarded SQL parsing keeps sorting, expiry counts and pagination in the DB.

    Nonnegative scalars and ascending ranges are accepted. Invalid, negative,
    reversed and nonfinite predictions become null instead of expiring stock.
    """
    raw = func.btrim(ScanClassification.spoilage_days, WHITESPACE)
    valid = raw.regexp_match(PREDICTION_PATTERN)
    lower = case((valid, cast(func.split_part(raw, "-", 1), Float)), else_=None)
    upper_text = func.nullif(func.btrim(func.split_part(raw, "-", 2), WHITESPACE), "")
    upper = case((valid, cast(upper_text, Float)), else_=None)
    return case(
        (upper.is_(None), lower),
        (upper >= lower, (lower + upper) / 2.0),
        else_=None,
    )


def _remaining_days(now: datetime):
    elapsed = (literal(now.timestamp()) - extract("epoch", Scan.date_time)) / 86400.0
    return _prediction_days() - elapsed


def _scoped_projection(user: UserAccount, now: datetime):
    role = user.role.name if user.role else None
    if role not in (RoleEnum.ADMIN.value, RoleEnum.OPERATOR.value):
        raise ForbiddenException("Dashboard access requires an Admin or Operator role")

    latest_status = (
        select(ScanStatusLog.inventory_status)
        .where(ScanStatusLog.scan_id == Scan.id)
        .order_by(ScanStatusLog.updated_at.desc(), ScanStatusLog.id.desc())
        .limit(1)
        .correlate(Scan)
        .scalar_subquery()
    )
    latest_status_time = (
        select(ScanStatusLog.updated_at)
        .where(ScanStatusLog.scan_id == Scan.id)
        .order_by(ScanStatusLog.updated_at.desc(), ScanStatusLog.id.desc())
        .limit(1)
        .correlate(Scan)
        .scalar_subquery()
    )
    # Missing status follows the scan pipeline's initial inventory state.
    status = func.coalesce(
        latest_status,
        literal(InventoryStatusEnum.IN_STOCK, type_=ScanStatusLog.inventory_status.type),
    )
    source_text = case(
        (Supplier.id.is_(None), func.nullif(func.btrim(Scan.source_text, WHITESPACE), "")),
        else_=None,
    )
    query = (
        select(
            Scan.id,
            Scan.revision,
            Scan.date_time,
            Scan.flagged,
            Scan.is_overridden,
            Scan.intake_id,
            Scan.intake_origin_id,
            Scan.intake_provenance,
            Intake.status.label("intake_status"),
            Scan.source_text.label("original_source_text"),
            Intake.source.label("legacy_intake_source"),
            Scan.operator_id,
            func.coalesce(Scan.operator_name_snapshot, UserAccount.full_name, "Unknown").label("operator_name"),
            UserAccount.username,
            Supplier.id.label("supplier_id"),
            source_text.label("source_text"),
            func.coalesce(Supplier.name, source_text, "Unknown").label("source_name"),
            ScanClassification.cultivar,
            ScanClassification.ripeness,
            ScanClassification.confidence,
            ScanClassification.spoilage_days,
            ScanClassification.temperature,
            ScanClassification.humidity,
            ScanClassification.vpd,
            ScanClassification.treatment,
            ScanClassification.finger_count,
            ScanClassification.thumbnail_url,
            _prediction_days().label("predicted_days"),
            status.label("inventory_status"),
            latest_status_time.label("status_updated_at"),
            _remaining_days(now).label("remaining_days"),
        )
        .select_from(Scan)
        .join(OperatorProfile, OperatorProfile.id == Scan.operator_id)
        .join(UserAccount, UserAccount.id == OperatorProfile.account_id)
        .outerjoin(ScanClassification, ScanClassification.scan_id == Scan.id)
        .outerjoin(Intake, Intake.id == Scan.intake_id)
        .outerjoin(Supplier, Supplier.id == Intake.supplier_id)
    )
    if role == RoleEnum.OPERATOR.value:
        query = query.where(OperatorProfile.account_id == user.id)
    return query.subquery("dashboard_scans")


def _source(row) -> tuple[str, str]:
    if row.supplier_id is not None:
        return f"supplier:{row.supplier_id}", row.source_name
    if row.source_text is not None:
        return f"text:{row.source_text}", row.source_name
    return "unknown", "Unknown"


def _fifo(row) -> DashboardFifoRecommendation:
    linked = row.intake_id is not None
    scan_id = None if linked else UUID(row.fifo_key)
    return DashboardFifoRecommendation(
        key=f"intake:{row.intake_id}" if linked else f"scan:{scan_id}",
        intake_id=row.intake_id,
        scan_id=scan_id,
        source_name=row.source_name,
        scanned_at=as_manila(row.scanned_at),
        hands=row.hands,
        earliest_remaining_days=(
            None if row.earliest_remaining_days is None
            else round(float(row.earliest_remaining_days), 4)
        ),
    )


def _scan(row, now: datetime, *, buckets=(), bucket_starts=None) -> DashboardScan:
    source_key, source_name = _source(row)
    treatment = getattr(row, "treatment", None)
    treatment_text = treatment.value if hasattr(treatment, "value") else treatment
    exposure = row_exposure(row, now, buckets=buckets, bucket_starts=bucket_starts) if buckets else None
    offset_days = exposure.exposure_offset_days if exposure is not None else 0
    remaining = (
        effective_remaining_days(row, now, buckets=buckets, bucket_starts=bucket_starts)
        if buckets
        else (None if row.remaining_days is None else round(float(row.remaining_days), 4))
    )
    return DashboardScan(
        id=row.id,
        date_time=as_manila(row.date_time),
        cultivar=row.cultivar,
        ripeness=row.ripeness,
        confidence=None if row.confidence is None else float(row.confidence),
        operator_id=row.operator_id,
        operator_name=row.operator_name,
        source_key=source_key,
        source_name=source_name,
        inventory_status=row.inventory_status,
        flagged=bool(row.flagged),
        spoilage_days=row.spoilage_days,
        remaining_days=remaining,
        treatment=treatment_text,
        # Derived from stored scan fields, elapsed Manila days, and continuous DHT22 exposure.
        shelf_life_window=shelf_life_window(
            row.spoilage_days, row.date_time, now, exposure_offset_days=offset_days,
        ),
        ripeness_projection=ripeness_projection(
            row.ripeness,
            row.cultivar,
            row.spoilage_days,
            row.date_time,
            now,
            temperature=getattr(row, "temperature", None),
            humidity=getattr(row, "humidity", None),
            vpd=getattr(row, "vpd", None),
            treatment=treatment_text,
            inventory_status=row.inventory_status,
            exposure_offset_days=offset_days,
        ),
    )


async def _threshold(db: AsyncSession) -> float:
    value = await db.scalar(
        select(SystemConfig.confidence_threshold).order_by(
            SystemConfig.canonical_key.desc().nulls_last(), SystemConfig.updated_at.desc(), SystemConfig.id.desc()
        ).limit(1)
    )
    return DEFAULT_CONFIDENCE_THRESHOLD if value is None else float(value)


def _review(scans, threshold: float):
    # The threshold is applied when a scan is saved (it sets the flag); keeping it in the
    # signature lets callers stay unchanged. A removed flag means a person checked it.
    del threshold
    return scans.c.flagged.is_(True)


def _successful(scans, threshold: float):
    # Not under review, and SQL NULL confidence stays unknown rather than auto-approved.
    return and_(not_(_review(scans, threshold)), scans.c.confidence.is_not(None))


def _expiring(scans):
    return and_(
        eligible_stock(scans),
        scans.c.remaining_days <= 2,
    )


def _day(scans, day: date):
    start, end = business_day_bounds(day)
    return and_(scans.c.date_time >= start, scans.c.date_time < end)


def _source_filter(scans, key: str):
    if key.startswith("supplier:"):
        try:
            return scans.c.supplier_id == UUID(key.removeprefix("supplier:"))
        except ValueError:
            return false()
    if key.startswith("text:"):
        return and_(scans.c.supplier_id.is_(None), scans.c.source_text == key[5:])
    if key == "unknown":
        return and_(scans.c.supplier_id.is_(None), scans.c.source_text.is_(None))
    return false()


async def get_summary(
    db: AsyncSession, user: UserAccount, business_date: date | None = None,
) -> DashboardSummary:
    now = now_manila()
    day = business_date or now.astimezone(MANILA).date()
    scans = _scoped_projection(user, now)
    threshold = await _threshold(db)
    today = _day(scans, day)
    totals = (await db.execute(
        select(
            func.count().label("total"),
            func.avg(scans.c.confidence).label("confidence"),
        ).select_from(scans).where(today)
    )).one()
    source_rows = (await db.execute(
        select(
            scans.c.supplier_id, scans.c.source_text, scans.c.source_name,
            func.count().label("count"),
        )
        .where(today)
        .group_by(scans.c.supplier_id, scans.c.source_text, scans.c.source_name)
        .order_by(func.count().desc(), scans.c.source_name, scans.c.supplier_id)
    )).all()
    operator_rows = (await db.execute(
        select(
            scans.c.operator_id, scans.c.operator_name, scans.c.username,
            func.count().label("scan_count"),
            func.avg(scans.c.confidence).label("avg_confidence"),
        )
        .where(today)
        .group_by(scans.c.operator_id, scans.c.operator_name, scans.c.username)
        .order_by(func.count().desc(), scans.c.operator_name, scans.c.operator_id)
    )).all()
    buckets, starts = await load_buckets_for_query(
        db,
        select(func.min(scans.c.date_time)).where(
            scans.c.inventory_status == InventoryStatusEnum.IN_STOCK,
        ),
        now,
    )
    recent = (await db.execute(
        select(scans).order_by(scans.c.date_time.desc(), scans.c.id.desc()).limit(5)
    )).all()
    alerts = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(_review(scans, threshold)).label("review"),
            func.count().filter(_expiring(scans)).label("expiring"),
            func.count().filter(_successful(scans, threshold)).label("success_count"),
        ).select_from(scans)
    )).one()
    success_rate = (alerts.success_count / alerts.total * 100.0) if alerts.total > 0 else None
    # One row per active intake, or one per unlinked scan; the oldest group sells first.
    fifo_key = func.coalesce(
        cast(scans.c.intake_id, String), cast(scans.c.id, String),
    ).label("fifo_key")
    if buckets:
        eligible_rows = (await db.execute(
            select(
                scans.c.intake_id,
                fifo_key,
                scans.c.date_time,
                scans.c.source_name,
                scans.c.predicted_days,
                scans.c.remaining_days,
                scans.c.temperature,
                scans.c.humidity,
                scans.c.inventory_status,
            ).where(eligible_stock(scans))
        )).all()
        expiring_count = 0
        fifo_groups: dict[str, dict] = {}
        for item in eligible_rows:
            eff = effective_remaining_days(item, now, buckets=buckets, bucket_starts=starts)
            if eff is not None and eff <= 2.0:
                expiring_count += 1
            key = str(item.fifo_key)
            group = fifo_groups.get(key)
            scanned_dt = as_manila(item.date_time)
            if group is None:
                fifo_groups[key] = {
                    "intake_id": item.intake_id,
                    "fifo_key": item.fifo_key,
                    "scanned_at": scanned_dt,
                    "source_name": item.source_name,
                    "hands": 1,
                    "earliest_remaining_days": eff,
                }
            else:
                group["hands"] += 1
                if scanned_dt < group["scanned_at"]:
                    group["scanned_at"] = scanned_dt
                if item.source_name < group["source_name"]:
                    group["source_name"] = item.source_name
                if eff is not None and (
                    group["earliest_remaining_days"] is None or eff < group["earliest_remaining_days"]
                ):
                    group["earliest_remaining_days"] = eff
        sorted_fifo = sorted(
            fifo_groups.values(),
            key=lambda g: (g["scanned_at"], str(g["fifo_key"])),
        )[:FIFO_LIMIT]
        fifo_recommendations = [_fifo(SimpleNamespace(**g)) for g in sorted_fifo]
    else:
        expiring_count = alerts.expiring
        fifo_rows = (await db.execute(
            select(
                scans.c.intake_id,
                fifo_key,
                func.min(scans.c.date_time).label("scanned_at"),
                func.min(scans.c.source_name).label("source_name"),
                func.count().label("hands"),
                func.min(scans.c.remaining_days).label("earliest_remaining_days"),
            )
            .where(eligible_stock(scans))
            .group_by(scans.c.intake_id, fifo_key)
            .order_by(func.min(scans.c.date_time).asc(), fifo_key.asc())
            .limit(FIFO_LIMIT)
        )).all()
        fifo_recommendations = [_fifo(r) for r in fifo_rows]

    return DashboardSummary(
        generated_at=now, business_date=day,
        total_scans=totals.total, avg_confidence=_mean(totals.confidence),
        success_rate=None if success_rate is None else round(success_rate, 1),
        active_operator_count=len(operator_rows),
        active_source_count=len(source_rows),
        sources=[
            DashboardSource(key=_source(r)[0], name=r.source_name, count=r.count)
            for r in source_rows
        ],
        operators=[DashboardOperator(
            operator_id=r.operator_id, name=r.operator_name, username=r.username,
            scan_count=r.scan_count, avg_confidence=_mean(r.avg_confidence),
        ) for r in operator_rows],
        recent_scans=[_scan(r, now, buckets=buckets, bucket_starts=starts) for r in recent],
        fifo_recommendations=fifo_recommendations,
        pending_review_count=alerts.review, expiring_stock_count=expiring_count,
        confidence_threshold=threshold,
    )


async def list_scans(
    db: AsyncSession, user: UserAccount, *, view: DashboardView = "today",
    page: int = 1, page_size: int = 25, business_date: date | None = None,
    source_key: str | None = None, operator_id: UUID | None = None,
    sort: DashboardSort = "date",
) -> DashboardScanList:
    now = now_manila()
    day = business_date if view == "today" and business_date else now.astimezone(MANILA).date()
    scans = _scoped_projection(user, now)
    conditions = []
    if view == "today":
        conditions.append(_day(scans, day))
    elif view == "review":
        conditions.append(_review(scans, await _threshold(db)))
    if source_key is not None:
        conditions.append(_source_filter(scans, source_key))
    if operator_id is not None:
        conditions.append(scans.c.operator_id == operator_id)
    buckets, starts = await load_buckets_for_query(
        db,
        select(func.min(scans.c.date_time)).where(
            *conditions, scans.c.inventory_status == InventoryStatusEnum.IN_STOCK,
        ),
        now,
    )
    ordering = [scans.c.date_time.desc(), scans.c.id.desc()]
    if sort == "confidence":
        ordering.insert(0, scans.c.confidence.asc().nulls_last())
    if view == "expiring":
        if buckets:
            eligible_rows = (await db.execute(
                select(scans).where(*conditions, eligible_stock(scans)).order_by(*ordering)
            )).all()
            matched = [
                row for row in eligible_rows
                if (eff := effective_remaining_days(row, now, buckets=buckets, bucket_starts=starts)) is not None
                and eff <= 2.0
            ]
            total = len(matched)
            offset = (page - 1) * page_size
            rows = matched[offset : offset + page_size]
            return DashboardScanList(
                items=[_scan(row, now, buckets=buckets, bucket_starts=starts) for row in rows],
                total=total, page=page, page_size=page_size,
                generated_at=now, business_date=day,
            )
        conditions.append(_expiring(scans))
    total = await db.scalar(select(func.count()).select_from(scans).where(*conditions))
    rows = (await db.execute(
        select(scans).where(*conditions).order_by(*ordering)
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    return DashboardScanList(
        items=[_scan(row, now, buckets=buckets, bucket_starts=starts) for row in rows],
        total=total or 0, page=page, page_size=page_size,
        generated_at=now, business_date=day,
    )
