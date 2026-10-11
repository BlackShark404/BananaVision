"""Ephemeral browse snapshots; intentionally excluded from station archives."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class ScanSnapshot(Base):
    __tablename__ = "scan_browse_snapshot"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String(20))
    token_version: Mapped[int] = mapped_column(Integer)
    generation: Mapped[str] = mapped_column(String(64))
    binding: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(ManilaDateTime(), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
