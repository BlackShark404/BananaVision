# `02_create_account_flow.md` — Module 2: Create Account Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 2 (Create Account) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Route & Admin Guard:** Protects `/admin/users` with `<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>`, redirecting non-authenticated users to `/` and non-Admin users to `/dashboard`. |
| `frontend/src/pages/admin/UserManagement.tsx` | **Create Account Modal & Handoff Dialog UI:** Renders the `"Add User"` header button, the `"Add New User"` Radix `<Dialog>` form (`fullName`, `username`, `role`, `status`), the form submit handler (`handleSubmit`), and the one-time `"Temporary credentials"` handoff `<Dialog>` (`handoff` state). |
| `frontend/src/context/AdminContext.tsx` | **Frontend Admin State Controller:** Exposes `addUser()`, maps camelCase `fullName` to snake_case `full_name`, calls `api.users.create(apiData)`, appends the mapped `User` to `users` state, and returns `{ user, password, pin }` for the handoff modal. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `POST /api/v1/users` with JSON body `{ username, full_name, role, status }` and `Authorization: Bearer <token>`. |
| `backend/app/api/deps.py` | **Admin Authorization Dependency (`AdminUser`):** Runs `get_current_user` → `require_admin`, verifying a valid JWT, `ActiveStatusEnum.ACTIVE`, matching `token_version`, and `user.role.name == "Admin"`. |
| `backend/app/api/v1/users.py` | **Create User Controller (`POST /api/v1/users`):** Checks duplicate `username` (409 Conflict), resolves `UserRole`, generates temporary password & operator PIN, creates `UserAccount` + `AdminProfile` or `OperatorProfile`, records `AuditAction.USER_CREATED`, sets `Cache-Control: no-store`, and returns `UserCreatedResponse` (HTTP 201). |
| `backend/app/schemas/user.py` | **Pydantic Request/Response Contracts:** Defines `UserCreate` (`username` 2–50 chars, `full_name` 2–100 chars, `role`, `status`), `UserResponse`, and `UserCreatedResponse` (adds `temporary_password` and `temporary_pin`). |
| `backend/app/core/temporary_credentials.py` | **Cryptographic Temporary Credential Generator:** Generates a 24-character URL-safe temporary password (`secrets.token_urlsafe(18)`) and a 4-digit zero-padded temporary operator PIN (`f"{secrets.randbelow(10000):04d}"`). |
| `backend/app/core/security.py` | **Bcrypt Hashing Utility:** Hashes the temporary password (`hash_password`) and temporary operator PIN (`hash_pin`) with `bcrypt.gensalt()` before storing in PostgreSQL. |
| `backend/app/models/user_account.py` | **SQLAlchemy ORM Model (`user_account`):** Persists the account row with `requires_password_change=True` and `password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT`. |
| `backend/app/models/admin_profile.py` | **SQLAlchemy ORM Model (`admin_profile`):** One-to-one profile row created when `body.role == RoleEnum.ADMIN.value`. |
| `backend/app/models/operator_profile.py` | **SQLAlchemy ORM Model (`operator_profile`):** One-to-one profile row created when `body.role == RoleEnum.OPERATOR.value` with `pin_hash`, `requires_pin_change=True`, and `pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT`. |
| `backend/app/models/activity_log.py` | **SQLAlchemy ORM Model (`activity_log`):** Stores the `user_created` audit row within the same database transaction. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A: Initial Page Load, Route Guard & Modal Trigger UI

#### Step A1: Admin Route Protection (`/admin/users`)
* **Step Title & Trigger:** Administrator navigates to `/admin/users` via the sidebar. React Router evaluates nested `<ProtectedRoute>` and `<ProtectedRoute reqAdmin>`.
* **Exact File Path & Line Numbers:** `frontend/src/App.tsx` (Lines 43–50 & 70–85)
* **Complete Uncut Code Block:**
```tsx
// Protected Route Wrapper
function ProtectedRoute({ children, reqAdmin = false }: { children: React.ReactNode; reqAdmin?: boolean }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/" replace />
  if (reqAdmin && user.role !== "Admin") return <Navigate to="/dashboard" replace />
  return <>{children}</>
}
```
```tsx
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/devices" element={<DeviceStatus />} />
          <Route path="/scans/:scanId" element={<ScanDetail />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin/users" element={<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>} />
          <Route path="/admin/delivery-intakes" element={<ProtectedRoute reqAdmin><DeliveryIntake /></ProtectedRoute>} />
          <Route path="/admin/suppliers" element={<ProtectedRoute reqAdmin><SupplierManagement /></ProtectedRoute>} />

          <Route path="/admin/quality" element={<ProtectedRoute reqAdmin><QualityControl /></ProtectedRoute>} />
          <Route path="/admin/activity" element={<ProtectedRoute reqAdmin><ActivityLog /></ProtectedRoute>} />
          <Route path="/admin/config" element={<ProtectedRoute reqAdmin><SystemConfig /></ProtectedRoute>} />
        </Route>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 44–49:** First checks `if (!user) return <Navigate to="/" replace />`. Then, because `reqAdmin` is `true` on Line 78, checks `if (reqAdmin && user.role !== "Admin") return <Navigate to="/dashboard" replace />`. Only an authenticated Admin can mount `<UserManagement />`.

---

### Phase B: User Input, Create Dialog Form & Client-Side State Handling

#### Step B1: Opening the `"Add New User"` Dialog, Form Input Binding & `handleSubmit`
* **Step Title & Trigger:** Administrator clicks the `"+ Add User"` button in `AppPageHeader` (`handleOpenDialog()`), fills out `Full Name`, `Username`, `Role`, and `Status`, and clicks `"Create User"`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 33–100, 213–226, 315–375)
* **Complete Uncut Code Block:**
```tsx
export default function UserManagement() {
  const { users, usersLoading, usersReady, usersError, addUser, updateUser, resetPassword, resetPin } = useAdmin()
  const [saving, setSaving] = useState(false)
  const initialLoading = usersLoading && !usersReady
  const [search, setSearch] = useState("")
  const [roleFilter, setRoleFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  
  const [resetConfirmUser, setResetConfirmUser] = useState<{id: string, fullName: string} | null>(null)
  const [resetConfirmPin, setResetConfirmPin] = useState<{id: string, fullName: string} | null>(null)
  
  const [handoff, setHandoff] = useState<{ username: string; password?: string; pin?: string } | null>(null)

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
  return (
    <TooltipProvider>
      <div className="space-y-6">
        <AppPageHeader
          title="User Management"
          description="Manage operators and system administrators"
          icon={Users}
          action={
            <Button disabled={saving} onClick={() => handleOpenDialog()} className="shadow-md gap-2 w-full sm:w-auto">
              <Plus className="w-4 h-4" /> Add User
            </Button>
          }
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

      <Dialog open={!!handoff} onOpenChange={open => !open && setHandoff(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Temporary credentials</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Share these privately with the account owner before closing. They are displayed only now and must be replaced on first use.</p>
          <p>Username: <strong>{handoff?.username}</strong></p>
          {handoff?.password && <p>Temporary password: <code className="select-all break-all">{handoff.password}</code></p>}
          {handoff?.pin && <p>Temporary PIN: <code className="select-all">{handoff.pin}</code></p>}
          <DialogFooter><Button onClick={() => setHandoff(null)}>Done</Button></DialogFooter>
        </DialogContent>
      </Dialog>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 74–78 (`handleOpenDialog()` with no `id`):** Resets `formData` to `{ username: "", fullName: "", role: "Operator", status: "Active" }`, sets `editingId = null`, and opens the Dialog (`setIsDialogOpen(true)`).
  * **Lines 323 & 327:** In create mode (`editingId === null`), both `Full Name` and `Username` `<Input>` fields are enabled and `required`.
  * **Lines 351–356:** Renders the informational box (`bg-muted/50 border text-muted-foreground p-4 rounded-xl text-sm leading-relaxed mt-2`) explaining that a unique temporary password (and PIN for Operators) will be generated by the server and shown once.
  * **Lines 89–94 (`handleSubmit` Create Branch):** Calls `const result = await addUser({ ...formData, lastActive: "Never" })`, stores the returned one-time credentials in `setHandoff({ username: result.user.username, password: result.password, pin: result.pin })`, fires `toast.success("User created")`, and closes the form modal (`setIsDialogOpen(false)`).

---

#### Step B2: `AdminContext.addUser()` & `api.users.create()` Dispatch
* **Step Title & Trigger:** `handleSubmit` calls `addUser()` in `AdminContext.tsx`, which sends `POST /api/v1/users` via `api.users.create()`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 49–59, 127–132, 255–267) and `frontend/src/lib/api.ts` (Lines 282–292)
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 49–59, 127–132, 255–267):**
```tsx
const mapApiUser = (u: ApiUser): User => ({
  id: u.id,
  username: u.username,
  fullName: u.full_name,
  role: u.role,
  status: u.status,
  lastActive: u.last_active ?? "Never",
  avatar: u.avatar_url || undefined,
  requiresPasswordChange: u.requires_password_change,
  requiresPinChange: u.requires_pin_change,
})
```
```tsx
  const acceptUserWrite = useCallback(() => {
    ++usersRequests.generation
    setUsersLoading(false)
    setUsersError(null)
    if (!usersReady) setUsersReload(value => value + 1)
  }, [usersRequests, usersReady, setUsersLoading, setUsersError, setUsersReload])
```
```tsx
  const addUser = useCallback(async (data: Omit<User, "id">) => {
    const apiData = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
    }
    const result = await api.users.create(apiData)
    acceptUserWrite()
    const savedUser = mapApiUser(result)
    setUsers((prev) => [...prev, savedUser])
    return { user: savedUser, password: result.temporary_password, pin: result.temporary_pin ?? undefined }
  }, [setUsers, acceptUserWrite])
```
* **Complete Uncut Code Block (`frontend/src/lib/api.ts`, Lines 282–292):**
```ts
  // ── Users ────────────────────────────────────────────────────────────────
  users: {
    summary: (signal?: AbortSignal) => get<{ total_scans: number; avg_confidence: number | null; last_7_days: number; recent_actions_7d?: number; total_users: number | null; activity: { id: string; action: string; details: string; timestamp: string }[] }>("/api/v1/users/me/summary", undefined, signal),
    list: () => get<{ items: ApiUser[]; total: number }>("/api/v1/users"),
    create: (data: ApiUserCreate) => post<ApiUserCreated>("/api/v1/users", data),
    update: (id: string, data: ApiUserUpdate) => patch<ApiUser>(`/api/v1/users/${id}`, data),
    resetPassword: (id: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, {}),
    resetPin: (id: string) => post<{ message: string; temporary_pin: string }>(`/api/v1/users/${id}/reset-pin`, {}),
    /** Self-service profile update — any authenticated user can update their own avatar. (PROFILE-01) */
    updateProfile: (data: { avatar_url?: string }) => patch<ApiUser>(`/api/v1/users/me/profile`, data),
  },
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`AdminContext.tsx` Lines 256–261:** Maps `data.fullName` → `full_name` to match the backend Pydantic `UserCreate` schema.
  * **`api.ts` Line 286:** Sends `POST /api/v1/users` with `Authorization: Bearer <token>`.
  * **`AdminContext.tsx` Lines 263–266:** Increments `usersRequests.generation` via `acceptUserWrite()` (preventing any in-flight initial list fetch from overwriting the newly added user), maps the response with `mapApiUser(result)`, appends `savedUser` to `users`, and returns `{ user: savedUser, password: result.temporary_password, pin: result.temporary_pin ?? undefined }`.

---

### Phase C: Request Routing, Admin Middleware & Schema Validation

#### Step C1: `AdminUser` Dependency & `UserCreate` Pydantic Validation
* **Step Title & Trigger:** FastAPI routes `POST /api/v1/users` to `create_user()`, running `AdminUser` (`require_admin`) and validating the payload against `UserCreate`.
* **Exact File Path & Line Numbers:** `backend/app/api/deps.py` (Lines 88–97 & 103) and `backend/app/schemas/user.py` (Lines 21–28 & 54–91)
* **Complete Uncut Code Block (`backend/app/api/deps.py`, Lines 88–97 & 103):**
```python
async def require_admin(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserAccount:
    """Require the current user to have Admin role."""
    from app.services.audit import remember_actor
    remember_actor(user)
    if not user.role or user.role.name != RoleEnum.ADMIN.value:
        raise ForbiddenException("Admin access required")
    return user
```
```python
AdminUser = Annotated[UserAccount, Depends(require_admin)]
```
* **Complete Uncut Code Block (`backend/app/schemas/user.py`, Lines 21–28 & 54–91):**
```python
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str | None = Field(None, min_length=6, max_length=128)
    pin: str | None = Field(None, min_length=4, max_length=4, pattern=r"^\d{4}$")
    role: RoleEnum = RoleEnum.OPERATOR
    status: ActiveStatusEnum = ActiveStatusEnum.ACTIVE
```
```python
class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: RoleEnum
    status: ActiveStatusEnum
    avatar_url: str | None = None
    requires_password_change: bool = False
    requires_pin_change: bool = False
    last_active: Timestamp | None = None
    created_at: Timestamp

    model_config = {"from_attributes": True}

    @classmethod
    def from_db_model(cls, account: "UserAccount") -> "UserResponse":
        return cls(
            id=account.id,
            username=account.username,
            full_name=account.full_name,
            role=account.role.name if account.role else "Unknown",
            status=account.status,
            avatar_url=account.avatar_url,
            requires_password_change=account.requires_password_change,
            requires_pin_change=account.operator_profile.requires_pin_change if account.operator_profile else False,
            last_active=account.last_active,
            created_at=account.created_at,
        )


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class UserCreatedResponse(UserResponse):
    temporary_password: str
    temporary_pin: str | None = None
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`deps.py` Lines 88–96:** If a non-Admin attempts `POST /api/v1/users`, `require_admin` raises `ForbiddenException("Admin access required")` (HTTP 403), and the audit handler logs an `access_denied` event.
  * **`schemas/user.py` Lines 21–28:** Enforces `username` (2–50 chars), `full_name` (2–100 chars), optional `password` (6–128 chars), optional `pin` (`^\d{4}$`), `role` (`Admin` | `Operator`), and `status` (`Active` | `Inactive`).

---

### Phase D: Backend Controller, Temporary Credential Generation & Bcrypt Hashing

#### Step D1: `create_user` Controller & Temporary Credential Generators
* **Step Title & Trigger:** `create_user()` in `backend/app/api/v1/users.py` checks uniqueness, generates temporary credentials via `temporary_credentials.py`, hashes them with `security.py`, creates the ORM entities, and records `AuditAction.USER_CREATED`.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/users.py` (Lines 89–138) and `backend/app/core/temporary_credentials.py` (Lines 1–10)
* **Complete Uncut Code Block (`backend/app/core/temporary_credentials.py`, Lines 1–10):**
```python
"""Temporary credentials are issued once to the creating/resetting administrator."""
import secrets


def temporary_password() -> str:
    return secrets.token_urlsafe(18)


def temporary_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"
```
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 89–138):**
```python
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
        # from_db_model reads this; an async session cannot lazy-load it after flush.
        user.operator_profile = None
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Line 92:** Sets `response.headers["Cache-Control"] = "no-store"` so proxies/browsers never cache the one-time plain-text `temporary_password` or `temporary_pin` returned in the 201 JSON response.
  * **Lines 93–95:** Checks `select(UserAccount).where(UserAccount.username == body.username)`. If a match exists, raises `ConflictException(f"Username '{body.username}' already exists")` (HTTP 409).
  * **Lines 97–100:** Looks up the `UserRole` row matching `body.role` (`"Admin"` or `"Operator"`).
  * **Lines 102–103:** Generates `password = body.password or temporary_password()` (18 random bytes → 24 URL-safe base64 characters) and, if `body.role == RoleEnum.OPERATOR`, `pin = body.pin or temporary_pin()` (random 4-digit string `"0000"`–`"9999"`).
  * **Lines 104–113:** Instantiates `UserAccount` with `password_hash=hash_password(password)` (bcrypt), `requires_password_change=True`, and `password_setup_reason=PasswordSetupReasonEnum.NEW_ACCOUNT` (`"new_account"`).
  * **Lines 115–125:**
    * If creating an **Admin**, attaches `user.admin_profile = AdminProfile()` and sets `user.operator_profile = None`.
    * If creating an **Operator**, attaches `user.operator_profile = OperatorProfile(pin_hash=hash_pin(pin), requires_pin_change=True, pin_setup_reason=PinSetupReasonEnum.NEW_ACCOUNT)`.
  * **Lines 126–135:** Calls `db.add(user)` and `await db.flush()` (which generates `user.id` UUID and cascades inserts to `admin_profile` or `operator_profile`), then calls `audit.record(db, audit.AuditAction.USER_CREATED, ...)` in the same transaction.

---

### Phase E: Database Operations & ORM Models

#### Step E1: `UserAccount`, `AdminProfile`, `OperatorProfile`, and `ActivityLog` Tables
* **Step Title & Trigger:** `db.add(user)` + `await db.flush()` + transaction commit at the end of `get_db` persist the new account, role profile, and audit log row.
* **Exact File Path & Line Numbers:**
  * `backend/app/models/admin_profile.py` (Lines 1–34)
  * `backend/app/models/operator_profile.py` (Lines 1–40)
* **Complete Uncut Code Block (`backend/app/models/admin_profile.py`, Lines 1–34):**
```python
"""
AdminProfile ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class AdminProfile(Base):
    __tablename__ = "admin_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships
    account = relationship("UserAccount", back_populates="admin_profile")
```
* **Complete Uncut Code Block (`backend/app/models/operator_profile.py`, Lines 1–40):**
```python
"""
OperatorProfile ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class OperatorProfile(Base):
    __tablename__ = "operator_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_pin_change: Mapped[bool] = mapped_column(Boolean, default=False
    )
    pin_setup_reason: Mapped[str | None] = mapped_column(String(50), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships
    account = relationship("UserAccount", back_populates="operator_profile", lazy="selectin")
    scans = relationship("Scan", back_populates="operator", lazy="raise")
```
* **Line-by-Line Connection & Trace Explanation:**
  * **SQL Operations Executed in One Atomic Transaction:**
    1. `SELECT * FROM user_account WHERE username = :username` (uniqueness check)
    2. `SELECT * FROM user_role WHERE name = :role` (role lookup)
    3. `INSERT INTO user_account (id, username, full_name, role_id, status, password_hash, requires_password_change, password_setup_reason, created_at, updated_at, token_version) VALUES (...)`
    4. Either `INSERT INTO operator_profile (id, account_id, pin_hash, requires_pin_change, pin_setup_reason, created_at, updated_at) VALUES (...)` (for Operator) or `INSERT INTO admin_profile (id, account_id, created_at, updated_at) VALUES (...)` (for Admin)
    5. `INSERT INTO activity_log (id, timestamp, user_id, action, details, ip_address, actor_name) VALUES (..., 'user_created', ...)`

---

### Phase F: Response, Handoff Modal Display & Error Handling

#### Step F1: One-Time Credential Handoff Modal & Duplicate Username Error Toast
* **Step Title & Trigger:** `POST /api/v1/users` returns HTTP 201 (`UserCreatedResponse`) or HTTP 409 (`ConflictException`).
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 89–97 & 365–374)
* **Complete Uncut Code Block:**
```tsx
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
```
```tsx
      <Dialog open={!!handoff} onOpenChange={open => !open && setHandoff(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Temporary credentials</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Share these privately with the account owner before closing. They are displayed only now and must be replaced on first use.</p>
          <p>Username: <strong>{handoff?.username}</strong></p>
          {handoff?.password && <p>Temporary password: <code className="select-all break-all">{handoff.password}</code></p>}
          {handoff?.pin && <p>Temporary PIN: <code className="select-all">{handoff.pin}</code></p>}
          <DialogFooter><Button onClick={() => setHandoff(null)}>Done</Button></DialogFooter>
        </DialogContent>
      </Dialog>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **On Success (HTTP 201):** `setHandoff({ username: result.user.username, password: result.password, pin: result.pin })` opens the `"Temporary credentials"` modal (`open={!!handoff}`). The temporary password and PIN are rendered inside `<code className="select-all break-all">` for easy click-to-copy. Simultaneously, the table and the `"Total Users"` / `"Active Users"` / `"Admins"` `AppStatsCard` counters update immediately because `setUsers((prev) => [...prev, savedUser])` updated the `users` array in `AdminContext`.
  * **On Failure (HTTP 409 / 422):** `api.ts` throws `new Error(detail)` (e.g., `"Username 'juan' already exists"`), and Line 96 renders `toast.error("Could not save user", { description: "Username 'juan' already exists" })` while keeping `isDialogOpen` open so the admin can correct the username.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Frontend Page & Route** | `/admin/users` → `frontend/src/pages/admin/UserManagement.tsx` (guarded by `<ProtectedRoute reqAdmin>`) |
| **Backend Endpoint** | `POST /api/v1/users` → `create_user()` in `backend/app/api/v1/users.py` (Lines 89–138, returns HTTP `201`) |
| **Pydantic Request Schema** | `UserCreate` in `backend/app/schemas/user.py` (Lines 21–28): `username` (2–50), `full_name` (2–100), `role`, `status` |
| **Pydantic Response Schema** | `UserCreatedResponse` in `backend/app/schemas/user.py` (Lines 89–91): extends `UserResponse` with `temporary_password` and `temporary_pin` |
| **Temp Credential Functions** | `temporary_password()` (`secrets.token_urlsafe(18)`) and `temporary_pin()` (`f"{secrets.randbelow(10000):04d}"`) in `backend/app/core/temporary_credentials.py` |
| **Forced Setup Flags on Create** | `UserAccount.requires_password_change = True`, `password_setup_reason = "new_account"`; `OperatorProfile.requires_pin_change = True`, `pin_setup_reason = "new_account"` |
| **Database Tables Written** | `user_account`, plus `operator_profile` (if Role = `Operator`) or `admin_profile` (if Role = `Admin`), plus `activity_log` (`action = 'user_created'`) |
| **Security Header** | `response.headers["Cache-Control"] = "no-store"` (`backend/app/api/v1/users.py` Line 92) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Enforce Strict Alphanumeric + Underscore Validation on `username` When Creating an Account
* **Examiner Prompt:** *"Prevent administrators from creating usernames with spaces or special characters. Enforce a regex pattern `^[a-zA-Z0-9_]+$` on `UserCreate.username` in the backend and add `pattern` validation on the frontend username `<Input>`."*
* **Files to Edit:**
  1. `backend/app/schemas/user.py` (Line 22)
  2. `frontend/src/pages/admin/UserManagement.tsx` (Line 327)
* **Before (`backend/app/schemas/user.py`, Line 22):**
```python
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
```
* **After (`backend/app/schemas/user.py`, Line 22):**
```python
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
```
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Line 327):**
```tsx
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required disabled={!!editingId} className={editingId ? "opacity-60 cursor-not-allowed" : ""} />
```
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Line 327):**
```tsx
              <Input id="username" pattern="^[a-zA-Z0-9_]+$" title="Only letters, numbers, and underscores are allowed" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required disabled={!!editingId} className={editingId ? "opacity-60 cursor-not-allowed" : ""} />
```

---

#### Drill Scenario 2: Add a `"Copy Credentials"` Button Inside the Temporary Credentials Handoff Dialog
* **Examiner Prompt:** *"In the `'Temporary credentials'` handoff dialog after creating a user, add a `'Copy Credentials'` button that copies the username, temporary password, and temporary PIN (if present) to the clipboard and shows a success toast."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 365–374)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 365–374):**
```tsx
      <Dialog open={!!handoff} onOpenChange={open => !open && setHandoff(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Temporary credentials</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Share these privately with the account owner before closing. They are displayed only now and must be replaced on first use.</p>
          <p>Username: <strong>{handoff?.username}</strong></p>
          {handoff?.password && <p>Temporary password: <code className="select-all break-all">{handoff.password}</code></p>}
          {handoff?.pin && <p>Temporary PIN: <code className="select-all">{handoff.pin}</code></p>}
          <DialogFooter><Button onClick={() => setHandoff(null)}>Done</Button></DialogFooter>
        </DialogContent>
      </Dialog>
```
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 365–385):**
```tsx
      <Dialog open={!!handoff} onOpenChange={open => !open && setHandoff(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Temporary credentials</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Share these privately with the account owner before closing. They are displayed only now and must be replaced on first use.</p>
          <p>Username: <strong>{handoff?.username}</strong></p>
          {handoff?.password && <p>Temporary password: <code className="select-all break-all">{handoff.password}</code></p>}
          {handoff?.pin && <p>Temporary PIN: <code className="select-all">{handoff.pin}</code></p>}
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const lines = [
                  `Username: ${handoff?.username ?? ""}`,
                  ...(handoff?.password ? [`Temporary Password: ${handoff.password}`] : []),
                  ...(handoff?.pin ? [`Temporary PIN: ${handoff.pin}`] : []),
                ]
                void navigator.clipboard.writeText(lines.join("\n"))
                toast.success("Credentials copied to clipboard")
              }}
            >
              Copy Credentials
            </Button>
            <Button onClick={() => setHandoff(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
```

---

#### Drill Scenario 3: Change the Generated Temporary PIN Length or Format (e.g., Avoid Leading Zeros `"1000"`–`"9999"`)
* **Examiner Prompt:** *"Modify the temporary operator PIN generator so that generated 4-digit PINs never start with `0` (always in the range `1000` to `9999`)."*
* **File to Edit:** `backend/app/core/temporary_credentials.py` (Lines 9–10)
* **Before (`backend/app/core/temporary_credentials.py`, Lines 9–10):**
```python
def temporary_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"
```
* **After (`backend/app/core/temporary_credentials.py`, Lines 9–10):**
```python
def temporary_pin() -> str:
    return f"{1000 + secrets.randbelow(9000):04d}"
```
