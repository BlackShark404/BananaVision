"""Immutable scan evidence and transaction-bound mutation receipts."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, event, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan


class ScanEvent(Base):
    __tablename__ = "scan_event"
    __table_args__ = (UniqueConstraint("scan_id", "revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila)
    # Do not depend on current account existence/names for historical evidence.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict] = mapped_column(JSON)
    evidence_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    scan = relationship("Scan", back_populates="events", lazy="selectin")


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


@event.listens_for(Scan, "before_delete")
def remember_scan_deletion(mapper, connection, scan):
    """Only actual ORM deletions; archive Core replacement does not trigger this."""
    owner = connection.scalar(
        select(OperatorProfile.account_id).where(OperatorProfile.id == scan.operator_id)
    )
    # An actual deletion supersedes a tombstone restored from an older snapshot.
    connection.execute(ScanTombstone.__table__.delete().where(ScanTombstone.scan_id == scan.id))
    connection.execute(ScanTombstone.__table__.insert().values(
        scan_id=scan.id, owner_account_id=owner, deleted_at=now_manila()))
