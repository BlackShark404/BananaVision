# `04_activate_deactivate_user_flow.md` — Module 4: Activate / Deactivate User Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 4 (Activate / Deactivate User) |
| :--- | :--- |
| `frontend/src/pages/admin/UserManagement.tsx` | **Status Badge & Edit User Status Selector UI:** Renders the green/gray `"Status"` badge in the user table (`Active` vs. `Inactive`), populates `formData.status` in `handleOpenDialog(user.id)`, renders the `"Status"` `<Select>` dropdown inside the `"Edit User"` modal, and submits via `updateUser(editingId, formData)`. |
| `frontend/src/context/AdminContext.tsx` | **Admin State Mutation (`updateUser`):** Sends `PATCH /api/v1/users/{id}` with `status: data.status`, updates the user in `users` state, and recalculates the `"Active Users"` KPI counter. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Executes `PATCH /api/v1/users/${id}` with JSON payload and `Authorization: Bearer <token>`. |
| `backend/app/api/v1/users.py` | **Update User Controller (`PATCH /api/v1/users/{user_id}`):** Acquires transaction lock on `UserRole` (`Admin`), enforces the **Last Active Admin Guard (`ADMIN-01`)**, updates `user.status`, bumps `user.token_version += 1` to immediately revoke all active sessions of a deactivated user, and records `AuditAction.USER_STATUS_CHANGED`. |
| `backend/app/api/deps.py` | **Immediate Session Enforcement (`_resolve_user`):** On every authenticated request, checks `if user.status != ActiveStatusEnum.ACTIVE: raise ForbiddenException("Account is inactive")` and `if token_version != user.token_version: raise CredentialsException(...)`. |
| `backend/app/services/auth_service.py` | **Login & Kiosk PIN Swap Enforcement:** Rejects login (`authenticate_user`) and kiosk PIN swap (`swap_operator`) when `user.status == ActiveStatusEnum.INACTIVE`, and excludes inactive operators from `GET /api/v1/auth/operators`. |
| `backend/app/schemas/enums.py` | **Status Enumeration (`ActiveStatusEnum`):** Defines `ACTIVE = "Active"` and `INACTIVE = "Inactive"`. |
| `backend/app/models/user_account.py` | **SQLAlchemy ORM Model (`user_account`):** Stores `status` (`ActiveStatusEnum`) and `token_version` (`Integer`). |
| `backend/app/models/activity_log.py` | **SQLAlchemy ORM Model (`activity_log`):** Stores `user_status_changed` audit rows (e.g., `"Updated user 'juan' (...): status Active → Inactive; sessions revoked"`). |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: UI Status Badge, Edit Modal Status Dropdown & Client Submit

#### Step A1: Status Column Rendering, Status Filter & Edit User Status Selection (`UserManagement.tsx`)
* **Step Title & Trigger:** Administrator clicks the `"Edit User"` (`Pencil`) action button on a user row (`handleOpenDialog(user.id)`), changes the `"Status"` `<Select>` dropdown between `"Active"` and `"Inactive"`, and clicks `"Save Changes"`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 48–100, 162–170, 243–252, 315–363)
* **Complete Uncut Code Block:**
```tsx
  const [formData, setFormData] = useState({
    username: "",
    fullName: "",
    role: "Operator" as Role,
    status: "Active" as "Active" | "Inactive",
  })

  const filteredUsers = useMemo(() =>
    users.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false
      if (statusFilter !== "all" && u.status !== statusFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return u.fullName.toLowerCase().includes(q) || u.username.toLowerCase().includes(q)
      }
      return true
    }), [users, search, roleFilter, statusFilter]
  )

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
      header: "Status",
      sortable: true,
      sortKey: "status",
      cell: (user) => (
        <Badge variant="secondary" className={user.status === "Active" ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-100" : "bg-muted text-muted-foreground"}>
          {user.status}
        </Badge>
      ),
    },
```
```tsx
        <AppStatsCard
          loading={initialLoading}
          title="Active Users"
          value={users.filter(u => u.status === "Active").length}
          icon={UserCheck}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Currently enabled"
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
  * **Lines 67–73 (`handleOpenDialog(id)`):** Finds the clicked user `u = users.find(x => x.id === id)` and populates `formData` with `{ username: u.username, fullName: u.fullName, role: u.role, status: u.status }` and `setEditingId(id)`.
  * **Lines 341–349:** The `"Status"` `<Select>` binds `value={formData.status}` and updates `formData.status` to `"Active"` or `"Inactive"`.
  * **Lines 86–88:** Because `editingId` is non-null, `handleSubmit` calls `await updateUser(editingId, formData)`.

---

#### Step B2: `AdminContext.updateUser()` Dispatch
* **Step Title & Trigger:** `updateUser(id, data)` serializes `ApiUserUpdate` and calls `api.users.update(id, apiData)` (`PATCH /api/v1/users/{id}`).
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 269–294)
* **Complete Uncut Code Block:**
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
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 270–282:** Sends `PATCH /api/v1/users/${id}` with `status: data.status` (`"Active"` or `"Inactive"`).
  * **Line 284:** Replaces the updated user in `users` state (`prev.map((u) => (u.id === id ? mapped : u))`), immediately flipping the row's badge between emerald green (`bg-emerald-100 text-emerald-700`) and muted gray (`bg-muted text-muted-foreground`) and updating the `"Active Users"` KPI card count.

---

### Phase C, D & E: Backend Last-Admin Guard (`ADMIN-01`), Token Version Revocation & Audit Logging

#### Step D1: `PATCH /api/v1/users/{user_id}` — Concurrency Lock, Last-Admin Guard, Status Update & Session Revocation
* **Step Title & Trigger:** FastAPI invokes `update_user()` in `backend/app/api/v1/users.py`.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/users.py` (Lines 213–342)
* **Complete Uncut Code Block:**
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
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 220–228 (Cross-Admin Deadlock & Concurrent Deactivation Serialization):** Acquires a row lock on the `"Admin"` `UserRole` row first (`update(UserRole).where(UserRole.name == RoleEnum.ADMIN.value).values(name=UserRole.name)`), then re-verifies that the calling `admin` is still `ACTIVE`, still an `Admin`, and still on the same `token_version`. This prevents two administrators from simultaneously deactivating each other in parallel transactions and leaving 0 active admins.
  * **Lines 229–238:** Locks the target `UserAccount` row with `.with_for_update().execution_options(populate_existing=True)`.
  * **Lines 243–270 (`ADMIN-01` Last Active Administrator Protection):** If the target user is currently an `Active` `Admin` and `body.status != ActiveStatusEnum.ACTIVE` (`deactivating`), queries `SELECT count(*) FROM user_account JOIN user_role ... WHERE user_role.name = 'Admin' AND user_account.status = 'Active' AND user_account.id != :user_id`. If `other_active_admins == 0`, raises `ConflictException("Cannot deactivate or demote the last active administrator. Promote or activate another admin first.")` (HTTP 409).
  * **Lines 320–322 (Immediate Session Revocation on Status Change):** Checks `sessions_revoked = user.role.name != old_role_name or user.status != old_status`. When `user.status` changes (`Active` → `Inactive` or `Inactive` → `Active`), `user.token_version += 1` is executed.
  * **Lines 324–338 (Specific Audit Action `USER_STATUS_CHANGED`):** When `before["status"] != after["status"]` (and role did not change), selects `action = audit.AuditAction.USER_STATUS_CHANGED` (`"user_status_changed"`) and records `"Updated user '<username>' (<id>): status Active → Inactive; sessions revoked"`.

---

### Phase F: System-Wide Enforcement Against Deactivated Users

#### Step F1: How Deactivation Blocks Active Sessions, Web Login, and Kiosk PIN Selection
* **Step Title & Trigger:** Immediately after a user's status is set to `Inactive`, four enforcement points block that user across the entire station.
* **Exact File Path & Line Numbers:**
  1. `backend/app/api/deps.py` (Lines 50–58) — Blocks existing JWTs on any API request
  2. `backend/app/services/auth_service.py` (Lines 137–138 & 181–182) — Blocks web password login and kiosk PIN swap
  3. `backend/app/api/v1/auth.py` (Lines 147–166) — Hides deactivated operators from the Kiosk operator picker
* **Complete Uncut Code Block (`backend/app/api/deps.py`, Lines 50–58):**
```python
    if user.status != ActiveStatusEnum.ACTIVE:
        raise ForbiddenException("Account is inactive")

    # ── Token version check (AUTH-02 fix) ────────────────────────────────
    # Reject tokens issued before the latest logout / credential change.
    token_version = payload.get("tv")
    if token_version is None or token_version != user.token_version:
        raise CredentialsException("Session has been revoked — please log in again")
```
* **Complete Uncut Code Block (`backend/app/services/auth_service.py`, Lines 137–138 & 181–182):**
```python
    if user.status == ActiveStatusEnum.INACTIVE:
        return "inactive", user, None
```
* **Complete Uncut Code Block (`backend/app/api/v1/auth.py`, Lines 159–166):**
```python
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .join(UserAccount.role)
        .where(UserAccount.status == ActiveStatusEnum.ACTIVE)
        .where(UserRole.name == RoleEnum.OPERATOR.value)
        .order_by(UserAccount.full_name)
    )
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Active API Sessions (`deps.py` Line 50):** Any request carrying the deactivated user's JWT immediately receives HTTP 403 `"Account is inactive"` (and their token version is also bumped).
  * **Web Login (`auth_service.py` Line 137 & `Login.tsx` Line 72):** Attempting to log in displays `toast.error("Account Inactive", { description: "Your account is inactive. Please contact an administrator." })` and logs `AuditAction.LOGIN_DENIED`.
  * **Kiosk Operator List (`auth.py` Line 163):** `.where(UserAccount.status == ActiveStatusEnum.ACTIVE)` removes the deactivated operator from the Kiosk operator selection modal.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Backend Endpoint** | `PATCH /api/v1/users/{user_id}` → `update_user()` in `backend/app/api/v1/users.py` (Lines 213–342) |
| **Status Enum Values** | `ActiveStatusEnum.ACTIVE = "Active"`, `ActiveStatusEnum.INACTIVE = "Inactive"` (`backend/app/schemas/enums.py`) |
| **Last-Admin Guard (`ADMIN-01`)** | `backend/app/api/v1/users.py` Lines 243–270 — raises HTTP 409 `ConflictException` if `other_active_admins == 0` |
| **Concurrency Lock** | `update(UserRole).where(UserRole.name == RoleEnum.ADMIN.value)` + `select(UserAccount)...with_for_update()` (`users.py` Lines 220–237) |
| **Session Revocation** | `user.token_version += 1` whenever `user.status != old_status` (`users.py` Line 322) |
| **Audit Action** | `AuditAction.USER_STATUS_CHANGED` (`"user_status_changed"`) — marked `critical: true` in `frontend/src/lib/activityActions.ts` |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Add a 1-Click Activate / Deactivate Toggle Button Directly in the User Table `"Actions"` Column
* **Examiner Prompt:** *"Instead of opening the Edit User modal to change a user's status, add a 1-click Activate/Deactivate button (`UserCheck` / `UserX` icon) directly in the `'Actions'` column of `UserManagement.tsx`."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 26 & 180–210)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 26 & 180–210):**
```tsx
import { Loader2, Users, Plus, Pencil, ShieldAlert, ShieldCheck, UserCheck, Filter, KeyRound, Key } from "lucide-react"
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
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 26 & 180–215):**
```tsx
import { Loader2, Users, Plus, Pencil, ShieldAlert, ShieldCheck, UserCheck, UserX, Filter, KeyRound, Key } from "lucide-react"
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
            tooltip={user.status === "Active" ? "Deactivate User" : "Activate User"}
            icon={user.status === "Active" ? UserX : UserCheck}
            onClick={async () => {
              if (saving) return
              setSaving(true)
              try {
                const nextStatus = user.status === "Active" ? "Inactive" : "Active"
                await updateUser(user.id, { status: nextStatus })
                toast.success(`User ${nextStatus === "Active" ? "activated" : "deactivated"}`)
              } catch (error) {
                toast.error("Could not update status", { description: error instanceof Error ? error.message : "Please try again." })
              } finally {
                setSaving(false)
              }
            }}
            className={user.status === "Active" ? "hover:text-destructive" : "hover:text-emerald-600"}
          />
          <AppActionButton 
            disabled={saving}
            tooltip="Edit User" 
            icon={Pencil} 
            onClick={() => handleOpenDialog(user.id)} 
            className="hover:text-primary" 
          />
```

---

#### Drill Scenario 2: Prevent an Administrator from Deactivating Their Own Currently Signed-In Account
* **Examiner Prompt:** *"Even if there are multiple active administrators, block an administrator from deactivating their own currently logged-in account (`user_id == admin.id`) in `PATCH /api/v1/users/{user_id}`."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 248–253)
* **Before (`backend/app/api/v1/users.py`, Lines 248–253):**
```python
    if is_currently_active_admin:
        # Check if this update demotes or deactivates the user
        demoting = body.role is not None and body.role != RoleEnum.ADMIN
        deactivating = body.status is not None and body.status != ActiveStatusEnum.ACTIVE
        if demoting or deactivating:
```
* **After (`backend/app/api/v1/users.py`, Lines 248–257):**
```python
    if is_currently_active_admin:
        # Check if this update demotes or deactivates the user
        demoting = body.role is not None and body.role != RoleEnum.ADMIN
        deactivating = body.status is not None and body.status != ActiveStatusEnum.ACTIVE
        if deactivating and user.id == admin.id:
            raise ConflictException("You cannot deactivate your own currently signed-in administrator account.")
        if demoting or deactivating:
```

---

#### Drill Scenario 3: Require Minimum 2 Active Administrators Before Allowing Admin Deactivation
* **Examiner Prompt:** *"Strengthen the `ADMIN-01` guard so the system requires at least 2 other active administrators (`other_active_admins < 2`) before an admin can be deactivated or demoted."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 264–270)
* **Before (`backend/app/api/v1/users.py`, Lines 264–270):**
```python
            other_active_admins = active_admin_count_result.scalar() or 0
            if other_active_admins == 0:
                raise ConflictException(
                    "Cannot deactivate or demote the last active administrator. "
                    "Promote or activate another admin first."
                )
```
* **After (`backend/app/api/v1/users.py`, Lines 264–270):**
```python
            other_active_admins = active_admin_count_result.scalar() or 0
            if other_active_admins < 2:
                raise ConflictException(
                    "At least two other active administrators must remain when deactivating or demoting an admin."
                )
```
