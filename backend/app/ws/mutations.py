"""Post-commit mutation notifications.

Every publisher in this module is called only after the owning transaction has
committed. Events are invalidation hints: they identify the changed record and
carry the authorized row fields needed to patch a visible row. Clients still
reject stale revisions and reconcile through the REST API after a reconnect.
"""

from __future__ import annotations

import uuid

from app.ws import events
from app.ws.manager import ws_manager


def scan_event(
    *,
    scan_id,
    revision: int,
    kind: str,
    changed,
    actor_id,
    scan: dict | None = None,
    partial: bool = False,
    deleted: bool = False,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "scan_id": str(scan_id),
        "revision": int(revision),
        "kind": kind,
        "changed": sorted(str(field) for field in changed),
        "actor_id": str(actor_id),
        "partial": bool(partial),
        "deleted": bool(deleted),
        "scan": scan,
    }


def intake_event(
    *, intake_id, kind: str, actor_id, intake: dict | None = None, status=None
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "intake_id": str(intake_id),
        "kind": kind,
        "actor_id": str(actor_id),
        "status": status,
        "intake": intake,
    }


def supplier_event(*, supplier_id, kind: str, actor_id, supplier: dict | None = None) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "supplier_id": str(supplier_id),
        "kind": kind,
        "actor_id": str(actor_id),
        "supplier": supplier,
    }


async def publish_scan_event(event: dict, *, owner_account_id=None) -> None:
    """Admins read the dashboard room; only the owning operator's sockets get kiosk.

    Admin sockets subscribe to both rooms, so they may receive the same event
    twice. The browser deduplicates by ``event_id``.
    """
    await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.SCAN_CHANGED, event)
    if owner_account_id is not None:
        await ws_manager.send_to_room(
            events.ROOM_KIOSK,
            events.SCAN_CHANGED,
            event,
            account_id=owner_account_id,
        )


async def publish_intake_event(event: dict) -> None:
    # The intake registry is shared and readable by every authenticated role.
    await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.INTAKE_CHANGED, event)
    await ws_manager.send_to_room(events.ROOM_KIOSK, events.INTAKE_CHANGED, event)


async def publish_supplier_event(event: dict) -> None:
    # Suppliers are shared reference data, not account-owned records.
    await ws_manager.send_to_room(events.ROOM_DASHBOARD, events.SUPPLIER_CHANGED, event)
    await ws_manager.send_to_room(events.ROOM_KIOSK, events.SUPPLIER_CHANGED, event)
