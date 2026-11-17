"""
User management routes.

ROLE-01: Role transitions now reconcile profiles — promoting an operator to admin
creates an AdminProfile, demoting an admin to operator creates an OperatorProfile
with requires_pin_change=True.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, func, case, update
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser, AdminUser
from app.core.exceptions import NotFoundException, ConflictException, ForbiddenException
from app.core.security import hash_password, hash_pin
from app.core.temporary_credentials import temporary_password, temporary_pin
from app.models.user_account import UserAccount
from app.models.user_role import UserRole
from app.models.admin_profile import AdminProfile
from app.models.operator_profile import OperatorProfile
from app.models.activity_log import ActivityLog
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.core.time import now_manila
from app.core.http import get_client_ip
from app.services import audit
from app.schemas.user import (
    UserCreate,
    UserCreatedResponse,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserPasswordReset,
    UserPinReset,
)
from app.schemas.enums import RoleEnum, ActiveStatusEnum, PasswordSetupReasonEnum, PinSetupReasonEnum


router = APIRouter(prefix="/users", tags=["Users"])


def _as_enum(enum_type, value):
    """Stored strings and request enums render the same way in the audit log."""
    try:
        return enum_type(value) if value is not None else None
    except ValueError:
        return value


def _audit_snapshot(user: UserAccount) -> dict:
    """Fields an administrator can change; private values are only noted as changed."""
    profile = user.operator_profile
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": _as_enum(RoleEnum, user.role.name if user.role else None),
        "status": _as_enum(ActiveStatusEnum, user.status),
        "avatar_url": user.avatar_url,
        "requires_password_change": user.requires_password_change,
        "password_setup_reason": _as_enum(PasswordSetupReasonEnum, user.password_setup_reason),
        "requires_pin_change": profile.requires_pin_change if profile else None,
        "pin_setup_reason": (
            _as_enum(PinSetupReasonEnum, profile.pin_setup_reason) if profile else None
        ),
    }


@router.get("", response_model=UserListResponse)
async def list_users(db: DbSession, admin: AdminUser):
    """List all users."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .order_by(UserAccount.created_at)
    )
    users = result.scalars().all()
    return UserListResponse(
        items=[UserResponse.from_db_model(u) for u in users],
        total=len(users),
    )


@router.post("", response_model=UserCreatedResponse, status_code=201)
async def create_user(body: UserCreate, db: DbSession, admin: AdminUser, request: Request, response: Response):
    """Create a new user (admin only)."""
    response.headers["Cache-Control"] = "no-store"
    existing = await db.execute(select(UserAccount).where(UserAccount.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Username '{body.username}' already exists")

    role_res = await db.execute(select(UserRole).where(UserRole.name == body.role))
    user_role = role_res.scalar_one_or_none()
    if not user_role:
        raise NotFoundException(f"Role '{body.role.value}' not found")

    password = body.password or temporary_password()
    pin = (body.pin or temporary_pin()) if body.role == RoleEnum.OPERATOR else None
    user = UserAccount(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(password),
        role_id=user_role.id,
        status=body.status,
        requires_password_change=True,
        password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT,
    )
    user.role = user_role  # Explicitly load for from_db_model

    if body.role == RoleEnum.ADMIN.value:
        user.admin_profile = AdminProfile()
    elif body.role == RoleEnum.OPERATOR.value:
        user.operator_profile = OperatorProfile(
            pin_hash=hash_pin(pin),
            requires_pin_change=True,
            pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT,
        )

    db.add(user)
    await db.flush()

    await audit.record(
        db, audit.AuditAction.USER_CREATED,
        f"Created user {audit.quoted(user.username)} ({user.id}) with role "
        f"{audit.clean(body.role)}, status {audit.clean(body.status)}; "
        "temporary credentials issued",
        actor=admin, ip=get_client_ip(request),
    )
    return UserCreatedResponse(**UserResponse.from_db_model(user).model_dump(),
                               temporary_password=password, temporary_pin=pin)


# ── PROFILE-01: Self-service profile update (any authenticated user) ────────

class SelfProfileUpdate(BaseModel):
    avatar_url: str | None = None


@router.get("/me/summary")
async def own_profile_summary(db: DbSession, user: CurrentUser):
    """All retained scan records; operators can only see their own aggregates/activity."""
    now = now_manila()
    query = select(
        func.count(Scan.id).label("total_scans"),
        func.avg(ScanClassification.confidence).label("avg_confidence"),
        func.sum(case((Scan.date_time.between(now - timedelta(days=7), now), 1), else_=0)).label("last_7_days"),
    ).select_from(Scan).outerjoin(ScanClassification, ScanClassification.scan_id == Scan.id)
    is_admin = user.role.name == RoleEnum.ADMIN.value
    if not is_admin:
        query = query.join(OperatorProfile, Scan.operator_id == OperatorProfile.id).where(
            OperatorProfile.account_id == user.id
        )
    row = (await db.execute(query)).one()
    recent_actions_7d = await db.scalar(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user.id,
            ActivityLog.timestamp.between(now - timedelta(days=7), now),
        )
    )
    logs = (await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()).limit(8)
    )).scalars().all()
    return {
        "total_scans": row.total_scans,
        "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
        "last_7_days": row.last_7_days or 0,
        "recent_actions_7d": recent_actions_7d or 0,
        "total_users": (await db.scalar(select(func.count(UserAccount.id)))) if is_admin else None,
        "activity": [{"id": str(log.id), "action": log.action, "details": log.details or "",
                      "timestamp": log.timestamp.isoformat()} for log in logs],
    }


@router.patch("/me/profile", response_model=UserResponse)
async def update_own_profile(
    body: SelfProfileUpdate, db: DbSession, user: CurrentUser, request: Request,
):
    """
    Self-service profile update — any authenticated user can update their own
    avatar without needing admin privileges.  (PROFILE-01 fix)
    """
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise NotFoundException("User")

    if body.avatar_url is not None and body.avatar_url != account.avatar_url:
        account.avatar_url = body.avatar_url
        # The image itself is private and large; only the fact of the change is kept.
        await audit.record(
            db, audit.AuditAction.PROFILE_UPDATED,
            f"Updated profile of user {audit.quoted(account.username)} ({account.id}): "
            "avatar changed",
            actor=account, ip=get_client_ip(request),
        )

    await db.flush()
    return UserResponse.from_db_model(account)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, admin: AdminUser, request: Request):
    """Update a user (admin only). ROLE-01: Role transitions reconcile profiles."""
    actor_version = getattr(admin, "token_version", None)
    # A common transaction lock serializes the count and every role/status update.
    # A no-op UPDATE also acquires SQLite's write lock; PostgreSQL locks this row.
    # Acquire it before any target-account lock to avoid cross-admin deadlocks.
    await db.execute(update(UserRole).where(UserRole.name == RoleEnum.ADMIN.value)
                     .values(name=UserRole.name))
    actor = (await db.execute(
        select(UserAccount.status, UserAccount.token_version, UserRole.name)
        .join(UserRole, UserAccount.role_id == UserRole.id).where(UserAccount.id == admin.id)
    )).one_or_none()
    if (not actor or actor.status != ActiveStatusEnum.ACTIVE or actor.name != RoleEnum.ADMIN.value
            or (actor_version is not None and actor.token_version != actor_version)):
        raise ForbiddenException("Administrator session changed; sign in again")
    result = await db.execute(
        select(UserAccount)
        .options(
            selectinload(UserAccount.role),
            selectinload(UserAccount.operator_profile),
            selectinload(UserAccount.admin_profile),
        )
        .where(UserAccount.id == user_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    # ── ADMIN-01: Guard against losing the last active admin ────────────
    is_currently_active_admin = (
        user.role and user.role.name == RoleEnum.ADMIN.value
        and user.status == ActiveStatusEnum.ACTIVE
    )
    if is_currently_active_admin:
        # Check if this update demotes or deactivates the user
        demoting = body.role is not None and body.role != RoleEnum.ADMIN
        deactivating = body.status is not None and body.status != ActiveStatusEnum.ACTIVE
        if demoting or deactivating:
            # Count other active admins
            active_admin_count_result = await db.execute(
                select(func.count())
                .select_from(UserAccount)
                .join(UserRole, UserAccount.role_id == UserRole.id)
                .where(
                    UserRole.name == RoleEnum.ADMIN.value,
                    UserAccount.status == ActiveStatusEnum.ACTIVE,
                    UserAccount.id != user_id,
                )
            )
            other_active_admins = active_admin_count_result.scalar() or 0
            if other_active_admins == 0:
                raise ConflictException(
                    "Cannot deactivate or demote the last active administrator. "
                    "Promote or activate another admin first."
                )

    # ── Detect role changes for ROLE-01 reconciliation ──────────────────
    old_role_name = user.role.name if user.role else None
    old_status = user.status
    old_username = user.username
    before = _audit_snapshot(user)
    new_role_name = None

    update_data = body.model_dump(exclude_none=True)
    if body.username is not None and body.username != user.username:
        existing = await db.scalar(select(UserAccount.id).where(UserAccount.username == body.username))
        if existing is not None:
            raise ConflictException(f"Username '{body.username}' already exists")
    for field, value in update_data.items():
        if field in ["requires_pin_change", "pin_setup_reason"]:
            if user.operator_profile:
                setattr(user.operator_profile, field, value)
        elif field == "role":
            role_res = await db.execute(select(UserRole).where(UserRole.name == value))
            user_role = role_res.scalar_one_or_none()
            if user_role:
                user.role_id = user_role.id
                user.role = user_role
                new_role_name = value
        else:
            setattr(user, field, value)

    # ── ROLE-01: Reconcile profiles on role change ──────────────────────
    if new_role_name and new_role_name != old_role_name:
        if new_role_name == RoleEnum.ADMIN.value:
            # Promoted to Admin — create AdminProfile if missing
            if not user.admin_profile:
                user.admin_profile = AdminProfile()
            # Keep historical scan ownership, but retire the operator credential.
            if user.operator_profile:
                user.operator_profile.pin_hash = None
                user.operator_profile.requires_pin_change = False
                user.operator_profile.pin_setup_reason = None
        elif new_role_name == RoleEnum.OPERATOR.value:
            # Demoted to Operator — create OperatorProfile if missing
            if not user.operator_profile:
                user.operator_profile = OperatorProfile(
                    requires_pin_change=True,
                    pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT,
                )
            user.operator_profile.pin_hash = None
            user.operator_profile.requires_pin_change = True
            user.operator_profile.pin_setup_reason = PinSetupReasonEnum.NEW_ACCOUNT
            # Admin must issue a fresh temporary PIN through reset-pin.

    sessions_revoked = user.role.name != old_role_name or user.status != old_status
    if sessions_revoked:
        user.token_version += 1

    after = _audit_snapshot(user)
    changes = audit.describe_changes(before, after)
    if changes:  # Saving unchanged values is not an event.
        if before["role"] != after["role"]:
            action = audit.AuditAction.USER_ROLE_CHANGED
        elif before["status"] != after["status"]:
            action = audit.AuditAction.USER_STATUS_CHANGED
        else:
            action = audit.AuditAction.USER_UPDATED
        await audit.record(
            db, action,
            f"Updated user {audit.quoted(old_username)} ({user.id}): {changes}"
            + ("; sessions revoked" if sessions_revoked else ""),
            actor=admin, ip=get_client_ip(request),
        )

    await db.flush()
    return UserResponse.from_db_model(user)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: uuid.UUID, body: UserPasswordReset, db: DbSession, admin: AdminUser, request: Request, response: Response
):
    """Reset a user's password (admin only). Now records an activity log."""
    response.headers["Cache-Control"] = "no-store"
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id)
                              .with_for_update().execution_options(populate_existing=True))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    password = body.new_password or temporary_password()
    user.password_hash = hash_password(password)
    user.requires_password_change = True
    user.password_setup_reason = body.password_setup_reason
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)

    # AUDIT-02: Record password reset in activity log (never the credential itself)
    await audit.record(
        db, audit.AuditAction.PASSWORD_RESET,
        f"Reset password for user {audit.quoted(user.username)} ({user.id}); "
        "setup required; sessions revoked",
        actor=admin, ip=get_client_ip(request),
    )
    await db.flush()

    return {"message": "Password reset successfully", "temporary_password": password}


@router.post("/{user_id}/reset-pin")
async def reset_user_pin(
    user_id: uuid.UUID, body: UserPinReset, db: DbSession, admin: AdminUser, request: Request, response: Response
):
    """Reset a user's PIN (admin only). Now records an activity log."""
    response.headers["Cache-Control"] = "no-store"
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.operator_profile), selectinload(UserAccount.role))
        .where(UserAccount.id == user_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if not user or not user.operator_profile:
        raise NotFoundException("User Operator Profile")
    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")

    pin = body.new_pin or temporary_pin()
    user.operator_profile.pin_hash = hash_pin(pin)
    user.operator_profile.requires_pin_change = True
    user.operator_profile.pin_setup_reason = body.pin_setup_reason
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)

    # AUDIT-02: Record PIN reset in activity log (never the credential itself)
    await audit.record(
        db, audit.AuditAction.PIN_RESET,
        f"Reset PIN for user {audit.quoted(user.username)} ({user.id}); "
        "setup required; sessions revoked",
        actor=admin, ip=get_client_ip(request),
    )
    await db.flush()

    return {"message": "PIN reset successfully", "temporary_pin": pin}
