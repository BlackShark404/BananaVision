/**
 * Display vocabulary for audit-log actions.
 *
 * Keys mirror `AuditAction` in backend/app/services/audit.py exactly
 * (tests/activityactions.test.mjs compares the two). Stored rows and API filters
 * keep the raw action string; UI and exports display the friendly label. Actions
 * this map does not know (legacy rows) still display through the title-case fallback.
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
