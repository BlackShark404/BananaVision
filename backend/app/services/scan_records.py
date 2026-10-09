"""Shared authorization boundary for stored scan records and their evidence."""

from sqlalchemy import select, true

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan


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
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    return await authorize_scan(db, scan, user)
