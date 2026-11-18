"""Shared authorization boundary for stored scan records and their evidence."""

import hashlib
import json
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select, text, true, update
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.time import now_manila
from app.models import (
    Intake,
    ScanClassification,
    ScanNote,
    ScanOriginalAiResult,
    ScanStatusLog,
)
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_history import ScanEvent, ScanMutation, ScanTombstone
from app.schemas.enums import IntakeStatusEnum, InventoryStatusEnum
from app.schemas.scan import (
    OriginalAiResult,
    ScanDetailResponse,
    ScanDetectionResponse,
    ScanHistoryResponse,
    ScanImageRef,
    ScanImageResponse,
    ScanNoteResponse,
    ScanResponse,
)
from app.services import audit
from app.services.auth_service import lock_current_account
from app.services.inventory_policy import inventory_facts
from app.services.scan_evidence import evidence_url, thumbnail_url
from app.ws.mutations import intake_event, publish_intake_event, publish_scan_event, scan_event


@dataclass(frozen=True)
class ScanChange:
    """A committed-shape description of exactly what apply_scan_change wrote."""

    note: ScanNote | None = None
    changed: tuple[str, ...] = ()


def is_admin(user) -> bool:
    return bool(user.role and user.role.name == "Admin")


# Sold and Spoiled end a scan's time in stock; changing them afterwards is an admin correction.
CLOSED_INVENTORY_STATUSES = (InventoryStatusEnum.SOLD, InventoryStatusEnum.SPOILED)


def current_inventory_status(scan):
    if not scan.status_logs:
        return InventoryStatusEnum.IN_STOCK
    return scan.status_logs[-1].inventory_status


def scan_scope(user):
    """Scope by the persisted account/profile relationship, never a display name."""
    if is_admin(user):
        return true()
    if not user.role or user.role.name != "Operator":
        raise ForbiddenException("Scan access requires an Admin or Operator role")
    return Scan.operator_id.in_(
        select(OperatorProfile.id).where(OperatorProfile.account_id == user.id)
    )


async def authorize_scan(db, scan, user):
    scan_scope(user)  # Reject unknown roles even for an absent record.
    if scan is None:
        raise NotFoundException("Scan")
    if not is_admin(user):
        owner = await db.scalar(
            select(OperatorProfile.account_id).where(OperatorProfile.id == scan.operator_id)
        )
        if owner != user.id:
            raise ForbiddenException("You do not have access to this scan")
    return scan


async def load_authorized_scan(db, scan_id, user):
    scan_scope(user)
    scan = (await db.execute(
        select(Scan).where(Scan.id == scan_id).options(
            selectinload(Scan.operator).selectinload(OperatorProfile.account)
        )
    )).scalar_one_or_none()
    if scan is None:
        deleted = (
            await db.execute(select(ScanTombstone).where(ScanTombstone.scan_id == scan_id))
        ).scalar_one_or_none()
        if deleted:
            if not is_admin(user) and deleted.owner_account_id != user.id:
                raise ForbiddenException("You do not have access to this scan")
            raise HTTPException(410, "This scan was deleted")
    return await authorize_scan(db, scan, user)


def serialize_scan(scan, user=None):
    classification = scan.classification
    latest = scan.status_logs[-1] if scan.status_logs else None
    return ScanResponse(
        id=scan.id,
        revision=scan.revision,
        date_time=scan.date_time,
        cultivar=classification.cultivar if classification else None,
        ripeness=classification.ripeness if classification else None,
        confidence=classification.confidence if classification else None,
        temperature=classification.temperature if classification else None,
        humidity=classification.humidity if classification else None,
        vpd=classification.vpd if classification else None,
        treatment=classification.treatment if classification else None,
        spoilage_days=classification.spoilage_days if classification else None,
        finger_count=classification.finger_count if classification else 0,
        operator_name=scan.operator_name_snapshot
        or (
            scan.operator.account.full_name
            if scan.operator and scan.operator.account
            else "Unknown"
        ),
        source_text=scan.source_text,
        intake_id=scan.intake_id,
        intake_origin_id=scan.intake_origin_id,
        intake_provenance=scan.intake_provenance,
        **inventory_facts(
            scan, latest.inventory_status if latest else InventoryStatusEnum.IN_STOCK, now_manila()
        ),
        inventory_status=latest.inventory_status if latest else InventoryStatusEnum.IN_STOCK,
        status_updated_at=latest.updated_at if latest else None,
        flagged=scan.flagged,
        is_overridden=scan.is_overridden,
        original_ai_result=OriginalAiResult.model_validate(scan.original_ai_result)
        if scan.original_ai_result
        else None,
        thumbnail_url=thumbnail_url(classification.thumbnail_url) if classification else None,
        has_notes=user is not None and is_admin(user) and bool(scan.notes),
        images=[
            ScanImageRef(camera_id=i.camera_id, file_path=evidence_url(i.file_path) or "")
            for i in scan.images
        ],
        updated_at=scan.updated_at,
    )


def _scan_source(scan) -> tuple[str, str]:
    """Match the Dashboard/Scan Logs source key without exposing a new query."""
    if scan.intake and scan.intake.supplier_id:
        supplier = scan.intake.supplier
        return f"supplier:{scan.intake.supplier_id}", (supplier.name if supplier else "Unknown")
    text = (scan.source_text or "").strip()
    if text:
        return f"text:{text}", text
    return "unknown", "Unknown"


def scan_event_payload(scan, user) -> dict:
    """Authorized row fields only; image lists and note text are never broadcast."""
    payload = serialize_scan(scan, user).model_dump(mode="json")
    payload.pop("images", None)
    payload.pop("original_ai_result", None)
    source_key, source_name = _scan_source(scan)
    payload.update({
        "operator_id": str(scan.operator_id),
        "source_key": source_key,
        "source_name": source_name,
    })
    return payload


def partial_scan_event_payload(scan) -> dict:
    """Bulk status changes do not need to hydrate a full classification row."""
    latest = scan.status_logs[-1] if scan.status_logs else None
    facts = inventory_facts(
        scan,
        latest.inventory_status if latest else InventoryStatusEnum.IN_STOCK,
        now_manila(),
    )
    return {
        "id": str(scan.id),
        "revision": scan.revision,
        "inventory_status": latest.inventory_status if latest else InventoryStatusEnum.IN_STOCK,
        "status_updated_at": latest.updated_at.isoformat() if latest else None,
        "inventory_eligible": facts["inventory_eligible"],
        "remaining_days": facts["remaining_days"],
        "risk_as_of": facts["risk_as_of"].isoformat(),
        "shelf_life_window": facts["shelf_life_window"],
    }


async def scan_history(db, scan, user):
    events = (
        (await db.execute(select(ScanEvent).where(ScanEvent.scan_id == scan.id))).scalars().all()
    )
    represented = {e.evidence_id for e in events if e.evidence_id}
    history = [ScanHistoryResponse(
        id=str(e.id), kind=e.kind, timestamp=e.timestamp, actor_id=e.actor_id,
        actor_name=e.actor_name, reason=e.reason, previous_values=e.previous_values,
        new_values=e.new_values, revision=e.revision,
    ) for e in events if e.kind != "note" or is_admin(user)]
    history.extend(ScanHistoryResponse(
        id=f"status:{s.id}", kind="status", timestamp=s.updated_at,
        new_values={"inventory_status": s.inventory_status}, legacy=True,
    ) for s in scan.status_logs if f"status:{s.id}" not in represented)
    if is_admin(user):
        history.extend(ScanHistoryResponse(
            id=f"note:{n.id}", kind="note", timestamp=n.timestamp,
            actor_name=n.author_name, new_values={"text": n.text}, legacy=True,
        ) for n in scan.notes if f"note:{n.id}" not in represented)
    return sorted(history, key=lambda e: (e.timestamp, e.revision or 0, e.id))


async def serialize_detail(db, scan, user):
    return ScanDetailResponse(
        **serialize_scan(scan, user).model_dump(exclude={"images"}),
        images=[
            ScanImageResponse.model_validate(i).model_copy(
                update={"file_path": evidence_url(i.file_path) or ""}
            )
            for i in scan.images
        ],
        detections=[ScanDetectionResponse.model_validate(d) for d in scan.detections],
        notes=[ScanNoteResponse.model_validate(n) for n in scan.notes] if is_admin(user) else [],
        history=await scan_history(db, scan, user),
    )


async def lock_mutation(db, request_id):
    """Serialize identical request IDs even when callers target different resources."""
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(request_id.bytes).digest()[:8], "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=key))


def mutation_fingerprint(user, target, kind, body):
    canonical = json.dumps({"actor": str(user.id), "role": user.role.name, "target": str(target),
                            "kind": kind, "payload": body.model_dump(mode="json")},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def mutation_replay(db, user, body, fingerprint):
    receipt = (
        await db.execute(select(ScanMutation).where(ScanMutation.request_id == body.request_id))
    ).scalar_one_or_none()
    if receipt:
        if receipt.actor_id != user.id or receipt.fingerprint != fingerprint:
            raise ConflictException("This request ID was already used for a different change")
        return receipt.response
    return None


def save_receipt(db, user, body, fingerprint, response):
    db.add(
        ScanMutation(
            request_id=body.request_id, actor_id=user.id, fingerprint=fingerprint, response=response
        )
    )


async def apply_scan_change(db, scan, user, kind, changes, reason=None, client_ip=None):
    """Caller owns locks/CAS. Only changed values create a revision and audit event."""
    previous, new, evidence_id = {}, {}, None
    classification_fields = {"cultivar", "ripeness", "finger_count", "spoilage_days"}
    for key, value in changes.items():
        if key == "inventory_status":
            old = (
                scan.status_logs[-1].inventory_status
                if scan.status_logs
                else InventoryStatusEnum.IN_STOCK
            )
        elif key in classification_fields:
            old = (
                getattr(scan.classification, key)
                if scan.classification
                else (0 if key == "finger_count" else None)
            )
        elif key == "text":
            old = None
        else:
            old = getattr(scan, key)
        if key == "text" or old != value:
            previous[key], new[key] = old, value
    if not new:
        return ScanChange()
    now = now_manila()
    expected = scan.revision
    result = await db.execute(update(Scan).where(Scan.id == scan.id, Scan.revision == expected)
                              .values(revision=expected + 1, updated_at=now)
                              .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ConflictException("This scan changed. Reload it before saving your changes.")
    scan.revision, scan.updated_at = expected + 1, now
    if classification_fields & new.keys():
        if not scan.original_ai_result:
            original = scan.classification
            scan.original_ai_result = ScanOriginalAiResult(
                scan_id=scan.id, cultivar=original.cultivar if original else None,
                ripeness=original.ripeness if original else None,
                confidence=original.confidence if original else None,
                finger_count=original.finger_count if original else 0,
                spoilage_days=original.spoilage_days if original else None,
            )
        if not scan.classification:
            scan.classification = ScanClassification(scan_id=scan.id, finger_count=0)
        scan.is_overridden = True
    note = None
    for key, value in new.items():
        if key == "inventory_status":
            log = ScanStatusLog(scan_id=scan.id, inventory_status=value, updated_at=now)
            scan.status_logs.append(log)
            await db.flush()
            evidence_id = f"status:{log.id}"
        elif key == "text":
            note = ScanNote(scan_id=scan.id, text=value, author_name=user.full_name, timestamp=now)
            scan.notes.append(note)
            await db.flush()
            evidence_id = f"note:{note.id}"
        elif key in classification_fields:
            setattr(scan.classification, key, value)
        else:
            setattr(scan, key, value)
            if key == "source_text":
                scan.source_name_snapshot = value
    # Enum members are str-backed and JSON-safe; unknown legacy facts remain null.
    db.add(ScanEvent(scan_id=scan.id, revision=scan.revision, kind=kind, timestamp=now,
                     actor_id=user.id, actor_name=user.full_name, reason=reason,
                     previous_values=previous, new_values=new, evidence_id=evidence_id))
    await audit.record(
        db, audit.SCAN_CHANGE_ACTIONS[kind], scan_change_details(scan, previous, new, reason),
        actor=user, ip=client_ip,
    )
    await db.flush()
    return ScanChange(note, tuple(sorted(new)))


def scan_change_details(scan, previous, new, reason=None) -> str:
    """Each changed field old → new. Note text is private and is never copied here."""
    fields = [key for key in new if key != "text"]
    parts = [audit.describe_changes(previous, new, fields)] if fields else []
    if "text" in new:
        parts.append(f"note added ({len(new['text'] or '')} chars)")
    text = f"Scan {scan.id}, revision {scan.revision}: {'; '.join(parts)}"
    if reason:
        text += f"; reason {audit.quoted(reason, 200)}"
    return text


async def mutate_scan(db, scan_id, user, kind, body, client_ip=None):
    await lock_mutation(db, body.request_id)
    # Re-read role and session version under lock, including after a queued retry.
    user = await lock_current_account(db, user)
    if kind in ("correction", "note", "provenance") and not is_admin(user):
        raise ForbiddenException("Admin access required")
    # Removing a flag takes a scan out of the review queue, so it is a quality decision.
    # Operators may still raise a flag on their own scans.
    if kind == "flag" and getattr(body, "flagged", None) is False and not is_admin(user):
        raise ForbiddenException("Admin access required to remove a flag")
    scan = await load_authorized_scan(db, scan_id, user)
    # Bulk inventory and scan attachment share this parent-first lock order. The scan reload
    # below re-reads scan.intake after this lock, so its status is current for the reopen rule.
    if scan.intake_id:
        await db.execute(select(Intake.id).where(Intake.id == scan.intake_id).with_for_update())
    scan = (await db.execute(
        select(Scan).where(Scan.id == scan_id)
        .options(selectinload(Scan.operator).selectinload(OperatorProfile.account))
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    await authorize_scan(db, scan, user)
    fingerprint = mutation_fingerprint(user, scan_id, kind, body)
    replay = await mutation_replay(db, user, body, fingerprint)
    if replay is not None:
        return replay
    reopen_intake = None
    if kind == "status" and body.inventory_status != current_inventory_status(scan):
        if current_inventory_status(scan) in CLOSED_INVENTORY_STATUSES and not is_admin(user):
            raise ForbiddenException("Admin access required to change a Sold or Spoiled scan")
        # Stock counts only in an Active intake, so restoring a scan reopens a Depleted one.
        if (
            body.inventory_status == InventoryStatusEnum.IN_STOCK
            and scan.intake is not None
            and scan.intake.status == IntakeStatusEnum.DEPLETED
        ):
            if not is_admin(user):
                raise ForbiddenException("Admin access required to reopen a depleted intake")
            reopen_intake = scan.intake
    if body.expected_revision != scan.revision:
        raise ConflictException("This scan changed. Reload it before saving your changes.")
    if kind == "provenance" and (
        scan.intake_id is not None or scan.intake_origin_id is not None
        or scan.intake_provenance not in ("unverified", "excluded")
    ):
        raise ConflictException(
            "Only ambiguous legacy stock can be reconciled. Known intake evidence is retained."
        )
    changes = body.model_dump(
        exclude={"request_id", "expected_revision", "reason"}, exclude_unset=True
    )
    if kind == "note":
        changes = {"text": body.note}
    change = await apply_scan_change(
        db, scan, user, kind, changes, getattr(body, "reason", None), client_ip=client_ip
    )
    if reopen_intake is not None and "inventory_status" in change.changed:
        old_intake_status = reopen_intake.status
        reopen_intake.status = IntakeStatusEnum.ACTIVE
        reopen_intake.updated_at = scan.updated_at
        await audit.record(
            db, audit.AuditAction.INTAKE_STATUS_CHANGED,
            f"Intake {reopen_intake.id} status {audit.clean(old_intake_status)} → "
            f"{audit.clean(reopen_intake.status)}: scan {scan.id} returned to In Stock",
            actor=user, ip=client_ip,
        )
        await db.flush()
    else:
        reopen_intake = None
    if change.note:
        response = {
            **ScanNoteResponse.model_validate(change.note).model_dump(mode="json"),
            "revision": scan.revision,
        }
    else:
        response = (await serialize_detail(db, scan, user)).model_dump(mode="json")
    save_receipt(db, user, body, fingerprint, response)
    if change.changed:
        # Publish only after the row, audit event and replay receipt are durable.
        event = scan_event(
            scan_id=scan.id,
            revision=scan.revision,
            kind=kind,
            changed=change.changed,
            actor_id=user.id,
            scan=scan_event_payload(scan, user),
        )
        owner_id = (
            scan.operator.account.id
            if scan.operator and scan.operator.account
            else None
        )
        intake_change = (
            intake_event(
                intake_id=reopen_intake.id,
                kind="scan-status",
                actor_id=user.id,
                intake={"id": str(reopen_intake.id), "status": reopen_intake.status.value,
                        "updated_at": reopen_intake.updated_at.isoformat()},
                status=reopen_intake.status,
            )
            if reopen_intake is not None
            else None
        )
        await db.commit()
        await publish_scan_event(event, owner_account_id=owner_id)
        if intake_change is not None:
            await publish_intake_event(intake_change)
    return response
