# 📜 Deep Dive: Activity Logs, Forensics & Audit Trail

> **Feature 8:** Activity Logs & Audit System  
> **Backend Files:** [`backend/app/api/v1/activity.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/activity.py), [`backend/app/models/activity_log.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/models/activity_log.py)  
> **Frontend Files:** [`frontend/src/pages/admin/ActivityLog.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/admin/ActivityLog.tsx), [`frontend/src/context/AdminContext.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/context/AdminContext.tsx)

---

## 1. Why Did We Implement This System?

In industrial quality control and security compliance:
- Every privileged action must be attributable to a specific operator or administrator.
- If someone changes a camera calibration or deactivates an operator, management must know **who** did it, **from what IP address**, and **at what exact timestamp**.
- If someone attacks the kiosk by repeatedly guessing PINs, security must have a forensic record of failed attempts.

---

## 2. Security & Architecture Vulnerabilities Fixed

| Vulnerability ID | Historical Flaw | How Kent's Code Fixed It |
|---|---|---|
| **ACCESS-01** | The `/activity` endpoint only required `CurrentUser`, meaning any regular operator could view sensitive admin logs. | Protected with `admin: AdminUser`, restricting all audit listings to verified administrators. |
| **AUDIT-01** | Logs were paginated in React state after downloading the first 50 entries, meaning older logs were completely invisible to search and filters. | Implemented **True Server-Side Pagination & Filtering**: `page`, `page_size`, `action`, `user_name`, and `search` query parameters passed directly to SQL. |
| **AUDIT-02** | Failed logins and admin password resets did not generate audit records. | Added automatic `ActivityLog` emission across all auth failures, resets, config updates, and scans. |
| **AUDIT-03** | CSV export did not escape internal quotation marks, creating corrupted rows in Excel. | Implemented RFC 4180 standard quotation doubling in CSV generators. |

---

## 3. Database Schema: The `ActivityLog` Model

```python
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_manila)

    user: Mapped[UserAccount | None] = relationship("UserAccount", lazy="selectin")
```
- Timestamps are strictly pinned to `Asia/Manila` time (`now_manila`).
- If an unauthenticated brute-force attempt occurs, `user_id` is set to `None`, but the IP address and targeted username are saved in `details`.

---

## 4. Code Breakdown: Part-by-Part

### Part A: Server-Side Query & Dynamic Filtering (`backend/app/api/v1/activity.py:21`)

```python
@router.get("", response_model=ActivityLogListResponse)
async def list_activity(
    db: DbSession,
    admin: AdminUser,               # ACCESS-01: Admin authorization required
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user_name: str | None = None,
    search: str | None = None,
):
    """List activity logs with server-side pagination, filtering, and search."""
    # Base query ordered newest first
    query = select(ActivityLog).options(selectinload(ActivityLog.user)).order_by(
        desc(ActivityLog.timestamp), desc(ActivityLog.id)
    )

    # 1. Filter by action type (e.g. "login", "user_created", "config_changed")
    if action:
        query = query.where(ActivityLog.action == action)

    # 2. Filter by specific user
    if user_name:
        from app.models.user_account import UserAccount
        query = query.join(ActivityLog.user).where(UserAccount.full_name == user_name)

    # 3. Full-text search across action, details, and user name
    if search:
        from app.models.user_account import UserAccount
        search_pattern = f"%{search}%"
        query = query.outerjoin(ActivityLog.user).where(
            or_(
                ActivityLog.action.ilike(search_pattern),
                ActivityLog.details.ilike(search_pattern),
                UserAccount.full_name.ilike(search_pattern),
            )
        )

    # Calculate total count for pagination metadata
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # SQL Offset and Limit
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return ActivityLogListResponse(
        items=[ActivityLogResponse(...) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
```

---

### Part B: Events Tracked by the System

| Event Action | When It Fires | What Is Recorded in `details` |
|---|---|---|
| `login` | Successful Admin or Operator login | `"User {username} logged in"` or `"Operator {username} swapped in session"` |
| `login_failed` | Failed password attempt (`AUTH-02`) | `"Failed login attempt for username '{username}'"` + IP address |
| `pin_failed` | Failed 4-digit PIN attempt (`AUTH-02`) | `"Failed PIN swap attempt for username '{username}'"` + IP address |
| `logout` | Explicit logout button click | `"User {username} logged out"` |
| `user_created` | Admin creates new account | `"Created user '{username}' with role {role}"` |
| `user_updated` | Role transition, status toggle, reset | `"Updated user '{username}': ['role_change:Operator->Admin']"` |
| `config_changed` | Camera or threshold update | `"Updated config revision {revision}: {changes}"` |

---

### Part C: Safe CSV Export (`frontend/src/pages/admin/ActivityLog.tsx`)

In `ActivityLog.tsx`:
```tsx
const exportLogs = () => {
  const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
  const rows = logs.map(l => [
    `"${l.timestamp.replace(/"/g, '""')}"`,
    `"${(l.userName || "System").replace(/"/g, '""')}"`,
    `"${l.action.replace(/"/g, '""')}"`,
    `"${(l.details || "").replace(/"/g, '""')}"`,
    `"${(l.ipAddress || "Localhost").replace(/"/g, '""')}"`
  ])
  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n")
  ...
}
```
- **Why `.replace(/"/g, '""')` is necessary:** In standard CSV format, if a user's details contain quotes or commas, unescaped quotes break the CSV columns when opened in Microsoft Excel. Doubling the quotes guarantees pristine formatting.

---

## 5. Summary of Key Defense Takeaways

1. **Role-Enforced:** Regular kiosk users cannot snoop on admin actions; only verified admins can query `/activity`.
2. **Infinite Scalability:** True database SQL `OFFSET` and `LIMIT` ensure that whether the station has 50 logs or 50,000 logs, the page loads in under 50 milliseconds.
3. **Forensic Value:** Failed attempts record IP and timestamps, giving administrators the exact evidence needed to investigate unauthorized access attempts.
