# 🔐 Deep Dive: Authentication, Login/Logout, PIN Swap & Security Architecture

> **Feature 1:** Login / Logout & Kiosk Session Management  
> **Backend Files:** [`backend/app/api/v1/auth.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/auth.py), [`backend/app/services/auth_service.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/auth_service.py), [`backend/app/core/security.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/security.py), [`backend/app/api/deps.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/deps.py), [`backend/app/core/rate_limiter.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/rate_limiter.py)  
> **Frontend Files:** [`frontend/src/pages/Login.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Login.tsx), [`frontend/src/context/AuthContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AuthContext.tsx), [`frontend/src/lib/api.ts`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/lib/api.ts)

---

## 1. Why Did We Implement This System? (Business & Ergonomic Rationale)

In a physical warehouse/packinghouse environment, two very different types of users interact with BananaVision:
1. **System Administrators:** Configure cameras, manage staff accounts, adjust AI review thresholds, export reports, and reboot hardware. They need **full credential security** (Username + Strong Password).
2. **Kiosk Sorting Operators:** Stand in front of the conveyor/station wearing gloves and sorting banana hands. Typing a complex alphanumeric password every time operators switch shifts creates friction and delays intake.
3. **The Solution — Dual Authentication Architecture:**
   - **Administrative Portal:** Secure Username + Password with bcrypt hashing.
   - **Kiosk Mode Operator Swap:** A dedicated modal displaying active operator avatars where operators can switch in seconds by punching a **4-digit numerical PIN**.
   - **Zero-Trust Token Security:** Both workflows issue a signed, cryptographically verified JSON Web Token (JWT) that encodes role-based access control (RBAC).

---

## 2. Security Vulnerabilities Fixed (Review Roadmap & Defenses)

| Vulnerability ID | Historical Weakness Found | How Kent's Code Fixed It |
|---|---|---|
| **AUTH-01** | Direct unauthenticated password/PIN changes could be called by anyone knowing the username. | Separated self-service changes (which require Current Password) from first-time setup (which requires an expiring cryptographic `setup_token`). |
| **AUTH-02** | Logged-out users or users whose passwords were reset could still use previously copied JWTs until natural expiry. | Implemented **Database Token Versioning (`token_version`)**. On logout or reset, `token_version += 1`. All prior JWTs become invalid instantly. |
| **AUTH-03** | WebSocket live events could be sniffed without validating user active status. | Connected WebSocket sessions require authenticated tokens and revalidate active account status. |
| **AUTH-04** | No brute-force protection existed on 4-digit PINs or login endpoints. | Implemented sliding-window rate limiters (`login_limiter` and `pin_limiter`) returning HTTP 429 Too Many Requests after 5 failed attempts with IP auditing. |

---

## 3. High-Level Flowchart: The Complete Authentication Flow

```
[ User Action ]
      │
      ├──> [ Login with Username + Password ] ──> POST /api/v1/auth/login
      │                                                │
      │                                        [ Check Rate Limit (AUTH-04) ]
      │                                                │
      │                                        [ Verify Bcrypt Password Hash ]
      │                                                │
      │                                        ┌───────┴────────────────────────┐
      │                                     Failed                            Success
      │                                        │                                │
      │                                [ Record Lockout ]             [ Check requires_password_change ]
      │                                [ Audit Log Entry ]                      │
      │                                [ Return 401 / 429 ]              ┌──────┴──────┐
      │                                                                True          False
      │                                                                  │             │
      │                                                      [ Issue setup_token ] [ Issue Access JWT ]
      │                                                      [ Redirect to Setup ] [ Redirect to App  ]
      │
      └──> [ Kiosk Swap with PIN ] ─────────────> POST /api/v1/auth/swap
                                                       │
                                               [ Check PIN Rate Limit ]
                                                       │
                                               [ Verify Bcrypt PIN Hash ]
                                                       │
                                               [ Check Operator Role & Active Status ]
                                                       │
                                               [ Issue Access JWT with Operator Claims ]
```

---

## 4. Code Breakdown: Part-by-Part Explanation

### Part A: Rate Limiting & Brute-Force Defense (`backend/app/core/rate_limiter.py` & `auth.py`)

In `backend/app/api/v1/auth.py`:
```python
# Check if this username is currently locked out
locked, remaining = login_limiter.is_locked(body.username)
if locked:
    raise HTTPException(
        status_code=429,
        detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
    )
```
- **How it works:** `login_limiter` maintains an in-memory sliding window of timestamps for each username.
- **Fail path:** If authentication fails:
  ```python
  is_locked, info = login_limiter.record_failure(body.username)
  db.add(ActivityLog(
      user_id=None,
      action="login_failed",
      details=f"Failed login attempt for username '{body.username}'",
      ip_address=get_client_ip(request),
  ))
  await db.flush()
  ```
- **Security Impact:** An attacker attempting to guess passwords or 4-digit PINs triggers an HTTP 429 lockout and a permanent forensic audit trail with their IP address.

---

### Part B: Password Verification & Setup Token Handling (`backend/app/services/auth_service.py`)

In `backend/app/services/auth_service.py`:
```python
async def authenticate_user(db: AsyncSession, username: str, password: str):
    # Fetch user with role and profile relationships
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()
    if not user:
        return "failed", None, "Invalid username or password"

    # Bcrypt hash verification
    if not verify_password(password, user.password_hash):
        return "failed", user, "Invalid username or password"

    if user.status != ActiveStatusEnum.ACTIVE:
        return "inactive", user, "Account is inactive"

    if user.requires_password_change:
        return "requires_password_change", user, "First-time setup or password reset required"

    return "success", user, None
```
- **Why `requires_password_change` exists:** When an administrator creates an employee account, they provide a temporary password. The user cannot access any dashboard or scan functions until they exchange their temporary credential for their own private password.
- **How `setup_token` works:** Rather than giving full access, the server issues a scoped JWT:
  ```python
  def create_setup_token(user: UserAccount, purpose: str) -> str:
      payload = {
          "sub": str(user.id),
          "username": user.username,
          "purpose": purpose,  # "setup_password" or "setup_pin"
          "scope": "setup",
          "tv": user.token_version,
          "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
      }
      return jwt.encode(payload, settings.secret_key, algorithm="HS256")
  ```
  This token **cannot** call any API endpoint other than `/auth/setup-password` or `/auth/setup-pin`!

---

### Part C: Token Generation & Revocation via `token_version` (`backend/app/core/security.py` & `deps.py`)

When issuing an access token:
```python
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=8))
    to_encode.update({"exp": expire, "scope": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
```
The token payload embeds:
- `sub`: User UUID
- `role`: "Admin" or "Operator"
- `tv`: `user.token_version` (integer counter)

Now look at how [`deps.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/deps.py) protects every request:
```python
async def get_current_user(db: AsyncSession, authorization: str = Header(...)) -> UserAccount:
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    user_id = uuid.UUID(payload["sub"])
    
    user = await db.scalar(select(UserAccount).where(UserAccount.id == user_id))
    if not user:
        raise CredentialsException("User not found")
    if user.status != ActiveStatusEnum.ACTIVE:
        raise ForbiddenException("Account is inactive")

    # ── Instant Session Revocation Check (AUTH-02) ──
    token_version = payload.get("tv")
    if token_version is None or token_version != user.token_version:
        raise CredentialsException("Session has been revoked — please log in again")

    return user
```
- **The Logout Implementation (`auth.py:340`):**
  ```python
  @router.post("/logout")
  async def logout(user: CurrentUser, db: DbSession, request: Request):
      user.token_version += 1  # Increment version in database!
      db.add(ActivityLog(user_id=user.id, action="logout", details=f"User {user.username} logged out"))
      await db.flush()
      return {"message": "Logged out successfully"}
  ```
  Because `token_version` increases from, say, `1` to `2`, **any copied token holding `tv: 1` is immediately dead**, even if its natural 8-hour expiration has not elapsed!

---

### Part D: Kiosk PIN Operator Swap (`backend/app/api/v1/auth.py:150`)

```python
@router.post("/swap", response_model=LoginResponse)
async def swap(body: PinSwapRequest, db: DbSession, request: Request):
    locked, remaining = pin_limiter.is_locked(body.username)
    if locked:
        raise HTTPException(429, f"Too many failed PIN attempts. Try again in {remaining}s.")

    status, user, reason = await swap_operator(db, body.username, body.pin)
    if status == "failed":
        pin_limiter.record_failure(body.username)
        # Audit log failed PIN attempt
        ...
        return LoginResponse(status="failed")

    # Successful PIN swap creates an Operator JWT and updates session
    token = create_user_token(user)
    db.add(ActivityLog(user_id=user.id, action="login", details=f"Operator {user.username} swapped in session"))
    return LoginResponse(status="success", token=TokenResponse(access_token=token), user=...)
```
- Only users with an active `OperatorProfile` and `role == Operator` can authenticate via PIN. An administrator cannot use PIN swap; they must use their password.

---

### Part E: Frontend State Management (`frontend/src/context/AuthContext.tsx` & `Login.tsx`)

In `frontend/src/pages/Login.tsx`:
```tsx
const result = await login(username, password)
if (result === "requires_password_change" || result.startsWith("requires_password_change")) {
  setIsChangingPassword(true)  // Switches form to Set New Password mode
  return
}
if (result === "success") {
  toast.success("Welcome back!")
  navigate("/dashboard")
}
```
In `AuthContext.tsx`:
- The browser stores the token in `localStorage` (`access_token`, `auth_user`).
- When making API calls, `api.ts` attaches the Bearer token via Axios/Fetch interceptor:
  ```ts
  headers: { Authorization: `Bearer ${token}` }
  ```
- If any backend response returns `401 Unauthorized` (such as when `token_version` mismatches), `AuthContext` clears local storage and immediately redirects the browser back to `/login`.

---

## 5. Summary of Key Defense Takeaways

1. **Dual Authentication:** Secure password auth for Admins; 4-digit PIN auth for high-speed kiosk shifts.
2. **Stateful Revocation on Stateless JWTs:** Solved using `token_version` checks in FastAPI dependencies.
3. **No Unauthenticated Credential Tampering:** Self-service requires the existing password; onboarding requires an expiring single-use `setup_token`.
4. **Brute Force Immunity:** `pin_limiter` and `login_limiter` lock out accounts after 5 failures and record forensic IP audit logs.
