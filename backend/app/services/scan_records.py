"""Shared authorization boundary for stored scan records and their evidence."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select, text, true, update
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.time import now_manila
from app.models import (
    ActivityLog,
    Intake,
    ScanClassification,
    ScanNote,
    ScanOriginalAiResult,
    ScanStatusLog,
)
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan
from app.models.scan_history import ScanEvent, ScanMutation, ScanTombstone
from app.schemas.enums import InventoryStatusEnum
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
from app.services.auth_service import lock_current_account
from app.services.inventory_policy import inventory_facts
from app.services.scan_evidence import evidence_url


def is_admin(user) -> bool:
    return bool(user.role and user.role.name == "Admin")


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


def serialize_scan(scan, user):
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
        thumbnail_url=evidence_url(classification.thumbnail_url) if classification else None,
        has_notes=is_admin(user) and bool(scan.notes),
        images=[
            ScanImageRef(camera_id=i.camera_id, file_path=evidence_url(i.file_path) or "")
            for i in scan.images
        ],
        updated_at=scan.updated_at,
    )


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


async def apply_scan_change(db, scan, user, kind, changes, reason=None):
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
        return None
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
    db.add(
        ActivityLog(
            user_id=user.id,
            action=f"scan_{kind}",
            details=f"Scan {scan.id}, revision {scan.revision}",
        )
    )
    await db.flush()
    return note


async def mutate_scan(db, scan_id, user, kind, body):
    await lock_mutation(db, body.request_id)
    # Re-read role and session version under lock, including after a queued retry.
    user = await lock_current_account(db, user)
    if kind in ("correction", "note", "provenance") and not is_admin(user):
        raise ForbiddenException("Admin access required")
    scan = await load_authorized_scan(db, scan_id, user)
    # Bulk inventory and scan attachment share this parent-first lock order.
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
    note = await apply_scan_change(db, scan, user, kind, changes, getattr(body, "reason", None))
    if note:
        response = {
            **ScanNoteResponse.model_validate(note).model_dump(mode="json"),
            "revision": scan.revision,
        }
    else:
        response = (await serialize_detail(db, scan, user)).model_dump(mode="json")
    save_receipt(db, user, body, fingerprint, response)
    return response
