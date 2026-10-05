import React, { createContext, useContext, useState, useCallback, useEffect } from "react"
import { api } from "@/lib/api"
import { collectScanPages, storedTimestamp } from "@/lib/scanData"
import { useAuth } from "@/context/AuthContext"
import type { User, Device, ActivityLog, SystemConfig } from "@/types"
import type { ApiUser, ApiDevice, ApiActivity, ApiUserUpdate, ApiConfig } from "@/types/api"
import { useLocation } from "react-router-dom"

// ── Types ───────────────────────────────────────────────────────────────────

interface AdminContextType {
  users: User[]
  devices: Device[]
  activityLogs: ActivityLog[]
  activityLoading: boolean
  activityError: string | null
  config: SystemConfig
  addUser: (user: Omit<User, "id">) => Promise<{ user: User; password: string; pin?: string }>
  updateUser: (id: string, data: Partial<User>) => Promise<User>
  resetPassword: (id: string) => Promise<string>
  resetPin: (id: string) => Promise<string>
  updateConfig: (cfg: Partial<SystemConfig>) => Promise<SystemConfig>
  /** Self-service profile update — avatar changes that any user can perform. */
  updateOwnProfile: (data: { avatar?: string }) => Promise<void>
  /** Called by ScanContext WebSocket handler when a device:status event arrives. */
  updateDeviceFromWs: (cameraId: string, status: string, lastSeen?: string) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const AdminContext = createContext<AdminContextType | null>(null)

// ── Mappers ─────────────────────────────────────────────────────────────────

const mapApiUser = (u: ApiUser): User => ({
  id: u.id,
  username: u.username,
  fullName: u.full_name,
  role: u.role,
  status: u.status,
  lastActive: u.last_active ?? "Never",
  avatar: u.avatar_url || undefined,
  requiresPasswordChange: u.requires_password_change,
  requiresPinChange: u.requires_pin_change,
})

const mapApiDevice = (d: ApiDevice): Device => ({
  id: d.id,
  cameraId: d.camera_id,
  label: d.label,
  status: d.status,
  resolution: d.resolution ?? "Unknown",
  lastSeen: d.last_seen ?? "Never",
})

const mapApiActivityLog = (a: ApiActivity): ActivityLog => ({
  id: a.id,
  timestamp: storedTimestamp(a.created_at),
  user: a.user_name ?? "System",
  action: a.action,
  details: a.details ?? "",
  ipAddress: a.ip_address ?? undefined,
})

// ── Provider ────────────────────────────────────────────────────────────────

function useScopedState<T>(scope: string, initial: T): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState({ scope, value: initial })
  // React discards this render and retries with the new scope before children commit.
  if (state.scope !== scope) setState({ scope, value: initial })
  const setValue = useCallback((action: React.SetStateAction<T>) => {
    setState(previous => {
      // Ignore late requests issued by an account that has since signed out/swapped.
      if (previous.scope !== scope) return previous
      const value = typeof action === "function" ? (action as (value: T) => T)(previous.value) : action
      return { scope, value }
    })
  }, [scope])
  return [state.scope === scope ? state.value : initial, setValue]
}

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const { user, updateAuthUser } = useAuth()
  const { pathname } = useLocation()
  const scope = `${user?.id ?? "anonymous"}:${user?.role ?? "none"}`

  const [users, setUsers] = useScopedState<User[]>(scope, [])
  const [devices, setDevices] = useScopedState<Device[]>(scope, [])
  const [activityLogs, setActivityLogs] = useScopedState<ActivityLog[]>(scope, [])
  const [activityLoading, setActivityLoading] = useScopedState(scope, user?.role === "Admin")
  const [activityError, setActivityError] = useScopedState<string | null>(scope, null)
  const [config, setConfig] = useScopedState<SystemConfig>(scope, { cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85, dataRetentionEnabled: true })

  // ── Load data on mount / navigation ─────────────────────────────────────

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    const loadData = async () => {
      await Promise.resolve()
      if (controller.signal.aborted) return
      setActivityLoading(user.role === "Admin")
      setActivityError(null)
      try {
        const [usersRes, devicesRes, activityRes, configRes] = await Promise.allSettled([
          user.role === "Admin" ? api.users.list() : Promise.resolve({ items: [], total: 0 }),
          api.devices.list(),
          user.role === "Admin" ? collectScanPages((page, page_size, signal) => api.activity.list({ page, page_size }, signal), controller.signal) : Promise.resolve([]),
          api.config.get(),
        ])
        if (controller.signal.aborted) return

        if (usersRes.status === "fulfilled") {
          setUsers(usersRes.value.items.map(mapApiUser))
        } else {
          console.warn("[AdminContext] Users API unavailable")
        }

        if (devicesRes.status === "fulfilled") {
          setDevices(devicesRes.value.map(mapApiDevice))
        } else {
          console.warn("[AdminContext] Devices API unavailable")
        }

        if (activityRes.status === "fulfilled") {
          setActivityLogs(activityRes.value.map(mapApiActivityLog))
        } else {
          console.warn("[AdminContext] Activity API unavailable")
          setActivityError("Activity history could not be loaded completely. Please reload to retry.")
        }
        setActivityLoading(false)

        if (configRes.status === "fulfilled") {
          setConfig({
            cameraIds: configRes.value.camera_ids,
            confidenceThreshold: configRes.value.confidence_threshold,
            dataRetentionEnabled: configRes.value.data_retention_enabled,
          })
        } else {
          console.warn("[AdminContext] Config API unavailable")
        }
      } catch (err) {
        if (controller.signal.aborted) return
        setActivityLoading(false)
        setActivityError("Activity history could not be loaded completely. Please reload to retry.")
        console.warn("[AdminContext] Backend unreachable", err)
      }
    }

    void loadData()
    return () => controller.abort()
  }, [user, pathname, setUsers, setDevices, setActivityLogs, setActivityLoading, setActivityError, setConfig])

  // ── CRUD Operations ─────────────────────────────────────────────────────

  const addUser = useCallback(async (data: Omit<User, "id">) => {
    const apiData = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
    }
    const result = await api.users.create(apiData)
    const savedUser = mapApiUser(result)
    setUsers((prev) => [...prev, savedUser])
    return { user: savedUser, password: result.temporary_password, pin: result.temporary_pin ?? undefined }
  }, [setUsers])

  const updateUser = useCallback(async (id: string, data: Partial<User>) => {
    const apiData: ApiUserUpdate = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
      requires_password_change: data.requiresPasswordChange,
      password_setup_reason: data.passwordSetupReason,
      requires_pin_change: data.requiresPinChange,
      pin_setup_reason: data.pinSetupReason,
      avatar_url: data.avatar,
    }

    const mapped = mapApiUser(await api.users.update(id, apiData))
    setUsers((prev) => prev.map((u) => (u.id === id ? mapped : u)))
    if (user?.id === id) {
      updateAuthUser({
        username: mapped.username,
        fullName: mapped.fullName,
        role: mapped.role,
        avatar: mapped.avatar,
      }, user)
    }
    return mapped
  }, [user, updateAuthUser, setUsers])

  const resetPassword = useCallback(async (id: string) => {
    const result = await api.users.resetPassword(id)
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
    return result.temporary_password
  }, [setUsers])

  const resetPin = useCallback(async (id: string) => {
    const result = await api.users.resetPin(id)
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPinChange: true, pinSetupReason: "pin_reset" }
      : u))
    return result.temporary_pin
  }, [setUsers])

  const updateConfig = useCallback(async (cfg: Partial<SystemConfig>) => {
    const apiData: Partial<ApiConfig> = {
      camera_ids: cfg.cameraIds,
      confidence_threshold: cfg.confidenceThreshold,
      data_retention_enabled: cfg.dataRetentionEnabled,
    }

    const saved = await api.config.update(apiData)
    const mapped: SystemConfig = {
      cameraIds: saved.camera_ids,
      confidenceThreshold: saved.confidence_threshold,
      dataRetentionEnabled: saved.data_retention_enabled,
    }
    setConfig(mapped)
    if (cfg.cameraIds !== undefined) {
      api.devices.list().then(res => setDevices(res.map(mapApiDevice))).catch(console.error)
    }
    return mapped
  }, [setConfig, setDevices])

  // ── PROFILE-01: Self-service avatar update ──────────────────────────────

  const updateOwnProfile = useCallback(async (data: { avatar?: string }) => {
    const saved = mapApiUser(await api.users.updateProfile({ avatar_url: data.avatar }))
    setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)))
    if (user?.id === saved.id) {
      updateAuthUser({ avatar: saved.avatar }, user)
    }
  }, [user, updateAuthUser, setUsers])

  // ── WebSocket handler for device status ─────────────────────────────────

  const updateDeviceFromWs = useCallback((cameraId: string, status: string, lastSeen?: string) => {
    if (status !== "Online" && status !== "Offline") return
    setDevices((prev) =>
      prev.map((d) =>
        d.cameraId === cameraId
          ? { ...d, status, lastSeen: lastSeen ?? d.lastSeen }
          : d
      )
    )
  }, [setDevices])

  return (
    <AdminContext value={{
      users,
      devices,
      activityLogs,
      activityLoading,
      activityError,
      config,
      addUser,
      updateUser,
      resetPassword,
      resetPin,
      updateConfig,
      updateOwnProfile,
      updateDeviceFromWs,
    }}>
      {children}
    </AdminContext>
  )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useAdmin() {
  const ctx = useContext(AdminContext)
  if (!ctx) throw new Error("useAdmin must be inside AdminProvider")
  return ctx
}
