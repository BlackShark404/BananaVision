"""Bounded, expiring, account/session/filter-bound immutable browse results."""
import hashlib
import json
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.time import now_manila
from app.models.maintenance_state import MaintenanceState
from app.models.scan_snapshot import ScanSnapshot
from app.services.auth_service import lock_current_account
from app.services.inventory_policy import ripeness_projection, shelf_life_window
from app.services.scan_records import scan_scope

MAX_ROWS = 50_000
MAX_BYTES = 20 * 1024 * 1024
LIFETIME = timedelta(minutes=10)
PER_ACCOUNT = 4
WINDOW = "shelf_life_window"
PROJECTION = "ripeness_projection"
DERIVED_FIELDS = frozenset({WINDOW, PROJECTION})


def binding(kind, filters):
    return hashlib.sha256(
        json.dumps([kind, filters], sort_keys=True, default=str).encode()
    ).hexdigest()


async def generation(db):
    return (
        await db.scalar(select(MaintenanceState.auth_generation).where(MaintenanceState.id == 1))
        or "initial"
    )


async def load_snapshot(db, user, token, key, *, lock=True):
    """The caller's snapshot, checked for owner, expiry and filters.

    ``lock=False`` reads it without locking the account row (a pre-check whose session must
    not hold that lock, such as before an export's audit row is written).
    """
    scan_scope(user)
    if lock:
        user = await lock_current_account(db, user)
    scan_scope(user)
    snapshot = await db.scalar(select(ScanSnapshot).where(ScanSnapshot.id == token))
    if snapshot is None:
        raise HTTPException(410, "Browse snapshot expired. Refresh to start a new snapshot.")
    if snapshot.owner_id != user.id or snapshot.role != user.role.name:
        raise HTTPException(403, "This browse snapshot is not available to this account")
    if (snapshot.expires_at <= now_manila() or snapshot.token_version != user.token_version
            or snapshot.generation != await generation(db)):
        raise HTTPException(410, "Browse snapshot expired. Refresh to start a new snapshot.")
    if snapshot.binding != key:
        raise HTTPException(409, "Browse filters changed. Refresh to start a new snapshot.")
    return snapshot


async def save_snapshot(db, user, key, payload):
    scan_scope(user)
    user = await lock_current_account(db, user)
    scan_scope(user)
    # Derived windows are rebuilt on read (slice_snapshot) from fields each row already
    # holds, so storing them would only spend the snapshot size budget.
    payload = {**payload, "items": [
        {key: value for key, value in row.items() if key not in DERIVED_FIELDS}
        for row in payload["items"]
    ]}
    if len(payload["items"]) > MAX_ROWS or len(json.dumps(payload).encode()) > MAX_BYTES:
        raise HTTPException(
            413,
            "Too many records for a browse snapshot. Narrow the filters or use a full export.",
        )
    now = now_manila()
    await db.execute(delete(ScanSnapshot).where(ScanSnapshot.expires_at <= now))
    old = (await db.execute(select(ScanSnapshot.id).where(ScanSnapshot.owner_id == user.id)
                           .order_by(ScanSnapshot.expires_at.desc(), ScanSnapshot.id.desc())
                           .offset(PER_ACCOUNT - 1))).scalars().all()
    if old:
        await db.execute(delete(ScanSnapshot).where(ScanSnapshot.id.in_(old)))
    snapshot = ScanSnapshot(owner_id=user.id, role=user.role.name, token_version=user.token_version,
        generation=await generation(db), binding=key, expires_at=now + LIFETIME, payload=payload)
    db.add(snapshot)
    await db.flush()
    return snapshot


def _instant(value):
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _with_window(row, generated_at):
    """Rebuild derived windows for the instant the row was frozen.

    That instant is the row's own `risk_as_of`, or the snapshot's `generated_at`. A
    frozen page therefore reads the same at any later time, and the page that shows
    it counts forward from `as_of_date`.
    """
    scanned_at = _instant(row.get("date_time"))
    as_of = _instant(row.get("risk_as_of") or generated_at)
    return {
        **row,
        WINDOW: shelf_life_window(row.get("spoilage_days"), scanned_at, as_of),
        PROJECTION: ripeness_projection(
            row.get("ripeness"),
            row.get("cultivar"),
            row.get("spoilage_days"),
            scanned_at,
            as_of,
            temperature=row.get("temperature"),
            humidity=row.get("humidity"),
            vpd=row.get("vpd"),
            treatment=row.get("treatment"),
            inventory_status=row.get("inventory_status"),
        ),
    }


def slice_snapshot(snapshot, page, page_size):
    start = (page - 1) * page_size
    generated_at = snapshot.payload.get("meta", {}).get("generated_at")
    return {
        **snapshot.payload.get("meta", {}),
        "items": [
            _with_window(row, generated_at)
            for row in snapshot.payload["items"][start : start + page_size]
        ],
        "page": page,
        "page_size": page_size,
        "total": len(snapshot.payload["items"]),
        "snapshot_id": snapshot.id,
        "snapshot_expires_at": snapshot.expires_at,
    }
