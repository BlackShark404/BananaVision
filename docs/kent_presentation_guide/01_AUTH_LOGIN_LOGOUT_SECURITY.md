# 🔐 Master Guide: Authentication, Login/Logout, PIN Swap & Zero-Trust Security

> **Presenter & Author:** Kent RG A. Baguio  
> **Core Focus:** End-to-End Authentication Architecture, Dual-Tier Credential Design, Stateful JWT Revocation (`token_version`), Rate Limiting, and Full Front-to-Back Code Flow.  
> **Backend Files:**
> - [`backend/app/api/v1/auth.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/auth.py) — Route controllers for login, swap, password/PIN setup, logout
> - [`backend/app/services/auth_service.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/auth_service.py) — Core authentication logic, credential verification, temporary setup tokens
> - [`backend/app/core/security.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/security.py) — Direct `bcrypt` hashing/verification, JWT generation and decoding
> - [`backend/app/api/deps.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/deps.py) — Dependency injection, Bearer token extraction, instant session revocation check
> - [`backend/app/core/rate_limiter.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/rate_limiter.py) — In-memory sliding-window brute force protection
>
> **Frontend Files:**
> - [`frontend/src/pages/Login.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Login.tsx) — Login page UI, state machine (Standard Login vs First-Time Password Change)
> - [`frontend/src/context/AuthContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AuthContext.tsx) — Global React authentication state provider and methods
> - [`frontend/src/lib/api.ts`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/lib/api.ts) — Fetch HTTP wrapper, Bearer token injection, 401 automatic session ejection
> - [`frontend/src/lib/auth.ts`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/lib/auth.ts) — `localStorage` token and user profile persistence helpers
> - [`frontend/src/App.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/App.tsx) — `ProtectedRoute` and `PublicRoute` client-side navigation guards
> - [`frontend/src/components/AppSidebarFooter.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/components/AppSidebarFooter.tsx) — User profile popover and Logout trigger

---

## 1. Why Did We Implement This System? (Panel Defense Rationale)

In a software defense, the panel will ask: *"Why didn't you just use standard cookies, or let anyone sign up, or use a Firebase/Auth0 service?"*  
Here is the exact engineering justification you must understand and present:

### 1.1 The Operational Environment: Offline Industrial Packinghouse
BananaVision is not a public SaaS website hosted on the internet. It is an **offline edge appliance** running on a physical Mini PC inside a tropical banana packinghouse or warehouse LAN.
- **No Internet / SMTP Gateway:** The station frequently operates with zero internet connectivity. Therefore, traditional web flows like *"Forgot Password? We emailed you a reset link"* are physically impossible.
- **No Self-Registration (Closed Appliance Model):** If anyone connected to the local Wi-Fi or Ethernet switch could click "Register Account", unauthorized personnel could manipulate camera calibrations, tamper with AI classification thresholds, or spoof banana batch intakes.
- **Administrator as Gatekeeper:** All accounts are provisioned exclusively by an Administrator via `backend/app/api/v1/users.py`. The Admin generates a temporary credential and hands it to the worker in person.

### 1.2 Dual-Tier Authentication (Admin vs Kiosk Operator)
A single authentication model fails in an industrial packinghouse due to user ergonomic differences:
1. **Administrators (High Security, Low Frequency):**
   - Manage cameras, configure hardware, adjust AI models, export database archives.
   - Interact via standard keyboards/laptops.
   - **Requirement:** Full alphanumeric Username + Strong Password (hashed with bcrypt).
2. **Kiosk Sorting Operators (High Speed, High Frequency):**
   - Stand directly on the conveyor line wearing wet rubber gloves, handling banana bunches.
   - Operators swap shifts every 1 to 2 hours or take breaks.
   - Forcing an operator to type a 12-character alphanumeric password on a touchscreen 20 times a day causes worker frustration, intake bottlenecks, and leads to bad security habits (writing passwords on sticky notes pasted to the monitor).
   - **Requirement:** Fast Kiosk PIN Swap (`/auth/swap`). Operators tap their picture from a public kiosk roster and punch a **4-digit numerical PIN**.
   - **Security Constraint:** Because a 4-digit PIN has only 10,000 combinations ($10^4$), it is guarded by strict sliding-window rate limiting (`pin_limiter`) that temporarily locks out brute-force attempts after 5 failures.

### 1.3 Why JWTs with Database Token Versioning (`token_version`)?
- **Why JWT over Server Cookies?**  
  BananaVision is architected as a decoupled Single-Page Application (React + Vite) communicating asynchronously with a FastAPI REST API and WebSocket streams for real-time camera telemetry and live YOLO scan events. JWT Bearer headers provide standardized cross-origin and WebSocket authorization without cookie-path collisions or CSRF vulnerabilities.
- **The Classic JWT Flaw & Kent's Fix (AUTH-02):**  
  Standard JWTs are stateless. Once signed, a token is cryptographically valid until its expiration timestamp (`exp`), even if the user logs out, is demoted, or has their account deactivated! In high-security systems, engineers often introduce Redis to maintain a revoked token blacklist—but running Redis on an edge Mini PC adds unnecessary memory overhead and operational complexity.
- **The Solution — `token_version`:**  
  Each `user_accounts` row in PostgreSQL has an integer column `token_version` (default `1`). When an access token is issued, its payload embeds `"tv": user.token_version`.  
  On **every single protected HTTP request**, the FastAPI dependency `get_current_user` in `deps.py` queries PostgreSQL and checks:
  $$\text{payload}["tv"] == \text{user.token\_version}$$
  When a user logs out (`POST /auth/logout`) or an Admin changes credentials/status:
  $$\text{user.token\_version} \mathrel{+}= 1$$
  **Instantly, every token previously issued to that user becomes invalid across all browser tabs and devices, achieving stateful instant revocation with zero Redis dependency.**

---

## 2. High-Level Architecture & End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as Operator / Admin
    participant UI as Login.tsx / PinModal.tsx
    participant Context as AuthContext.tsx
    participant ApiClient as lib/api.ts & auth.ts
    participant Router as api/v1/auth.py
    participant Limiter as rate_limiter.py
    participant Service as auth_service.py
    participant Sec as security.py (bcrypt/JWT)
    participant DB as PostgreSQL (UserAccount)
    participant Audit as ActivityLog

    %% LOGIN REQUEST
    User->>UI: Enter Username & Password (or PIN)
    UI->>UI: inFlight.current = true (Debounce Guard)
    UI->>Context: login(username, password)
    Context->>ApiClient: api.auth.login(username, password)
    ApiClient->>Router: POST /api/v1/auth/login { username, password }

    %% RATE LIMIT CHECK
    Router->>Limiter: login_limiter.is_locked(username)
    alt Locked (>= 5 failed attempts in 300s)
        Limiter-->>Router: (True, remaining_seconds)
        Router-->>ApiClient: HTTP 429 Too Many Requests
        ApiClient-->>UI: Display Lockout Toast
    end

    %% CREDENTIAL VERIFICATION
    Router->>Service: authenticate_user(db, username, password)
    Service->>DB: SELECT UserAccount WHERE username = :username
    DB-->>Service: user record (password_hash, status, token_version, role)
    
    Service->>Sec: verify_password(plain, password_hash)
    Sec-->>Service: True / False (via bcrypt.checkpw)

    alt Password Invalid
        Service-->>Router: ("failed", None, None)
        Router->>Limiter: record_failure(username)
        Router->>Audit: INSERT INTO activity_logs (action='login_failed', ip_address)
        Router-->>ApiClient: HTTP 200 { status: "failed" }
        ApiClient-->>UI: "Login failed: Check username & password"
    else Account Inactive
        Service-->>Router: ("inactive", None, None)
        Router-->>ApiClient: HTTP 200 { status: "inactive" }
        ApiClient-->>UI: "Account is inactive. Contact Admin."
    else First-Time Setup Required (requires_password_change == True)
        Service-->>Router: ("requires_password_change", user, reason)
        Router->>Sec: create_setup_token(user, scope="setup_password", exp=10m)
        Router-->>ApiClient: HTTP 200 { status: "requires_password_change", setup_token: "..." }
        ApiClient-->>Context: Store setup_token in passwordSetup.current
        Context-->>UI: Set isChangingPassword = true (Switch Form UI)
    else Success
        Service-->>Router: ("success", user, None)
        Router->>Limiter: record_success(username)
        Router->>Sec: create_user_token(user) -> JWT with sub, username, role, tv, exp
        Router->>Audit: INSERT INTO activity_logs (action='login', user_id, ip_address)
        Router-->>ApiClient: HTTP 200 { status: "success", token: { access_token }, user: {...} }
        
        %% FRONTEND STATE HYDRATION
        ApiClient->>Context: setToken(token) & setStoredUser(user)
        Context->>ApiClient: localStorage.setItem("bananavision_token", token)
        Context->>ApiClient: localStorage.setItem("bananavision_user", JSON.stringify(user))
        Context->>Context: setUser(authUser) (React State Re-render)
        Context-->>UI: return "success"
        UI->>UI: toast.success("Welcome back!")
        UI->>User: navigate("/dashboard")
    end

    %% SUBSEQUENT PROTECTED CALLS
    opt Authenticated Protected API Request
        User->>UI: View Dashboard
        UI->>ApiClient: api.dashboard.getSummary()
        ApiClient->>ApiClient: Read token from localStorage
        ApiClient->>Router: GET /api/v1/dashboard/summary (Header: Authorization: Bearer <token>)
        Router->>DB: _resolve_user(db, token)
        Note over Router,DB: Compares token.tv == DB.token_version
        DB-->>Router: Token version matches & user is Active
        Router-->>ApiClient: HTTP 200 JSON Data
    end

    %% LOGOUT
    opt User Clicks Logout
        User->>UI: Click "Log Out" in Sidebar
        UI->>Context: logout()
        Context->>Router: POST /api/v1/auth/logout (Bearer <token>)
        Router->>DB: UPDATE user_accounts SET token_version = token_version + 1
        Router->>Audit: INSERT INTO activity_logs (action='logout')
        Router-->>Context: HTTP 200 { message: "Logged out successfully" }
        Context->>ApiClient: clearAuth() (Deletes localStorage token & user)
        Context->>Context: setUser(null)
        Context-->>UI: Redirect to Landing Page ("/")
    end
```

---

## 3. Step-by-Step Code Walkthrough: Front to Back to Front

Let us trace every line of code executed during the authentication lifecycle.

### Step 1: The Trigger in [`frontend/src/pages/Login.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Login.tsx)

When the user types their credentials into the form and clicks **Sign In**:

```tsx
// frontend/src/pages/Login.tsx (lines 27-79)
const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
  e.preventDefault()
  
  // 1. Debounce / Concurrency Guard: Prevents duplicate clicks from firing parallel network requests
  if (inFlight.current) return
  inFlight.current = true
  
  try {
    setLoading(true)
    // 2. Delegate authentication logic to the AuthContext hook
    const result = await login(username, password)
    
    // 3. Handle First-Time Temporary Credential Setup (AUTH-01)
    if (result === "requires_password_change" || result.startsWith("requires_password_change")) {
      setIsChangingPassword(true) // Flips UI mode to New Password form
      setLoading(false)
      return
    }
    
    // 4. Handle Successful Login
    if (result === "success") {
      toast.success("Welcome back!", { description: "Logged in successfully" })
      navigate("/dashboard") // React Router client redirect
    } else if (result === "inactive") {
      toast.error("Account Inactive", { description: "Your account is inactive. Please contact an administrator." })
    } else {
      toast.error("Login failed", { description: "Check your username and password, or contact an administrator." })
    }
  } catch {
    toast.error("Sign in unavailable", { description: "Please try again." })
  } finally {
    inFlight.current = false
    setLoading(false)
  }
}
```

- **Key Defense Detail:** Notice `inFlight.current`. If an impatient user double-clicks the submit button, the second click is dropped instantly in memory without spamming the backend rate limiter.

---

### Step 2: The Context & API Client in [`AuthContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AuthContext.tsx) & [`api.ts`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/lib/api.ts)

Inside `AuthContext.tsx`:
```tsx
// frontend/src/context/AuthContext.tsx (lines 53-85)
const login = useCallback(async (username: string, password?: string) => {
  try {
    passwordSetup.current = null
    // Calls the centralized API client
    const res = await api.auth.login(username, password || "")

    if (res.status === "requires_password_change") {
      if (!res.setup_token) return "failed" as const
      // Keep single-use setup token in React memory (never localStorage!)
      passwordSetup.current = { username, token: res.setup_token }
      if (res.reason === "new_account") return "requires_password_change_new_account" as const
      if (res.reason === "password_reset") return "requires_password_change_reset" as const
      return "requires_password_change" as const
    }

    if (res.status === "inactive") return "inactive" as const
    if (res.status === "failed" || !res.token || !res.user) return "failed" as const

    // Save token and user in localStorage and React State
    setToken(res.token.access_token)
    const u = res.user
    const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
    setStoredUser(authUser)
    setUser(authUser)
    return "success" as const
  } catch {
    return "failed" as const
  }
}, [])
```

Inside `frontend/src/lib/api.ts`:
```ts
// frontend/src/lib/api.ts (lines 43-70)
async function request<T>(method: string, path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) headers["Authorization"] = `Bearer ${token}` // Injects Bearer token automatically

  let res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  })
  ...
}
```

---

### Step 3: Backend Ingress & Rate Limiter in [`auth.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/auth.py) & [`rate_limiter.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/rate_limiter.py)

FastAPI receives `POST /api/v1/auth/login`.  
The first defensive barrier executed is the **AUTH-04 Sliding-Window Rate Limiter**:

```python
# backend/app/api/v1/auth.py (lines 76-85)
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, request: Request):
    # ── AUTH-04: Check rate limit before hitting the database ────────
    locked, remaining = login_limiter.is_locked(body.username)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
        )
```

#### How the Rate Limiter Actually Works:
In `backend/app/core/rate_limiter.py`:
```python
MAX_ATTEMPTS = 5           # Max failures before lockout
LOCKOUT_SECONDS = 300      # 5-minute lockout penalty
WINDOW_SECONDS = 300       # 5-minute sliding evaluation window

class RateLimiter:
    def __init__(self, ...):
        self._records: dict[str, _AttemptRecord] = defaultdict(_AttemptRecord)
        self._lock = threading.Lock() # Thread-safe concurrency lock

    def is_locked(self, key: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if not record: return False, 0
            if record.locked_until > now:
                return True, int(record.locked_until - now)
            return False, 0
```
- **Panel Q&A Value:** If an attacker tries passwords continuously, on the 5th failed attempt, `record_failure()` sets `locked_until = now + 300`. The server immediately short-circuits further attempts with `HTTP 429` without performing expensive password hashes or database queries.

---

### Step 4: Verification & Password Hashing in [`auth_service.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/auth_service.py) & [`security.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/core/security.py)

If not rate-limited, `auth.py` invokes `authenticate_user`:

```python
# backend/app/services/auth_service.py (lines 75-107)
async def authenticate_user(db: AsyncSession, username: str, password: str, *, readonly: bool = False):
    # 1. Fetch user by username with eager relationships
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    # 2. Timing-safe password verification
    if not user or not verify_password(password, user.password_hash):
        return "failed", None, None

    # 3. Check Account Status
    if user.status == ActiveStatusEnum.INACTIVE:
        return "inactive", None, None

    # 4. Check Forced Onboarding / Password Reset Flag
    if user.requires_password_change:
        reason = user.password_setup_reason or "password_change"
        return "requires_password_change", user, reason

    # 5. Update last active timestamp (Asia/Manila time)
    if not readonly:
        user.last_active = now_manila()
    return "success", user, None
```

#### Why Direct `bcrypt` Instead of `passlib`?
In `backend/app/core/security.py`:
```python
import bcrypt

def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
```
> [!NOTE]
> **Defense Trap:** Many older Python tutorials use `passlib.context.CryptContext`. In modern Python 3.12/3.13, `passlib` is abandoned and incompatible with `bcrypt >= 4.1`. We call the official C-extension `bcrypt` library directly, ensuring optimal cryptographic hashing speed and long-term security maintenance.

---

### Step 5: Token Issuance & Forensic Audit Trail

Back in `backend/app/api/v1/auth.py`:

```python
# backend/app/api/v1/auth.py (lines 114-147)
if status == "requires_password_change":
    login_limiter.record_success(body.username)
    # Issue a scoped, short-lived setup token (AUTH-01)
    return LoginResponse(
        status="requires_password_change", 
        reason=reason,
        setup_token=create_setup_token(user, "setup_password")
    )

# Authentication Success:
login_limiter.record_success(body.username) # Reset failure counter
token = create_user_token(user)

# Write forensic audit trail to PostgreSQL
db.add(ActivityLog(
    user_id=user.id,
    action="login",
    details=f"User {user.username} logged in",
    ip_address=get_client_ip(request),
))
await db.flush()

return LoginResponse(
    status="success",
    token=TokenResponse(access_token=token),
    user=AuthUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=getattr(user.role, "name", "Unknown") if user.role else "Unknown",
        avatar_url=user.avatar_url,
    ),
)
```

#### What is inside the JWT Access Token?
In `backend/app/core/security.py` and `auth_service.py`:
```python
def create_user_token(user: UserAccount, *, generation: str | None = None) -> str:
    return create_access_token(
        data={
            "sub": str(user.id),       # Subject UUID
            "username": user.username, # Username
            "role": user.role.name,    # "Admin" or "Operator"
            "tv": user.token_version,  # State version integer! (AUTH-02)
        }
    )
```
The token is signed with **HMAC-SHA256 (`HS256`)** using the server's private secret key.

---

### Step 6: Frontend Storage & Route Protection

1. **Storage in Browser:**  
   `AuthContext.tsx` receives the token and calls:
   ```ts
   localStorage.setItem("bananavision_token", token)
   localStorage.setItem("bananavision_user", JSON.stringify(authUser))
   setUser(authUser) // Updates React state
   ```
2. **Client-Side Routing Guard in [`frontend/src/App.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/App.tsx):**
   ```tsx
   function ProtectedRoute({ children, reqAdmin = false }: { children: React.ReactNode; reqAdmin?: boolean }) {
     const { user } = useAuth()
     if (!user) return <Navigate to="/" replace /> // Not logged in? Kick to Landing
     if (reqAdmin && user.role !== "Admin") return <Navigate to="/dashboard" replace /> // Not Admin? Kick to Dashboard
     return <>{children}</>
   }
   ```

---

### Step 7: How Protected API Calls Work (`deps.py`)

When the user is on the Dashboard and the frontend calls `api.dashboard.getSummary()`, `api.ts` attaches the header:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
FastAPI intercepts this via `CurrentUser = Annotated[UserAccount, Depends(get_current_user)]`:

```python
# backend/app/api/deps.py (lines 21-55)
async def _resolve_user(db: AsyncSession, token: str) -> UserAccount:
    # 1. Cryptographically decode and verify signature & expiration
    payload = decode_access_token(token)
    if not payload or "sub" not in payload or payload.get("scope", "access") != "access":
        raise CredentialsException("Invalid or expired token")

    user_id = uuid.UUID(payload["sub"])
    
    # 2. Fetch live user record from database
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user: raise CredentialsException("User not found")
    if user.status != ActiveStatusEnum.ACTIVE: raise ForbiddenException("Account is inactive")

    # 3. ── INSTANT SESSION REVOCATION CHECK (AUTH-02) ───────────────────
    token_version = payload.get("tv")
    if token_version is None or token_version != user.token_version:
        raise CredentialsException("Session has been revoked — please log in again")

    return user # Injected directly into the API endpoint function!
```

---

### Step 8: The Complete Logout Flow & Instant Token Revocation

When the user clicks **Log Out** in [`AppSidebarFooter.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/components/AppSidebarFooter.tsx):

```tsx
// frontend/src/components/AppSidebarFooter.tsx
const handleLogout = () => {
  logout()
  navigate("/")
}
```

Inside `AuthContext.tsx`:
```tsx
const logout = useCallback(() => {
  // 1. Notify backend asynchronously
  api.auth.logout().catch(() => {})
  // 2. Clear single-use setup tokens from memory
  passwordSetup.current = null
  pinSetup.current = null
  // 3. Clear browser storage
  clearAuth() // Removes bananavision_token & bananavision_user
  // 4. Reset React state to null (causes AppLayout to unmount)
  setUser(null)
}, [])
```

Inside `backend/app/api/v1/auth.py:340`:
```python
@router.post("/logout")
async def logout(user: CurrentUser, db: DbSession, request: Request):
    # Lock user row to prevent concurrent race conditions
    user = await lock_current_account(db, user)
    
    # ── THE MAGIC: Increment token_version in PostgreSQL ─────────────
    user.token_version += 1
    
    db.add(ActivityLog(
        user_id=user.id,
        action="logout",
        details=f"User {user.username} logged out",
        ip_address=get_client_ip(request),
    ))
    await db.flush()
    return {"message": "Logged out successfully"}
```

#### What happens if an attacker previously copied the JWT token?
1. The attacker sends a request with the copied token holding `"tv": 1`.
2. The request reaches `backend/app/api/deps.py`.
3. `deps.py` reads PostgreSQL and discovers `user.token_version` is now `2`.
4. Because `1 != 2`, the backend raises `HTTP 401 Session has been revoked`.
5. In `frontend/src/lib/api.ts`:
   ```ts
   if (res.status === 401 && !isCredentialSubmission) {
     clearAuth()
     window.location.href = "/login"
     throw new Error("Session expired")
   }
   ```
   The browser immediately purges any lingering session and kicks the client back to the login screen!

---

### Step 9: The Kiosk Operator PIN Swap Flow ([`PinModal.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/components/kiosk/PinModal.tsx) & `/auth/swap`)

In high-throughput packinghouse sorting, operators do not log out of the station. Instead, they tap their avatar in the Kiosk modal:

```
[ Active Operators Grid ] ──> [ Select Avatar ] ──> [ Enter 4-Digit PIN ]
                                                              │
                                                     POST /api/v1/auth/swap
                                                              │
                                                    [ pin_limiter check ]
                                                              │
                                                    [ verify_pin (bcrypt) ]
                                                              │
                                                    [ Enforce Role=Operator ]
                                                              │
                                                    [ Issue Operator JWT ]
```

1. **Frontend Call:** `switchOperator(username, pin)` sends `POST /api/v1/auth/swap`.
2. **Rate Limiting:** `pin_limiter` monitors attempts per username (5 fails $\rightarrow$ 300s lockout).
3. **Role Enforcement in `auth_service.py:126`:**
   ```python
   if (not user or not user.role or user.role.name != RoleEnum.OPERATOR.value
           or not user.operator_profile or not user.operator_profile.pin_hash
           or not verify_pin(pin, user.operator_profile.pin_hash)):
       return "failed", None, None
   ```
   **Crucial Rule:** An Administrator **cannot** log in with a PIN swap! If an attacker enters an Admin's username and tries PINs, it returns `failed` immediately. PIN authentication is strictly quarantined to accounts with an active `OperatorProfile`.

---

## 4. Security Vulnerability Fixes (Historical Review Roadmap)

During code audits, our team identified four potential vulnerabilities in authentication. Here is how our architecture solved each:

| Vulnerability ID | Historical Weakness Found | How Kent's Code Fixed It in BananaVision |
|---|---|---|
| **AUTH-01** | Unauthenticated password or PIN setup could be abused if an attacker knew a username. | Separated self-service changes (requiring the Current Password/PIN) from first-time setup (requiring a cryptographically signed, 10-minute expiring `setup_token` scoped strictly to `setup_password` or `setup_pin`). |
| **AUTH-02** | Stolen or copied JWTs remained valid until their 8-hour expiration, even after logout or password reset. | Implemented **Database Token Versioning (`token_version`)**. On logout, password reset, or deactivation, `user.token_version += 1`. Every request verifies `tv == user.token_version` in `deps.py`. Revocation is immediate. |
| **AUTH-03** | Live camera and WebSocket events could be sniffed without session authentication. | Connected media and WebSocket endpoints validate tokens via `get_media_user` in `deps.py` and verify `ActiveStatusEnum.ACTIVE`. |
| **AUTH-04** | A 4-digit PIN ($10^4$ combinations) could be brute-forced in minutes without rate limiting. | Implemented thread-safe in-memory sliding-window rate limiters (`login_limiter` and `pin_limiter`) locking accounts for 300 seconds (5 minutes) after 5 failed attempts, writing forensic IP audit entries. |

---

## 5. Defense Cheat Sheet: Panel Traps & Winning Answers

### Question 1: "Why does your system have no Sign-Up / Register page or Forgot-Password link?"
> **Kent's Winning Answer:**  
> "BananaVision is a closed, industrial edge appliance running offline on a Mini PC inside a packinghouse LAN. If public registration were open, any worker or device on the local network could create accounts and manipulate sorting classifications. Furthermore, the station has no outgoing internet or SMTP mail server to deliver password reset emails. Therefore, the Administrator is the sole gatekeeper: they provision accounts, assign roles, hand out temporary credentials in person, and the system forces workers to set their private password or PIN upon first login."

### Question 2: "If JWT is supposed to be stateless, why do you query PostgreSQL on every single request in `deps.py`?"
> **Kent's Winning Answer:**  
> "Pure stateless JWTs have a fatal security flaw: you cannot revoke a token if a worker leaves their shift, gets deactivated, or if a token is copied from browser storage. To solve this without running a heavy external cache like Redis on our Mini PC, we implemented **Token Versioning (`token_version`)**. On every request, `deps.py` performs a single, lightning-fast indexed primary key query on `UserAccount` and compares the token's embedded `tv` claim against the database. When a user logs out, we increment `token_version` by 1. That invalidates every existing token instantly with sub-millisecond database overhead."

### Question 3: "A 4-digit PIN is very weak—only 10,000 combinations. What prevents an attacker from brute-forcing it on the Kiosk?"
> **Kent's Winning Answer:**  
> "A 4-digit PIN is used solely for physical ergonomics so banana sorters wearing gloves can switch shifts rapidly. To make brute-forcing mathematically impossible, we built `pin_limiter` in `rate_limiter.py`. It tracks attempts in a 5-minute sliding window. On the 5th failed attempt, the account is locked for 300 seconds (5 minutes) with an `HTTP 429 Too Many Requests` status, and an `ActivityLog` entry is immediately committed to PostgreSQL recording the attacker's client IP address. At that rate, testing 10,000 combinations would take over 10 days."

### Question 4: "Why do you store JWTs in `localStorage` instead of `HttpOnly` cookies?"
> **Kent's Winning Answer:**  
> "BananaVision's frontend is a decoupled React Single-Page Application communicating across REST endpoints and high-frequency WebSocket streams. Bearer headers prevent cross-site request forgery (CSRF) vulnerabilities by default. Additionally, our camera preview streams require authentication; standard HTML `<img>` elements cannot send HTTP headers, so `get_media_user` accepts the revocable session token via query parameters. We mitigate `localStorage` XSS risk by enforcing strict token lifetimes, zero unvetted client scripts, and instant `token_version` revocation on logout."

### Question 5: "What happens when an Administrator resets a user's password in the admin panel?"
> **Kent's Winning Answer:**  
> "In `users.py:reset_user_password`, the backend sets `user.requires_password_change = True`, sets `user.password_setup_reason = 'password_reset'`, generates a temporary password, and **increments `user.token_version += 1`**. This immediately terminates any active sessions the user has open anywhere. When the user logs in with the temporary password, the system intercepts the `requires_password_change` flag and issues a 10-minute cryptographic `setup_token`. They cannot access any dashboard or scan endpoints until they submit a brand new private password."
