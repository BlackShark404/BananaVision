# 👤 Master Guide: Profile Management, Self-Service & Lifetime Analytics

> **Presenter & Author:** Kent RG A. Baguio  
> **Core Focus:** Self-Service Avatar Customization (`PROFILE-01`), Old Credential Verification (`PROFILE-02`), Database-Level Lifetime SQL Aggregations (`PROFILE-03`), and Identity Tamper Resistance.  
> **Backend Files:**
> - [`backend/app/api/v1/users.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/users.py) — Endpoints for `/me/profile` and `/me/summary`
> - [`backend/app/api/v1/auth.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/auth.py) — Self-service `/change-password` and `/change-pin`
> - [`backend/app/services/auth_service.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/auth_service.py) — Current credential bcrypt validation
>
> **Frontend Files:**
> - [`frontend/src/pages/Profile.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Profile.tsx) — User profile page, avatar uploader, credential dialogs, analytics cards
> - [`frontend/src/context/AuthContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AuthContext.tsx) — Session credential updating and user state synchronization

---

## 1. Why Did We Implement This System? (Panel Defense Rationale)

### 1.1 The Operational Purpose: Personal Hub & Visual Station Identification
In a busy warehouse packinghouse:
1. **Visual Recognition on Touchscreen:** When multiple operators share a kiosk station across shifts, recognizing fellow workers by avatar photos on the Kiosk selection modal (`/auth/operators`) is far faster than reading small text usernames.
2. **Autonomous Security Maintenance:** Workers must be empowered to update their personal password or kiosk PIN when their shift changes or if they suspect someone glimpsed their PIN over their shoulder, without bothering the plant administrator.
3. **Worker Productivity & Activity Visibility:** Operators and administrators get personal visibility into their activity (`Your Actions (7d)` and `Recent Activity`), while Operators also see their own scan throughput (`Total Scans` and `Last 7 Days`)—keeping AI confidence metrics where they belong in Scan Logs and Analytics.

### 1.2 Identity Immutability: Why Workers Cannot Edit Username or Role
In standard consumer apps, users can freely change their name, email, or handle. In BananaVision:
- **Username and Full Name are strictly Admin-controlled:** If an operator could change their username from "Juan Dela Cruz" to "Admin Kent", they could obscure audit trails, spoof intake records, or impersonate other workers in activity logs.
- **The Solution — Scoped Endpoint (`PATCH /users/me/profile`):** The self-service update schema (`SelfProfileUpdate`) allows modification of **only one attribute**: `avatar_url`. All identity fields (role, username, full name, status) are excluded from the request model and cannot be altered by non-administrators.

### 1.3 True SQL Aggregation vs Client-Side Averaging (PROFILE-03)
A common amateur flaw in dashboard design is calculating statistics by averaging whatever 10 or 20 records happen to be rendered on the current screen.
- In BananaVision, `/users/me/summary` executes true **SQL database aggregation** directly inside PostgreSQL using `func.count()`, `func.avg()`, and date-windowed `func.sum()`.
- Whether a worker has processed 5 scans or 50,000 scans over 6 months, the metrics are mathematically exact and computed in milliseconds via database indexing.

---

## 2. High-Level Architecture & End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as Operator / Admin
    participant UI as Profile.tsx
    participant ApiClient as lib/api.ts
    participant Router as users.py & auth.py
    participant Service as auth_service.py
    participant DB as PostgreSQL (UserAccount & Scans)

    %% LIFETIME ANALYTICS FETCH
    User->>UI: Navigate to /profile
    UI->>ApiClient: api.users.getOwnSummary()
    ApiClient->>Router: GET /api/v1/users/me/summary (Bearer <token>)
    Router->>Router: Extract user.id from JWT (CurrentUser)
    Router->>DB: Execute SQL Aggregations (COUNT scans, AVG confidence, SUM last 7 days)
    DB-->>Router: Aggregate Row: { total_scans, avg_conf, last_7_days }
    Router->>DB: SELECT ActivityLog WHERE user_id = :user_id LIMIT 8
    DB-->>Router: Recent audit events
    Router-->>ApiClient: HTTP 200 Summary JSON
    ApiClient-->>UI: Render Analytics Cards & Recent Activity Timeline

    %% AVATAR UPLOAD
    User->>UI: Upload new avatar image (Client file picker)
    UI->>UI: Check file size <= 2 MB & convert to Base64 data URL
    UI->>ApiClient: api.users.updateOwnProfile({ avatar_url: base64 })
    ApiClient->>Router: PATCH /api/v1/users/me/profile
    Router->>DB: UPDATE user_accounts SET avatar_url = :base64 WHERE id = :jwt_user_id
    DB-->>Router: Commit update
    Router-->>ApiClient: HTTP 200 Updated UserResponse
    ApiClient-->>UI: Update AuthContext state; avatar reflects immediately across UI

    %% SELF-SERVICE PASSWORD CHANGE
    User->>UI: Enter Current Password + New Password
    UI->>ApiClient: api.auth.changePassword(current_pw, new_pw)
    ApiClient->>Router: POST /api/v1/auth/change-password
    Router->>Service: change_password(db, user, current_pw, new_pw)
    Service->>Service: verify_password(current_pw, user.password_hash) (bcrypt check)
    alt Current Password Incorrect
        Service-->>Router: Raise HTTP 403 Forbidden "Incorrect current password"
        Router-->>UI: Error Toast: Verification failed!
    else Current Password Valid
        Service->>DB: UPDATE user_accounts SET password_hash = hash(new_pw), token_version += 1
        Service-->>Router: Return updated user
        Router->>Router: Issue new JWT with bumped tv
        Router-->>UI: HTTP 200 { status: "success", token, user }
        UI->>User: Toast "Password updated successfully"
    end
```

---

## 3. Step-by-Step Code Walkthrough: Front to Back to Front

### Step 1: Self-Service Avatar Customization in [`frontend/src/pages/Profile.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Profile.tsx)

When an operator selects a photo to upload:

```tsx
// frontend/src/pages/Profile.tsx (lines 142-178)
const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0]
  if (!file) return

  // 1. Client-Side Size Guard: Maximum 2 MB
  if (file.size > 2 * 1024 * 1024) {
    toast.error("File too large", { description: "Avatar image must be under 2 MB." })
    return
  }

  // 2. Read file as Base64 Data URL
  const reader = new FileReader()
  reader.onload = async () => {
    const base64 = reader.result as string
    try {
      setSavingAvatar(true)
      // 3. Send to backend self-service endpoint
      const updated = await api.users.updateOwnProfile({ avatar_url: base64 })
      
      // 4. Synchronize global AuthContext so sidebar and header update instantly
      updateAuthUser({ avatar: updated.avatar_url })
      toast.success("Avatar updated successfully")
    } catch {
      toast.error("Failed to update avatar")
    } finally {
      setSavingAvatar(false)
    }
  }
  reader.readAsDataURL(file)
}
```

---

### Step 2: Backend Scoped Route in [`backend/app/api/v1/users.py:146`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/users.py)

FastAPI receives `PATCH /api/v1/users/me/profile`:

```python
# backend/app/api/v1/users.py (lines 113-166)
class SelfProfileUpdate(BaseModel):
    # Only avatar_url is allowed! No username, role, or status can be touched here.
    avatar_url: str | None = None

@router.patch("/me/profile", response_model=UserResponse)
async def update_own_profile(
    body: SelfProfileUpdate, 
    db: DbSession, 
    user: CurrentUser                 # PROFILE-01 Fix: Any authenticated user!
):
    """Self-service profile update — scoped strictly to avatar_url."""
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id) # user.id comes from verified JWT payload!
    )
    account = result.scalar_one_or_none()
    if not account:
        raise NotFoundException("User")

    if body.avatar_url is not None:
        account.avatar_url = body.avatar_url

    await db.flush()
    return UserResponse.from_db_model(account)
```

- **Security Verification (PROFILE-01):** Previously, the frontend tried calling `PATCH /users/{id}`, which failed with `HTTP 403 Forbidden` because operators cannot access administrative update routes. By establishing `/users/me/profile`, workers can update their photo safely without privilege escalation.

---

### Step 3: Database Lifetime Aggregates in [`backend/app/api/v1/users.py:144`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/users.py)

When `/profile` mounts, it calls `GET /api/v1/users/me/summary`:

```python
# backend/app/api/v1/users.py (lines 144-177)
@router.get("/me/summary")
async def own_profile_summary(db: DbSession, user: CurrentUser):
    now = now_manila()
    
    # Construct SQL aggregation query across scans and classifications
    query = select(
        func.count(Scan.id).label("total_scans"),
        func.avg(ScanClassification.confidence).label("avg_confidence"),
        func.sum(
            case((Scan.date_time.between(now - timedelta(days=7), now), 1), else_=0)
        ).label("last_7_days"),
    ).select_from(Scan).outerjoin(
        ScanClassification, ScanClassification.scan_id == Scan.id
    )

    is_admin = user.role.name == RoleEnum.ADMIN.value
    # Role-Based Scoping: Operators only see their own scans; Admins see system totals
    if not is_admin:
        query = query.join(
            OperatorProfile, Scan.operator_id == OperatorProfile.id
        ).where(OperatorProfile.account_id == user.id)

    row = (await db.execute(query)).one()
    recent_actions_7d = await db.scalar(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user.id,
            ActivityLog.timestamp.between(now - timedelta(days=7), now),
        )
    )

    # Retrieve last 8 activity events belonging strictly to this user
    logs = (await db.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
        .limit(8)
    )).scalars().all()

    return {
        "total_scans": row.total_scans,
        "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
        "last_7_days": row.last_7_days or 0,
        "recent_actions_7d": recent_actions_7d or 0,
        "total_users": (await db.scalar(select(func.count(UserAccount.id)))) if is_admin else None,
        "activity": [
            {"id": str(log.id), "action": log.action, "details": log.details or "", "timestamp": log.timestamp.isoformat()}
            for log in logs
        ],
    }
```

- **Role-Aware Profile Cards (`Profile.tsx:223-267`):** Admins see **System Scans**, **Total Users**, and **Your Actions (7d)**; Operators see **Total Scans**, **Last 7 Days** (*Your scans in the last 7 days*), and **Your Actions (7d)**. Model confidence metrics are intentionally reserved for Scan Logs, Dashboard, and Analytics rather than a personal profile page.
- **Panel Defense Value (PROFILE-03):** You can explain: *"Notice `users.py:148-167`. We don't query raw scan rows into memory and loop over them. PostgreSQL evaluates `func.count()`, `func.avg()`, and conditional `func.sum()` in database engine memory. This keeps network payload tiny (< 1 KB) regardless of scan history size."*

---

### Step 4: Old Credential Verification (`PROFILE-02`) in [`auth_service.py:142`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/auth_service.py)

When an operator changes their password or PIN from the Profile page:

```python
# backend/app/services/auth_service.py (lines 142-161)
async def change_password(
    db: AsyncSession, user: UserAccount, current_password: str, new_password: str
) -> UserAccount:
    # 1. Lock user row to serialize concurrent changes
    user = await lock_current_account(db, user)

    # 2. PROFILE-02: Cryptographically verify current password before updating!
    if not verify_password(current_password, user.password_hash):
        raise CredentialsException("Current password is incorrect")

    # 3. Hash new password with bcrypt
    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    
    # 4. Revoke prior sessions (AUTH-02)
    user.token_version += 1
    user.last_active = now_manila()
    return user
```
And for PIN changes:
```python
# backend/app/services/auth_service.py (lines 191-215)
async def change_pin(
    db: AsyncSession, user: UserAccount, current_pin: str, new_pin: str
) -> UserAccount:
    user = await lock_current_account(db, user)
    if user.role.name != RoleEnum.OPERATOR.value:
        raise ForbiddenException("PIN credentials are only available to operators")
    if not user.operator_profile or not user.operator_profile.pin_hash:
        raise NotFoundException("Operator Profile")

    # Cryptographically verify current PIN before updating
    if not verify_pin(current_pin, user.operator_profile.pin_hash):
        raise CredentialsException("Current PIN is incorrect")

    user.operator_profile.pin_hash = hash_pin(new_pin)
    user.operator_profile.requires_pin_change = False
    user.token_version += 1
    return user
```

---

## 4. Security Vulnerabilities Fixed in This Module

| Vulnerability ID | Historical Flaw Identified | How Kent's Code Fixed It |
|---|---|---|
| **PROFILE-01** | Non-admin operators trying to update their avatar called admin-only `PATCH /users/{id}`, which failed on the backend. | Created dedicated self-service endpoint `PATCH /users/me/profile` accepting `CurrentUser` and scoped strictly to `avatar_url`. |
| **PROFILE-02** | The Profile password change modal accepted a "Current Password" input field, but never validated it against the stored hash on the server. | Enforced in `auth_service.py`: `verify_password(current_pw, user.password_hash)` must pass or transaction raises `CredentialsException`. |
| **PROFILE-03** | Operator lifetime statistics were calculated by averaging whatever 20 scans were currently visible in the UI table. | Built backend SQL aggregation endpoint `/users/me/summary` executing `func.count()`, `func.avg()`, and `func.sum()` across the entire PostgreSQL database. |

---

## 5. Defense Cheat Sheet: Panel Traps & Winning Answers

### Question 1: "Why can't an Operator change their own username or full name in Profile?"
> **Kent's Winning Answer:**  
> "In an industrial packinghouse with strict traceability standards, identity records are non-repudiable. If workers could alter their own username or full name, they could disguise their identity, tamper with historical activity logs, or impersonate colleagues during banana intake. We intentionally locked all identity attributes to the Administrator in `UserManagement.tsx`. Operators can only customize their avatar and change their private password or PIN after verifying their current one."

### Question 2: "Storing 2 MB Base64 avatar images directly in PostgreSQL can bloat the database. Why didn't you upload them to Amazon S3 or a local disk folder?"
> **Kent's Winning Answer:**  
> "BananaVision is designed as an offline edge appliance running on a standalone Mini PC with zero cloud dependencies, which rules out Amazon S3. For our prototype, storing Base64 data URLs in PostgreSQL kept the database self-contained and simplified backups into a single database dump. However, for a high-scale production deployment, the natural next step is saving avatar files to a local media directory on the Mini PC SSD and storing only the relative path string in PostgreSQL."

### Question 3: "If someone leaves their browser open on the Profile page, what stops another worker from changing their password?"
> **Kent's Winning Answer:**  
> "We resolved that with our **PROFILE-02 Old Credential Verification** safeguard. In `backend/app/services/auth_service.py:151`, the `change_password` and `change_pin` endpoints strictly require the user to submit their `current_password` or `current_pin`. The server verifies that credential against the stored bcrypt hash before accepting any new password. An unauthorized person at an unattended screen cannot modify the credentials without knowing the existing secret."
