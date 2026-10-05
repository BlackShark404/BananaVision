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

### 5. Follow-up security and schema gaps (Completed)
- **[x] AUTH-02 / AUTH-03:** Existing WebSocket sessions revalidate on delivery, incoming messages and idle checks.
- **[x] ROLE-01:** PIN access requires the current Operator role; promotion retires the PIN and role/status changes revoke sessions.
- **[x] ADMIN-01:** A shared database transaction lock makes the last-admin safeguard safe across concurrent requests and workers.
- **[x] Database upgrades:** Recorded Alembic revisions run before startup account reads, including legacy `token_version` upgrades.
- **[x] API/AdminContext cleanup:** Typed contracts and account-scoped state replace explicit `any` types and synchronous effect resets.

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

---

## [Date: October 5, 2026] - Live Sessions, Role Transitions and Versioned Upgrades

### Status: Implementation and automated regression verification completed; station acceptance pending

- **Live WebSockets:** Every delivery and incoming message validates JWT expiry, access scope, account status, session version and current database role. Idle sessions recheck every 15 seconds. Invalid sessions are removed from rooms and closed; database validation failures stop delivery. Subscriptions update membership without accepting the socket twice. The browser returns to login for a revoked current token, while delayed closes from an older socket cannot clear a rotated token.
- **Roles and PINs:** PIN login/setup/change/reset require the current Operator role, including legacy promoted accounts that still contain a PIN hash. Promotion clears the PIN and its setup flags while keeping historical scan ownership. Demotion clears any old PIN, requires fresh administrator handoff and preserves existing profiles. Role/status changes increment the session version, so reactivation cannot restore a revoked session.
- **Concurrent account changes:** All user updates acquire a common role-row transaction lock before loading/counting targets. Waiting requests recheck the administrator's current status, role and token version. This protects both simultaneous self-changes and admins attempting to change each other. Credential changes, logout and resets lock/refresh the account to prevent stale session versions from overwriting a concurrent revocation.
- **Migrations:** Added Alembic configuration, revision templates and explicit session-revocation/feature-column revisions. Startup and `python -m app.core.migrations` initialize missing tables and apply recorded upgrades before ORM reads. Existing rows/credentials and already-present columns survive upgrades. PostgreSQL startup uses a transaction advisory lock; concurrent starts are tested. Historical engineered features are not recomputed and unsafe automatic downgrades are blocked.
- **Frontend contracts and account state:** API responses and write bodies have explicit types, including nullable values and actual pagination parameters. API/AdminContext explicit `any` types, the unused delete helper and synchronous effect-state warnings are removed. Cached admin data clears on account/role changes without remounting child screens; late responses from the old scope are ignored. Delayed profile responses cannot overwrite the current account's displayed identity. Missing stored device timestamps are not replaced with the current time.

### Verification

- **Backend: 96 passed**, including real simultaneous transactions on SQLite and an isolated PostgreSQL 17 instance, fresh/legacy/repeated schema upgrades, concurrent startup, connected/idle WebSocket revocation, JWT expiry, legacy PIN denial, preserved scan ownership and stale credential updates. PostgreSQL tests use unique temporary schemas and leave the station database untouched.
- **Browser: 16 passed** in headless Chrome with fixture APIs. Added cases verify account-cache clearing, late-response rejection, preserved setup-screen state, stale profile protection and WebSocket token rotation/logout behavior.
- **Frontend:** TypeScript/Vite production build and focused ESLint checks for API, AdminContext, AuthContext, API/domain types and the updated fixture passed. This resolves the reported API/AdminContext debt; it does not claim repository-wide lint cleanup.
- The Windows default pytest temporary folder was inaccessible; verification used a writable ignored workspace test directory with cache writes disabled. No production schema upgrade, real power command, station reboot, real camera remapping or model benchmark was performed.

### Remaining acceptance work

Rehearse migrations against a disposable copy of the deployed database and verify its recorded revision. Complete physical camera/reboot, power permissions, offline startup, autostart, model asset/performance/latency and full station acceptance checks listed above. Automated code checks do not establish hardware or deployment readiness.

---

## Team Testing Guide — Account Handoff and Follow-up Fixes

Use the branch/commit containing these updates. The commands below use **Windows PowerShell** and each block starts from the **BananaVision repository root**. Install backend requirements in `backend/venv` and frontend dependencies first; see [backend setup](../backend/README.md). Use test accounts and a disposable database for manual checks, role/status changes, credential resets and migration rehearsals.

### 1. Run the backend regression suite

```powershell
cd backend
New-Item -ItemType Directory -Force node_modules | Out-Null
.\venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=node_modules\verify-temp
cd ..
```

**Expected:** No failures or errors. Without a PostgreSQL test URL, the current suite should report **90 passed, 6 skipped**. The six skipped cases require PostgreSQL; skipping them does not verify PostgreSQL locking or migrations. `verify-temp` is a disposable directory that pytest clears on reruns; `node_modules` is ignored by Git. This avoids the inaccessible default Windows temporary folder encountered during verification.

Coverage includes credential handoff/setup, revoked sessions, PIN/role restrictions, last-admin protection, stale credential writes, profile totals, persistence failures, camera settings, mocked power outcomes and capture cleanup. The tests do not boot the physical station or execute real power commands.

### 2. Include PostgreSQL concurrency and migration tests

Start a disposable PostgreSQL test database. Replace the example connection values below with that database's credentials; the test user needs permission to create schemas. These tests create unique temporary schemas and remove those schemas afterward.

```powershell
cd backend
$env:BANANAVISION_TEST_DATABASE_URL = 'postgresql+asyncpg://TEST_USER:TEST_PASSWORD@localhost:5432/bananavision_test'
New-Item -ItemType Directory -Force node_modules | Out-Null
.\venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=node_modules\verify-postgresql
Remove-Item Env:\BANANAVISION_TEST_DATABASE_URL
cd ..
```

**Expected:** **96 passed**, with no PostgreSQL skips. This verifies simultaneous self-demotion/deactivation, admins changing each other, fresh/legacy/repeated schema upgrades and concurrent startup. At least one active admin must remain after the concurrent account changes.

### 3. Check frontend compilation and the cleaned-up files

```powershell
cd frontend
npm run build
npx eslint src/lib/api.ts src/context/AdminContext.tsx src/context/AuthContext.tsx src/types/api.ts src/types/index.ts tests/assigned.fixture.tsx
cd ..
```

**Expected:** Both commands exit successfully. Build checks TypeScript and produces the production bundle. Focused lint checks the files covered by this cleanup; `npm run lint` checks the wider repository and may still report unrelated legacy issues.

### 4. Run browser regression tests

These tests start isolated Vite servers and use fixture APIs, so the real backend and cameras are not required. They require Node.js, installed Google Chrome and Playwright. See [browser test setup](../frontend/tests/dashboard.README.md) for alternate browser/module paths. If Playwright is not already installed, the following optional command installs the version used for verification into an ignored test-tools folder:

```powershell
cd frontend
npm install --prefix node_modules/.qa-tools --no-save --package-lock=false playwright@1.63.0
$env:PLAYWRIGHT_MODULE = (Resolve-Path 'node_modules/.qa-tools/node_modules/playwright/index.mjs').Path
node --test --test-concurrency=1 tests/persistence.test.mjs tests/assigned.test.mjs
Remove-Item Env:\PLAYWRIGHT_MODULE
cd ..
```

If using an existing Playwright installation, skip the install command and set `PLAYWRIGHT_MODULE` to its absolute `playwright/index.mjs` path instead.

**Expected:** **16 passed**, with no failures or uncaught browser errors. These checks cover one-time credential display, setup proofs, complete history, failed writes, account-cache clearing, late-response rejection, profile metadata protection and WebSocket token rotation/logout behavior.

### 5. Check the behavior in the running app

Run the backend using [its startup instructions](../backend/README.md), configured for the test database. In another terminal, run `npm run dev` from `frontend`. Use separate browser profiles or a normal and an incognito window for independent sessions; two normal tabs share local storage.

| Change | Test steps | Expected result |
| --- | --- | --- |
| Temporary credential handoff | Create two test operators. Inspect each handoff dialog, close it, and complete password/PIN setup using the issued temporary credentials. | Temporary passwords differ; each operator receives a generated four-digit PIN. Setup requires replacement. Values disappear when the dialog closes and are absent from browser storage and audit logs. |
| Live WebSocket revocation | Sign the same test account into two independent browser sessions. Open a live page and confirm its WebSocket is connected. Log out in one session. Repeat with an admin password/PIN reset or account deactivation. | The other socket stops receiving events, closes and returns to login. Idle revocation occurs by the next 15-second check; outgoing events are checked before delivery. Browser DevTools → Network → WS can show the close/frame behavior. |
| Promotion retires the PIN | Start with a working operator PIN and an existing scan. Promote that operator to Admin, then retry the old PIN and old session. | PIN login fails, old sessions are revoked, and historical scans retain their owner. A fresh administrator session uses password authentication. |
| Demotion requires fresh handoff | Demote that test Admin back to Operator while keeping another active Admin. Retry the old PIN, then issue a new PIN through **Reset PIN** and finish PIN setup. | The old PIN remains unusable. The fresh temporary PIN requires replacement before normal PIN login. |
| Reactivation does not revive tokens | Sign in as a test operator, deactivate and reactivate it from a separate Admin session, then reuse its original token. | The old token is rejected; a fresh sign-in is required. |
| Last-active-admin safeguard | On the disposable database, leave one active Admin. Try to demote or deactivate it. For direct API verification, authorize a test Admin in Swagger at `/docs` and call `PATCH /api/v1/users/{user_id}`. | The backend returns **409** and preserves the active Admin. Use the automated PostgreSQL tests above for genuinely simultaneous requests. |
| Account-state cleanup | Switch between accounts/roles after loading admin data. Also inspect the browser regression cases for delayed responses during a switch. | Previous admin data disappears; late responses cannot restore it or overwrite the new account's displayed identity. Setup screens retain their own state. |
| Full profile totals | Seed more than 100 retained test scans, including scans belonging to different operators. Compare Profile totals with the test database. | Operators see all their own retained scans and personal activity; Admins see platform totals. Results are not limited to the first history page. |

### 6. Rehearse an existing database upgrade

Restore an old database backup into a **disposable copy**. This step uses **`DATABASE_URL`**, which selects the application database; `BANANAVISION_TEST_DATABASE_URL` only selects optional automated-test connections. Replace the URL below before running the commands:

```powershell
cd backend
$env:DATABASE_URL = 'postgresql+asyncpg://TEST_USER:TEST_PASSWORD@localhost:5432/bananavision_upgrade_copy'
.\venv\Scripts\python.exe -m app.core.migrations
.\venv\Scripts\python.exe -m app.core.migrations
Remove-Item Env:\DATABASE_URL
cd ..
```

Run these read-only queries against that copy using your PostgreSQL client:

```sql
SELECT version_num FROM alembic_version;

SELECT column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'user_account'
  AND column_name = 'token_version';
```

**Expected:** Revision `0002_feature_engineering`; a non-null `token_version` column with default `1` when added by the migration; both upgrade runs succeed without duplicate columns. Compare account/scan counts and credential hashes before and after. Existing data must survive. Start the backend against the copy, verify sign-in, and confirm logout/reset invalidates old tokens. Never use the scan-summary CSV as the recovery backup.

### 7. Record station acceptance separately

- Verify real camera mapping, labels, unplug/reconnect behavior and capture evidence.
- Test an actual restart/shutdown on the designated test station, then confirm frontend/backend autostart after reboot.
- Test offline startup with required dependencies and model assets already provisioned.
- Record model version/class map, classification/regression performance and station latency.

For each check, record **tester, date, branch/commit, environment, steps, expected result, actual result and pass/fail**, with screenshots or sanitized logs where useful. Keep passwords, PINs and tokens out of the report. Report skipped or blocked checks separately from passes; automated test results do not certify hardware or deployment readiness.
