import React, { createContext, useContext, useState, useCallback, useRef } from "react"
import { api } from "@/lib/api"
import {
  setToken,
  clearAuth,
  getStoredUser,
  setStoredUser,
  type AuthUser,
} from "@/lib/auth"
import type { Role } from "@/types"

// ── Types ───────────────────────────────────────────────────────────────────

interface AuthContextType {
  user: AuthUser | null
  login: (username: string, password?: string) =>
    Promise<
      | "success"
      | "failed"
      | "inactive"
      | "requires_password_change"
      | "requires_password_change_new_account"
      | "requires_password_change_reset"
    >
  /** Self-service password change — requires current password for verification. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>
  /** First-time / post-reset password setup — user proved identity at login. */
  setupPasswordAndLogin: (username: string, newPassword: string) => Promise<boolean>
  /** Self-service PIN change — requires current PIN for verification. */
  changePin: (currentPin: string, newPin: string) => Promise<boolean>
  /** First-time / post-reset PIN setup — user proved identity at PIN swap. */
  setupPinAndLogin: (username: string, newPin: string) => Promise<boolean>
  logout: () => void
  switchOperator: (username: string, pin: string) => Promise<"success" | "failed" | "inactive" | "requires_pin_change" | "requires_pin_change_new_account" | "requires_pin_change_reset">
  /** Update the currently authenticated user's data (for cross-context profile edits). */
  updateAuthUser: (data: Partial<AuthUser>) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | null>(null)

// ── Provider ────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())

  const passwordSetup = useRef<{ username: string; token: string } | null>(null)
  const pinSetup = useRef<{ username: string; token: string } | null>(null)

  // ── Login ───────────────────────────────────────────────────────────────

  const login = useCallback(async (username: string, password?: string) => {
    try {
      passwordSetup.current = null
      const res = await api.auth.login(username, password || "")

      // Check status for password change requirements
      if (res.status === "requires_password_change") {
        if (!res.setup_token) return "failed" as const
        passwordSetup.current = { username, token: res.setup_token }
        if (res.reason === "new_account") return "requires_password_change_new_account" as const
        if (res.reason === "password_reset") return "requires_password_change_reset" as const
        return "requires_password_change" as const
      }

      if (res.status === "inactive") {
        return "inactive" as const
      }

      if (res.status === "failed" || !res.token || !res.user) {
        return "failed" as const
      }

      // Save token and user
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch {
      return "failed" as const
    }
  }, [])

  // ── Switch Operator ─────────────────────────────────────────────────────

  const switchOperator = useCallback(async (username: string, pin: string) => {
    try {
      pinSetup.current = null
      const res = await api.auth.swap(username, pin)

      // Check status for PIN change requirements
      if (res.status === "requires_pin_change") {
        if (!res.setup_token) return "failed" as const
        pinSetup.current = { username, token: res.setup_token }
        if (res.reason === "new_account") return "requires_pin_change_new_account" as const
        if (res.reason === "pin_reset") return "requires_pin_change_reset" as const
        return "requires_pin_change" as const
      }

      if (res.status === "inactive") {
        return "inactive" as const
      }

      if (res.status === "failed" || !res.token || !res.user) {
        return "failed" as const
      }

      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch {
      return "failed" as const
    }
  }, [])

  // ── Logout ──────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    api.auth.logout().catch(() => {})
    passwordSetup.current = null
    pinSetup.current = null
    clearAuth()
    setUser(null)
  }, [])

  // ── Self-service Password Change (requires current password) ────────────

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    try {
      const res = await api.auth.changePassword(currentPassword, newPassword)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])

  // ── First-time / Post-reset Password Setup ──────────────────────────────

  const setupPasswordAndLogin = useCallback(async (username: string, newPassword: string) => {
    if (!newPassword || passwordSetup.current?.username !== username) return false
    try {
      const res = await api.auth.setupPassword(passwordSetup.current.token, newPassword)
      passwordSetup.current = null
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])

  // ── Self-service PIN Change (requires current PIN) ──────────────────────

  const changePin = useCallback(async (currentPin: string, newPin: string) => {
    try {
      const res = await api.auth.changePin(currentPin, newPin)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])

  // ── First-time / Post-reset PIN Setup ───────────────────────────────────

  const setupPinAndLogin = useCallback(async (username: string, newPin: string) => {
    if (!newPin || pinSetup.current?.username !== username) return false
    try {
      const res = await api.auth.setupPin(pinSetup.current.token, newPin)
      pinSetup.current = null
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])

  // ── Update Auth User (cross-context) ────────────────────────────────────

  const updateAuthUser = useCallback((data: Partial<AuthUser>) => {
    setUser((prev) => {
      if (!prev) return prev
      const updated = { ...prev, ...data }
      setStoredUser(updated)
      return updated
    })
  }, [])

  return (
    <AuthContext value={{
      user,
      login,
      changePassword,
      setupPasswordAndLogin,
      changePin,
      setupPinAndLogin,
      logout,
      switchOperator,
      updateAuthUser,
    }}>
      {children}
    </AuthContext>
  )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be inside AuthProvider")
  return ctx
}
