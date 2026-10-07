/**
 * Centralized API client for BananaVision backend.
 *
 * Auto-attaches JWT, handles 401 redirects, groups endpoints by domain.
 */

import { getToken, clearAuth } from "@/lib/auth"
import { scanWrite, requireScanRevision } from "@/lib/scanWrites"
import type { DashboardScanPage, DashboardScanParams, DashboardSummary } from "@/types/dashboard"
import type { ScanLogPage, ScanLogParams } from "@/types/scanLogs"
import type { ApiScan, ApiScanNote, RecordPage } from "@/lib/scanData"
import type { InventoryStatus, IntakeStatus } from "@/types"
import type { AnalyticsRange, AnalyticsSummary, AnalyticsOperator } from "@/types/analytics"
import type { ApiConfigUpdate, MaintenanceOperation, MaintenanceStatus, RestoreValidation, ApiActivity, ApiConfig, ApiDevice, ApiIntake, ApiMessage, ApiNotification, ApiSensor, ApiSupplier, ApiSupplierWrite, ApiUser, ApiUserCreate, ApiUserCreated, ApiUserUpdate } from "@/types/api"

const host = window.location.hostname
export const BASE_URL = import.meta.env.VITE_API_URL || `http://${host}:8000`

// ── Core Fetch Wrapper ──────────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts?: { params?: Record<string, string | number | boolean | undefined>; signal?: AbortSignal }
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (body instanceof FormData) delete headers["Content-Type"]
  if (token) headers["Authorization"] = `Bearer ${token}`

  // Build query string
  let url = `${BASE_URL}${path}`
  if (opts?.params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(opts.params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    }
    const str = qs.toString()
    if (str) url += `?${str}`
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    signal: opts?.signal,
    cache: "no-store",
  })

  // Handle 401 — token expired / invalid
  if (res.status === 401) {
    clearAuth()
    window.location.href = "/login"
    throw Object.assign(new Error("Session expired"), { status: 401 })
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof err.detail === "string" ? err.detail : Array.isArray(err.detail)
      ? err.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ") : `API error ${res.status}`
    throw Object.assign(new Error(detail), { status: res.status })
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json()
}

function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>, signal?: AbortSignal) {
  return request<T>("GET", path, undefined, { params, signal })
}

function post<T>(path: string, body?: unknown) {
  return request<T>("POST", path, body)
}

function patch<T>(path: string, body?: unknown) {
  return request<T>("PATCH", path, body)
}

// ── API Namespaces ──────────────────────────────────────────────────────────

export const api = {
  // ── Auth ─────────────────────────────────────────────────────────────────
  auth: {
    login: (username: string, password: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
        reason?: string | null
        setup_token?: string | null
      }>("/api/v1/auth/login", { username, password }),

    swap: (username: string, pin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
        reason?: string | null
        setup_token?: string | null
      }>("/api/v1/auth/swap", { username, pin }),

    /** Self-service password change — requires JWT auth + current password. */
    changePassword: (currentPassword: string, newPassword: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/change-password", { current_password: currentPassword, new_password: newPassword }),

    /** First-time / post-reset password setup — requires limited setup authorization issued at login. */
    setupPassword: (setupToken: string, newPassword: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/setup-password", { setup_token: setupToken, new_password: newPassword }),

    /** Self-service PIN change — requires JWT auth + current PIN. */
    changePin: (currentPin: string, newPin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/change-pin", { current_pin: currentPin, new_pin: newPin }),

    /** First-time / post-reset PIN setup — requires limited setup authorization issued at PIN swap. */
    setupPin: (setupToken: string, newPin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/setup-pin", { setup_token: setupToken, new_pin: newPin }),

    logout: () => post<void>("/api/v1/auth/logout"),

    /** Public endpoint — no auth needed. Returns active operators for kiosk selection. */
    kioskOperators: () =>
      get<{ id: string; username: string; full_name: string; role: string; status: string; avatar_url?: string }[]>(
        "/api/v1/auth/operators"
      ),
  },

  // ── Scans ────────────────────────────────────────────────────────────────
  scans: {
    trigger: (data: { source?: string; intake_id?: string }) =>
      post<ApiScan>("/api/v1/scans/trigger", { source_text: data.source, intake_id: data.intake_id }),

    list: (params?: { page?: number; page_size?: number; cultivar?: string; ripeness?: string; flagged?: boolean }, signal?: AbortSignal) =>
      get<RecordPage<ApiScan>>("/api/v1/scans", params, signal),

    detail: (id: string, signal?: AbortSignal) => get<ApiScan>(`/api/v1/scans/${id}`, undefined, signal),

    flag: (id: string, flagged: boolean, revision: number) =>
      scanWrite(`${getToken()}:${id}`, { flagged, expected_revision: requireScanRevision(revision) }, body => patch<ApiScan>(`/api/v1/scans/${id}/flag`, body)),

    override: (id: string, data: { cultivar?: string; ripeness?: string; finger_count?: number; spoilage_days?: string; source_text?: string }, revision: number, reason: string) =>
      scanWrite(`${getToken()}:${id}`, { ...data, expected_revision: requireScanRevision(revision), reason: reason.trim() }, body => patch<ApiScan>(`/api/v1/scans/${id}`, body)),

    updateStatus: (id: string, status: string, revision: number, reason: string) =>
      scanWrite(`${getToken()}:${id}`, { inventory_status: status, expected_revision: requireScanRevision(revision), reason: reason.trim() }, body => patch<ApiScan>(`/api/v1/scans/${id}/status`, body)),

    notes: {
      list: (scanId: string) => get<ApiScanNote[]>(`/api/v1/scans/${scanId}/notes`),
      add: (scanId: string, note: string, revision: number) => scanWrite(`${getToken()}:${scanId}`, { note, expected_revision: requireScanRevision(revision) }, body => post<ApiScanNote>(`/api/v1/scans/${scanId}/notes`, body)),
    },
  },

  // ── Cameras ─────────────────────────────────────────────────────────────
  cameras: {
    map: (device_ids: number[], expected_revision: number) => post<ApiConfig>("/api/v1/cameras/mapping", { device_ids, expected_revision }),
    list: (signal?: AbortSignal) => get<{ device_id: number; camera_id: string; label: string; online: boolean }[]>("/api/v1/cameras", undefined, signal),
  },

  // ── Devices ──────────────────────────────────────────────────────────────
  devices: {
    list: () => get<ApiDevice[]>("/api/v1/devices"),
  },

  // ── Sensors ──────────────────────────────────────────────────────────────
  sensors: {
    latest: () => get<ApiSensor | null>("/api/v1/sensors/latest"),
    history: (params?: { limit?: number }) => get<{ items: ApiSensor[]; total: number }>("/api/v1/sensors/history", params),
  },

  // ── Users ────────────────────────────────────────────────────────────────
  users: {
    summary: (signal?: AbortSignal) => get<{ total_scans: number; avg_confidence: number | null; last_7_days: number; total_users: number | null; activity: { id: string; action: string; details: string; timestamp: string }[] }>("/api/v1/users/me/summary", undefined, signal),
    list: () => get<{ items: ApiUser[]; total: number }>("/api/v1/users"),
    create: (data: ApiUserCreate) => post<ApiUserCreated>("/api/v1/users", data),
    update: (id: string, data: ApiUserUpdate) => patch<ApiUser>(`/api/v1/users/${id}`, data),
    resetPassword: (id: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, {}),
    resetPin: (id: string) => post<{ message: string; temporary_pin: string }>(`/api/v1/users/${id}/reset-pin`, {}),
    /** Self-service profile update — any authenticated user can update their own avatar. (PROFILE-01) */
    updateProfile: (data: { avatar_url?: string }) => patch<ApiUser>(`/api/v1/users/me/profile`, data),
  },

  // ── Suppliers ────────────────────────────────────────────────────────────
  suppliers: {
    list: () => get<ApiSupplier[]>("/api/v1/suppliers"),
    create: (data: ApiSupplierWrite) => post<ApiSupplier>("/api/v1/suppliers", data),
    update: (id: string, data: Partial<ApiSupplierWrite>) => patch<ApiSupplier>(`/api/v1/suppliers/${id}`, data),
  },

  // ── Intakes ──────────────────────────────────────────────────────────────
  intakes: {
    list: () => get<ApiIntake[]>("/api/v1/intakes"),
    create: (data: { supplier_id: string; batch_number: string; source?: string; treatment?: string }) => post<ApiIntake>("/api/v1/intakes", data),
    update: (id: string, data: { status: IntakeStatus }) => patch<{ message: string }>(`/api/v1/intakes/${id}/status`, data),
    bulkInventory: (id: string, data: { inventory_status: InventoryStatus; expected_revisions: Record<string, number>; reason: string }) =>
      scanWrite(`${getToken()}:intake:${id}`, data, body => patch<{ updated_count: number; updated_scan_ids: string[]; status_updated_at: string; intake_status: IntakeStatus }>(`/api/v1/intakes/${id}/bulk-inventory`, body)),
  },

  // Dashboard metrics and their record views share server-enforced user scope.
  dashboard: {
    summary: (signal?: AbortSignal, businessDate?: string) => get<DashboardSummary>("/api/v1/dashboard", { business_date: businessDate }, signal),
    scans: (params: DashboardScanParams, signal?: AbortSignal) =>
      get<DashboardScanPage>("/api/v1/dashboard/scans", { ...params }, signal),
  },

  scanLogs: {
    list: (params: ScanLogParams, signal?: AbortSignal) => get<ScanLogPage>("/api/v1/scan-logs", { ...params }, signal),
    export: async (params: ScanLogParams, signal?: AbortSignal) => {
      const query = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") query.set(key, String(value))
      const token = getToken()
      const response = await fetch(`${BASE_URL}/api/v1/scan-logs/export?${query}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, signal, cache: "no-store",
      })
      if (!response.ok) throw new Error("Scan export failed. Please retry.")
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url
      link.download = `banana-scans-${params.business_date || "filtered"}.csv`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  },

  // ── Analytics ────────────────────────────────────────────────────────────
  analytics: {
    summary: (params?: { range?: AnalyticsRange; source?: string; source_key?: string; confidence_threshold?: number }, signal?: AbortSignal) =>
      get<AnalyticsSummary>("/api/v1/analytics/summary", params, signal),
    operatorPerformance: (params?: { range?: AnalyticsRange; source?: string; source_key?: string }, signal?: AbortSignal) =>
      get<{ items: AnalyticsOperator[]; total_operators: number }>("/api/v1/analytics/operator-performance", params, signal),
  },

  // ── Activity ─────────────────────────────────────────────────────────────
  activity: {
    list: (params?: { page?: number; page_size?: number; action?: string }, signal?: AbortSignal) =>
      get<RecordPage<ApiActivity>>("/api/v1/activity", params, signal),
  },

  // ── Config ───────────────────────────────────────────────────────────────
  config: {
    get: (signal?: AbortSignal) => get<ApiConfig>("/api/v1/config", undefined, signal),
    update: (data: ApiConfigUpdate) => patch<ApiConfig>("/api/v1/config", data),
    export: async () => {
      const token = getToken()
      const res = await fetch(`${BASE_URL}/api/v1/config/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      })
      if (!res.ok) throw new Error("Export failed")
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "bananavision_inventory_export.csv"
      a.click()
      window.URL.revokeObjectURL(url)
    },
    maintenance: () => get<MaintenanceStatus>("/api/v1/config/maintenance"),
    operation: (id: string) => get<MaintenanceOperation>(`/api/v1/config/operations/${encodeURIComponent(id)}`),
    backup: (operation_id: string) => post<MaintenanceOperation>("/api/v1/config/backups", { operation_id }),
    downloadBackup: async (id: string, filename: string) => {
      const token = getToken()
      const response = await fetch(`${BASE_URL}/api/v1/config/backups/${encodeURIComponent(id)}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!response.ok) throw new Error("Backup download failed")
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url; link.download = filename; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    },
    validateRestore: (file: File) => {
      const form = new FormData(); form.append("file", file)
      return request<RestoreValidation>("POST", "/api/v1/config/restores/validate", form)
    },
    restore: (body: { operation_id: string; validation_id: string; token: string; password: string; confirmation: "REPLACE" }) => post<MaintenanceOperation>("/api/v1/config/restores", body),
    recoverPower: (body: { operation_id: string; password: string; confirmation: "RECOVER" }) => post<MaintenanceOperation>("/api/v1/config/power/recover", body),
    shutdown: (operation_id: string) => post<MaintenanceOperation>("/api/v1/config/shutdown", { operation_id }),
    restart: (operation_id: string) => post<MaintenanceOperation>("/api/v1/config/restart", { operation_id }),
  },

  // ── Quality Control ──────────────────────────────────────────────────────
  quality: {
    flagged: (params?: { page?: number; page_size?: number }) =>
      get<RecordPage<Pick<ApiScan, "id" | "scanned_at" | "cultivar" | "ripeness" | "confidence" | "finger_count" | "operator_name" | "flagged">>>("/api/v1/quality/flagged", params),
  },

  // ── Notifications ───────────────────────────────────────────────────────
  notifications: {
    list: () => get<{ items: ApiNotification[]; total: number }>("/api/v1/notifications"),
    markRead: (id: string) => patch<ApiMessage>(`/api/v1/notifications/${id}/read`),
    markAllRead: () => post<ApiMessage>("/api/v1/notifications/read-all"),
  },

  // ── System ─────────────────────────────────────────────────────────────
  system: {
    metrics: () => get<{
      cpu_name: string
      cpu_percent: number
      memory_used_gb: number
      memory_total_gb: number
      memory_percent: number
      disk_used_gb: number
      disk_total_gb: number
      disk_percent: number
      uptime: string
      cpu_temp: number | null
    }>("/api/v1/system/metrics"),
  },

  // ── Health ───────────────────────────────────────────────────────────────
  health: () => get<{ status: string; cameras_online: number; cameras_total: number; yolo_loaded: boolean; rfr_loaded: boolean; sensor_connected: boolean }>("/health"),
}
