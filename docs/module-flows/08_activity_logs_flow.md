# `08_activity_logs_flow.md` — Module 8: Activity Logs (Audit Trail, Snapshot Paging, Filtering & CSV/XLSX Export) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 8 (Activity Logs) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Route & Admin Guard:** Maps `/admin/activity` to `<ProtectedRoute reqAdmin><ActivityLog /></ProtectedRoute>`. |
| `frontend/src/pages/admin/ActivityLog.tsx` | **Activity Log Table, KPI Cards, Filters & Export UI:** Renders 3 KPI cards (`Last 24 Hours`, `Active Users`, `Critical Actions`), `AppTableFilters` (`search`, `actionFilter`, `userFilter`), `ExportDropdown` (`handleExportCsv` & `handleExportXlsx`), and `AppDataTable` (`PAGE_SIZE = 15`). |
| `frontend/src/lib/activityActions.ts` | **Audit Action Vocabulary & Color Palette:** Maps all 63 `AuditAction` enum strings to human-readable labels (`activityLabel`), Tailwind color badges (`activityBadgeClass`), criticality flags (`isCriticalActivity`), and actorless fallbacks (`actorlessName` → `"Unauthenticated"` or `"System"`). |
| `frontend/src/context/AdminContext.tsx` | **Snapshot-Pinned Multi-Page Loader:** Uses `collectScanPages` to fetch all pages of `api.activity.list({ page, page_size, as_of })` pinned to Page 1's `as_of` timestamp boundary, and maps rows via `mapApiActivityLog`. |
| `frontend/src/lib/scanData.ts` | **Multi-Page Snapshot Collector (`collectScanPages`):** Loops `page = 1..N` (`pageSize = 100`), verifying `response.snapshot_id === snapshotId` (`as_of`) and `records.size === response.total` before publishing the complete history. |
| `frontend/src/lib/exportUtils.ts` | **Client-Side RFC 4180 CSV & OpenXML XLSX Exporter:** Exports the currently filtered/sorted activity rows (`sortedLogsRef.current`) to UTF-8 BOM `.csv` (`downloadCsv` with formula-injection protection) or auto-sized `.xlsx` (`downloadXlsx`). |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `GET /api/v1/activity` with query parameters `{ page, page_size, action, as_of }`. |
| `backend/app/api/v1/activity.py` | **Activity Log Controller (`GET /api/v1/activity`):** Pins pagination to `boundary = as_of or max(now_manila(), max(ActivityLog.timestamp))`, filters by `action`, `user_name`, and `search`, orders by `desc(ActivityLog.timestamp), desc(ActivityLog.id)`, and returns `ActivityLogListResponse`. |
| `backend/app/services/audit.py` | **Single Audit Log Writer (`record`, `emit`, `attach`):** Enforces text hygiene (`clean`, `MAX_DETAILS = 2000`), sensitive field redaction (`SENSITIVE_FIELDS`), anonymous rate capping (`120/min`), 403 throttling (`ACCESS_DENIED_WINDOW = 600s`), and maintenance deferral (`_deferred`). |
| `backend/app/schemas/common.py` | **Pydantic Response Contracts:** Defines `ActivityLogResponse` and `ActivityLogListResponse` (`items`, `total`, `page`, `page_size`, `as_of`). |
| `backend/app/models/activity_log.py` | **SQLAlchemy ORM Model (`activity_log`):** Defines `id`, `timestamp` (`ManilaDateTime`), `user_id` (`ondelete="SET NULL"`), `action`, `details`, `ip_address`, and `actor_name` (snapshot of the user's name so deleted accounts still display their name). |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Snapshot-Pinned Multi-Page Loading (`AdminContext.tsx` & `scanData.ts`)

#### Step A1: Fetching All Activity Log Pages with `as_of` Snapshot Pinning
* **Step Title & Trigger:** When an Admin logs in or navigates to `/admin/activity`, `AdminProvider` invokes `collectScanPages` with `api.activity.list({ page, page_size, as_of })`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 70–77 & 197–215) and `frontend/src/lib/scanData.ts` (Lines 142–169)
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 70–77 & 197–215):**
```tsx
const mapApiActivityLog = (a: ApiActivity): ActivityLog => ({
  id: a.id,
  timestamp: storedTimestamp(a.created_at),
  user: a.user_name ?? actorlessName(a.action),
  action: a.action,
  details: a.details ?? "",
  ipAddress: a.ip_address ?? undefined,
})
```
```tsx
        (async () => {
          try {
            const result = user.role === "Admin"
              // Page 1's as_of pins later pages (checked like a scan snapshot id), so rows
              // written while the log loads cannot shift or duplicate them.
              ? await collectScanPages(async (page, page_size, signal, as_of) => {
                const response = await api.activity.list({ page, page_size, as_of }, signal)
                return { ...response, snapshot_id: response.as_of }
              }, controller.signal)
              : []
            if (controller.signal.aborted) return
            setActivityLogs(result.map(mapApiActivityLog))
            setActivityReady(true)
          } catch {
            if (!controller.signal.aborted) setActivityError("Activity history could not be loaded completely. Please reload to retry.")
          } finally {
            if (!controller.signal.aborted) setActivityLoading(false)
          }
        })(),
```
* **Complete Uncut Code Block (`frontend/src/lib/scanData.ts`, Lines 142–169):**
```ts
export interface RecordPage<T> { items: T[]; total: number; page: number; page_size: number; snapshot_id?: string }

/** Publish a complete history only after every page succeeds. */
export async function collectScanPages<T extends { id: string }>(
  fetchPage: (page: number, pageSize: number, signal?: AbortSignal, snapshotId?: string) => Promise<RecordPage<T>>,
  signal?: AbortSignal,
): Promise<T[]> {
  const records = new Map<string, T>()
  const pageSize = 100
  let snapshotId: string | undefined
  for (let page = 1; ; page++) {
    signal?.throwIfAborted()
    const response = await fetchPage(page, pageSize, signal, snapshotId)
    signal?.throwIfAborted()
    if (snapshotId && response.snapshot_id !== snapshotId) throw new Error("Scan snapshot changed. Please retry.")
    snapshotId = response.snapshot_id
    if (!Array.isArray(response.items) || response.page !== page || !Number.isInteger(response.page_size) || response.page_size < 1 || response.items.length > response.page_size || !Number.isInteger(response.total) || response.total < 0) {
      throw new Error("The server returned an invalid scan history page.")
    }
    const previousSize = records.size
    response.items.forEach(record => records.set(record.id, record))
    if (page * response.page_size >= response.total) {
      if (records.size !== response.total) throw new Error("Scan history changed or is incomplete. Please retry.")
      return [...records.values()]
    }
    if (response.items.length === 0 || previousSize === records.size) throw new Error("Scan history is incomplete. Please retry.")
  }
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Why `as_of` Snapshot Pinning Matters (`AdminContext.tsx` Lines 200–205):** If new audit rows are inserted while Page 2 is being fetched, standard `OFFSET/LIMIT` paging would shift rows down and cause duplicates or skipped rows across pages. Page 1 returns an `as_of` timestamp boundary from FastAPI; `collectScanPages` passes that exact `as_of` timestamp back on Page 2, Page 3, etc., guaranteeing a consistent point-in-time snapshot.
  * **Actorless Fallback (`AdminContext.tsx` Line 73):** When `a.user_name` is `null` (e.g., failed login with unknown username or system startup event), `actorlessName(a.action)` returns `"Unauthenticated"` for `"security"` category events and `"System"` for all other events.

---

### Phase C & D: Backend Activity Controller & Single Audit Writer Architecture

#### Step C1: `GET /api/v1/activity` Controller (`backend/app/api/v1/activity.py`)
* **Step Title & Trigger:** FastAPI handles `GET /api/v1/activity` with `AdminUser` authorization.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/activity.py` (Lines 1–106) and `backend/app/schemas/common.py` (Lines 199–215)
* **Complete Uncut Code Block (`backend/app/api/v1/activity.py`, Lines 1–106):**
```python
"""
Activity log routes.

AUDIT-01: True server-side pagination, filtering by action/user/search query.
Paging is pinned to an ``as_of`` boundary so rows written while an administrator pages
through the log cannot shift later pages.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.core.time import now_manila
from app.models.activity_log import ActivityLog
from app.schemas.common import ActivityLogListResponse, ActivityLogResponse
from app.schemas.timestamps import InputTimestamp

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=ActivityLogListResponse)
async def list_activity(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user_name: str | None = None,
    search: str | None = None,
    as_of: InputTimestamp | None = None,
):
    """List activity logs with server-side pagination, filtering, and search.

    Count and page only include rows at or before ``as_of``; the response returns the
    boundary used so later pages can pass it back. Without ``as_of`` the boundary is the
    later of now and the newest row, so rows stamped ahead of this clock (a restored backup
    from a station whose clock ran ahead, or a clock stepped back) are never hidden.
    """
    boundary = as_of
    if boundary is None:
        boundary = now_manila()
        newest = await db.scalar(select(func.max(ActivityLog.timestamp)))
        if newest is not None and newest > boundary:
            boundary = newest
    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.user))
        .where(ActivityLog.timestamp <= boundary)
        .order_by(desc(ActivityLog.timestamp), desc(ActivityLog.id))
    )

    # Filter by action type
    if action:
        query = query.where(ActivityLog.action == action)

    # Filter by user name (actor snapshot or user table)
    if user_name:
        from app.models.user_account import UserAccount
        query = query.outerjoin(ActivityLog.user).where(
            or_(
                ActivityLog.actor_name == user_name,
                UserAccount.full_name == user_name,
            )
        )

    # Full-text search across user name, action, and details
    if search:
        from app.models.user_account import UserAccount
        search_pattern = f"%{search}%"
        # Need left outer join since user might be null
        query = query.outerjoin(ActivityLog.user).where(
            or_(
                ActivityLog.action.ilike(search_pattern),
                ActivityLog.details.ilike(search_pattern),
                ActivityLog.actor_name.ilike(search_pattern),
                UserAccount.full_name.ilike(search_pattern),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return ActivityLogListResponse(
        items=[
            ActivityLogResponse(
                id=log.id,
                user_name=log.actor_name or (log.user.full_name if log.user else None),
                action=log.action,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.timestamp,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        as_of=boundary,
    )
```
* **Complete Uncut Code Block (`backend/app/schemas/common.py`, Lines 199–215):**
```python
class ActivityLogResponse(BaseModel):
    id: uuid.UUID
    user_name: str | None = None
    action: str
    details: str | None = None
    ip_address: str | None = None
    created_at: Timestamp


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogResponse]
    total: int
    page: int
    page_size: int
    # The boundary the page was read at; pass it back as ``as_of`` for later pages.
    as_of: Timestamp
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 42–47 (Clock-Skew Safe Boundary):** If `as_of` is omitted (Page 1), `boundary` defaults to `max(now_manila(), max(ActivityLog.timestamp))`. This ensures that even if the mini PC's hardware clock stepped backward or a backup from a slightly ahead clock was restored, no newest rows are ever hidden.
  * **Line 52:** Orders deterministically by `desc(ActivityLog.timestamp), desc(ActivityLog.id)` so two events with identical millisecond timestamps never swap order across pages.
  * **Line 94:** Resolves `user_name = log.actor_name or (log.user.full_name if log.user else None)`, preferring the immutable `actor_name` snapshot stored when the event occurred.

---

### Phase E & F: Frontend Vocabulary (`activityActions.ts`), Table UI & CSV/XLSX Export (`ActivityLog.tsx`)

#### Step F1: Action Vocabulary (`activityActions.ts`) & Activity Log View (`ActivityLog.tsx`)
* **Step Title & Trigger:** `ActivityLog.tsx` renders the 3 KPI cards, search & dropdown filters, color-coded action badges, and CSV/XLSX exports.
* **Exact File Path & Line Numbers:** `frontend/src/lib/activityActions.ts` (Lines 1–148) and `frontend/src/pages/admin/ActivityLog.tsx` (Lines 1–260)
* **Complete Uncut Code Block (`frontend/src/lib/activityActions.ts`, Lines 1–148):**
```ts
/**
 * Display vocabulary for audit-log actions.
 *
 * Keys mirror `AuditAction` in backend/app/services/audit.py exactly
 * (tests/activityactions.test.mjs compares the two). Stored rows keep the raw
 * action string; exports and API filters use it unchanged. Actions this map
 * does not know (legacy rows) still display through the title-case fallback.
 */

export type ActivityCategory = "auth" | "security" | "credential" | "data" | "export" | "system"

export interface ActivityActionInfo {
  /** Friendly name for badges, filters and search. */
  label: string
  category: ActivityCategory
  /** Badge classes from the Activity Log palette. */
  badge: string
  /** Counted on the "Critical Actions" card. */
  critical: boolean
  /** First-person phrase for the Profile page's recent activity feed. */
  profile: string
}

const BLUE = "bg-blue-50 text-blue-700 border-blue-200"
const GRAY = "bg-gray-50 text-gray-700 border-gray-200"
const RED = "bg-red-50 text-red-700 border-red-200"
const INDIGO = "bg-indigo-50 text-indigo-700 border-indigo-200"
const EMERALD = "bg-emerald-50 text-emerald-700 border-emerald-200"
const YELLOW = "bg-yellow-50 text-yellow-700 border-yellow-200"
const PURPLE = "bg-purple-50 text-purple-700 border-purple-200"
const AMBER = "bg-amber-50 text-amber-700 border-amber-200"
const CYAN = "bg-cyan-50 text-cyan-700 border-cyan-200"
const ORANGE = "bg-orange-50 text-orange-700 border-orange-200"

const entry = (label: string, category: ActivityCategory, badge: string, profile: string, critical = false): ActivityActionInfo =>
  ({ label, category, badge, critical, profile })

export const ACTIVITY_ACTIONS = {
  // Sign-in and session
  login: entry("Signed in", "auth", BLUE, "Signed in to the web dashboard"),
  pin_login: entry("Signed in with PIN", "auth", BLUE, "Signed in to the kiosk with a PIN"),
  logout: entry("Signed out", "auth", GRAY, "Signed out from the session"),
  credential_setup_started: entry("Credential setup started", "auth", BLUE, "Started setting up sign-in credentials"),
  // Security failures
  login_failed: entry("Sign-in failed", "security", RED, "A sign-in attempt failed", true),
  pin_failed: entry("PIN sign-in failed", "security", RED, "A PIN sign-in attempt failed", true),
  login_blocked: entry("Blocked while locked", "security", RED, "An attempt was refused while locked out", true),
  account_locked: entry("Account locked", "security", RED, "Account was locked after failed attempts", true),
  login_denied: entry("Sign-in denied", "security", RED, "A sign-in was denied", true),
  setup_token_rejected: entry("Setup token rejected", "security", RED, "A credential setup link was rejected", true),
  access_denied: entry("Access denied", "security", RED, "Was denied access to a restricted page", true),
  reauth_failed: entry("Re-authentication failed", "security", RED, "Identity confirmation failed", true),
  password_change_failed: entry("Password change failed", "security", RED, "A password change attempt failed", true),
  pin_change_failed: entry("PIN change failed", "security", RED, "A PIN change attempt failed", true),
  // Credentials
  password_changed: entry("Password changed", "credential", INDIGO, "Changed account password"),
  password_setup_completed: entry("Password set up", "credential", INDIGO, "Completed password setup"),
  pin_changed: entry("PIN changed", "credential", INDIGO, "Changed kiosk PIN"),
  pin_setup_completed: entry("PIN set up", "credential", INDIGO, "Completed kiosk PIN setup"),
  password_reset: entry("Password reset", "credential", INDIGO, "Reset a user's password", true),
  pin_reset: entry("PIN reset", "credential", INDIGO, "Reset a user's kiosk PIN", true),
  // Records
  user_created: entry("User created", "data", PURPLE, "Created a user account"),
  user_updated: entry("User updated", "data", INDIGO, "Updated a user account"),
  user_role_changed: entry("User role changed", "data", PURPLE, "Changed a user's role", true),
  user_status_changed: entry("User status changed", "data", PURPLE, "Changed a user's account status", true),
  profile_updated: entry("Profile updated", "data", PURPLE, "Updated profile details"),
  supplier_created: entry("Supplier created", "data", EMERALD, "Added a new supplier"),
  supplier_updated: entry("Supplier updated", "data", YELLOW, "Updated supplier details"),
  intake_created: entry("Intake created", "data", EMERALD, "Recorded a new delivery intake"),
  intake_status_changed: entry("Intake status changed", "data", YELLOW, "Updated intake status in Intake Management"),
  scan_created: entry("Scan created", "data", EMERALD, "Captured a new banana scan in Kiosk"),
  scan_rejected: entry("Scan rejected", "data", AMBER, "Scan rejected: no supported banana detected"),
  scan_failed: entry("Scan failed", "data", AMBER, "A scan could not be completed"),
  scan_flag: entry("Scan flag changed", "data", AMBER, "Changed a scan's review flag"),
  scan_correction: entry("Scan corrected", "data", YELLOW, "Updated scan data in Quality Control"),
  scan_status: entry("Scan status changed", "data", YELLOW, "Updated a scan's inventory status"),
  scan_note: entry("Scan note added", "data", EMERALD, "Added a note to a scan"),
  scan_provenance: entry("Scan intake link changed", "data", YELLOW, "Updated a scan's intake link"),
  label_print_requested: entry("Label print requested", "data", EMERALD, "Requested a label print"),
  label_print_retried: entry("Label print retried", "data", YELLOW, "Retried a label print"),
  data_exported: entry("Data exported", "export", CYAN, "Exported data", true),
  // Configuration, maintenance and system
  config_changed: entry("Configuration changed", "system", ORANGE, "Adjusted system configuration settings", true),
  config_applied: entry("Configuration applied", "system", ORANGE, "Applied saved camera configuration", true),
  backup_created: entry("Backup created", "system", ORANGE, "Created a system backup"),
  backup_failed: entry("Backup failed", "system", RED, "A system backup failed"),
  backup_downloaded: entry("Backup downloaded", "export", CYAN, "Downloaded a system backup", true),
  restore_validated: entry("Restore file validated", "system", ORANGE, "Validated a backup for restore"),
  restore_validation_failed: entry("Restore validation failed", "system", RED, "A backup failed restore validation"),
  restore_completed: entry("Restore completed", "system", ORANGE, "Restored the system from a backup", true),
  restore_failed: entry("Restore failed", "system", RED, "A system restore failed", true),
  maintenance_recovered: entry("Maintenance recovered", "system", ORANGE, "Recovered the station after interrupted maintenance", true),
  system_restart: entry("System restart", "system", ORANGE, "Restarted the station", true),
  system_shutdown: entry("System shutdown", "system", ORANGE, "Shut down the station", true),
  power_failed: entry("Power action failed", "system", RED, "A station power action failed", true),
  power_cancelled: entry("Power action cancelled", "system", ORANGE, "Cancelled a station power action", true),
  power_completed: entry("Power action completed", "system", ORANGE, "Completed a station power action"),
  retention_cleanup: entry("Retention cleanup", "system", ORANGE, "Ran data retention cleanup"),
  retention_failed: entry("Retention cleanup failed", "system", RED, "Data retention cleanup failed"),
  system_started: entry("System started", "system", ORANGE, "Started the station"),
  bootstrap_admin_created: entry("Initial admin created", "system", ORANGE, "Created the initial administrator account", true),
} satisfies Record<string, ActivityActionInfo>

export type KnownActivityAction = keyof typeof ACTIVITY_ACTIONS

/** Own keys only: "toString", "__proto__" and friends are not actions. */
function known(action: string): ActivityActionInfo | null {
  return Object.prototype.hasOwnProperty.call(ACTIVITY_ACTIONS, action)
    ? ACTIVITY_ACTIONS[action as KnownActivityAction]
    : null
}

/** Previous display for actions without an entry: "made_up_action" → "Made Up Action". */
function titleCase(action: string): string {
  return action.split("_").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")
}

export function activityLabel(action: string): string {
  return known(action)?.label ?? titleCase(action)
}

export function activityBadgeClass(action: string): string {
  return known(action)?.badge ?? "bg-muted"
}

export function activityCategory(action: string): ActivityCategory | null {
  return known(action)?.category ?? null
}

export function isCriticalActivity(action: string): boolean {
  return known(action)?.critical ?? false
}

/** Name shown for a row written without an account (failed sign-ins, station events). */
export function actorlessName(action: string): string {
  return activityCategory(action) === "security" ? "Unauthenticated" : "System"
}

/** Phrase for the Profile feed; unknown actions show their stored details. */
export function activityProfileLabel(action: string, details: string): string {
  if (action === "scan_flag") {
    // Flag edits are stored as "flagged False → True" (or the reverse).
    if (/flagged\s+false\s*→\s*true/i.test(details)) return "Flagged a scan for manual review"
    if (/flagged\s+true\s*→\s*false/i.test(details)) return "Cleared a scan's review flag"
  }
  return known(action)?.profile ?? (details || titleCase(action))
}
```
* **Complete Uncut Code Block (`frontend/src/pages/admin/ActivityLog.tsx`, Lines 1–260):**
```tsx
import { useState, useMemo, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { ExportDropdown } from "@/components/ExportDropdown"
import { downloadCsv, downloadXlsx } from "@/lib/exportUtils"
import { ScrollText, Filter, Activity, UserCheck, AlertCircle } from "lucide-react"
import { toast } from "sonner"
import { manilaDayKey } from "@/lib/manilaTime"
import { activityBadgeClass, activityLabel, isCriticalActivity } from "@/lib/activityActions"
import type { ActivityLog as ActivityEntry } from "@/types"

const PAGE_SIZE = 15

export default function ActivityLog() {
  const { activityLogs, activityLoading, activityReady, activityError } = useAdmin()
  const initialLoading = activityLoading && !activityReady
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [userFilter, setUserFilter] = useState<string>("all")

  const users = useMemo(() => Array.from(new Set(activityLogs.map(log => log.user))).sort(), [activityLogs])
  const actionTypes = useMemo(() => Array.from(new Set(activityLogs.map(log => log.action)))
    .sort((a, b) => activityLabel(a).localeCompare(activityLabel(b))), [activityLogs])

  const filtered = useMemo(() => {
    return activityLogs.filter((log) => {
      if (actionFilter !== "all" && log.action !== actionFilter) return false
      if (userFilter !== "all" && log.user !== userFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return log.user.toLowerCase().includes(q) || 
               log.action.toLowerCase().includes(q) || 
               activityLabel(log.action).toLowerCase().includes(q) ||
               log.details.toLowerCase().includes(q)
      }
      return true
    })
  }, [activityLogs, search, actionFilter, userFilter])

  const stats = useMemo(() => {
    const last24h = activityLogs.filter(log => {
      const logTime = new Date(log.timestamp).getTime()
      const now = Date.now()
      return now - logTime < 24 * 60 * 60 * 1000
    }).length

    const uniqueUsers = new Set(activityLogs.map(log => log.user)).size
    const criticalActions = activityLogs.filter(log => isCriticalActivity(log.action)).length

    return { last24h, uniqueUsers, criticalActions }
  }, [activityLogs])

  const sortedLogsRef = useRef(filtered)
  const [exporting, setExporting] = useState(false)

  const handleExportCsv = () => {
    if (activityLoading || !!activityError || !activityReady) return
    const logs = sortedLogsRef.current
    const filename = `activity-log-${manilaDayKey(Date.now())}.csv`
    const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
    const rows = logs.map(log => [
      log.timestamp,
      log.user,
      log.action,
      log.details,
      log.ipAddress || ""
    ])
    downloadCsv(filename, headers, rows)
    toast.success("Export successful", { description: `${logs.length} activities exported to CSV` })
  }

  const handleExportXlsx = async () => {
    if (activityLoading || !!activityError || !activityReady) return
    setExporting(true)
    try {
      const logs = sortedLogsRef.current
      const filename = `activity-log-${manilaDayKey(Date.now())}.xlsx`
      const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
      const rows = logs.map(log => [
        log.timestamp,
        log.user,
        log.action,
        log.details,
        log.ipAddress || ""
      ])
      await downloadXlsx(filename, "Activity Log", headers, rows)
      toast.success("Export successful", { description: `${logs.length} activities exported to Excel` })
    } catch (e) {
      toast.error("Export failed", { description: e instanceof Error ? e.message : "Please try again" })
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnDef<ActivityEntry>[] = [
    {
      header: "Timestamp",
      sortable: true,
      sortKey: "timestamp",
      cell: (log) => (
        <div className="text-sm">
          {new Date(log.timestamp).toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })}
          <br />
          <span className="text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleTimeString(undefined, { timeZone: "Asia/Manila" })}</span>
        </div>
      ),
    },
    {
      header: "User",
      sortable: true,
      sortKey: "user",
      cell: (log) => (
        <div className="flex items-center gap-2">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
              {log.user.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium">{log.user}</span>
        </div>
      ),
    },
    {
      header: "Action",
      sortable: true,
      sortKey: (log) => activityLabel(log.action),
      cell: (log) => (
        <Badge variant="outline" className={`text-xs font-medium rounded-md ${activityBadgeClass(log.action)}`}>
          {activityLabel(log.action)}
        </Badge>
      ),
    },
    {
      header: "Details",
      className: "text-sm max-w-md truncate",
      // The full text stays reachable: rejection rows end with the per-view scores.
      cell: (log) => <span title={log.details}>{log.details}</span>,
    },
    {
      header: "IP Address",
      className: "text-sm text-muted-foreground font-mono",
      cell: (log) => log.ipAddress || "—",
    },
  ]

  return (
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Activity Log"
        description="System activity and audit trail"
        icon={ScrollText}
        action={
          <ExportDropdown
            onExportCsv={handleExportCsv}
            onExportXlsx={handleExportXlsx}
            disabled={activityLoading || !!activityError || !activityReady}
            exporting={exporting}
          />
        }
      />

      {(activityLoading || activityError) && (
        <p role={activityError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {activityError || (activityReady ? "Refreshing activity…" : "Loading activity…")}
        </p>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Last 24 Hours"
          value={stats.last24h}
          icon={Activity}
          delay={50}
          description="Recent activity"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Active Users"
          value={stats.uniqueUsers}
          icon={UserCheck}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={100}
          description="Unique operators"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Critical Actions"
          value={stats.criticalActions}
          icon={AlertCircle}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={150}
          description="Security, access & system changes"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search activities..."
        hasActiveFilters={search !== "" || actionFilter !== "all" || userFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setActionFilter("all")
          setUserFilter("all")
        }}
      >
        <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Actions</SelectItem>
            {actionTypes.map((action) => (
              <SelectItem key={action} value={action}>{activityLabel(action)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={userFilter} onValueChange={(v) => { setUserFilter(v) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="User" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Users</SelectItem>
            {users.map((user) => (
              <SelectItem key={user} value={user}>{user}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <AppDataTable
        loading={initialLoading}
        data={filtered}
        columns={columns}
        rowKey={(log) => log.id}
        pagination={{ pageSize: PAGE_SIZE }}
        onSortedData={(rows) => { sortedLogsRef.current = rows }}
        emptyState={{
          icon: Activity,
          title: activityError && !activityReady ? "Data unavailable" : "No activities found",
          description: activityError && !activityReady ? "Reload to try again." : "Try adjusting your filters or search query"
        }}
      />
    </div>
  )
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 31–44 (`filtered`):** Searches across `log.user`, raw `log.action` (e.g., `"login_failed"`), friendly `activityLabel(log.action)` (e.g., `"Sign-in failed"`), and `log.details`.
  * **Lines 59 & 251 (`sortedLogsRef`):** `AppDataTable` passes the currently filtered **and** user-sorted array to `onSortedData={(rows) => { sortedLogsRef.current = rows }}`, so clicking Export CSV or Export Excel exports the exact filtered/sorted order shown on screen, named `activity-log-${manilaDayKey(Date.now())}.csv` (or `.xlsx`).

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Route & Component** | `/admin/activity` → `frontend/src/pages/admin/ActivityLog.tsx` (`PAGE_SIZE = 15`) |
| **Backend Endpoint** | `GET /api/v1/activity` → `list_activity()` in `backend/app/api/v1/activity.py` |
| **Audit Writer Methods (`audit.py`)** | `audit.record(db, ...)` (same transaction), `audit.emit(...)` (separate session, survives rollback), `audit.attach(exc, ...)` (written after rollback releases row locks) |
| **Action Vocabulary Map** | `ACTIVITY_ACTIONS` in `frontend/src/lib/activityActions.ts` (mirrors `AuditAction` in `backend/app/services/audit.py`) |
| **Export Filenames** | `activity-log-${manilaDayKey(Date.now())}.csv` and `.xlsx` (`ActivityLog.tsx` Lines 65 & 83) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Add a `"Critical Only"` Quick Filter Toggle Button to the Activity Log Filters Bar
* **Examiner Prompt:** *"Add a `'Critical Only'` toggle button next to the Action and User dropdown filters in `ActivityLog.tsx` so administrators can filter the table to only critical security/system events (`isCriticalActivity(log.action)`) with one click."*
* **File to Edit:** `frontend/src/pages/admin/ActivityLog.tsx` (Lines 23–44 & 207–242)
* **Before (`frontend/src/pages/admin/ActivityLog.tsx`, Lines 23–44):**
```tsx
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [userFilter, setUserFilter] = useState<string>("all")
```
```tsx
  const filtered = useMemo(() => {
    return activityLogs.filter((log) => {
      if (actionFilter !== "all" && log.action !== actionFilter) return false
      if (userFilter !== "all" && log.user !== userFilter) return false
      if (search) {
```
* **After (`frontend/src/pages/admin/ActivityLog.tsx`, Lines 23–45):**
```tsx
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [userFilter, setUserFilter] = useState<string>("all")
  const [criticalOnly, setCriticalOnly] = useState(false)
```
```tsx
  const filtered = useMemo(() => {
    return activityLogs.filter((log) => {
      if (criticalOnly && !isCriticalActivity(log.action)) return false
      if (actionFilter !== "all" && log.action !== actionFilter) return false
      if (userFilter !== "all" && log.user !== userFilter) return false
      if (search) {
```

---

#### Drill Scenario 2: Include the Friendly Action Label Column in CSV and Excel Exports
* **Examiner Prompt:** *"When exporting the Activity Log to CSV or Excel, include both the friendly `'Action Label'` (`activityLabel(log.action)`) and the raw `'Action Code'` (`log.action`)."*
* **File to Edit:** `frontend/src/pages/admin/ActivityLog.tsx` (Lines 66–73 & 84–91)
* **Before (`frontend/src/pages/admin/ActivityLog.tsx`, Lines 66–73):**
```tsx
    const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
    const rows = logs.map(log => [
      log.timestamp,
      log.user,
      log.action,
      log.details,
      log.ipAddress || ""
    ])
```
* **After (`frontend/src/pages/admin/ActivityLog.tsx`, Lines 66–74):**
```tsx
    const headers = ["Timestamp", "User", "Action Label", "Action Code", "Details", "IP Address"]
    const rows = logs.map(log => [
      log.timestamp,
      log.user,
      activityLabel(log.action),
      log.action,
      log.details,
      log.ipAddress || ""
    ])
```

---

#### Drill Scenario 3: Add a Custom Audit Action When an Admin Views or Searches the Activity Log
* **Examiner Prompt:** *"Understand how `AuditAction` and `ACTIVITY_ACTIONS` are synchronized: `tests/activityactions.test.mjs` requires every `AuditAction` enum member in `backend/app/services/audit.py` to have a matching key in `ACTIVITY_ACTIONS` in `frontend/src/lib/activityActions.ts`."*
* **Files to Edit Together Whenever Adding an Audit Action:**
  1. `backend/app/services/audit.py` (`class AuditAction(StrEnum)`)
  2. `frontend/src/lib/activityActions.ts` (`export const ACTIVITY_ACTIONS`)
