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
