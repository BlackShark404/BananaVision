# `05_edit_user_flow.md` — Module 5: Edit User (Details & Role Transitions `ROLE-01`) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 5 (Edit User) |
| :--- | :--- |
| `frontend/src/pages/admin/UserManagement.tsx` | **Edit User Dialog UI:** Renders the `"Edit User"` (`Pencil`) button in the `"Actions"` column, populates `formData` (`fullName`, `username`, `role`, `status`) and `editingId` via `handleOpenDialog(user.id)`, disables the `username` field (`disabled={!!editingId}`), and submits via `updateUser(editingId, formData)`. |
| `frontend/src/context/AdminContext.tsx` | **Admin State & Cross-Context Sync (`updateUser`):** Maps `Partial<User>` to `ApiUserUpdate`, calls `api.users.update(id, apiData)`, updates `users` state, and if the admin edited their own account (`user?.id === id`), calls `updateAuthUser()` in `AuthContext`. |
| `frontend/src/context/AuthContext.tsx` | **Active Session User Sync (`updateAuthUser`):** Updates the signed-in user's `fullName`, `username`, `role`, and `avatar` in React state and `localStorage` (`bananavision_user`) so the header greeting and sidebar footer update immediately without re-login. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `PATCH /api/v1/users/${id}` with JSON body and `Authorization: Bearer <token>`. |
| `backend/app/api/v1/users.py` | **Update User Controller (`PATCH /api/v1/users/{user_id}`):** Enforces `ADMIN-01` (last active admin protection on demotion), applies field updates, reconciles `AdminProfile` and `OperatorProfile` on role change (`ROLE-01`), increments `token_version += 1` if role or status changed, computes field diffs via `audit.describe_changes()`, and records `USER_UPDATED`, `USER_ROLE_CHANGED`, or `USER_STATUS_CHANGED`. |
| `backend/app/schemas/user.py` | **Pydantic Request/Response Contracts:** Defines `UserUpdate` (all fields optional) and `UserResponse.from_db_model(user)`. |
| `backend/app/services/audit.py` | **Diff Formatter & Audit Writer (`describe_changes` & `record`):** Formats `"field old → new"` strings while redacting `SENSITIVE_FIELDS` (`avatar_url`, passwords, PINs) to `"<field> changed"`. |
| `backend/app/models/user_account.py` | **SQLAlchemy ORM Model (`user_account`):** Stores `full_name`, `username`, `role_id`, `status`, and `token_version`. |
| `backend/app/models/admin_profile.py` | **SQLAlchemy ORM Model (`admin_profile`):** Created automatically when an Operator is promoted to Admin. |
| `backend/app/models/operator_profile.py` | **SQLAlchemy ORM Model (`operator_profile`):** Created or updated when an Admin is demoted to Operator (or retired by clearing `pin_hash = None` when an Operator is promoted to Admin). |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Opening the Edit Dialog, Form Pre-Population & Submission

#### Step A1: Edit Button Trigger (`handleOpenDialog(user.id)`), Form State & Submit (`UserManagement.tsx`)
* **Step Title & Trigger:** Administrator clicks the `"Edit User"` (`Pencil`) icon button on any row in the User Management table, edits `Full Name`, `Role`, or `Status`, and clicks `"Save Changes"`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 48–54, 67–100, 180–192, 315–363)
* **Complete Uncut Code Block:**
```tsx
  const [formData, setFormData] = useState({
    username: "",
    fullName: "",
    role: "Operator" as Role,
    status: "Active" as "Active" | "Inactive",
  })
```
```tsx
  const handleOpenDialog = (id?: string) => {
    if (id) {
      const u = users.find(x => x.id === id)
      if (u) {
        setFormData({ username: u.username, fullName: u.fullName, role: u.role, status: u.status })
        setEditingId(id)
      }
    } else {
      setFormData({ username: "", fullName: "", role: "Operator", status: "Active" })
      setEditingId(null)
    }
    setIsDialogOpen(true)
  }

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (saving) return
    setSaving(true)
    try {
      if (editingId) {
        await updateUser(editingId, formData)
        toast.success("User updated")
      } else {
        const result = await addUser({ ...formData, lastActive: "Never" })
        setHandoff({ username: result.user.username, password: result.password, pin: result.pin })
        toast.success("User created")
      }
      setIsDialogOpen(false)
    } catch (error) {
      toast.error("Could not save user", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSaving(false)
    }
  }
```
```tsx
    {
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (user) => (
        <div className="flex items-center justify-end gap-1">
          <AppActionButton 
            disabled={saving}
            tooltip="Edit User" 
            icon={Pencil} 
            onClick={() => handleOpenDialog(user.id)} 
            className="hover:text-primary" 
          />
```
```tsx
      <Dialog open={isDialogOpen} onOpenChange={open => !saving && setIsDialogOpen(open)}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle>{editingId ? "Edit User" : "Add New User"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="fullName">Full Name</Label>
              <Input id="fullName" value={formData.fullName} onChange={e => setFormData({ ...formData, fullName: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required disabled={!!editingId} className={editingId ? "opacity-60 cursor-not-allowed" : ""} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={formData.role} onValueChange={(v: Role) => setFormData({ ...formData, role: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Operator">Operator</SelectItem>
                    <SelectItem value="Admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={formData.status} onValueChange={(v: "Active" | "Inactive") => setFormData({ ...formData, status: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Active">Active</SelectItem>
                    <SelectItem value="Inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {!editingId && (
              <div className="bg-muted/50 border text-muted-foreground p-4 rounded-xl text-sm leading-relaxed mt-2">
                <p>A unique temporary password and, for operators, PIN will be displayed once after creation. Share them privately with the account owner.</p>
                <p className="mt-2">They will be required to change their credentials upon first login.</p>
              </div>
            )}
            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" disabled={saving} onClick={() => setIsDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>{saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Saving…" : editingId ? "Save Changes" : "Create User"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 68–73:** When `handleOpenDialog(user.id)` runs, `editingId` is set to `user.id` and `formData` is populated from the selected user in `users`.
  * **Line 318:** Dialog title switches to `"Edit User"` (`{editingId ? "Edit User" : "Add New User"}`).
  * **Line 327:** The `Username` input is locked in the UI during edits via `disabled={!!editingId}` and styled with `className={editingId ? "opacity-60 cursor-not-allowed" : ""}`.
  * **Line 351:** `{!editingId && (...)}` hides the temporary-credentials info box when editing an existing user.
  * **Line 359:** Submit button label renders `"Save Changes"` (or `"Saving…"` with spinning `Loader2` while `saving === true`).

---

#### Step B2: `AdminContext.updateUser()` & Cross-Context `AuthContext.updateAuthUser()`
* **Step Title & Trigger:** `handleSubmit` calls `updateUser(editingId, formData)` in `AdminContext.tsx`, which sends `PATCH /api/v1/users/${id}` and synchronizes both `AdminContext.users` and `AuthContext.user`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 269–294) and `frontend/src/context/AuthContext.tsx` (Lines 209–220)
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 269–294):**
```tsx
  const updateUser = useCallback(async (id: string, data: Partial<User>) => {
    const apiData: ApiUserUpdate = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
      requires_password_change: data.requiresPasswordChange,
      password_setup_reason: data.passwordSetupReason,
      requires_pin_change: data.requiresPinChange,
      pin_setup_reason: data.pinSetupReason,
      avatar_url: data.avatar,
    }

    const mapped = mapApiUser(await api.users.update(id, apiData))
    acceptUserWrite()
    setUsers((prev) => prev.map((u) => (u.id === id ? mapped : u)))
    if (user?.id === id) {
      updateAuthUser({
        username: mapped.username,
        fullName: mapped.fullName,
        role: mapped.role,
        avatar: mapped.avatar,
      }, user)
    }
    return mapped
  }, [user, updateAuthUser, setUsers, acceptUserWrite])
```
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 209–220):**
```tsx
  // ── Update Auth User (cross-context) ────────────────────────────────────

  const updateAuthUser = useCallback((data: Partial<AuthUser>, expectedUser?: Pick<AuthUser, "id" | "role">) => {
    setUser((prev) => {
      if (!prev) return prev
      if (expectedUser && (prev.id !== expectedUser.id || prev.role !== expectedUser.role)) return prev
      const updated = { ...prev, ...data }
      setStoredUser(updated)
      return updated
    })
  }, [])
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`AdminContext.tsx` Lines 285–292:** If the administrator edited their own user record (`user?.id === id`), `updateAuthUser` is invoked so that `AppHeader` (`"Welcome back, <FirstName>"`) and `AppSidebarFooter` (`user.fullName` and avatar) reflect the new name immediately and persist it to `localStorage` (`setStoredUser(updated)`).
  * **`AuthContext.tsx` Line 214:** `expectedUser` guard verifies `prev.id === expectedUser.id && prev.role === expectedUser.role` so a late response after an account swap cannot overwrite a different signed-in user.

---

### Phase C, D & E: Backend Controller, Profile Reconciliation (`ROLE-01`), Diff Calculation & Database Persistence

#### Step D1: `PATCH /api/v1/users/{user_id}` & `ROLE-01` Profile Reconciliation
* **Step Title & Trigger:** FastAPI validates `UserUpdate` (`backend/app/schemas/user.py`) and executes `update_user()` in `backend/app/api/v1/users.py`.
* **Exact File Path & Line Numbers:** `backend/app/schemas/user.py` (Lines 30–40), `backend/app/api/v1/users.py` (Lines 48–72 & 213–342), and `backend/app/services/audit.py` (Lines 193–206)
* **Complete Uncut Code Block (`backend/app/schemas/user.py`, Lines 30–40):**
```python
class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=2, max_length=50)
    full_name: str | None = Field(None, min_length=2, max_length=100)
    role: RoleEnum | None = None
    status: ActiveStatusEnum | None = None
    avatar_url: str | None = None
    requires_password_change: bool | None = None
    password_setup_reason: PasswordSetupReasonEnum | None = None
    requires_pin_change: bool | None = None
    pin_setup_reason: PinSetupReasonEnum | None = None
```
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 48–72 & 213–342):**
```python
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
```
```python
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
```
* **Complete Uncut Code Block (`backend/app/services/audit.py`, Lines 193–206):**
```python
def describe_changes(before: dict, after: dict, fields=None) -> str:
    """'field old → new' for each changed field; private fields only say they changed."""
    keys = list(fields) if fields is not None else list(dict.fromkeys([*before, *after]))
    parts = []
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if key in SENSITIVE_FIELDS:
            parts.append(f"{key} changed")
        else:
            parts.append(f"{key} {_render(old)} → {_render(new)}")
    return "; ".join(parts)
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 275 & 324–325 (`_audit_snapshot` & `audit.describe_changes`):** Captures the exact state of the user before and after applying `update_data`. If the admin clicks `"Save Changes"` without modifying any field, `changes` is `""` (`if changes:` is `False`) and no redundant audit row is written.
  * **Lines 298–319 (`ROLE-01` Profile Reconciliation):**
    * **Promoting Operator → Admin (`new_role_name == "Admin"`):** Creates `user.admin_profile = AdminProfile()` if one doesn't exist. Crucially, it **does not delete** `user.operator_profile` (because `scan.operator_id` foreign keys reference `operator_profile.id` for historical scans), but it retires the kiosk credential by setting `user.operator_profile.pin_hash = None`, `requires_pin_change = False`, and `pin_setup_reason = None`.
    * **Demoting Admin → Operator (`new_role_name == "Operator"`):** Creates `user.operator_profile = OperatorProfile(...)` if missing, sets `pin_hash = None`, `requires_pin_change = True`, and `pin_setup_reason = PinSetupReasonEnum.NEW_ACCOUNT` (so the admin can issue a fresh temporary PIN via Reset Kiosk PIN).
  * **Lines 320–338:** If `role` changed, bumps `user.token_version += 1` (revoking any active JWT carrying the old role claim) and logs `AuditAction.USER_ROLE_CHANGED`. If only `full_name` (or another general field) changed, logs `AuditAction.USER_UPDATED` without revoking the user's session.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Backend Endpoint** | `PATCH /api/v1/users/{user_id}` → `update_user()` in `backend/app/api/v1/users.py` (Lines 213–342) |
| **Request Schema** | `UserUpdate` in `backend/app/schemas/user.py` (Lines 30–40) |
| **Profile Reconciliation (`ROLE-01`)** | Operator → Admin: creates `AdminProfile`, clears `operator_profile.pin_hash = None` (preserves row for scan history FKs). Admin → Operator: creates `OperatorProfile` with `requires_pin_change = True`. |
| **Audit Action Selection** | Role changed → `USER_ROLE_CHANGED`; Status changed → `USER_STATUS_CHANGED`; Other fields → `USER_UPDATED` (`users.py` Lines 327–332) |
| **Cross-Context Sync** | `if (user?.id === id) updateAuthUser(...)` in `frontend/src/context/AdminContext.tsx` (Lines 285–292) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Allow Administrators to Edit a User's `username` Inside the `"Edit User"` Modal
* **Examiner Prompt:** *"Currently, the `Username` input in `UserManagement.tsx` is disabled when editing an existing user (`disabled={!!editingId}`), even though the backend `PATCH /api/v1/users/{user_id}` already supports username updates with uniqueness checking. Enable editing the username in the Edit User modal."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 325–328)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 325–328):**
```tsx
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required disabled={!!editingId} className={editingId ? "opacity-60 cursor-not-allowed" : ""} />
            </div>
```
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 325–328):**
```tsx
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required />
            </div>
```

---

#### Drill Scenario 2: Automatically Issue and Display a Temporary PIN When Demoting an Admin to Operator
* **Examiner Prompt:** *"When an Admin is demoted to an Operator in `PATCH /api/v1/users/{user_id}`, automatically generate and hash a temporary PIN using `temporary_pin()` and `hash_pin()` so they don't have a `None` `pin_hash`."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 308–319)
* **Before (`backend/app/api/v1/users.py`, Lines 308–319):**
```python
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
```
* **After (`backend/app/api/v1/users.py`, Lines 308–319):**
```python
        elif new_role_name == RoleEnum.OPERATOR.value:
            # Demoted to Operator — create OperatorProfile if missing
            if not user.operator_profile:
                user.operator_profile = OperatorProfile(
                    requires_pin_change=True,
                    pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT,
                )
            user.operator_profile.pin_hash = hash_pin(temporary_pin())
            user.operator_profile.requires_pin_change = True
            user.operator_profile.pin_setup_reason = PinSetupReasonEnum.NEW_ACCOUNT
```

---

#### Drill Scenario 3: Disable the `"Save Changes"` Button When No Fields Have Changed in the Edit User Modal
* **Examiner Prompt:** *"In `UserManagement.tsx`, disable the `'Save Changes'` button during Edit mode if the form fields (`fullName`, `username`, `role`, `status`) are identical to the original user record."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 67–80 & 357–360)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 357–360):**
```tsx
            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" disabled={saving} onClick={() => setIsDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>{saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Saving…" : editingId ? "Save Changes" : "Create User"}</Button>
            </DialogFooter>
```
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 357–368):**
```tsx
            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" disabled={saving} onClick={() => setIsDialogOpen(false)}>Cancel</Button>
              <Button
                type="submit"
                disabled={
                  saving ||
                  Boolean(
                    editingId &&
                    users.some(
                      (u) =>
                        u.id === editingId &&
                        u.fullName === formData.fullName &&
                        u.username === formData.username &&
                        u.role === formData.role &&
                        u.status === formData.status
                    )
                  )
                }
              >
                {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}
                {saving ? "Saving…" : editingId ? "Save Changes" : "Create User"}
              </Button>
            </DialogFooter>
```
