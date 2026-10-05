/**
 * Centralized API client for BananaVision backend.
 *
 * Auto-attaches JWT, handles 401 redirects, groups endpoints by domain.
 */

import { getToken, clearAuth } from "@/lib/auth"
import type { DashboardScanPage, DashboardScanParams, DashboardSummary } from "@/types/dashboard"
import type { ScanLogPage, ScanLogParams } from "@/types/scanLogs"
import type { ApiScan, ApiScanNote, RecordPage } from "@/lib/scanData"
import type { InventoryStatus, IntakeStatus } from "@/types"
import type { AnalyticsRange, AnalyticsSummary, AnalyticsOperator } from "@/types/analytics"

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
    body: body ? JSON.stringify(body) : undefined,
    signal: opts?.signal,
    cache: "no-store",
  })

  // Handle 401 — token expired / invalid
  if (res.status === 401) {
    clearAuth()
    window.location.href = "/login"
    throw new Error("Session expired")
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

function del<T>(path: string) {
  return request<T>("DELETE", path)
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

    flag: (id: string, flagged: boolean) =>
      patch<any>(`/api/v1/scans/${id}/flag`, { flagged }),

    override: (id: string, data: { cultivar?: string; ripeness?: string; finger_count?: number; spoilage_days?: string; source_text?: string }) =>
      patch<ApiScan>(`/api/v1/scans/${id}`, data),

    updateStatus: (id: string, status: string) =>
      patch<any>(`/api/v1/scans/${id}/status`, { inventory_status: status }),

    notes: {
      list: (scanId: string) => get<ApiScanNote[]>(`/api/v1/scans/${scanId}/notes`),
      add: (scanId: string, note: string) => post<ApiScanNote>(`/api/v1/scans/${scanId}/notes`, { note }),
    },
  },

  // ── Cameras ─────────────────────────────────────────────────────────────
  cameras: {
    list: (signal?: AbortSignal) => get<{ device_id: number; camera_id: string; label: string; online: boolean }[]>("/api/v1/cameras", undefined, signal),
  },

  // ── Devices ──────────────────────────────────────────────────────────────
  devices: {
    list: () => get<any[]>("/api/v1/devices"),
  },

  // ── Sensors ──────────────────────────────────────────────────────────────
  sensors: {
    latest: () => get<{ temperature: number; humidity: number; recorded_at: string }>("/api/v1/sensors/latest"),
    history: (params?: { hours?: number }) => get<any[]>("/api/v1/sensors/history", params as any),
  },

  // ── Users ────────────────────────────────────────────────────────────────
  users: {
    summary: (signal?: AbortSignal) => get<{ total_scans: number; avg_confidence: number | null; last_7_days: number; total_users: number | null; activity: { id: string; action: string; details: string; timestamp: string }[] }>("/api/v1/users/me/summary", undefined, signal),
    list: () => get<{ items: any[]; total: number }>("/api/v1/users"),
    create: (data: any) => post<any>("/api/v1/users", data),
    update: (id: string, data: any) => patch<any>(`/api/v1/users/${id}`, data),
    resetPassword: (id: string) => post<{ message: string; temporary_password: string }>(`/api/v1/users/${id}/reset-password`, {}),
    resetPin: (id: string) => post<{ message: string; temporary_pin: string }>(`/api/v1/users/${id}/reset-pin`, {}),
    /** Self-service profile update — any authenticated user can update their own avatar. (PROFILE-01) */
    updateProfile: (data: { avatar_url?: string }) => patch<any>(`/api/v1/users/me/profile`, data),
  },

  // ── Suppliers ────────────────────────────────────────────────────────────
  suppliers: {
    list: () => get<any[]>("/api/v1/suppliers"),
    create: (data: any) => post<any>("/api/v1/suppliers", data),
    update: (id: string, data: any) => patch<any>(`/api/v1/suppliers/${id}`, data),
  },

  // ── Intakes ──────────────────────────────────────────────────────────────
  intakes: {
    list: () => get<any[]>("/api/v1/intakes"),
    create: (data: { supplier_id: string; batch_number: string; source?: string; treatment?: string }) => post<any>("/api/v1/intakes", data),
    update: (id: string, data: { status: IntakeStatus }) => patch<{ message: string }>(`/api/v1/intakes/${id}/status`, data),
    bulkInventory: (id: string, data: { inventory_status: InventoryStatus }) =>
      patch<{ updated_count: number; updated_scan_ids: string[]; status_updated_at: string; intake_status: IntakeStatus }>(`/api/v1/intakes/${id}/bulk-inventory`, data),
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
      get<RecordPage<{ id: string; created_at: string; user_name?: string; action: string; details: string; ip_address?: string }>>("/api/v1/activity", params, signal),
  },

  // ── Config ───────────────────────────────────────────────────────────────
  config: {
    get: () => get<any>("/api/v1/config"),
    update: (data: any) => patch<any>("/api/v1/config", data),
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
    shutdown: () => post<any>("/api/v1/config/shutdown"),
    restart: () => post<any>("/api/v1/config/restart"),
  },

  // ── Quality Control ──────────────────────────────────────────────────────
  quality: {
    flagged: (params?: { page?: number; per_page?: number }) =>
      get<{ items: any[]; total: number }>("/api/v1/quality/flagged", params as any),
  },

  // ── Notifications ───────────────────────────────────────────────────────
  notifications: {
    list: () => get<{ items: any[]; total: number }>("/api/v1/notifications"),
    markRead: (id: string) => patch<any>(`/api/v1/notifications/${id}/read`),
    markAllRead: () => post<any>("/api/v1/notifications/read-all"),
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
