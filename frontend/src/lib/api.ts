/**
 * Centralized API client for BananaVision backend.
 *
 * Auto-attaches JWT, handles 401 redirects, groups endpoints by domain.
 */

import { getToken, clearAuth } from "@/lib/auth"

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

// ── Core Fetch Wrapper ──────────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts?: { params?: Record<string, string | number | boolean | undefined> }
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
  })

  // Handle 401 — token expired / invalid
  if (res.status === 401) {
    clearAuth()
    window.location.href = "/login"
    throw new Error("Session expired")
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API error ${res.status}`)
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json()
}

function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>) {
  return request<T>("GET", path, undefined, { params })
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
      }>("/api/v1/auth/login", { username, password }),

    swap: (username: string, pin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
        reason?: string | null
      }>("/api/v1/auth/swap", { username, pin }),

    changePassword: (username: string, currentPassword: string, newPassword: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string } | null
      }>("/api/v1/auth/change-password", { username, current_password: currentPassword, new_password: newPassword }),

    changePin: (username: string, newPin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/change-pin", { username, new_pin: newPin }),

    logout: () => post<void>("/api/v1/auth/logout"),
  },

  // ── Scans ────────────────────────────────────────────────────────────────
  scans: {
    trigger: (data: { source?: string; intake_id?: string }) =>
      post<{ scan_id: string; status: string }>("/api/v1/scans/trigger", { source_text: data.source, intake_id: data.intake_id }),

    list: (params?: { page?: number; per_page?: number; cultivar?: string; ripeness?: string; flagged?: boolean; source?: string; operator?: string }) =>
      get<{ items: any[]; total: number; page: number; per_page: number }>("/api/v1/scans", params as any),

    detail: (id: string) => get<any>(`/api/v1/scans/${id}`),

    flag: (id: string, flagged: boolean) =>
      patch<any>(`/api/v1/scans/${id}/flag`, { flagged }),

    override: (id: string, data: { cultivar?: string; ripeness?: string; finger_count?: number; spoilage_days?: string }) =>
      patch<any>(`/api/v1/scans/${id}`, data),

    updateStatus: (id: string, status: string) =>
      patch<any>(`/api/v1/scans/${id}`, { inventory_status: status }),

    notes: {
      list: (scanId: string) => get<any[]>(`/api/v1/scans/${scanId}/notes`),
      add: (scanId: string, note: string) => post<any>(`/api/v1/scans/${scanId}/notes`, { note }),
    },
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
    list: () => get<{ items: any[]; total: number }>("/api/v1/users"),
    create: (data: any) => post<any>("/api/v1/users", data),
    update: (id: string, data: any) => patch<any>(`/api/v1/users/${id}`, data),
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
    update: (id: string, data: any) => patch<any>(`/api/v1/intakes/${id}`, data),
  },

  // ── Analytics ────────────────────────────────────────────────────────────
  analytics: {
    summary: (params?: { days?: number }) => get<any>("/api/v1/analytics/summary", params as any),
  },

  // ── Activity ─────────────────────────────────────────────────────────────
  activity: {
    list: (params?: { page?: number; per_page?: number; action?: string }) =>
      get<{ items: any[]; total: number }>("/api/v1/activity", params as any),
  },

  // ── Config ───────────────────────────────────────────────────────────────
  config: {
    get: () => get<any>("/api/v1/config"),
    update: (data: any) => patch<any>("/api/v1/config", data),
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

  // ── Health ───────────────────────────────────────────────────────────────
  health: () => get<{ status: string; cameras_online: number; cameras_total: number; yolo_loaded: boolean; rfr_loaded: boolean; sensor_connected: boolean }>("/health"),
}
