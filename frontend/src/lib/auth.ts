/**
 * Auth token management — localStorage wrappers.
 */

import { clearScanWrites } from "@/lib/scanWrites"

const TOKEN_KEY = "bananavision_token"
const USER_KEY = "bananavision_user"

export interface AuthUser {
  id: string
  username: string
  fullName: string
  role: "Admin" | "Operator"
  avatar?: string
}

// ── Token ───────────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  clearScanWrites()
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  clearScanWrites()
  localStorage.removeItem(TOKEN_KEY)
}

// ── User ────────────────────────────────────────────────────────────────────

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearStoredUser(): void {
  localStorage.removeItem(USER_KEY)
}

// ── Helpers ─────────────────────────────────────────────────────────────────

export function isAuthenticated(): boolean {
  return !!getToken()
}

export function clearAuth(): void {
  clearToken()
  clearStoredUser()
}
