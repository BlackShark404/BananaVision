# BananaVision - Development Changelog

This document tracks completed features, bug fixes, and security updates implemented from the `KENT_ASSIGNED_FEATURES_REVIEW.md` checklist. 

---

## [Date: October 4, 2026] - Security Patch: AUTH-01 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** AUTH-01 (Critical) - Password and PIN change endpoints lacked identity verification.

### What was the issue?
Previously, the system allowed password and PIN changes simply by providing a `username`. It did not check if the user was currently logged in, nor did it require the user to provide their current password or PIN. This meant anyone who knew a valid username could easily hijack an account.

### What did we change?
We split the credential change logic into two distinct, highly secure flows across both the frontend and backend:

**1. Self-Service Change (Profile Page)**
- Users must be authenticated (Active JWT Session).
- Users must provide their **Current Password/PIN**.
- The backend verifies the current credential before allowing the change.
- Replaced `changePasswordAndLogin` with a secure `changePassword(current, new)` method.

**2. First-Time Setup (Login & Kiosk Swap)**
- Used when an admin creates a new account or resets a user's credentials (temporary password/PIN).
- Dedicated endpoints (`/setup-password` and `/setup-pin`) now strictly verify the `requires_password_change` or `requires_pin_change` flag in the database.
- If the flag is `False`, the request is rejected immediately, preventing abuse.
- Frontend properly utilizes new `setupPasswordAndLogin` and `setupPinAndLogin` methods for this specific flow.

### Files Modified:
- `backend/app/schemas/auth.py`
- `backend/app/services/auth_service.py`
- `backend/app/api/v1/auth.py`
- `frontend/src/lib/api.ts`
- `frontend/src/context/AuthContext.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Profile.tsx`
- `frontend/src/components/KioskOperatorSwap.tsx`

---

## [Date: October 4, 2026] - Security Patch: AUTH-02 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** AUTH-02 (High) - Logout and credential reset do not revoke existing JWTs.

### What was the issue?
Previously, logging out only cleared the token from the browser. The JWT itself remained valid on the server until its natural expiry. This meant:
- A copied or stolen token could still be used after the user logged out.
- Changing a password or PIN did not invalidate already-issued tokens.
- An admin-initiated password/PIN reset did not kick out the target user's active sessions.
- WebSocket connections with revoked tokens could still receive live scan data.

### What did we change?
We implemented a **`token_version`** system — a lightweight, database-backed JWT revocation mechanism that requires no Redis or external dependencies:

**1. Database: `token_version` column on `UserAccount`**
- New integer column (default `1`) that acts as a session generation counter.
- Uses `server_default="1"` so existing rows get the value automatically.

**2. JWT Payload: version embedded in every token**
- Every issued JWT now includes a `"tv"` (token version) claim matching the user's current `token_version`.
- `create_user_token()` reads the version from the user object at issuance time.

**3. Central Validation: version checked on every authenticated request**
- `get_current_user()` in `deps.py` compares the JWT's `tv` claim against the database's `token_version`.
- If they don't match, the request is rejected with a clear "Session has been revoked" error.
- The frontend's existing 401 handler automatically clears auth and redirects to `/login`.

**4. Revocation Triggers: version bumped on every security-sensitive action**
- **Logout** (`/auth/logout`) — bumps version, instantly invalidating all prior tokens.
- **Self-service password change** (`/auth/change-password`) — bumps version, issues new token.
- **First-time password setup** (`/auth/setup-password`) — bumps version, issues new token.
- **Self-service PIN change** (`/auth/change-pin`) — bumps version, issues new token.
- **First-time PIN setup** (`/auth/setup-pin`) — bumps version, issues new token.
- **Admin password reset** (`/users/{id}/reset-password`) — bumps version, forces re-auth.
- **Admin PIN reset** (`/users/{id}/reset-pin`) — bumps version, forces re-auth.

**5. WebSocket Hardening**
- WebSocket connections now validate `token_version` and active status against the database on connect.
- Revoked tokens and inactive accounts are rejected with appropriate close codes.

### How it works
```
User logs in → JWT issued with tv=1
User logs out → DB token_version bumped to 2
Old JWT (tv=1) used → deps.py sees tv=1 ≠ DB version 2 → 401 Rejected
User logs in again → New JWT issued with tv=2 → Works normally
```

### Files Modified:
- `backend/app/models/user_account.py` — Added `token_version` column
- `backend/app/services/auth_service.py` — Embed `tv` in JWT, bump version on credential changes
- `backend/app/api/deps.py` — Central token version validation
- `backend/app/api/v1/auth.py` — Bump version on logout
- `backend/app/api/v1/users.py` — Bump version on admin password/PIN resets
- `backend/app/ws/handlers.py` — Token version + active status validation on WebSocket connect


---

## [Date: October 5, 2026] - Security Patch: SCANNER-01 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** SCANNER-01 (High) - Camera mapping API was publicly writable without authentication.

### What was the issue?
`POST /api/v1/cameras/mapping` allowed anyone to modify the backend `.env` file and restart the camera manager without any authentication or authorization.

### What did we change?
- Added `AdminUser` dependency to the `/mapping` endpoint — now requires a valid JWT with Admin role.
- Updated `CameraCalibrationModal.tsx` to send the `Authorization: Bearer` header with both camera list fetch and mapping save requests.

### Files Modified:
- `backend/app/api/v1/cameras.py` — Added `AdminUser` dependency to `update_camera_mapping`
- `frontend/src/components/CameraCalibrationModal.tsx` — Added JWT auth headers to fetch calls

---

## [Date: October 5, 2026] - Security Patch: ACCESS-01 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** ACCESS-01 (High) - User directory and audit logs were accessible to all authenticated users.

### What was the issue?
`GET /api/v1/users` and `GET /api/v1/activity` used `CurrentUser` dependency, meaning any logged-in operator could see the full user directory (names, statuses, roles) and system audit logs (IPs, admin actions).

### What did we change?
- Changed both endpoints to require `AdminUser` instead of `CurrentUser`.
- Operators can no longer access user listings or activity logs directly.

### Files Modified:
- `backend/app/api/v1/users.py` — `list_users` now requires `AdminUser`
- `backend/app/api/v1/activity.py` — `list_activity` now requires `AdminUser`

---

## [Date: October 5, 2026] - Security Patch: ADMIN-01 & SAVE-02 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** ADMIN-01 (High) - Last active admin could be deactivated/demoted, locking everyone out.

### What was the issue?
The `PATCH /users/{id}` endpoint allowed an admin to deactivate or demote themselves (or another admin) even if they were the last active administrator. This could make the system unrecoverable without direct database access.

### What did we change?
- Added a guard in `update_user` that checks if the target user is the last active admin before allowing demotion or deactivation.
- Counts other active admins via a database query. If none exist, the request is rejected with a 409 Conflict error.
- SAVE-02 was already resolved: `AdminContext.updateUser` correctly awaits the API response and only updates state from the committed backend data. Errors propagate and are shown via `toast.error`.

### Files Modified:
- `backend/app/api/v1/users.py` — Added last-active-admin guard with `func.count()` query

---

## [Date: October 5, 2026] - Feature Fix: PROFILE-01 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** PROFILE-01 (High) - Operator avatar uploads failed silently because they used an admin-only endpoint.

### What was the issue?
The Profile page called `updateUser` (which sends `PATCH /users/{id}`) for avatar changes. This endpoint requires `AdminUser`, so operator avatar uploads were silently rejected by the backend, while the frontend showed a success message based on local state.

### What did we change?

**1. New Self-Service Endpoint: `PATCH /users/me/profile`**
- Any authenticated user can update their own avatar without admin privileges.
- Route is registered before `/{user_id}` to ensure correct FastAPI path matching.

**2. Frontend API Method: `api.users.updateProfile()`**
- New method in the API client that calls the self-service endpoint.

**3. AdminContext: `updateOwnProfile()`**
- New context method that calls the self-service API, updates the user list, and syncs auth state.

**4. Profile Page**
- `handleAvatarUpload` and `handleRemoveAvatar` now use `updateOwnProfile` instead of `updateUser`.

### Files Modified:
- `backend/app/api/v1/users.py` — Added `SelfProfileUpdate` schema and `PATCH /me/profile` endpoint
- `frontend/src/lib/api.ts` — Added `users.updateProfile()` method
- `frontend/src/context/AdminContext.tsx` — Added `updateOwnProfile` method
- `frontend/src/pages/Profile.tsx` — Switched avatar handlers to use `updateOwnProfile`

---

## Previously Completed

*(Note: **SAVE-01 & CREATE-01** were verified and are already correctly implemented — `addUser` awaits the API response and the `status` field is properly passed through. **RESET-01** was also verified as already successfully implemented!)*

---

## [Date: October 5, 2026] - Feature Fix: CONFIG-01 Resolution

### Status: ✅ COMPLETED
**Feature/Issue:** CONFIG-01 (High) - System Configuration page simulated a successful save after 800ms instead of waiting for the backend request to finish.

### What was the issue?
The `SystemConfig` page previously used a `setTimeout(800)` to fake a loading delay and then announced success regardless of whether the backend actually committed the changes. The `AdminContext.updateConfig` method also swallowed errors by catching failures and applying local state anyway.

### What did we change?

**1. AdminContext: `updateConfig()` now returns committed data or throws**
- The method `await`s the API call, maps the response into the frontend `SystemConfig` shape, updates state from the **server response only**, and returns it.
- On failure, the error propagates to the caller — no silent local fallback.

**2. SystemConfig: `handleSave()` awaits the real API response**
- Removed the 800ms `setTimeout` simulation entirely.
- Calls `await updateConfig(localConfig)` and updates `localConfig` from the committed result.
- Shows `toast.success` only after a successful save; shows `toast.error` with the failure message on catch.

**3. SystemConfig: `toggleDataRetention()` awaits the real API response**
- Same pattern: `await`s `updateConfig`, reads `saved.dataRetentionEnabled` from the committed response, and preserves unsaved camera/threshold edits in the local draft.
- Error case shows `toast.error` instead of silently succeeding.

### Files Modified:
- `frontend/src/context/AdminContext.tsx` — `updateConfig` returns committed data or throws
- `frontend/src/pages/admin/SystemConfig.tsx` — `handleSave` and `toggleDataRetention` await real API, removed setTimeout simulation

---

## Assigned Issue Checklist (updated October 5, 2026)

Based on the `KENT_ASSIGNED_FEATURES_REVIEW.md` priority roadmap, the implementation status is recorded below. Completed means code changes are present; deployment and hardware verification remain separate.

### 1. Remaining Security & Authorization (Completed)
- **[x] AUTH-03 (High):** Live-event access via WebSockets can bypass login/status checks.
- **[x] AUTH-04 (High):** No application rate limiter or attempt counter for login/PIN guesses.
- **[x] ROLE-01 (High):** Changing a user's role does not reconcile their specific profiles.

### 2. Configuration & Settings Integrity (Completed)
- **[x] CONFIG-01 (High):** System Configuration page simulated save with setTimeout.
- **[x] SCANNER-02 (High):** Camera ID rename deleted/recreated all device records.
- **[x] AI-01 (High):** Confidence threshold slider didn't control YOLO inference.

### 3. Audit Logging & Data Retention (Completed)
- **[x] AUDIT-01 (Medium):** Activity Logs only paginated/filtered locally.
- **[x] RETENTION-01 (High):** 30-day automated data cleanup was not implemented.

### 4. Account Handoff and Remaining Feature Fixes (Completed)
- **[x] CREATE-02 (High):** Shared temporary credentials and initial admin bootstrap need a secure handoff.
- **[x] EDIT-01 (Medium):** Username editing is offered in the UI but backend schema ignores it.
- **[x] VALIDATION-01 (Medium):** Password/PIN/name validation rules differ between frontend and backend.
- **[x] PROFILE-02 (High):** Current-password field on profile not verified (should be resolved by AUTH-01).
- **[x] PROFILE-03 (Medium):** Lifetime statistics computed from partial scan page, not all records.
- **[x] AUDIT-02 (Medium):** Admin password/PIN resets and failed login attempts lack audit log entries.
- **[x] AUDIT-03 (Medium):** CSV export doesn't escape embedded quotation marks.
- **[x] CONFIG-02 (Medium):** Backend lacks range validation for threshold and camera-ID values.
- **[x] CONFIG-03 (Medium):** Power command responses don't verify OS command execution success.
- **[x] SCANNER-03 (Medium):** Camera remapping leaves stale settings snapshots in some modules.
- **[x] AI-02 (Medium):** Model version wording inconsistent (YOLOv8 vs YOLO26) across UI/docs.
- **[x] AI-03 (Medium):** Health endpoint always returns healthy even when models fail to load.
- **[x] RETENTION-02 (Medium):** Failed scans leave orphaned capture files on disk.
- **[x] RETENTION-03 (Medium):** "Database Backup" label is misleading — it's a limited CSV export.
- **[x] LANDING-01 (Medium):** Logo container lacks keyboard/button accessibility.

---

## [Date: October 5, 2026] - Remaining Assigned Issues and Setup Authorization

### Status: Implementation completed; deployment verification pending

- **CREATE-02:** Account creation and password/PIN resets now generate unique temporary credentials on the server. Only the authenticated administrator receives the values, with `Cache-Control: no-store`; the UI displays them in a one-time handoff dialog and keeps them out of account state/browser storage and audit logs. Owners must replace them. Empty-database startup requires an explicit `BOOTSTRAP_ADMIN_PASSWORD` (12–72 UTF-8 bytes), forces first-login replacement, and never logs it. Demo seeding is restricted to non-production with an explicit bootstrap secret; the fixture operator starts inactive with no usable PIN.
- **AUTH-01 follow-up:** The previous setup endpoints still trusted a username and a database flag. Login/PIN authentication now issues a ten-minute setup JWT scoped to exactly password or PIN setup. Setup validates account status, token version and purpose, locks the account row, and invalidates the proof on success. Reusing the temporary credential is rejected. Setup JWTs cannot authenticate ordinary REST or WebSocket access; the frontend keeps them only in memory.
- **PROFILE-03:** `/users/me/summary` aggregates all retained scans on the server. Operator ownership and personal activity are filtered by immutable account ID; admins receive platform totals. The Profile page labels confidence as confidence, displays request failures, and no longer derives totals from a partial scan page. Retention can reduce historical totals, so labels describe retained records.
- **CONFIG-03:** Shutdown/restart commands use a bounded subprocess wait and check exit status. Unsupported OS, permissions and timeout failures return errors; the UI shows backend failure messages. Successful responses describe OS acceptance of a scheduled command. Windows uses ten seconds; Linux/macOS use a one-minute delay and noninteractive sudo. Autostart remains a host configuration check.
- **SCANNER-03 / SCANNER-02 follow-up:** Mapping rejects empty, duplicate, negative, noninteger and oversized selections. It persists the environment file atomically and updates the existing settings object shared by camera listing and startup. Scans, camera mapping, identity changes, health probing and power scheduling share a station-operation lock. Camera display IDs are loaded at startup and reused by captures and the health monitor; renaming preserves device rows/status, including label swaps. The monitor refreshes status after mapping changes even when physical online state is unchanged. Capture filenames use hardware indices rather than editable labels.
- **RETENTION-02:** Failed/cancelled scans remove only their own UUID capture directory; failures after a database commit preserve evidence. Retention commits database deletions before deleting capture directories and cleans old orphan UUID directories even when there are no expired scan rows. Recent, referenced, unrelated and external directories are preserved; failed file removal is logged and retried later.
- **RETENTION-03:** The settings action is labeled **Export Scan Summaries** and describes excluded accounts, settings, audit logs and images. It does not claim backup/restore support.

Deployment notes are in `backend/README.md` and `backend/.env.example`. No deployed account credentials, database rows, hardware mapping or real capture data were changed during verification. Power commands were mocked.

### Verification (October 5, 2026)

- Backend: `venv/Scripts/python.exe -m pytest -q` — **67 passed**, including 17 new regression cases against isolated SQLite databases and temporary directories.
- Browser: `node --test --test-concurrency=1 tests/persistence.test.mjs tests/assigned.test.mjs` — **13 passed** in headless Chrome with fixture APIs. Checks cover one-time credential display/storage, setup proof propagation, operator profile scope, history completeness and failed-write behavior. Separate Vite caches prevent fixture interference.
- Frontend: production TypeScript/Vite build passed; focused lint checks for Profile, AuthContext, SystemConfig and UserManagement passed. Broader checks still report legacy `any` typing, unused helper and effect warnings in AdminContext/API; this patch does not claim repository-wide lint is clean.
- No shutdown/restart command, deployed-database cleanup, seed utility or real camera remapping was run. OS commands were mocked and cleanup tests used disposable directories.

### Remaining station/panel checks

- Demonstrate camera mapping, labels, disconnected devices and capture evidence on the physical station, including a reboot.
- Verify OS power permissions, backend/frontend autostart and offline startup on the deployed host.
- Confirm model metadata/class map, provision ignored weight assets, and record classification/regression performance and station latency.
- Validate existing database schema upgrades and rotate any credentials issued under the old shared-credential workflow.
- Exercise the full role/access/live-session matrix and retention cutoffs on disposable deployment data; code completion alone is not a deployed-system certification.
- Check landing-page layouts, keyboard navigation, contact destination and product claims against demonstrated behavior.
