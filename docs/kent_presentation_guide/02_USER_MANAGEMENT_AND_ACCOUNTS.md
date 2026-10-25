# 👥 Deep Dive: User Management, Account Governance & Role Reconciliation

> **Features Covered:**  
> - Feature 2: Create Account  
> - Feature 3: User Management (List, Search, Filter, Pagination)  
> - Feature 4: Activate / Deactivate User  
> - Feature 5: Edit User  
> - Feature 6: Reset Password & PIN  
> **Backend Files:** [`backend/app/api/v1/users.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/users.py), [`backend/app/models/user_account.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/models/user_account.py), [`backend/app/models/admin_profile.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/models/admin_profile.py), [`backend/app/models/operator_profile.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/models/operator_profile.py)  
> **Frontend Files:** [`frontend/src/pages/admin/UserManagement.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/admin/UserManagement.tsx), [`frontend/src/context/AdminContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AdminContext.tsx)

---

## 1. Why Did We Implement This System? (Business & Security Purpose)

In an automated banana packing facility, access to sensitive operations (calibration, device mapping, system reboots, and historical data exports) must be strictly separated from routine quality scanning.
- **Administrators** hold system authority.
- **Operators** hold scanning authority.
- Staff turnover requires clean onboarding, temporary credentials with forced first-login change, immediate account suspension (deactivation), and foolproof credential recovery when PINs or passwords are forgotten.

---

## 2. Security Vulnerabilities Fixed in This Module

| Vulnerability ID | Historical Flaw | How Kent's Code Fixed It |
|---|---|---|
| **SAVE-01** | Failed account creation would catch errors and create a "phantom" local user in React state, making failed operations look successful. | React context now awaits real backend DB commit; on failure, throws an exception, leaves the modal open with inputs intact, and displays the exact backend error. |
| **CREATE-01** | Creating an account with "Inactive" status ignored the field and defaulted to "Active". | `body.status` is now passed directly to SQLAlchemy model initialization. |
| **CREATE-02** | Hardcoded initial credentials were logged to standard output. | Dynamic temporary credential generator (`temporary_password()` and `temporary_pin()`) with cryptographic setup flags. |
| **ACCESS-01** | Listing users was permitted with basic `CurrentUser` instead of `AdminUser`. | Endpoint now requires `admin: AdminUser` dependency, blocking non-admins. |
| **ROLE-01** | Promoting an operator to admin or demoting an admin left orphaned profile records and lingering PIN credentials. | **Automatic Profile Reconciliation**: Demoting an admin creates an `OperatorProfile` with forced PIN change; promoting an operator creates an `AdminProfile` and retires their PIN. |
| **ADMIN-01** | The last active administrator could deactivate or demote themselves, locking everyone out forever. | **Last Admin Protection Policy**: Atomic database transaction counts active admins before allowing demotion/deactivation. If count is 0, request is rejected with HTTP 409. |
| **RESET-01** | The UI called generic `PATCH /users/{id}` (which ignored password/PIN) instead of dedicated reset endpoints. | UI now calls dedicated POST endpoints: `/users/{id}/reset-password` and `/users/{id}/reset-pin`, revoking old sessions. |

---

## 3. Database Architecture: Polymorphic Roles & Profile Tables

```
                    ┌─────────────────────────┐
                    │       UserAccount       │
                    ├─────────────────────────┤
                    │ id: UUID (PK)           │
                    │ username: String(50)    │
                    │ full_name: String(100)  │
                    │ password_hash: String   │
                    │ role_id: UUID (FK)      │
                    │ status: Enum('Active')  │
                    │ token_version: Integer  │
                    └────────────┬────────────┘
                                 │
           ┌─────────────────────┴─────────────────────┐
           ▼                                           ▼
┌──────────────────────┐                   ┌──────────────────────┐
│     AdminProfile     │                   │   OperatorProfile    │
├──────────────────────┤                   ├──────────────────────┤
│ id: UUID (PK)        │                   │ id: UUID (PK)        │
│ account_id: UUID(FK) │                   │ account_id: UUID(FK) │
│ department: String   │                   │ pin_hash: String     │
│                      │                   │ requires_pin_change  │
└──────────────────────┘                   └──────────────────────┘
```

---

## 4. Part-by-Part Code Walkthrough

### Part A: Account Creation (`backend/app/api/v1/users.py:62`)

```python
@router.post("", response_model=UserCreatedResponse, status_code=201)
async def create_user(body: UserCreate, db: DbSession, admin: AdminUser, request: Request, response: Response):
    # 1. Prevent duplicate usernames
    existing = await db.execute(select(UserAccount).where(UserAccount.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Username '{body.username}' already exists")

    # 2. Generate temporary credentials if not provided
    password = body.password or temporary_password()
    pin = (body.pin or temporary_pin()) if body.role == RoleEnum.OPERATOR else None

    # 3. Create core user account with forced password change
    user = UserAccount(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(password),
        role_id=user_role.id,
        status=body.status,
        requires_password_change=True,
        password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT,
    )

    # 4. Attach appropriate profile based on role
    if body.role == RoleEnum.ADMIN.value:
        user.admin_profile = AdminProfile()
    elif body.role == RoleEnum.OPERATOR.value:
        user.operator_profile = OperatorProfile(
            pin_hash=hash_pin(pin),
            requires_pin_change=True,
            pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT,
        )

    db.add(user)
    # 5. Record administrative audit log
    db.add(ActivityLog(
        user_id=admin.id,
        action="user_created",
        details=f"Created user '{body.username}' with role {body.role}",
        ip_address=get_client_ip(request),
    ))
    await db.flush()
    return UserCreatedResponse(..., temporary_password=password, temporary_pin=pin)
```
- **Handoff Dialog in Frontend:** In `UserManagement.tsx`, when this endpoint returns, the frontend opens a secure `CredentialHandoffDialog` displaying the generated temporary password and PIN so the administrator can hand it to the physical worker.

---

### Part B: The Last Active Admin Safeguard (`ADMIN-01`) (`users.py:198`)

```python
# Check if target user is currently an active admin
is_currently_active_admin = (
    user.role and user.role.name == RoleEnum.ADMIN.value
    and user.status == ActiveStatusEnum.ACTIVE
)

if is_currently_active_admin:
    demoting = body.role is not None and body.role != RoleEnum.ADMIN
    deactivating = body.status is not None and body.status != ActiveStatusEnum.ACTIVE
    
    if demoting or deactivating:
        # Count all other active administrators in the database
        active_admin_count_result = await db.execute(
            select(func.count())
            .select_from(UserAccount)
            .join(UserRole, UserAccount.role_id == UserRole.id)
            .where(
                UserRole.name == RoleEnum.ADMIN.value,
                UserAccount.status == ActiveStatusEnum.ACTIVE,
                UserAccount.id != user_id,  # Exclude target user!
            )
        )
        other_active_admins = active_admin_count_result.scalar() or 0
        if other_active_admins == 0:
            raise ConflictException(
                "Cannot deactivate or demote the last active administrator. "
                "Promote or activate another admin first."
            )
```
- **Why this is critical:** Without this check, a lone admin could accidentally deactivate themselves, leaving the kiosk in a permanent bricked administrative state requiring direct database shell intervention.

---

### Part C: Role Reconciliation (`ROLE-01`) (`users.py:250`)

When an admin edits a user's role:
```python
if new_role_name and new_role_name != old_role_name:
    if new_role_name == RoleEnum.ADMIN.value:
        # Promoted from Operator to Admin:
        if not user.admin_profile:
            user.admin_profile = AdminProfile()
        # Retire the kiosk PIN so old PIN cannot be used to bypass admin auth
        if user.operator_profile:
            user.operator_profile.pin_hash = None
            user.operator_profile.requires_pin_change = False

    elif new_role_name == RoleEnum.OPERATOR.value:
        # Demoted from Admin to Operator:
        if not user.operator_profile:
            user.operator_profile = OperatorProfile()
        user.operator_profile.pin_hash = None
        user.operator_profile.requires_pin_change = True
        user.operator_profile.pin_setup_reason = PinSetupReasonEnum.NEW_ACCOUNT

    # Revoke all currently active JWTs across devices!
    user.token_version += 1
```
- If an operator is demoted or promoted, their `token_version` increments, forcing them to re-login with their new role capabilities immediately.

---

### Part D: Dedicated Password & PIN Reset Endpoints (`users.py:291` & `321`)

When an operator forgets their kiosk PIN or an admin forgets their password:
```python
@router.post("/{user_id}/reset-password")
async def reset_user_password(user_id: uuid.UUID, body: UserPasswordReset, db: DbSession, admin: AdminUser):
    password = body.new_password or temporary_password()
    user.password_hash = hash_password(password)
    user.requires_password_change = True
    user.token_version += 1  # Session revocation!
    db.add(ActivityLog(user_id=admin.id, action="user_updated", details=f"Admin reset password for '{user.username}'"))
    await db.flush()
    return {"message": "Password reset successfully", "temporary_password": password}
```
And for PIN reset:
```python
@router.post("/{user_id}/reset-pin")
async def reset_user_pin(user_id: uuid.UUID, body: UserPinReset, db: DbSession, admin: AdminUser):
    # Only operators have PINs!
    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")
    pin = body.new_pin or temporary_pin()
    user.operator_profile.pin_hash = hash_pin(pin)
    user.operator_profile.requires_pin_change = True
    user.token_version += 1
    ...
    return {"message": "PIN reset successfully", "temporary_pin": pin}
```

---

### Part E: Frontend User Management Page (`UserManagement.tsx`)

In `frontend/src/pages/admin/UserManagement.tsx`:
1. **Real-time Filter & Search Memoization:**
   ```tsx
   const filteredUsers = useMemo(() => 
     users.filter(u => {
       if (roleFilter !== "All" && u.role !== roleFilter) return false
       if (statusFilter !== "All" && u.status !== statusFilter) return false
       if (search) {
         const q = search.toLowerCase()
         return u.fullName.toLowerCase().includes(q) || u.username.toLowerCase().includes(q)
       }
       return true
     }), [users, search, roleFilter, statusFilter]
   )
   ```
2. **Dedicated Reset Password Modal:** An admin clicks "Reset Password", confirms the action, and receives the new temporary password to deliver to the user.
3. **Dedicated Reset PIN Modal:** An admin clicks "Reset PIN", confirms the action, and receives the 4-digit temporary PIN.

---

## 5. Summary of Key Defense Takeaways

1. **Strict Admin Verification:** Only users authenticated with the `Admin` role can view, create, edit, or reset accounts.
2. **Fail-Safe Administration:** The database transaction explicitly blocks self-deactivation of the final administrator.
3. **Clean Profile Lifecycle:** Role changes automatically provision or deprecate `AdminProfile` and `OperatorProfile` records without data corruption.
4. **Session Killing on Change:** Bumping `token_version` ensures that a suspended or demoted employee is logged out of all connected browsers instantly.
