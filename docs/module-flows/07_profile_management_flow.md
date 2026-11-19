# `07_profile_management_flow.md` — Module 7: Profile Management (Stats, Avatar Upload, Theme, Self-Service Password & PIN Change) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 7 (Profile Management) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Route & Auth Guard:** Maps `/profile` inside `<ProtectedRoute><AppLayout /></ProtectedRoute>` so any authenticated Admin or Operator can access their profile. |
| `frontend/src/components/AppSidebarFooter.tsx` | **Profile Navigation Entry:** Renders the `<NavLink to="/profile">` (`"My Profile"`) inside the sidebar user popover and displays the user's live `user.avatar` and `user.fullName`. |
| `frontend/src/pages/Profile.tsx` | **Profile Management View:** Fetches `api.users.summary()`, renders 3 role-aware KPI cards, renders the Personal Information card with 2MB base64 avatar upload (`FileReader.readAsDataURL`) & removal, Preferences card (Dark/Light mode `<Switch>` + `D` shortcut badge), Security & Authentication card (`Update Password` dialog & 3-step `InputOTP` `Change Kiosk PIN` dialog for Operators), and the sticky `Recent Activity` feed. |
| `frontend/src/lib/activityActions.ts` | **First-Person Activity Formatter (`activityProfileLabel`):** Maps raw backend audit actions (`login`, `scan_created`, `profile_updated`, `password_changed`, etc.) to first-person phrases for the Profile page's recent activity feed. |
| `frontend/src/context/AdminContext.tsx` | **Self-Service Avatar Controller (`updateOwnProfile`):** Calls `api.users.updateProfile({ avatar_url: data.avatar })`, updates `users` state, and calls `updateAuthUser({ avatar: saved.avatar }, user)` in `AuthContext`. |
| `frontend/src/context/AuthContext.tsx` | **Self-Service Credential Controllers (`changePassword`, `changePin`, `updateAuthUser`):** Calls `api.auth.changePassword` and `api.auth.changePin`, replaces the stored JWT in `localStorage` with the newly issued token (which carries the incremented `token_version`), and updates `bananavision_user`. |
| `frontend/src/components/theme-provider.tsx` | **Theme Context & Keyboard Shortcut (`useTheme`):** Persists `"light"` / `"dark"` in `localStorage` under `"bananavision-theme"`, toggles `.light` / `.dark` on `document.documentElement`, and listens for the global `D` keydown shortcut. |
| `backend/app/api/v1/users.py` | **Profile Summary & Avatar Endpoints:** Defines `GET /api/v1/users/me/summary` (`own_profile_summary`) and `PATCH /api/v1/users/me/profile` (`update_own_profile`, `PROFILE-01`), recording `AuditAction.PROFILE_UPDATED` without logging the base64 image string. |
| `backend/app/api/v1/auth.py` | **Self-Service Credential Endpoints:** Defines `POST /api/v1/auth/change-password` and `POST /api/v1/auth/change-pin`, rate-limited per user ID via `credential_limiter` (`"password:<user.id>"` and `"pin:<user.id>"`). |
| `backend/app/services/auth_service.py` | **Credential Verification & Session Rotation (`change_password` & `change_pin`):** Locks `UserAccount` with `SELECT ... FOR UPDATE` (`lock_current_account`), verifies `current_password` / `current_pin` with bcrypt, hashes the new secret, increments `user.token_version += 1` (`AUTH-02` revoking all other devices/tabs), and issues a new JWT for the current session. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A: Initial Page Load, Summary Metrics Query & UI Rendering

#### Step A1: Fetching `GET /api/v1/users/me/summary` on Mount (`Profile.tsx` → `users.py`)
* **Step Title & Trigger:** Authenticated user navigates to `/profile`. `Profile.tsx` mounts and runs its `useEffect` calling `api.users.summary(controller.signal)`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/Profile.tsx` (Lines 88–122) and `backend/app/api/v1/users.py` (Lines 146–180)
* **Complete Uncut Code Block (`frontend/src/pages/Profile.tsx`, Lines 88–122):**
```tsx
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof api.users.summary>> | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    setSummary(null)
    setSummaryError(false)
    if (user) {
      api.users.summary(controller.signal).then(data => {
        if (!controller.signal.aborted) setSummary(data)
      }).catch(() => {
        if (!controller.signal.aborted) setSummaryError(true)
      })
    }
    return () => controller.abort()
  }, [user])

  const recentActivityFeed = useMemo(() => {
    const userActivity = summary?.activity ?? []
    if (userActivity.length > 0) {
      return userActivity.slice(0, 8).map((activity) => ({
        id: activity.id,
        details: activityProfileLabel(activity.action, activity.details),
        timestamp: activity.timestamp,
      }))
    }
    return []
  }, [summary])

  const stats = {
    totalScans: summary?.total_scans ?? "—",
    totalUsers: summary?.total_users ?? "—",
    last7Days: summary?.last_7_days ?? "—",
    recentActions7d: summary?.recent_actions_7d ?? "—",
  }
```
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 146–180):**
```python
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Role-Scoped SQL Aggregation (`users.py` Lines 150–160):**
    * For an **Admin** (`is_admin == True`), `total_scans`, `avg_confidence`, and `last_7_days` aggregate across **all** scans in `scan`, and `total_users` counts all rows in `user_account`.
    * For an **Operator** (`is_admin == False`), the query joins `OperatorProfile` (`Scan.operator_id == OperatorProfile.id`) and filters `.where(OperatorProfile.account_id == user.id)`, so operators only see their own scan totals, and `total_users` returns `None`.
  * **Activity Feed Query (`users.py` Lines 161–170):** Counts `recent_actions_7d` and fetches the 8 most recent `ActivityLog` rows for `user.id`.
  * **First-Person Label Mapping (`Profile.tsx` Line 109):** Calls `activityProfileLabel(activity.action, activity.details)` from `frontend/src/lib/activityActions.ts` (e.g., `"login"` → `"Signed in to the web dashboard"`, `"profile_updated"` → `"Updated profile details"`).

---

### Phase B & C: Self-Service Avatar Upload & Removal (`PROFILE-01`)

#### Step B1: Client-Side 2MB Validation, Base64 Encoding & `PATCH /api/v1/users/me/profile`
* **Step Title & Trigger:** User clicks their circular avatar in `Profile.tsx` (`fileInputRef.current?.click()`), selects an image file (`handleAvatarUpload`), or clicks `"Remove Photo"` (`handleRemoveAvatar`).
* **Exact File Path & Line Numbers:** `frontend/src/pages/Profile.tsx` (Lines 43–82 & 274–325), `frontend/src/context/AdminContext.tsx` (Lines 334–343), and `backend/app/api/v1/users.py` (Lines 142–144 & 182–211)
* **Complete Uncut Code Block (`frontend/src/pages/Profile.tsx`, Lines 43–82 & 274–325):**
```tsx
  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file || !user || savingAvatar) return

    if (file.size > 2 * 1024 * 1024) {
      toast.error("Image size must be less than 2MB")
      return
    }

    setSavingAvatar(true)
    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("Could not read image"))
        reader.onerror = () => reject(new Error("Could not read image"))
        reader.readAsDataURL(file)
      })
      await updateOwnProfile({ avatar: base64 })
      toast.success("Avatar updated successfully")
    } catch (error) {
      toast.error("Could not update avatar", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSavingAvatar(false)
    }
  }

  const handleRemoveAvatar = async () => {
    if (!user || savingAvatar) return
    setSavingAvatar(true)
    try {
      await updateOwnProfile({ avatar: "" })
      toast.success("Avatar removed successfully")
    } catch (error) {
      toast.error("Could not remove avatar", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSavingAvatar(false)
    }
  }
```
```tsx
              <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
                <div 
                  className="relative group cursor-pointer inline-block rounded-full" 
                  aria-busy={savingAvatar}
                  onClick={() => !savingAvatar && fileInputRef.current?.click()}
                  title="Upload new avatar"
                >
                  <Avatar className="w-20 h-20 sm:w-24 sm:h-24 border-[3px] border-background ring-1 ring-border shadow-sm transition-all group-hover:ring-primary/50 group-hover:shadow-md">
                    <AvatarImage src={user.avatar || undefined} className="object-cover" />
                    <AvatarFallback className="text-2xl sm:text-3xl bg-primary/10 text-primary font-bold">
                      {user.fullName.split(' ').map(n => n[0]).join('').toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Camera className="w-6 h-6 text-white" />
                  </div>
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept="image/*"
                    onChange={handleAvatarUpload}
                    disabled={savingAvatar}
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-xl sm:text-2xl font-bold tracking-tight">{user.fullName}</h3>
                      <p className="text-sm sm:text-base text-muted-foreground font-medium">@{user.username}</p>
                    </div>
                    {user.avatar && (
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        onClick={handleRemoveAvatar} 
                        disabled={savingAvatar}
                        className="text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/50"
                      >
                        Remove Photo
                      </Button>
                    )}
                  </div>
```
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 334–343):**
```tsx
  // ── PROFILE-01: Self-service avatar update ──────────────────────────────

  const updateOwnProfile = useCallback(async (data: { avatar?: string }) => {
    const saved = mapApiUser(await api.users.updateProfile({ avatar_url: data.avatar }))
    acceptUserWrite()
    setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)))
    if (user?.id === saved.id) {
      updateAuthUser({ avatar: saved.avatar }, user)
    }
  }, [user, updateAuthUser, setUsers, acceptUserWrite])
```
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 142–144 & 182–211):**
```python
class SelfProfileUpdate(BaseModel):
    avatar_url: str | None = None
```
```python
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`Profile.tsx` Lines 48–51:** Validates `file.size > 2 * 1024 * 1024` (2 MB limit) on the client before reading the file.
  * **`Profile.tsx` Lines 55–61:** Converts the image file into a Data URL (`data:image/...;base64,...`) via `FileReader.readAsDataURL(file)` and calls `updateOwnProfile({ avatar: base64 })`.
  * **`users.py` Line 184:** Uses `user: CurrentUser` (not `AdminUser`), allowing both Operators and Admins to update their own `avatar_url` column (`Text` column in `user_account`).
  * **`users.py` Lines 201–207:** Logs `AuditAction.PROFILE_UPDATED` with `"avatar changed"` instead of dumping the multi-kilobyte base64 Data URL into `activity_log`.
  * **`AdminContext.tsx` Line 56 & Lines 340–342:** When removing a photo (`avatar: ""`), `mapApiUser` converts `"" || undefined` to `undefined`, and `updateAuthUser({ avatar: saved.avatar }, user)` updates `localStorage` and both `<Avatar>` components in `Profile.tsx` and `AppSidebarFooter.tsx`.

---

### Phase D & E: Self-Service Password Change & 3-Step Operator Kiosk PIN Change

#### Step D1: Frontend Password Dialog & 3-Step `InputOTP` PIN Dialog (`Profile.tsx` & `AuthContext.tsx`)
* **Step Title & Trigger:** User clicks `"Update Password"` (or `"Change Kiosk PIN"` for Operators) in `Profile.tsx`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/Profile.tsx` (Lines 123–209 & 370–531) and `frontend/src/context/AuthContext.tsx` (Lines 135–150 & 171–186)
* **Complete Uncut Code Block (`frontend/src/pages/Profile.tsx`, Lines 123–209):**
```tsx
  const handlePasswordChange = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (credentialFlight.current) return
    if (passwordData.new !== passwordData.confirm) {
      toast.error("Passwords don't match")
      return
    }
    if (passwordData.new.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }
    if (!passwordData.current) {
      toast.error("Please enter your current password")
      return
    }
    
    if (user) {
      credentialFlight.current = true; setSavingCredential(true)
      try {
        const success = await changePassword(passwordData.current, passwordData.new)
        if (success) {
          toast.success("Password changed successfully")
          setPasswordData({ current: "", new: "", confirm: "" })
          setIsEditingPassword(false)
        } else {
          toast.error("Failed to change password. Please check your current password.")
        }
      } catch {
        toast.error("An error occurred while changing password.")
      } finally { credentialFlight.current = false; setSavingCredential(false) }
    }
  }

  const handlePinOtpChange = async (val: string) => {
    if (credentialFlight.current) return
    if (pinStep === "current") {
      setPinData(prev => ({ ...prev, current: val }))
      if (val.length === 4) {
        if (!user) return
        // Current PIN will be verified server-side when we submit the change
        setPinStep("new")
      }
    } else if (pinStep === "new") {
      setPinData(prev => ({ ...prev, new: val }))
      if (val.length === 4) {
        setPinStep("confirm")
      }
    } else {
      setPinData(prev => ({ ...prev, confirm: val }))
      if (val.length === 4) {
        if (pinData.new !== val) {
          toast.error("PINs don't match. Try again.")
          setPinData(prev => ({ ...prev, new: "", confirm: "" }))
          setPinStep("new")
          return
        }
        if (user) {
          credentialFlight.current = true; setSavingCredential(true)
          try {
            const success = await changePin(pinData.current, val)
            if (success) {
              toast.success("Kiosk PIN changed successfully")
              setPinData({ current: "", new: "", confirm: "" })
              setPinStep("current")
              setIsEditingPin(false)
            } else {
              toast.error("Failed to change Kiosk PIN. Please check your current PIN.")
              setPinData({ current: "", new: "", confirm: "" })
              setPinStep("current")
            }
          } catch {
            toast.error("Current PIN is incorrect")
            setPinData({ current: "", new: "", confirm: "" })
            setPinStep("current")
          } finally { credentialFlight.current = false; setSavingCredential(false) }
        }
      }
    }
  }

  const resetPinDialog = () => {
    if (credentialFlight.current) return
    setPinData({ current: "", new: "", confirm: "" })
    setPinStep("current")
    setIsEditingPin(false)
  }
```
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 135–150 & 171–186):**
```tsx
  // ── Self-service Password Change (requires current password) ────────────

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    try {
      const res = await api.auth.changePassword(currentPassword, newPassword)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])
```
```tsx
  // ── Self-service PIN Change (requires current PIN) ──────────────────────

  const changePin = useCallback(async (currentPin: string, newPin: string) => {
    try {
      const res = await api.auth.changePin(currentPin, newPin)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Password Change (`handlePasswordChange`):** Checks `passwordData.new !== passwordData.confirm`, `passwordData.new.length < 6`, and `!passwordData.current`, then calls `changePassword(passwordData.current, passwordData.new)`.
  * **3-Step PIN Wizard (`handlePinOtpChange`):** Uses a 4-slot `<InputOTP maxLength={4}>` wizard with 3 visual step circles (`1: current` → `2: new` → `3: confirm`). Auto-advances when 4 digits are typed (`val.length === 4`). On step 3 (`confirm`), verifies `pinData.new === val` and calls `changePin(pinData.current, val)`.
  * **Seamless Token Rotation (`AuthContext.tsx` Lines 141 & 177):** Because changing a password or PIN increments `user.token_version += 1` on the backend (revoking all old tokens), the backend returns a brand-new JWT in `res.token.access_token`. `AuthContext` immediately calls `setToken(res.token.access_token)` so the current browser tab stays logged in while any other devices/tabs using the old token are logged out.

---

#### Step D2: Backend Credential Rate Limiter, Row Locking & Verification (`auth.py` & `auth_service.py`)
* **Step Title & Trigger:** FastAPI handles `POST /api/v1/auth/change-password` and `POST /api/v1/auth/change-pin`.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/auth.py` (Lines 323–394 & 415–437) and `backend/app/services/auth_service.py` (Lines 88–100, 192–211, 242–266)
* **Complete Uncut Code Block (`backend/app/api/v1/auth.py`, Lines 323–394 & 415–437):**
```python
def _refuse_change_while_locked(key: str, noun: str, what: str, user, ip: str | None) -> None:
    """A locked password/PIN change is refused before the current secret is checked."""
    locked, remaining = credential_limiter.is_locked(key)
    if not locked:
        return
    error = HTTPException(
        status_code=429,
        detail=f"Too many failed {noun} attempts. Try again in {remaining} seconds.",
        headers={"Retry-After": str(max(remaining, 1))},
    )
    suppressed = _blocked_suppressed("credential", key)
    if suppressed is not None:
        audit.attach(error, AuditAction.LOGIN_BLOCKED, _with_suppressed(
            f"{what} refused for {_user(user)}: locked for another {remaining} s", suppressed,
        ), actor=user, ip=ip)
    raise error


def _failed_change(error: HTTPException, key: str, noun: str, scope: str, action, user,
                   ip: str | None) -> HTTPException:
    """Count a wrong current secret; the 5th within the window locks further changes.

    ``lock_current_account`` holds the account row lock, so the events ride on the error and
    are written after the request rolls back.
    """
    is_locked, info = credential_limiter.record_failure(key)
    failure = f"{scope[0].upper()}{scope[1:]} failed for {_user(user)}: current {noun} incorrect"
    if not is_locked:
        return audit.attach(error, action, f"{failure}; {_attempts_left(info)}",
                            actor=user, ip=ip)
    locked = HTTPException(
        status_code=429,
        detail=f"Too many failed {noun} attempts. Try again in {info} seconds.",
        headers={"Retry-After": str(info)},
    )
    audit.attach(locked, action, f"{failure}; {scope} locked", actor=user, ip=ip)
    audit.attach(locked, AuditAction.ACCOUNT_LOCKED, _locked(user, scope, info, "attempts"),
                 actor=user, ip=ip)
    return locked
```
```python
@router.post("/change-password", response_model=LoginResponse)
async def change_password_route(
    body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service password change — requires authentication (JWT) and
    current password verification.
    """
    ip = get_client_ip(request)
    key = f"password:{user.id}"
    _refuse_change_while_locked(key, "password", "Password change", user, ip)
    try:
        user = await change_password(db, user, body.current_password, body.new_password)
    except CurrentCredentialIncorrect as error:
        raise _failed_change(error, key, "password", "password change",
                             AuditAction.PASSWORD_CHANGE_FAILED, user, ip) from None
    credential_limiter.record_success(key)
    token = create_user_token(user)
    await audit.record(db, AuditAction.PASSWORD_CHANGED,
                       f"User {_name(user)} changed password; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)
```
```python
@router.post("/change-pin", response_model=LoginResponse)
async def change_pin_route(
    body: ChangePinRequest, user: CurrentUser, db: DbSession, request: Request
):
    """
    Self-service PIN change — requires authentication (JWT) and
    current PIN verification.
    """
    ip = get_client_ip(request)
    key = f"pin:{user.id}"
    _refuse_change_while_locked(key, "PIN", "PIN change", user, ip)
    try:
        user = await change_pin(db, user, body.current_pin, body.new_pin)
    except CurrentCredentialIncorrect as error:
        raise _failed_change(error, key, "PIN", "PIN change",
                             AuditAction.PIN_CHANGE_FAILED, user, ip) from None
    credential_limiter.record_success(key)
    token = create_user_token(user)
    await audit.record(db, AuditAction.PIN_CHANGED,
                       f"User {_name(user)} changed PIN; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)
```
* **Complete Uncut Code Block (`backend/app/services/auth_service.py`, Lines 88–100, 192–211, 242–266):**
```python
async def lock_current_account(db: AsyncSession, user: UserAccount) -> UserAccount:
    """Refresh under lock so concurrent credential changes cannot reuse a version."""
    version = user.token_version
    account = (await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not account or account.status != ActiveStatusEnum.ACTIVE or account.token_version != version:
        raise CredentialsException("Session has been revoked; sign in again")
    return account
```
```python
async def change_password(
    db: AsyncSession, user: UserAccount, current_password: str, new_password: str
) -> UserAccount:
    """
    Self-service password change — requires the authenticated user object
    and their current password for verification.

    Raises CurrentCredentialIncorrect (401) if current_password does not match.
    """
    user = await lock_current_account(db, user)
    if not verify_password(current_password, user.password_hash):
        raise CurrentCredentialIncorrect("Current password is incorrect")

    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user
```
```python
async def change_pin(
    db: AsyncSession, user: UserAccount, current_pin: str, new_pin: str
) -> UserAccount:
    """
    Self-service PIN change — requires the authenticated user object
    and their current PIN for verification.

    Raises CurrentCredentialIncorrect (401) if current_pin does not match.
    """
    user = await lock_current_account(db, user)
    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")
    if not user.operator_profile:
        raise NotFoundException("Operator Profile")

    if not user.operator_profile.pin_hash or not verify_pin(current_pin, user.operator_profile.pin_hash):
        raise CurrentCredentialIncorrect("Current PIN is incorrect")

    user.operator_profile.pin_hash = hash_pin(new_pin)
    user.operator_profile.requires_pin_change = False
    user.operator_profile.pin_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Per-Account Rate Limit (`credential_limiter`):** Uses keys `"password:<user.id>"` and `"pin:<user.id>"` (`MAX_ATTEMPTS = 5`, `LOCKOUT_SECONDS = 300`).
  * **Why `_failed_change` Uses `audit.attach()` Instead of `audit.emit()`:** Because `change_password` and `change_pin` call `lock_current_account(db, user)` (`SELECT ... FOR UPDATE`), the request transaction holds an exclusive row lock on `user_account`. Calling `audit.emit()` (which opens a second DB session and queries `user_account`) while that lock is held could wait on the lock. Instead, `audit.attach()` attaches the `PASSWORD_CHANGE_FAILED` / `PIN_CHANGE_FAILED` event to the raised `HTTPException`, and `_handle_http_exception` in `audit.py` writes it **after** FastAPI rolls back the request transaction and releases the row lock.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Frontend Page & Route** | `/profile` → `frontend/src/pages/Profile.tsx` |
| **Profile Summary Endpoint** | `GET /api/v1/users/me/summary` → `own_profile_summary()` (`backend/app/api/v1/users.py` Lines 146–180) |
| **Avatar Update Endpoint (`PROFILE-01`)** | `PATCH /api/v1/users/me/profile` → `update_own_profile()` (`backend/app/api/v1/users.py` Lines 182–211) |
| **Avatar Size Limit** | `2 * 1024 * 1024` bytes (2 MB) checked in `Profile.tsx` Line 48 |
| **Change Password Endpoint** | `POST /api/v1/auth/change-password` → `change_password_route()` (`backend/app/api/v1/auth.py` Lines 372–394) |
| **Change PIN Endpoint** | `POST /api/v1/auth/change-pin` → `change_pin_route()` (`backend/app/api/v1/auth.py` Lines 415–437) |
| **Credential Limiter Keys** | `"password:<user.id>"` and `"pin:<user.id>"` in `credential_limiter` (`backend/app/core/rate_limiter.py`) |
| **Theme Shortcut** | Pressing `D` anywhere outside an input field toggles `"light"` ↔ `"dark"` (`frontend/src/components/theme-provider.tsx` Lines 141–179) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Allow Users to Edit Their Own `Full Name` from the My Profile Page
* **Examiner Prompt:** *"Currently, `Full Name` on `Profile.tsx` is a disabled input, and `PATCH /api/v1/users/me/profile` only accepts `avatar_url`. Extend `SelfProfileUpdate`, `update_own_profile`, `AdminContext.updateOwnProfile`, and `Profile.tsx` so any user can edit and save their own `Full Name`."*
* **Files to Edit:**
  1. `backend/app/api/v1/users.py` (Lines 142–144 & 182–211)
  2. `frontend/src/lib/api.ts` (Line 291)
  3. `frontend/src/context/AdminContext.tsx` (Lines 336–343)
* **Before (`backend/app/api/v1/users.py`, Lines 142–144 & 199–210):**
```python
class SelfProfileUpdate(BaseModel):
    avatar_url: str | None = None
```
```python
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
```
* **After (`backend/app/api/v1/users.py`, Lines 142–145 & 199–216):**
```python
class SelfProfileUpdate(BaseModel):
    avatar_url: str | None = None
    full_name: str | None = None
```
```python
    changes: list[str] = []
    if body.full_name is not None and body.full_name.strip() and body.full_name.strip() != account.full_name:
        old_name = account.full_name
        account.full_name = body.full_name.strip()
        changes.append(f"full_name {audit.quoted(old_name)} → {audit.quoted(account.full_name)}")
    if body.avatar_url is not None and body.avatar_url != account.avatar_url:
        account.avatar_url = body.avatar_url
        changes.append("avatar changed")

    if changes:
        await audit.record(
            db, audit.AuditAction.PROFILE_UPDATED,
            f"Updated profile of user {audit.quoted(account.username)} ({account.id}): "
            + "; ".join(changes),
            actor=account, ip=get_client_ip(request),
        )

    await db.flush()
    return UserResponse.from_db_model(account)
```

---

#### Drill Scenario 2: Prevent Users from Reusing Their Current Password When Changing Passwords
* **Examiner Prompt:** *"In `change_password()` (`backend/app/services/auth_service.py`) and `handlePasswordChange()` (`frontend/src/pages/Profile.tsx`), reject the password change if `new_password` is identical to `current_password`."*
* **Files to Edit:**
  1. `frontend/src/pages/Profile.tsx` (Lines 126–137)
  2. `backend/app/services/auth_service.py` (Lines 201–206)
* **Before (`frontend/src/pages/Profile.tsx`, Lines 126–137):**
```tsx
    if (passwordData.new !== passwordData.confirm) {
      toast.error("Passwords don't match")
      return
    }
    if (passwordData.new.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }
```
* **After (`frontend/src/pages/Profile.tsx`, Lines 126–141):**
```tsx
    if (passwordData.new !== passwordData.confirm) {
      toast.error("Passwords don't match")
      return
    }
    if (passwordData.new === passwordData.current) {
      toast.error("New password must be different from your current password")
      return
    }
    if (passwordData.new.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }
```
* **Before (`backend/app/services/auth_service.py`, Lines 201–206):**
```python
    user = await lock_current_account(db, user)
    if not verify_password(current_password, user.password_hash):
        raise CurrentCredentialIncorrect("Current password is incorrect")

    user.password_hash = hash_password(new_password)
```
* **After (`backend/app/services/auth_service.py`, Lines 201–208):**
```python
    user = await lock_current_account(db, user)
    if not verify_password(current_password, user.password_hash):
        raise CurrentCredentialIncorrect("Current password is incorrect")
    if current_password == new_password:
        raise CredentialsException("New password must be different from current password")

    user.password_hash = hash_password(new_password)
```

---

#### Drill Scenario 3: Add a `"Average Confidence"` Card to the Profile Page Stats Grid
* **Examiner Prompt:** *"The backend `GET /api/v1/users/me/summary` already returns `avg_confidence`, Retrieve `summary?.avg_confidence` in `Profile.tsx` and display it as a 4th `AppStatsCard` titled `'Avg Confidence'`."*
* **File to Edit:** `frontend/src/pages/Profile.tsx` (Lines 116–122 & 222–264)
* **Before (`frontend/src/pages/Profile.tsx`, Lines 116–121):**
```tsx
  const stats = {
    totalScans: summary?.total_scans ?? "—",
    totalUsers: summary?.total_users ?? "—",
    last7Days: summary?.last_7_days ?? "—",
    recentActions7d: summary?.recent_actions_7d ?? "—",
  }
```
* **After (`frontend/src/pages/Profile.tsx`, Lines 116–122):**
```tsx
  const stats = {
    totalScans: summary?.total_scans ?? "—",
    avgConfidence: summary?.avg_confidence != null ? `${summary.avg_confidence.toFixed(1)}%` : "—",
    totalUsers: summary?.total_users ?? "—",
    last7Days: summary?.last_7_days ?? "—",
    recentActions7d: summary?.recent_actions_7d ?? "—",
  }
```
*(And in `<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">` on Line 222, add `<AppStatsCard loading={!summary && !summaryError} title="Avg Confidence" value={stats.avgConfidence} icon={TrendingUp} delay={200} description="Mean scan confidence" />`.)*
