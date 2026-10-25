# 👤 Deep Dive: Profile Management, Self-Service & Lifetime Analytics

> **Feature 7:** Profile Management  
> **Backend Files:** [`backend/app/api/v1/users.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/users.py), [`backend/app/api/v1/auth.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/auth.py)  
> **Frontend Files:** [`frontend/src/pages/Profile.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Profile.tsx), [`frontend/src/context/AuthContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AuthContext.tsx)

---

## 1. Why Did We Implement This System?

Operators and administrators need a personal hub where they can:
1. Customize their profile avatar for easy visual identification on the kiosk screen.
2. Change their personal password or kiosk PIN securely without needing an administrator's assistance.
3. Review their own historical scanning performance metrics (e.g. Total Scans conducted, Average AI Confidence score, and Weekly throughput).

---

## 2. Security & Architecture Vulnerabilities Fixed

| Vulnerability ID | Historical Flaw | How Kent's Code Fixed It |
|---|---|---|
| **PROFILE-01** | Operators trying to update their avatar called `PATCH /users/{id}`, which was an Admin-only route. It failed on the server and fell back to temporary React state. | Created dedicated self-service endpoint: `PATCH /users/me/profile` accessible to **any authenticated user** (`CurrentUser`) scoped strictly to updating `avatar_url`. |
| **PROFILE-02** | The Profile password change modal accepted a "Current Password" input but never sent or verified it with the backend. | Updated `change_password` service in `auth.py` and `auth_service.py` to require and verify the current password via bcrypt before updating the password hash. |
| **PROFILE-03** | Operator lifetime statistics were calculated by averaging whatever 20 scans were currently loaded in the frontend table. | Implemented backend SQL aggregation (`/users/me/summary`) that queries all historical records in PostgreSQL using `func.count()`, `func.avg()`, and date ranges. |

---

## 3. Code Breakdown: Part-by-Part

### Part A: Self-Service Profile Update (`backend/app/api/v1/users.py:146`)

```python
class SelfProfileUpdate(BaseModel):
    avatar_url: str | None = None

@router.patch("/me/profile", response_model=UserResponse)
async def update_own_profile(body: SelfProfileUpdate, db: DbSession, user: CurrentUser):
    """
    Self-service profile update — any authenticated user can update their own
    avatar without needing admin privileges. (PROFILE-01 fix)
    """
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise NotFoundException("User")

    if body.avatar_url is not None:
        account.avatar_url = body.avatar_url

    await db.flush()
    return UserResponse.from_db_model(account)
```
- **Security Check:** The endpoint uses `user.id` extracted directly from the verified JWT. An operator cannot supply another user's ID or modify their own role, username, or active status through this route.

---

### Part B: True Database Lifetime Aggregates (`users.py:117`)

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
    # Operators are filtered strictly to scans linked to their OperatorProfile
    if not is_admin:
        query = query.join(OperatorProfile, Scan.operator_id == OperatorProfile.id).where(
            OperatorProfile.account_id == user.id
        )
    row = (await db.execute(query)).one()

    # Fetch last 8 activity events belonging to this user
    logs = (await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()).limit(8)
    )).scalars().all()

    return {
        "total_scans": row.total_scans,
        "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
        "last_7_days": row.last_7_days or 0,
        "total_users": (await db.scalar(select(func.count(UserAccount.id)))) if is_admin else None,
        "activity": [{"id": str(log.id), "action": log.action, "details": log.details or "",
                      "timestamp": log.timestamp.isoformat()} for log in logs],
    }
```
- **Why this matters for your defense:** If the panel asks: *"How do you calculate lifetime scan metrics?"* You can explain that metrics are **not** computed client-side; they are computed via SQL aggregation functions on PostgreSQL, ensuring 100% mathematical accuracy across all scans.

---

### Part C: Verified Password & PIN Self-Service Change (`backend/app/api/v1/auth.py:213`)

```python
@router.post("/change-password", response_model=LoginResponse)
async def change_password_route(
    body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request
):
    """Requires authentication (JWT) and current password verification."""
    user = await change_password(db, user, body.current_password, body.new_password)
    token = create_user_token(user)

    db.add(ActivityLog(
        user_id=user.id,
        action="user_updated",
        details=f"User {user.username} changed password",
        ip_address=get_client_ip(request),
    ))
    await db.flush()
    return LoginResponse(...)
```
In `auth_service.py`:
```python
async def change_password(db: AsyncSession, user: UserAccount, current_pw: str, new_pw: str):
    # Verify current password matches existing hash!
    if not verify_password(current_pw, user.password_hash):
        raise ForbiddenException("Incorrect current password")
    user.password_hash = hash_password(new_pw)
    user.requires_password_change = False
    return user
```
- A rogue party sitting at an unlocked terminal cannot change the password without knowing the current password!

---

## 4. Frontend Profile Experience (`frontend/src/pages/Profile.tsx`)

In `Profile.tsx`:
1. **Avatar Customization:** Users can select curated banana-themed avatars or upload their own image URL, instantly saving to the database.
2. **Credential Modals:** Separate dialogs for "Change Password" and "Change PIN" with client-side validation (minimum 6 characters for password, exactly 4 digits for PIN).
3. **Responsive Stats Cards:** Displays "Total Scans Handled", "Average Model Confidence", and "Throughput (Last 7 Days)".
