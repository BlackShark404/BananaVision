# `06_reset_password_flow.md` — Module 6: Reset Password (& Kiosk PIN Reset) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 6 (Reset Password & Kiosk PIN) |
| :--- | :--- |
| `frontend/src/pages/admin/UserManagement.tsx` | **Reset Triggers, Confirmation `AlertDialog`s & One-Time Handoff Modal:** Renders the `"Reset Password"` (`KeyRound`) button on every row and `"Reset Kiosk PIN"` (`Key`) on Operator rows, opens the confirmation `AlertDialog` (`resetConfirmUser` / `resetConfirmPin`), executes `confirmResetPassword()` / `confirmResetPin()`, and displays the new temporary secret in the `"Temporary credentials"` `<Dialog>` (`handoff`). |
| `frontend/src/context/AdminContext.tsx` | **Admin Reset State Controllers (`resetPassword` & `resetPin`):** Calls `api.users.resetPassword(id)` / `api.users.resetPin(id)`, marks `requiresPasswordChange: true` (`passwordSetupReason: "password_reset"`) or `requiresPinChange: true` (`pinSetupReason: "pin_reset"`) on the user in `users` state, and returns the plain-text temporary credential. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `POST /api/v1/users/${id}/reset-password` and `POST /api/v1/users/${id}/reset-pin` with `Authorization: Bearer <token>`. |
| `backend/app/api/v1/users.py` | **Reset Controllers (`reset_user_password` & `reset_user_pin`):** Locks `UserAccount` with `SELECT ... FOR UPDATE`, generates a cryptographic temporary password/PIN, hashes it with bcrypt, sets `requires_password_change = True` (`password_setup_reason = "password_reset"`) or `requires_pin_change = True` (`pin_setup_reason = "pin_reset"`), increments `user.token_version += 1` (`AUTH-02`), records `AuditAction.PASSWORD_RESET` / `PIN_RESET` (`AUDIT-02`), sets `Cache-Control: no-store`, and returns the temporary credential. |
| `backend/app/schemas/user.py` | **Pydantic Request Schemas:** Defines `UserPasswordReset` (`new_password`, `password_setup_reason = PasswordSetupReasonEnum.PASSWORD_RESET`) and `UserPinReset` (`new_pin`, `pin_setup_reason = PinSetupReasonEnum.PIN_RESET`). |
| `backend/app/core/temporary_credentials.py` | **Cryptographic Generator:** Generates the 24-char URL-safe temporary password (`secrets.token_urlsafe(18)`) and 4-digit temporary PIN (`f"{secrets.randbelow(10000):04d}"`). |
| `backend/app/core/security.py` | **Bcrypt Hasher:** Hashes the temporary password/PIN before database update. |
| `frontend/src/pages/Login.tsx` & `backend/app/api/v1/auth.py` | **Post-Reset First-Login Enforcement:** When the user signs in with the temporary password, `authenticate_user` returns `("requires_password_change", user, "password_reset")`, `Login.tsx` displays `"Welcome back! Because your password was recently reset, please set a new secure password to continue."`, and `POST /api/v1/auth/setup-password` forces a new password distinct from the temporary password. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Action Buttons, Confirmation `AlertDialog` & Client Handler

#### Step A1: `"Reset Password"` & `"Reset Kiosk PIN"` Action Buttons and Confirmation Dialogs (`UserManagement.tsx`)
* **Step Title & Trigger:** Administrator clicks the `"Reset Password"` (`KeyRound`) or `"Reset Kiosk PIN"` (`Key`) icon button in the `"Actions"` column of `UserManagement.tsx`, then confirms in the `AlertDialog`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/UserManagement.tsx` (Lines 43–47, 102–131, 180–210, 365–413)
* **Complete Uncut Code Block:**
```tsx
  const [resetConfirmUser, setResetConfirmUser] = useState<{id: string, fullName: string} | null>(null)
  const [resetConfirmPin, setResetConfirmPin] = useState<{id: string, fullName: string} | null>(null)
  
  const [handoff, setHandoff] = useState<{ username: string; password?: string; pin?: string } | null>(null)
```
```tsx
  const confirmResetPassword = async () => {
    if (!resetConfirmUser || saving) return
    setSaving(true)
    try {
      const password = await resetPassword(resetConfirmUser.id)
      setHandoff({ username: users.find(u => u.id === resetConfirmUser.id)?.username || resetConfirmUser.fullName, password })
      toast.success("Password reset")
      setResetConfirmUser(null)
    } catch (error) {
      toast.error("Could not reset password", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSaving(false)
    }
  }

  const confirmResetPin = async () => {
    if (!resetConfirmPin || saving) return
    setSaving(true)
    try {
      const pin = await resetPin(resetConfirmPin.id)
      setHandoff({ username: users.find(u => u.id === resetConfirmPin.id)?.username || resetConfirmPin.fullName, pin })
      toast.success("PIN reset")
      setResetConfirmPin(null)
    } catch (error) {
      toast.error("Could not reset PIN", { description: error instanceof Error ? error.message : "Please try again." })
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

      <AlertDialog open={!!resetConfirmUser} onOpenChange={(open) => !saving && !open && setResetConfirmUser(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Password</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the password for <span className="font-semibold text-foreground">{resetConfirmUser?.fullName}</span>?
              <br /><br />
              A unique temporary password will be displayed once after reset. The user must replace it on their next login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={saving} className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={event => { event.preventDefault(); void confirmResetPassword() }}>
              {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Resetting…" : "Reset Password"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!resetConfirmPin} onOpenChange={(open) => !saving && !open && setResetConfirmPin(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Kiosk PIN</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the Kiosk PIN for <span className="font-semibold text-foreground">{resetConfirmPin?.fullName}</span>?
              <br /><br />
              A unique temporary PIN will be displayed once after reset. They will be required to change it on their next Kiosk login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={saving} className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={event => { event.preventDefault(); void confirmResetPin() }}>
              {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Resetting…" : "Reset PIN"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 192–207:** Clicking `KeyRound` (`className="hover:text-amber-600"`) sets `resetConfirmUser = { id: user.id, fullName: user.fullName }`. For operators (`user.role === "Operator"`), clicking `Key` (`className="hover:text-indigo-600"`) sets `resetConfirmPin = { id: user.id, fullName: user.fullName }`.
  * **Line 388:** `<AlertDialogAction ... onClick={event => { event.preventDefault(); void confirmResetPassword() }}>` calls `event.preventDefault()` so the Radix `AlertDialog` does not auto-close before the async API call finishes; it stays open showing `"Resetting…"` with a spinner until `setResetConfirmUser(null)` runs on Line 109.
  * **Lines 106–108:** Once `resetPassword(resetConfirmUser.id)` resolves with the temporary password string, `setHandoff({ username, password })` opens the `"Temporary credentials"` modal (`Lines 365–374`) so the admin can copy and share the temporary password.

---

#### Step B2: `AdminContext.resetPassword()` & `resetPin()` State Updates
* **Step Title & Trigger:** `confirmResetPassword()` / `confirmResetPin()` calls `AdminContext.tsx`, which invokes `api.users.resetPassword(id)` / `api.users.resetPin(id)`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 296–312) and `frontend/src/lib/api.ts` (Lines 288–289)
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 296–312):**
```tsx
  const resetPassword = useCallback(async (id: string) => {
    const result = await api.users.resetPassword(id)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
    return result.temporary_password
  }, [setUsers, acceptUserWrite])

  const resetPin = useCallback(async (id: string) => {
    const result = await api.users.resetPin(id)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPinChange: true, pinSetupReason: "pin_reset" }
      : u))
    return result.temporary_pin
  }, [setUsers, acceptUserWrite])
```
* **Complete Uncut Code Block (`frontend/src/lib/api.ts`, Lines 288–289):**
```ts
    resetPassword: (id: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, {}),
    resetPin: (id: string) => post<{ message: string; temporary_pin: string }>(`/api/v1/users/${id}/reset-pin`, {}),
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`AdminContext.tsx` Lines 297–302:** Calls `POST /api/v1/users/${id}/reset-password` with body `{}`, updates the target user in `users` state with `requiresPasswordChange: true` and `passwordSetupReason: "password_reset"`, and returns `result.temporary_password`.

---

### Phase C, D & E: Backend Reset Controllers, Session Revocation (`AUTH-02`) & Audit Trail (`AUDIT-02`)

#### Step D1: `POST /api/v1/users/{user_id}/reset-password` and `POST /api/v1/users/{user_id}/reset-pin`
* **Step Title & Trigger:** FastAPI validates `UserPasswordReset` / `UserPinReset` and executes `reset_user_password()` / `reset_user_pin()` in `backend/app/api/v1/users.py`.
* **Exact File Path & Line Numbers:** `backend/app/schemas/user.py` (Lines 42–50) and `backend/app/api/v1/users.py` (Lines 344–407)
* **Complete Uncut Code Block (`backend/app/schemas/user.py`, Lines 42–50):**
```python
class UserPasswordReset(BaseModel):
    new_password: str | None = Field(None, min_length=6, max_length=128)
    password_setup_reason: PasswordSetupReasonEnum = PasswordSetupReasonEnum.PASSWORD_RESET


class UserPinReset(BaseModel):
    new_pin: str | None = Field(None, min_length=4, max_length=4, pattern=r"^\d{4}$")
    pin_setup_reason: PinSetupReasonEnum = PinSetupReasonEnum.PIN_RESET
```
* **Complete Uncut Code Block (`backend/app/api/v1/users.py`, Lines 344–407):**
```python
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Line 349 & Line 379:** Sets `response.headers["Cache-Control"] = "no-store"` so the one-time temporary password/PIN is never cached.
  * **Lines 350–354:** Locks the target `UserAccount` row with `.with_for_update()`.
  * **Lines 356–360:**
    1. Generates `password = body.new_password or temporary_password()`.
    2. Hashes with bcrypt: `user.password_hash = hash_password(password)`.
    3. Sets `user.requires_password_change = True` and `user.password_setup_reason = PasswordSetupReasonEnum.PASSWORD_RESET` (`"password_reset"`).
    4. Increments `user.token_version += 1` (`AUTH-02`), immediately revoking any existing JWT session held by that user.
  * **Lines 363–368 (`AUDIT-02`):** Calls `audit.record(db, audit.AuditAction.PASSWORD_RESET, f"Reset password for user {audit.quoted(user.username)} ({user.id}); setup required; sessions revoked", actor=admin, ip=get_client_ip(request))`. The temporary password itself is never written to `activity_log`.
  * **Lines 389–390 (`reset_user_pin` Role Guard):** Verifies `user.role.name == RoleEnum.OPERATOR.value`, raising `ForbiddenException("PIN credentials are only available to operators")` (HTTP 403) if called on an Admin.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Reset Password Endpoint** | `POST /api/v1/users/{user_id}/reset-password` → `reset_user_password()` (`backend/app/api/v1/users.py` Lines 344–371) |
| **Reset PIN Endpoint** | `POST /api/v1/users/{user_id}/reset-pin` → `reset_user_pin()` (`backend/app/api/v1/users.py` Lines 374–407) |
| **Database Columns Updated** | `user_account`: `password_hash`, `requires_password_change = True`, `password_setup_reason = 'password_reset'`, `token_version = token_version + 1`. `operator_profile`: `pin_hash`, `requires_pin_change = True`, `pin_setup_reason = 'pin_reset'` |
| **Audit Actions (`AUDIT-02`)** | `AuditAction.PASSWORD_RESET` (`"password_reset"`) and `AuditAction.PIN_RESET` (`"pin_reset"`), both marked `critical: true` in `activityActions.ts` |
| **Post-Reset Login Banner** | `"Welcome back! Because your password was recently reset, please set a new secure password to continue."` (`Login.tsx` Line 60) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Allow the Administrator to Optionally Type a Custom Temporary Password in the Reset Password Dialog
* **Examiner Prompt:** *"In `UserManagement.tsx` and `AdminContext.tsx`, allow the administrator to optionally type a custom temporary password (minimum 6 characters) inside the Reset Password `AlertDialog`, or leave it blank to auto-generate one."*
* **Files to Edit:**
  1. `frontend/src/lib/api.ts` (Line 288)
  2. `frontend/src/context/AdminContext.tsx` (Lines 34 & 296–303)
  3. `frontend/src/pages/admin/UserManagement.tsx` (Lines 43, 102–115, 376–393)
* **Before (`frontend/src/lib/api.ts`, Line 288):**
```ts
    resetPassword: (id: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, {}),
```
* **After (`frontend/src/lib/api.ts`, Line 288):**
```ts
    resetPassword: (id: string, newPassword?: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, newPassword ? { new_password: newPassword } : {}),
```
* **Before (`frontend/src/context/AdminContext.tsx`, Lines 296–303):**
```tsx
  const resetPassword = useCallback(async (id: string) => {
    const result = await api.users.resetPassword(id)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
    return result.temporary_password
  }, [setUsers, acceptUserWrite])
```
* **After (`frontend/src/context/AdminContext.tsx`, Lines 296–303):**
```tsx
  const resetPassword = useCallback(async (id: string, newPassword?: string) => {
    const result = await api.users.resetPassword(id, newPassword)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
    return result.temporary_password
  }, [setUsers, acceptUserWrite])
```

---

#### Drill Scenario 2: Clear Brute-Force Rate-Limiter Lockout Automatically When an Admin Resets a User's Password or PIN
* **Examiner Prompt:** *"If a user locked their account after 5 failed login attempts, and an administrator resets their password (or PIN), automatically clear `login_limiter` (or `pin_limiter`) for that username so the user can sign in immediately with their new temporary credentials without waiting out the 300-second lockout."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 356–371 & 392–407)
* **Before (`backend/app/api/v1/users.py`, Lines 356–371):**
```python
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
```
* **After (`backend/app/api/v1/users.py`, Lines 356–373):**
```python
    from app.core.rate_limiter import login_limiter

    password = body.new_password or temporary_password()
    user.password_hash = hash_password(password)
    user.requires_password_change = True
    user.password_setup_reason = body.password_setup_reason
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    login_limiter.record_success(user.username)

    # AUDIT-02: Record password reset in activity log (never the credential itself)
    await audit.record(
        db, audit.AuditAction.PASSWORD_RESET,
        f"Reset password for user {audit.quoted(user.username)} ({user.id}); "
        "setup required; sessions revoked",
        actor=admin, ip=get_client_ip(request),
    )
    await db.flush()

    return {"message": "Password reset successfully", "temporary_password": password}
```

---

#### Drill Scenario 3: Block Inactive Users from Having Their Password or PIN Reset Until Reactivated
* **Examiner Prompt:** *"In `POST /api/v1/users/{user_id}/reset-password` and `POST /api/v1/users/{user_id}/reset-pin`, reject the reset with a 409 `ConflictException` if `user.status == ActiveStatusEnum.INACTIVE`."*
* **File to Edit:** `backend/app/api/v1/users.py` (Lines 352–356 & 386–391)
* **Before (`backend/app/api/v1/users.py`, Lines 352–356):**
```python
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")

    password = body.new_password or temporary_password()
```
* **After (`backend/app/api/v1/users.py`, Lines 352–358):**
```python
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User")
    if user.status == ActiveStatusEnum.INACTIVE:
        raise ConflictException("Cannot reset password for an inactive account. Activate the user first.")

    password = body.new_password or temporary_password()
```
