"""Bounded, expiring, account/session/filter-bound immutable browse results."""
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.time import now_manila
from app.models.maintenance_state import MaintenanceState
from app.models.scan_snapshot import ScanSnapshot
from app.services.auth_service import lock_current_account
from app.services.scan_records import scan_scope

MAX_ROWS = 50_000
MAX_BYTES = 20 * 1024 * 1024
LIFETIME = timedelta(minutes=10)
PER_ACCOUNT = 4


def binding(kind, filters):
    return hashlib.sha256(
        json.dumps([kind, filters], sort_keys=True, default=str).encode()
    ).hexdigest()


async def generation(db):
    return (
        await db.scalar(select(MaintenanceState.auth_generation).where(MaintenanceState.id == 1))
        or "initial"
    )


async def load_snapshot(db, user, token, key):
    scan_scope(user)
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
    if len(payload["items"]) > MAX_ROWS or len(json.dumps(payload).encode()) > MAX_BYTES:
        raise HTTPException(
            413,
            "Too many records for a browse snapshot. Narrow the filters or use a full CSV export.",
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


def slice_snapshot(snapshot, page, page_size):
    start = (page - 1) * page_size
    return {
        **snapshot.payload.get("meta", {}),
        "items": snapshot.payload["items"][start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": len(snapshot.payload["items"]),
        "snapshot_id": snapshot.id,
        "snapshot_expires_at": snapshot.expires_at,
    }
