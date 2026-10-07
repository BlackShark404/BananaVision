"""Scoped scan hydration and atomic, payload-bound, replayable mutations."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenException, NotFoundException, ConflictException
from app.core.time import now_manila
from app.models import (Scan, ScanEvent, ScanMutation, ScanTombstone, ScanStatusLog,
                        ScanNote, ScanOriginalAiResult, OperatorProfile)
from app.schemas.enums import InventoryStatusEnum
from app.schemas.scan import (ScanDetailResponse, ScanResponse, ScanNoteResponse,
                              ScanDetectionResponse, ScanImageResponse, ScanHistoryResponse)


def is_admin(user):
    return bool(user.role and user.role.name == "Admin")


def authorize_owner(user, owner):
    if is_admin(user):
        return
    if not user.role or user.role.name != "Operator" or user.id != owner:
        raise ForbiddenException("You do not have access to this scan")


async def load_scan(db, scan_id, user):
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id).options(
        selectinload(Scan.operator).selectinload(OperatorProfile.account),
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if scan is None:
        deleted = (await db.execute(select(ScanTombstone).where(ScanTombstone.scan_id == scan_id))).scalar_one_or_none()
        if deleted:
            authorize_owner(user, deleted.owner_account_id)
            raise HTTPException(410, "This scan was deleted")
        raise NotFoundException("Scan")
    authorize_owner(user, scan.operator.account_id if scan.operator else None)
    return scan


def summary(scan, user):
    classification = scan.classification
    original = scan.original_ai_result
    status = scan.status_logs[-1] if scan.status_logs else None
    return ScanResponse(
        id=scan.id, date_time=scan.date_time,
        cultivar=classification.cultivar if classification else None,
        ripeness=classification.ripeness if classification else None,
        confidence=classification.confidence if classification else None,
        temperature=classification.temperature if classification else None,
        humidity=classification.humidity if classification else None,
        vpd=classification.vpd if classification else None,
        treatment=classification.treatment.value if classification and classification.treatment else None,
        spoilage_days=classification.spoilage_days if classification else None,
        finger_count=classification.finger_count if classification else 0,
        operator_name=scan.operator.account.full_name if scan.operator and scan.operator.account else "Unknown",
        source_text=scan.source_text, intake_id=scan.intake_id,
        inventory_status=status.inventory_status if status else InventoryStatusEnum.IN_STOCK,
        status_updated_at=status.updated_at if status else None,
        flagged=scan.flagged, is_overridden=scan.is_overridden,
        original_ai_result={
            "cultivar": original.cultivar, "ripeness": original.ripeness,
            "confidence": original.confidence, "finger_count": original.finger_count,
            "spoilage_days": original.spoilage_days,
        } if original else None,
        thumbnail_url=classification.thumbnail_url if classification else None,
        has_notes=bool(scan.notes) if is_admin(user) else False,
        images=[{"camera_id": image.camera_id, "file_path": image.file_path} for image in scan.images],
        updated_at=scan.updated_at, revision=scan.revision,
    )


async def detail(db, scan, user):
    events = (await db.execute(select(ScanEvent).where(ScanEvent.scan_id == scan.id))).scalars().all()
    represented = {(event.kind, event.evidence_id) for event in events}
    history = [ScanHistoryResponse(
        id=str(event.id), kind=event.kind, timestamp=event.timestamp,
        actor_name=event.actor_name, reason=event.reason,
        previous_values=event.previous_values, new_values=event.new_values,
        revision=event.revision,
    ) for event in events if is_admin(user) or event.kind != "note"]
    previous = None
    for log in scan.status_logs:
        if ("status", str(log.id)) not in represented and ("created", str(log.id)) not in represented:
            history.append(ScanHistoryResponse(
                id=f"legacy-status-{log.id}", kind="status", timestamp=log.updated_at,
                previous_values={"inventory_status": previous} if previous is not None else None,
                new_values={"inventory_status": log.inventory_status.value},
            ))
        previous = log.inventory_status.value
    if is_admin(user):
        for note in scan.notes:
            if ("note", str(note.id)) not in represented:
                history.append(ScanHistoryResponse(
                    id=f"legacy-note-{note.id}", kind="note", timestamp=note.timestamp,
                    actor_name=note.author_name, new_values={"text": note.text},
                ))
    history.sort(key=lambda event: (event.timestamp, event.revision or 0, event.id))
    return ScanDetailResponse(
        **summary(scan, user).model_dump(exclude={"images"}),
        detections=[ScanDetectionResponse.model_validate(value) for value in scan.detections],
        images=[ScanImageResponse.model_validate(value) for value in scan.images],
        notes=[ScanNoteResponse.model_validate(value) for value in sorted(scan.notes, key=lambda note: (note.timestamp, str(note.id)))] if is_admin(user) else [],
        history=history,
    )


async def claim_request(db, user, resource, kind, body):
    """The unique insert waits for an identical in-flight request to commit/rollback.

    Receipt and domain changes share a transaction. No pending receipt can become
    visible, and retry checks happen before any version precondition is evaluated.
    """
    payload = json.dumps({"resource": str(resource), "kind": kind,
                          "body": body.model_dump(mode="json")}, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    inserted = (await db.execute(insert(ScanMutation).values(
        request_id=body.request_id, actor_id=user.id, fingerprint=fingerprint,
        response={}, created_at=now_manila(),
    ).on_conflict_do_nothing(index_elements=["request_id"]).returning(ScanMutation.request_id))).scalar_one_or_none()
    if inserted is not None:
        return None
    receipt = (await db.execute(select(ScanMutation).where(ScanMutation.request_id == body.request_id))).scalar_one()
    if receipt.actor_id != user.id or receipt.fingerprint != fingerprint:
        raise ConflictException("Request ID was already used for a different operation")
    return receipt.response


async def save_receipt(db, request_id, response):
    result = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
    await db.execute(update(ScanMutation).where(ScanMutation.request_id == request_id).values(response=result))
    return response


async def lock_revision(db, scan, revision, user):
    # Explicitly retain updated_at for no-ops. The conditional UPDATE is also a
    # PostgreSQL row lock: a waiting writer rechecks the committed revision.
    locked = (await db.execute(update(Scan).where(
        Scan.id == scan.id, Scan.revision == revision,
    ).values(revision=Scan.revision, updated_at=Scan.updated_at)
      .execution_options(synchronize_session=False).returning(Scan.id))).scalar_one_or_none()
    if locked is None:
        raise ConflictException("Scan changed; reload it before saving")
    return await load_scan(db, scan.id, user)


def append_event(db, scan, user, kind, previous, new, reason=None, evidence_id=None):
    event = ScanEvent(scan_id=scan.id, kind=kind, timestamp=now_manila(),
                      actor_id=user.id, actor_name=user.full_name, reason=reason,
                      previous_values=previous, new_values=new,
                      revision=scan.revision, evidence_id=evidence_id)
    db.add(event)
    return event


async def change_status(db, scan, user, status, reason):
    current = scan.status_logs[-1].inventory_status if scan.status_logs else InventoryStatusEnum.IN_STOCK
    if current == status:
        return False
    scan.revision += 1
    scan.updated_at = now_manila()
    log = ScanStatusLog(scan_id=scan.id, inventory_status=status, updated_at=scan.updated_at)
    scan.status_logs.append(log)
    db.add(log)
    await db.flush()
    append_event(db, scan, user, "status", {"inventory_status": current.value},
                 {"inventory_status": status.value}, reason, str(log.id))
    return True


async def mutate_scan(db, scan_id, user, kind, body):
    scan = await load_scan(db, scan_id, user)
    replay = await claim_request(db, user, scan_id, kind, body)
    if replay is not None:
        return replay
    scan = await lock_revision(db, scan, body.expected_revision, user)
    if kind == "status":
        await change_status(db, scan, user, body.inventory_status, body.reason)
    elif kind == "note":
        scan.revision += 1
        scan.updated_at = now_manila()
        note = ScanNote(scan_id=scan.id, author_name=user.full_name, text=body.note)
        scan.notes.append(note)
        db.add(note)
        await db.flush()
        append_event(db, scan, user, "note", None, {"text": note.text}, evidence_id=str(note.id))
        response = ScanNoteResponse.model_validate(note).model_copy(update={"revision": scan.revision})
        return await save_receipt(db, body.request_id, response)
    else:
        previous, new = {}, {}
        fields = {"flagged": body.flagged} if kind == "flag" else body.model_dump(exclude={"reason", "request_id", "expected_revision"}, exclude_unset=True)
        classification_fields = {"cultivar", "ripeness", "finger_count", "spoilage_days"}
        if any(field in classification_fields for field in fields) and not scan.classification:
            raise HTTPException(422, "This scan has no classification to correct")
        for field, value in fields.items():
            if field in classification_fields and value is None:
                raise HTTPException(422, "Classification values cannot be cleared")
            target = scan.classification if field in classification_fields else scan
            old = getattr(target, field)
            if old != value:
                previous[field] = old.value if hasattr(old, "value") else old
                new[field] = value.value if hasattr(value, "value") else value
        if new:
            if classification_fields.intersection(new):
                if scan.original_ai_result is None:
                    source = scan.classification
                    scan.original_ai_result = ScanOriginalAiResult(
                        scan_id=scan.id, cultivar=source.cultivar, ripeness=source.ripeness,
                        confidence=source.confidence, finger_count=source.finger_count,
                        spoilage_days=source.spoilage_days,
                    )
                scan.is_overridden = True
            for field in new:
                target = scan.classification if field in classification_fields else scan
                setattr(target, field, fields[field])
            scan.revision += 1
            scan.updated_at = now_manila()
            append_event(db, scan, user, kind, previous, new, getattr(body, "reason", None))
    await db.flush()
    response = await detail(db, scan, user)
    return await save_receipt(db, body.request_id, response)
