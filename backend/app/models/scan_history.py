"""Append-only scan evidence and transactional mutation receipts."""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, JSON, event, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila


class ScanEvent(Base):
    __tablename__ = "scan_event"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    # Link to pre-existing evidence so detail never shows it twice.
    evidence_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ScanMutation(Base):
    __tablename__ = "scan_mutation"
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila)


class ScanTombstone(Base):
    __tablename__ = "scan_tombstone"
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila)


from app.models.scan import Scan
from app.models.operator_profile import OperatorProfile


@event.listens_for(Scan, "before_delete")
def remember_deleted_scan(_mapper, connection, scan):
    """ORM deletions also preserve evidence on databases without the PostgreSQL trigger."""
    owner = connection.scalar(select(OperatorProfile.account_id).where(OperatorProfile.id == scan.operator_id))
    from sqlalchemy.dialects.postgresql import insert
    connection.execute(insert(ScanTombstone).values(
        scan_id=scan.id, owner_account_id=owner, deleted_at=now_manila(),
    ).on_conflict_do_nothing(index_elements=["scan_id"]))
