"""Station control state is deliberately excluded from restorable application data."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila


class MaintenanceState(Base):
    __tablename__ = "maintenance_state"
    __table_args__ = (CheckConstraint("id = 1", name="maintenance_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    auth_generation: Mapped[str] = mapped_column(String(64), nullable=False, default="initial")
    restore_marker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    power: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retention: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    operations: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila, onupdate=now_manila)
