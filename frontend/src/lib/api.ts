/**
 * Centralized API client for BananaVision backend.
 *
 * Auto-attaches JWT, handles 401 redirects, groups endpoints by domain.
 */

import { getToken, clearAuth } from "@/lib/auth"
import type { DashboardScanPage, DashboardScanParams, DashboardSummary } from "@/types/dashboard"
import type { ScanLogPage, ScanLogParams, ScanLogPending, ScanLogReconciliation } from "@/types/scanLogs"
import type { ApiScan, ApiScanNote, RecordPage } from "@/lib/scanData"
import type { RipenessProjection } from "@/lib/ripenessProjection"
import type { ShelfLifeWindow } from "@/lib/shelfLifeWindow"
import type { LabelPreview, PrintJob } from "@/types/printing"
import type { CameraDiscovery } from "@/types/cameras"
import type { InventoryStatus, IntakeStatus, StorageExposureSummary } from "@/types"
import type { AnalyticsRange, AnalyticsSummary, AnalyticsOperator } from "@/types/analytics"
import type { ApiConfigUpdate, MaintenanceOperation, MaintenanceStatus, RestoreValidation, ApiActivityPage, ApiConfig, ApiDevice, ApiIntake, ApiMessage, ApiNotification, ApiSensor, ApiSupplier, ApiSupplierWrite, ApiUser, ApiUserCreate, ApiUserCreated, ApiUserUpdate } from "@/types/api"

export interface ScanMutationEnvelope { request_id: string; expected_revision: number }

const host = window.location.hostname
const secureContext = window.location.protocol === "https:"
// An HTTPS page must call the same origin so a reverse proxy can forward /api.
// Plain-HTTP LAN pages keep the historical direct backend port.
export const BASE_URL = import.meta.env.VITE_API_URL || (secureContext ? "" : `http://${host}:8000`)

/** Adds the session token to URLs loaded by <img>, which cannot send Authorization headers. */
export function withMediaToken(url: string): string {
  const token = getToken()
  if (!token) return url
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`
}

// ── Core Fetch Wrapper ──────────────────────────────────────────────────────

type RequestOptions = { params?: Record<string, string | number | boolean | undefined>; signal?: AbortSignal }

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts?: RequestOptions
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (body instanceof FormData) delete headers["Content-Type"]
  if (body instanceof Blob) headers["Content-Type"] = "application/octet-stream"
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

  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body instanceof FormData || body instanceof Blob ? body : body ? JSON.stringify(body) : undefined,
      signal: opts?.signal,
      cache: "no-store",
    })
  } catch (e) {
    // Network error (connection refused, DNS failure, etc.) — don't clear auth
    if (e instanceof DOMException && e.name === "AbortError") throw e
    throw Object.assign(new Error("Backend unavailable — please check the server and retry"), { status: 0 })
  }

  // Credential rejection must not expire an existing operator/admin session.
  const isCredentialSubmission = path === "/api/v1/auth/login" || path === "/api/v1/auth/swap"
  // Handle 401 — token expired / invalid on protected requests.
  if (res.status === 401 && !isCredentialSubmission) {
    clearAuth()
    window.location.href = "/login"
    throw new Error("Session expired")
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof err.detail === "string" ? err.detail : Array.isArray(err.detail)
      ? err.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ") : `API error ${res.status}`
    // Machine-readable outcome of a refused scan. Copied by name: the body also has a
    // text `status`, which must never replace the numeric HTTP status below.
    const code = typeof err.code === "string" ? err.code : undefined
    const reason = typeof err.reason === "string" ? err.reason : undefined
    throw Object.assign(new Error(detail), { status: res.status, code, reason })
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json()
}

async function requestWithDeadline<T>(method: string, path: string, body?: unknown, opts: RequestOptions = {}, timeoutMessage = "Request timed out. Please try again.") {
  const { signal } = opts
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort(signal?.reason)
  if (signal?.aborted) cancel()
  else signal?.addEventListener("abort", cancel, { once: true })
  // Keep the deadline active through body parsing, not just receipt of headers.
  const timer = window.setTimeout(() => { timedOut = true; controller.abort() }, 15_000)
  try {
    return await request<T>(method, path, body, { ...opts, signal: controller.signal })
  } catch (error) {
    if (timedOut) throw Object.assign(new Error(timeoutMessage), { status: 0 })
    throw error
  } finally {
    window.clearTimeout(timer)
    signal?.removeEventListener("abort", cancel)
  }
}

function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>, signal?: AbortSignal) {
  return requestWithDeadline<T>("GET", path, undefined, { params, signal })
}

// Mutations opt in only when their recovery is safe; hardware jobs keep their status workflow.
function post<T>(path: string, body?: unknown, timeoutMessage?: string) {
  return timeoutMessage ? requestWithDeadline<T>("POST", path, body, {}, timeoutMessage) : request<T>("POST", path, body)
}

function patch<T>(path: string, body?: unknown, timeoutMessage?: string) {
  return timeoutMessage ? requestWithDeadline<T>("PATCH", path, body, {}, timeoutMessage) : request<T>("PATCH", path, body)
}

// ── API Namespaces ──────────────────────────────────────────────────────────

/** Shared analytics query; date_from/date_to (inclusive Manila days) replace range. */
type AnalyticsQuery = {
  range?: AnalyticsRange; source?: string; source_key?: string; cultivar?: string
  inventory_status?: string; date_from?: string; date_to?: string
}

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
      }>("/api/v1/auth/swap", { username, pin }, "PIN verification timed out. Your current session has not changed."),

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
      }>("/api/v1/auth/setup-pin", { setup_token: setupToken, new_pin: newPin }, "PIN setup timed out; its result is unknown. Go back to operator selection and sign in with the new PIN to check whether it was saved."),

    logout: () => post<void>("/api/v1/auth/logout"),

    /** Public endpoint — no auth needed. Returns active operators for kiosk selection. */
    kioskOperators: () =>
      get<{ id: string; username: string; full_name: string; role: string; status: string; avatar_url?: string }[]>(
        "/api/v1/auth/operators"
      ),
  },

  // ── Scans ────────────────────────────────────────────────────────────────
  scans: {
    label: (id: string) => get<LabelPreview>(`/api/v1/scans/${id}/label`),
    print: (id: string, data: { request_id: string; quantity: number }) =>
      post<PrintJob>(`/api/v1/scans/${id}/print`, data),
    printStatus: (id: string, jobId: string) =>
      get<PrintJob>(`/api/v1/scans/${id}/print-jobs/${jobId}`),
    retryPrint: (id: string, jobId: string, expectedAttempt: number) =>
      post<PrintJob>(`/api/v1/scans/${id}/print-jobs/${jobId}/retry`, { expected_attempt: expectedAttempt }),
    trigger: (data: { source?: string; intake_id?: string }) =>
      post<ApiScan>("/api/v1/scans/trigger", { source_text: data.source, intake_id: data.intake_id }),

    list: (params?: { page?: number; page_size?: number; cultivar?: string; ripeness?: string; flagged?: boolean; stable?: boolean; snapshot_id?: string }, signal?: AbortSignal) =>
      get<RecordPage<ApiScan>>("/api/v1/scans", params, signal),

    detail: (id: string, signal?: AbortSignal) => get<ApiScan>(`/api/v1/scans/${id}`, undefined, signal),

    flag: (id: string, data: ScanMutationEnvelope & { flagged: boolean }) =>
      patch<ApiScan>(`/api/v1/scans/${id}/flag`, data),

    override: (id: string, data: ScanMutationEnvelope & { reason: string; cultivar?: string; ripeness?: string; finger_count?: number; spoilage_days?: string; source_text?: string }) =>
      patch<ApiScan>(`/api/v1/scans/${id}`, data),

    updateStatus: (id: string, data: ScanMutationEnvelope & { inventory_status: InventoryStatus; reason: string }) =>
      patch<ApiScan>(`/api/v1/scans/${id}/status`, data),

    reviewProvenance: (id: string, data: ScanMutationEnvelope & { intake_provenance: "unlinked" | "excluded"; reason: string }) =>
      patch<ApiScan>(`/api/v1/scans/${id}/provenance`, data),

    notes: {
      list: (scanId: string) => get<ApiScanNote[]>(`/api/v1/scans/${scanId}/notes`),
      add: (scanId: string, data: ScanMutationEnvelope & { note: string }) => post<ApiScanNote & { revision: number }>(`/api/v1/scans/${scanId}/notes`, data),
    },

    /** Public scan lookup for QR code tracking — no auth token attached. */
    publicTrack: async (id: string, signal?: AbortSignal) => {
      const res = await fetch(`${BASE_URL}/api/v1/scans/${id}/track`, { signal, cache: "no-store" })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw Object.assign(new Error(typeof err.detail === "string" ? err.detail : `Error ${res.status}`), { status: res.status })
      }
      return res.json() as Promise<{
        id: string
        date_time: string
        cultivar: string | null
        ripeness: string | null
        confidence: number | null
        spoilage_days: string | null
        remaining_days: number | null
        risk_as_of: string | null
        shelf_life_window?: ShelfLifeWindow | null
        ripeness_projection?: RipenessProjection | null
        storage_exposure?: StorageExposureSummary | null
        finger_count: number
        temperature: number | null
        humidity: number | null
        vpd: number | null
        treatment: string | null
        source_text: string | null
        inventory_status: string
        flagged: boolean
        images: { camera_id: string; file_path: string }[]
      }>
    },
  },

  // ── Cameras ─────────────────────────────────────────────────────────────
  cameras: {
    discover: (signal?: AbortSignal) => get<CameraDiscovery>("/api/v1/cameras/discovery", undefined, signal),
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
    summary: (signal?: AbortSignal) => get<{ total_scans: number; avg_confidence: number | null; last_7_days: number; recent_actions_7d?: number; total_users: number | null; activity: { id: string; action: string; details: string; timestamp: string }[] }>("/api/v1/users/me/summary", undefined, signal),
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
    scanRevisions: (id: string) => get<{ revisions: Record<string, number> }>(`/api/v1/intakes/${id}/scan-revisions`),
    bulkInventory: (id: string, data: { inventory_status: InventoryStatus; request_id: string; expected_revisions: Record<string, number>; reason: string }) =>
      patch<{ revisions: Record<string, number>; updated_count: number; updated_scan_ids: string[]; status_updated_at: string; intake_status: IntakeStatus }>(`/api/v1/intakes/${id}/bulk-inventory`, data),
    setExpectedStock: (id: string, items: { cultivar: string; expected_bunches: number }[]) =>
      patch<ApiIntake>(`/api/v1/intakes/${id}/expected-stock`, { items }),
  },

  // Dashboard metrics and their record views share server-enforced user scope.
  dashboard: {
    summary: (signal?: AbortSignal, businessDate?: string) => get<DashboardSummary>("/api/v1/dashboard", { business_date: businessDate }, signal),
    scans: (params: DashboardScanParams, signal?: AbortSignal) =>
      get<DashboardScanPage>("/api/v1/dashboard/scans", { ...params }, signal),
  },

  scanLogs: {
    reconcile: (params: ScanLogParams, signal?: AbortSignal) => get<ScanLogReconciliation>("/api/v1/scan-logs/reconcile", { ...params }, signal),
    list: (params: ScanLogParams, signal?: AbortSignal) => get<ScanLogPage>("/api/v1/scan-logs", { ...params }, signal),
    pending: (params: ScanLogParams, signal?: AbortSignal) => get<ScanLogPending>("/api/v1/scan-logs/pending", { ...params }, signal),
    export: async (params: ScanLogParams, signal?: AbortSignal) => {
      const query = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") query.set(key, String(value))
      const token = getToken()
      const format = params.format || "xlsx"
      query.set("format", format)
      const response = await fetch(`${BASE_URL}/api/v1/scan-logs/export?${query}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, signal, cache: "no-store",
      })
      if (!response.ok) throw new Error("Scan export failed. Please retry.")
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url
      link.download = `banana-scans-${params.business_date || "filtered"}.${format}`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  },

  // ── Analytics ────────────────────────────────────────────────────────────
  analytics: {
    summary: (params?: AnalyticsQuery & { confidence_threshold?: number }, signal?: AbortSignal) =>
      get<AnalyticsSummary>("/api/v1/analytics/summary", params, signal),
    operatorPerformance: (params?: AnalyticsQuery, signal?: AbortSignal) =>
      get<{ items: AnalyticsOperator[]; total_operators: number }>("/api/v1/analytics/operator-performance", params, signal),
  },

  // ── Activity ─────────────────────────────────────────────────────────────
  activity: {
    list: (params?: { page?: number; page_size?: number; action?: string; as_of?: string }, signal?: AbortSignal) =>
      get<ApiActivityPage>("/api/v1/activity", params, signal),
  },

  // ── Config ───────────────────────────────────────────────────────────────
  config: {
    get: (signal?: AbortSignal) => get<ApiConfig>("/api/v1/config", undefined, signal),
    update: (data: ApiConfigUpdate) => patch<ApiConfig>("/api/v1/config", data),
    export: async (format: "xlsx" | "pdf" = "xlsx") => {
      const token = getToken()
      const res = await fetch(`${BASE_URL}/api/v1/config/export?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      })
      if (!res.ok) throw new Error("Export failed")
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `bananavision_inventory_export.${format}`
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
    validateRestore: (file: File) => request<RestoreValidation>("POST", "/api/v1/config/restores/validate", file),
    restore: (body: { operation_id: string; validation_id: string; token: string; password: string; confirmation: "REPLACE" }) => post<MaintenanceOperation>("/api/v1/config/restores", body),
    recoverPower: (password: string) => post<MaintenanceOperation>("/api/v1/config/power/cancel", { password }),
    recoverRestore: (password: string) => post<MaintenanceStatus>("/api/v1/config/maintenance/recover", { password }),
    applyCameras: (operation_id: string) => post<ApiConfig>("/api/v1/config/maintenance/apply", { operation_id }),
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
    list: (signal?: AbortSignal) => get<{ items: ApiNotification[]; total: number }>("/api/v1/notifications", undefined, signal),
    markRead: (id: string) => patch<ApiMessage>(`/api/v1/notifications/${id}/read`, undefined, "Marking notification read timed out. Refresh or retry."),
    markAllRead: () => post<ApiMessage>("/api/v1/notifications/read-all", undefined, "Marking notifications read timed out. Refresh or retry."),
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
  health: () => get<{ status: string; cameras_online: number; cameras_total: number; yolo_loaded: boolean; rfr_loaded: boolean; sensor_connected: boolean; sensor_recorded_at?: string | null; sensor_stale_after_seconds?: number; server_time?: string }>("/health"),
}
