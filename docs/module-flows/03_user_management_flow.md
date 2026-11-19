# `03_user_management_flow.md` — Module 3: User Management (Listing, Stats, Search & Filtering) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 3 (User Management) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Route & Admin Guard:** Maps `/admin/users` to `<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>`. |
| `frontend/src/components/AppSidebar.tsx` | **Admin Sidebar Navigation Link:** Conditionally renders the `"Admin"` navigation group (`isAdmin = user?.role === "Admin"`) containing `<NavLink to="/admin/users">` (`User Management`). |
| `frontend/src/pages/admin/UserManagement.tsx` | **User Management Table, Stats Cards & Filters View:** Renders the 3 summary `AppStatsCard` widgets (`Total Users`, `Active Users`, `Admins`), `AppTableFilters` (search box, `roleFilter`, `statusFilter`), and `AppDataTable` with 5 columns (`User`, `Role`, `Status`, `Last Active`, `Actions`) paginated at `PAGE_SIZE = 10`. |
| `frontend/src/context/AdminContext.tsx` | **Admin Data Loader & Reconciler:** Calls `api.users.list()` when `user.role === "Admin"`, maps `ApiUser[]` to `User[]` via `mapApiUser`, manages `usersLoading`/`usersReady`/`usersError`, and auto-reconciles on window `focus`, `online`, `visibilitychange`, and `LIVE_RESUMED_EVENT`. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Executes `GET /api/v1/users` with a 15-second deadline (`requestWithDeadline`) and `Authorization: Bearer <token>`. |
| `frontend/src/lib/manilaTime.ts` | **Asia/Manila Date Formatter:** Provides `inManila()` used by the `"Last Active"` table column (`new Date(user.lastActive).toLocaleDateString(undefined, inManila())`). |
| `backend/app/api/deps.py` | **Admin Authorization Dependency (`AdminUser`):** Validates JWT bearer token and enforces `user.role.name == "Admin"`. |
| `backend/app/api/v1/users.py` | **List Users Controller (`GET /api/v1/users`):** Queries all `UserAccount` rows ordered by `UserAccount.created_at` with eager `selectinload(UserAccount.role)` and `selectinload(UserAccount.operator_profile)`. |
| `backend/app/schemas/user.py` | **Pydantic Response Contracts:** Defines `UserResponse.from_db_model(u)` and `UserListResponse` (`items: list[UserResponse]`, `total: int`). |
| `backend/app/models/user_account.py` | **SQLAlchemy ORM Model (`user_account`):** Source table for user accounts, joined to `user_role` and `operator_profile`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A: Sidebar Navigation & Route Guard Interception

#### Step A1: Admin Sidebar Menu & `/admin/users` Route Guard
* **Step Title & Trigger:** Logged-in Administrator clicks `"User Management"` in the left sidebar (`AppSidebar.tsx`), navigating to `/admin/users`.
* **Exact File Path & Line Numbers:** `frontend/src/components/AppSidebar.tsx` (Lines 27–39 & 80–94) and `frontend/src/App.tsx` (Lines 43–49 & 78)
* **Complete Uncut Code Block (`frontend/src/components/AppSidebar.tsx`, Lines 27–39 & 80–94):**
```tsx
const adminItems = [
  { to: "/admin/users", icon: Users, label: "User Management" },
  { to: "/admin/delivery-intakes", icon: Package, label: "Delivery Intakes" },
  { to: "/admin/suppliers", icon: Building2, label: "Supplier Management" },
  { to: "/admin/quality", icon: ShieldCheck, label: "Quality Control" },
  { to: "/admin/activity", icon: ScrollText, label: "Activity Log" },
  { to: "/admin/config", icon: Settings, label: "System Config" },
]

export default function AppSidebar({ onLinkClick }: { onLinkClick?: () => void } = {}) {
  const { user } = useAuth()
  const isAdmin = user?.role === "Admin"
  const navigate = useNavigate()
```
```tsx
        {isAdmin && (
          <>
            <Separator className="my-3" />
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-3">
              Admin
            </p>
            {adminItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={linkClass} onClick={onLinkClick}>
                <item.icon className="w-5 h-5 shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
```
* **Complete Uncut Code Block (`frontend/src/App.tsx`, Lines 43–49 & 78):**
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
          <Route path="/admin/users" element={<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>} />
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`AppSidebar.tsx` Lines 38 & 80:** Checks `isAdmin = user?.role === "Admin"`. Operators never see the `"Admin"` section in the sidebar.When active, `linkClass` applies `"bg-primary text-primary-foreground shadow-md"`.
  * **`App.tsx` Line 78:** Enforces `<ProtectedRoute reqAdmin>` so even if an Operator types `/admin/users` into the address bar, they are redirected to `/dashboard`.

---

### Phase B: Data Fetching, Scoped State & Live Reconciliation (`AdminContext.tsx`)

#### Step B1: `AdminProvider` Fetch Lifecycle & `mapApiUser` Transformation
* **Step Title & Trigger:** When the Admin logs in or navigates to `/admin/users`, `AdminProvider`'s `useEffect` triggers `api.users.list()` (`GET /api/v1/users`) and stores the mapped `User[]` in `users` state.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 49–59, 91–133, 159–185, 223–251)
* **Complete Uncut Code Block:**
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
function useScopedState<T>(scope: string, initial: T): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState({ scope, value: initial })
  // React discards this render and retries with the new scope before children commit.
  if (state.scope !== scope) setState({ scope, value: initial })
  const setValue = useCallback((action: React.SetStateAction<T>) => {
    setState(previous => {
      // Ignore late requests issued by an account that has since signed out/swapped.
      if (previous.scope !== scope) return previous
      const value = typeof action === "function" ? (action as (value: T) => T)(previous.value) : action
      return { scope, value }
    })
  }, [scope])
  return [state.scope === scope ? state.value : initial, setValue]
}

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const { user, updateAuthUser } = useAuth()
  const { pathname } = useLocation()
  const scope = `${user?.id ?? "anonymous"}:${user?.role ?? "none"}`

  // Each account scope owns its request generation; late writes cannot cancel a new account read.
  const usersRequests = useMemo(() => ({ scope, generation: 0 }), [scope])
  const [users, setUsers] = useScopedState<User[]>(scope, [])
  const [devices, setDevices] = useScopedState<Device[]>(scope, [])
  const [activityLogs, setActivityLogs] = useScopedState<ActivityLog[]>(scope, [])
  const [activityLoading, setActivityLoading] = useScopedState(scope, user?.role === "Admin")
  const [activityError, setActivityError] = useScopedState<string | null>(scope, null)
  const [usersReady, setUsersReady] = useScopedState(scope, false)
  const [usersLoading, setUsersLoading] = useScopedState(scope, Boolean(user?.role === "Admin"))
  const [usersError, setUsersError] = useScopedState<string | null>(scope, null)
  const [usersReload, setUsersReload] = useScopedState(scope, 0)
  const [devicesReady, setDevicesReady] = useScopedState(scope, false)
  const [devicesLoading, setDevicesLoading] = useScopedState(scope, Boolean(user))
  const [devicesError, setDevicesError] = useScopedState<string | null>(scope, null)
  const [activityReady, setActivityReady] = useScopedState(scope, false)
  const [config, setConfig] = useScopedState<SystemConfig>(scope, { cameraIds: "CAM-001, CAM-002", confidenceThreshold: 80, dataRetentionEnabled: true })
  const acceptUserWrite = useCallback(() => {
    ++usersRequests.generation
    setUsersLoading(false)
    setUsersError(null)
    if (!usersReady) setUsersReload(value => value + 1)
  }, [usersRequests, usersReady, setUsersLoading, setUsersError, setUsersReload])
```
```tsx
  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    const loadData = async () => {
      await Promise.resolve()
      if (controller.signal.aborted) return
      setActivityLoading(user.role === "Admin")
      setActivityError(null)
      const usersGeneration = ++usersRequests.generation
      setUsersLoading(user.role === "Admin")
      setDevicesLoading(true)
      setUsersError(null)
      setDevicesError(null)
      await Promise.allSettled([
        (async () => {
          try {
            const result = user.role === "Admin" ? await api.users.list() : { items: [] }
            if (controller.signal.aborted || usersGeneration !== usersRequests.generation) return
            setUsers(result.items.map(mapApiUser))
            setUsersReady(true)
          } catch {
            if (!controller.signal.aborted && usersGeneration === usersRequests.generation) setUsersError("Users could not be loaded. Please reload to retry.")
          } finally {
            if (!controller.signal.aborted && usersGeneration === usersRequests.generation) setUsersLoading(false)
          }
        })(),
```
```tsx
  // Reconcile after a reconnect, tab restore or network recovery. The debounce
  // collapses focus + visibilitychange into one authoritative read.
  const adminLoadingRef = useRef(false)
  adminLoadingRef.current = usersLoading || devicesLoading || activityLoading
  const reconcileTimer = useRef<number | null>(null)
  useEffect(() => {
    const reconcile = () => {
      if (!user || document.hidden || adminLoadingRef.current) return
      if (reconcileTimer.current) window.clearTimeout(reconcileTimer.current)
      reconcileTimer.current = window.setTimeout(() => {
        reconcileTimer.current = null
        if (document.hidden) return
        setUsersReload(value => value + 1)
        void reloadConfig()
      }, 250)
    }
    const onVisibility = () => { if (!document.hidden) reconcile() }
    window.addEventListener("focus", reconcile)
    window.addEventListener("online", reconcile)
    window.addEventListener(LIVE_RESUMED_EVENT, reconcile)
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      window.removeEventListener("focus", reconcile)
      window.removeEventListener("online", reconcile)
      window.removeEventListener(LIVE_RESUMED_EVENT, reconcile)
      document.removeEventListener("visibilitychange", onVisibility)
      if (reconcileTimer.current) window.clearTimeout(reconcileTimer.current)
    }
  }, [reloadConfig, setUsersReload, user])
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 91–104 (`useScopedState`):** Ties state to `scope = "${user?.id ?? 'anonymous'}:${user?.role ?? 'none'}"`. If an account logs out or swaps, all previous user list state is discarded immediately and late responses from the previous account are ignored.
  * **Lines 173–184:** Calls `await api.users.list()`, checks `usersGeneration === usersRequests.generation` (so a read that started before a `create`/`update`/`reset` write cannot overwrite the newer mutation), maps each item with `mapApiUser` (converting `null` `last_active` to `"Never"`), and sets `usersReady = true`.
  * **Lines 228–251:** Debounces (`250ms`) automatic background refresh (`setUsersReload(v => v + 1)`) whenever the browser tab regains focus, reconnects to the network (`online`), or receives a WebSocket `LIVE_RESUMED_EVENT`.

---

### Phase C & D: Backend Routing, Admin Authorization & Controller Query

#### Step C1: `GET /api/v1/users` Controller (`list_users`) & ORM Serialization
* **Step Title & Trigger:** FastAPI handles `GET /api/v1/users` in `backend/app/api/v1/users.py`, verifies `AdminUser`, queries `user_account` ordered by `created_at`, and serializes `UserListResponse`.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/users.py` (Lines 74–87) and `backend/app/schemas/user.py` (Lines 54–86)
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 74–87):**
```python
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
```
* **Complete Uncut Code Block (`backend/app/schemas/user.py`, Lines 54–86):**
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`users.py` Lines 77–81:** Runs `select(UserAccount).options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile)).order_by(UserAccount.created_at)`. Using `selectinload` avoids the N+1 query problem when reading `account.role.name` and `account.operator_profile.requires_pin_change`.
  * **`schemas/user.py` Lines 69–81 (`from_db_model`):** Flattens the relational ORM graph into a single JSON object per user, extracting `role=account.role.name` and `requires_pin_change=account.operator_profile.requires_pin_change if account.operator_profile else False`. Notice that `password_hash`, `pin_hash`, and `token_version` are **never** exposed in `UserResponse`.

---

### Phase E & F: UI Rendering — Stats Cards, Client-Side Filtering, Sorting & Table Columns

#### Step F1: `UserManagement.tsx` Filtering (`filteredUsers`), KPI Cards, and `AppDataTable` Columns
* **Step Title & Trigger:** `UserManagement` receives `users` from `useAdmin()`, computes `filteredUsers` via `useMemo`, renders the 3 `AppStatsCard` KPI widgets, renders `AppTableFilters`, and passes `filteredUsers` and `columns` to `AppDataTable`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 31–66 & 132–314)
* **Complete Uncut Code Block:**
```tsx
const PAGE_SIZE = 10

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
```
```tsx
  const columns: ColumnDef<User>[] = [
    {
      header: "User",
      sortable: true,
      sortKey: "fullName",
      cell: (user) => (
        <div className="flex items-center gap-3">
          <Avatar className="w-9 h-9">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">
              {user.fullName.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div>
            <div className="font-medium">{user.fullName}</div>
            <div className="text-xs text-muted-foreground">@{user.username}</div>
          </div>
        </div>
      ),
    },
    {
      header: "Role",
      sortable: true,
      sortKey: "role",
      cell: (user) => (
        <Badge variant="outline" className={`gap-1 ${user.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : ""}`}>
          {user.role === "Admin" ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
          {user.role}
        </Badge>
      ),
    },
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
    {
      header: "Last Active",
      className: "text-sm text-muted-foreground",
      sortable: true,
      sortKey: "lastActive",
      cell: (user) => user.lastActive === "Never" ? "Never" : new Date(user.lastActive).toLocaleDateString(undefined, inManila()),
    },
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
          <AppActionButton 
            disabled={saving}
            tooltip="Reset Password" 
            icon={KeyRound} 
            onClick={() => setResetConfirmUser({ id: user.id, fullName: user.fullName })} 
            className="hover:text-amber-600" 
          />
          {user.role === "Operator" && (
            <AppActionButton 
            disabled={saving}
              tooltip="Reset Kiosk PIN" 
              icon={Key} 
              onClick={() => setResetConfirmPin({ id: user.id, fullName: user.fullName })} 
              className="hover:text-indigo-600" 
            />
          )}
        </div>
      ),
    },
  ]

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

      {(usersLoading || usersError) && (
        <p role={usersError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {usersError || (usersReady ? "Refreshing users…" : "Loading users…")}
        </p>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Total Users"
          value={users.length}
          icon={Users}
          delay={50}
          description="System accounts"
        />
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
        <AppStatsCard
          loading={initialLoading}
          title="Admins"
          value={users.filter(u => u.role === "Admin").length}
          icon={ShieldAlert}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={150}
          description="Privileged accounts"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search users..."
        hasActiveFilters={search !== "" || roleFilter !== "all" || statusFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setRoleFilter("all")
          setStatusFilter("all")
        }}
      >
        <Select value={roleFilter} onValueChange={(v) => { setRoleFilter(v) }}>
          <SelectTrigger className="w-full sm:w-40 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Roles" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Roles</SelectItem>
            <SelectItem value="Admin">Admin</SelectItem>
            <SelectItem value="Operator">Operator</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v) }}>
          <SelectTrigger className="w-full sm:w-40 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="Active">Active</SelectItem>
            <SelectItem value="Inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </AppTableFilters>

      <AppDataTable
        loading={initialLoading}
        data={filteredUsers}
        columns={columns}
        rowKey={(user) => user.id}
        pagination={{ pageSize: PAGE_SIZE }}
        className="rounded-2xl border-none shadow-none"
        emptyState={{
          icon: Users,
          title: usersError && !usersReady ? "Data unavailable" : "No users found",
          description: usersError && !usersReady ? "Reload to try again." : "Try adjusting your search query"
        }}
      />
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 55–65 (`filteredUsers` Memoized Filter):** Filters `users` in memory by `roleFilter` (`"all"` | `"Admin"` | `"Operator"`), `statusFilter` (`"all"` | `"Active"` | `"Inactive"`), and case-insensitive substring match against `u.fullName` or `u.username`.
  * **Lines 137–149 (Column 1 — `"User"`):** Displays initials inside `<AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">`, `user.fullName`, and `@{user.username}`.
  * **Lines 155–160 (Column 2 — `"Role"`):** Displays `ShieldAlert` with golden primary badge classes (`bg-primary/10 text-primary border-primary/20`) for `"Admin"`, or `ShieldCheck` with default outline badge for `"Operator"`.
  * **Lines 166–170 (Column 3 — `"Status"`):** Displays green badge (`bg-emerald-100 text-emerald-700 hover:bg-emerald-100`) for `"Active"` and muted gray badge (`bg-muted text-muted-foreground`) for `"Inactive"`.
  * **Line 177 (Column 4 — `"Last Active"`):** Formats timestamps in `Asia/Manila` via `inManila()`, or displays `"Never"`.
  * **Lines 183–209 (Column 5 — `"Actions"`):** Renders up to 3 `AppActionButton` icon triggers: `"Edit User"` (`Pencil`), `"Reset Password"` (`KeyRound`), and—only when `user.role === "Operator"` (Line 199)—`"Reset Kiosk PIN"` (`Key`).

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Route & Component** | `/admin/users` → `frontend/src/pages/admin/UserManagement.tsx` |
| **Backend Endpoint** | `GET /api/v1/users` → `list_users()` in `backend/app/api/v1/users.py` (Lines 74–87) |
| **Table Page Size** | `const PAGE_SIZE = 10` (`UserManagement.tsx` Line 31) |
| **Sortable Columns** | `fullName` (`User`), `role` (`Role`), `status` (`Status`), `lastActive` (`Last Active`) |
| **KPI Stats Cards** | `Total Users` (`users.length`), `Active Users` (`users.filter(u => u.status === "Active").length`), `Admins` (`users.filter(u => u.role === "Admin").length`) |
| **Timezone Rule** | `new Date(user.lastActive).toLocaleDateString(undefined, inManila())` (`UserManagement.tsx` Line 177) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Add a 4th Stats Card Showing `"Operators"` Count on the User Management Page
* **Examiner Prompt:** *"Add a 4th KPI card to the User Management stats grid titled `'Operators'` that counts how many users have the `'Operator'` role."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 234–263)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 234–263):**
```tsx
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Total Users"
          value={users.length}
          icon={Users}
          delay={50}
          description="System accounts"
        />
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
        <AppStatsCard
          loading={initialLoading}
          title="Admins"
          value={users.filter(u => u.role === "Admin").length}
          icon={ShieldAlert}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={150}
          description="Privileged accounts"
        />
      </div>
```
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 234–273):**
```tsx
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Total Users"
          value={users.length}
          icon={Users}
          delay={50}
          description="System accounts"
        />
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
        <AppStatsCard
          loading={initialLoading}
          title="Admins"
          value={users.filter(u => u.role === "Admin").length}
          icon={ShieldAlert}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={150}
          description="Privileged accounts"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Operators"
          value={users.filter(u => u.role === "Operator").length}
          icon={ShieldCheck}
          iconColor="text-amber-600"
          iconBgColor="bg-amber-500/10"
          delay={200}
          description="Scanning station staff"
        />
      </div>
```

---

#### Drill Scenario 2: Display a `"Pending Setup"` Badge in the User Table When `requiresPasswordChange` or `requiresPinChange` Is True
* **Examiner Prompt:** *"In the User Management table's `'Status'` column, display an additional amber `'Pending Setup'` badge next to `'Active'` whenever `user.requiresPasswordChange` or `user.requiresPinChange` is true."*
* **File to Edit:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 162–171)
* **Before (`frontend/src/pages/admin/UserManagement.tsx`, Lines 162–171):**
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
* **After (`frontend/src/pages/admin/UserManagement.tsx`, Lines 162–178):**
```tsx
    {
      header: "Status",
      sortable: true,
      sortKey: "status",
      cell: (user) => (
        <div className="flex items-center gap-1.5">
          <Badge variant="secondary" className={user.status === "Active" ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-100" : "bg-muted text-muted-foreground"}>
            {user.status}
          </Badge>
          {(user.requiresPasswordChange || user.requiresPinChange) && (
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-[11px]">
              Pending Setup
            </Badge>
          )}
        </div>
      ),
    },
```

---

#### Drill Scenario 3: Change Backend User List Ordering from `created_at` Ascending to Alphabetical by `full_name`
* **Examiner Prompt:** *"Change `GET /api/v1/users` so that users are returned in alphabetical order by `full_name` instead of `created_at`."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 77–81)
* **Before (`backend/app/api/v1/users.py`, Lines 77–81):**
```python
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .order_by(UserAccount.created_at)
    )
```
* **After (`backend/app/api/v1/users.py`, Lines 77–81):**
```python
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .order_by(UserAccount.full_name)
    )
```
