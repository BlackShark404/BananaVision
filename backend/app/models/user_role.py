"""
UserRole ORM model.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(Base):
    __tablename__ = "user_role"

    id: Mapped[int] = mapped_column("ur_id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column("ur_name", String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column("ur_description", String(255), nullable=True)

    # Relationships
    accounts = relationship("UserAccount", back_populates="role", lazy="selectin")
