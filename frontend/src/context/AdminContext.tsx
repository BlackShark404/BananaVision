import React, { createContext, useContext, useState, useCallback, useEffect, useRef, useMemo } from "react"
import { api } from "@/lib/api"
import { collectScanPages, storedTimestamp } from "@/lib/scanData"
import { useAuth } from "@/context/AuthContext"
import type { User, Device, ActivityLog, SystemConfig } from "@/types"
import type { ApiUser, ApiDevice, ApiActivity, ApiUserUpdate, ApiConfigUpdate, ApiConfig } from "@/types/api"
import { useLocation } from "react-router-dom"

// ── Types ───────────────────────────────────────────────────────────────────

interface AdminContextType {
  users: User[]
  usersReady: boolean
  usersLoading: boolean
  usersError: string | null
  devices: Device[]
  devicesReady: boolean
  devicesLoading: boolean
  devicesError: string | null
  activityLogs: ActivityLog[]
  activityReady: boolean
  activityLoading: boolean
  activityError: string | null
  configReady: boolean
  configError: string | null
  configConflict: boolean
  reloadConfig: () => Promise<void>
  acceptConfig: (saved: ApiConfig) => void
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

const mapConfig = (saved: ApiConfig): SystemConfig => ({
  cameraIds: saved.camera_ids, confidenceThreshold: saved.confidence_threshold,
  detectionConfidenceThreshold: saved.detection_confidence_threshold,
  dataRetentionEnabled: saved.data_retention_enabled, revision: saved.revision,
  cameraDeviceIds: saved.camera_device_ids, appliedRevision: saved.applied_revision,
  applicationStatus: saved.application_status, applicationError: saved.application_error,
  restartRequired: saved.restart_required, retentionDays: saved.retention_days,
  retentionPolicy: saved.retention_policy, legacyConflict: saved.legacy_conflict,
})

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

  // Each account scope owns its request generation; late writes cannot cancel a new account read.
  const usersRequests = useMemo(() => ({ scope, generation: 0 }), [scope])
  const [users, setUsers] = useScopedState<User[]>(scope, [])
  const [devices, setDevices] = useScopedState<Device[]>(scope, [])
  const [activityLogs, setActivityLogs] = useScopedState<ActivityLog[]>(scope, [])
  const [activityLoading, setActivityLoading] = useScopedState(scope, user?.role === "Admin")
  const [activityError, setActivityError] = useScopedState<string | null>(scope, null)
  const [usersReady, setUsersReady] = useScopedState(scope, false)
  const [usersLoading, setUsersLoading] = useScopedState(scope, Boolean(user?.role === "Admin"))
  const [usersError, setUsersError] = useScopedState<string | null>(scope, null)
  const [usersReload, setUsersReload] = useScopedState(scope, 0)
  const [devicesReady, setDevicesReady] = useScopedState(scope, false)
  const [devicesLoading, setDevicesLoading] = useScopedState(scope, Boolean(user))
  const [devicesError, setDevicesError] = useScopedState<string | null>(scope, null)
  const [activityReady, setActivityReady] = useScopedState(scope, false)
  const [config, setConfig] = useScopedState<SystemConfig>(scope, { cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85, dataRetentionEnabled: true })
  const acceptUserWrite = useCallback(() => {
    ++usersRequests.generation
    setUsersLoading(false)
    setUsersError(null)
    if (!usersReady) setUsersReload(value => value + 1)
  }, [usersRequests, usersReady, setUsersLoading, setUsersError, setUsersReload])

  // ── Load data on mount / navigation ─────────────────────────────────────

  const [configReady, setConfigReady] = useScopedState(scope, false)
  const [configError, setConfigError] = useScopedState<string | null>(scope, null)
  const [configConflict, setConfigConflict] = useScopedState(scope, false)
  const configRequests = useRef(0)
  const acceptConfig = useCallback((saved: ApiConfig) => {
    setConfig(previous => (previous.revision ?? 0) > saved.revision ? previous : mapConfig(saved))
    setConfigReady(true)
    setConfigError(null)
  }, [setConfig, setConfigReady, setConfigError])
  const reloadConfig = useCallback(async () => {
    if (!user) return
    const generation = ++configRequests.current
    try {
      const saved = await api.config.get()
      if (generation !== configRequests.current) return
      acceptConfig(saved)
      setConfigConflict(false)
    } catch (error) {
      if (generation === configRequests.current) setConfigError(error instanceof Error ? error.message : "Configuration unavailable")
    }
  }, [acceptConfig, setConfigConflict, setConfigError, user])
  useEffect(() => { void reloadConfig(); return () => { configRequests.current++ } }, [reloadConfig])

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    const loadData = async () => {
      await Promise.resolve()
      if (controller.signal.aborted) return
      setActivityLoading(user.role === "Admin")
      setActivityError(null)
      const usersGeneration = ++usersRequests.generation
      setUsersLoading(user.role === "Admin")
      setDevicesLoading(true)
      setUsersError(null)
      setDevicesError(null)
      await Promise.allSettled([
        (async () => {
          try {
            const result = user.role === "Admin" ? await api.users.list() : { items: [] }
            if (controller.signal.aborted || usersGeneration !== usersRequests.generation) return
            setUsers(result.items.map(mapApiUser))
            setUsersReady(true)
          } catch {
            if (!controller.signal.aborted && usersGeneration === usersRequests.generation) setUsersError("Users could not be loaded. Please reload to retry.")
          } finally {
            if (!controller.signal.aborted && usersGeneration === usersRequests.generation) setUsersLoading(false)
          }
        })(),
        (async () => {
          try {
            const result = await api.devices.list()
            if (controller.signal.aborted) return
            setDevices(result.map(mapApiDevice))
            setDevicesReady(true)
          } catch {
            if (!controller.signal.aborted) setDevicesError("Devices could not be loaded. Please reload to retry.")
          } finally {
            if (!controller.signal.aborted) setDevicesLoading(false)
          }
        })(),
        (async () => {
          try {
            const result = user.role === "Admin"
              ? await collectScanPages((page, page_size, signal) => api.activity.list({ page, page_size }, signal), controller.signal)
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
      ])
    }

    void loadData()
    return () => controller.abort()
  }, [user, pathname, usersRequests, usersReload, setUsers, setDevices, setActivityLogs, setActivityLoading, setActivityError, setUsersLoading, setUsersReady, setUsersError, setDevicesLoading, setDevicesReady, setDevicesError, setActivityReady])

  // ── CRUD Operations ─────────────────────────────────────────────────────

  const addUser = useCallback(async (data: Omit<User, "id">) => {
    const apiData = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
    }
    const result = await api.users.create(apiData)
    acceptUserWrite()
    const savedUser = mapApiUser(result)
    setUsers((prev) => [...prev, savedUser])
    return { user: savedUser, password: result.temporary_password, pin: result.temporary_pin ?? undefined }
  }, [setUsers, acceptUserWrite])

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
    acceptUserWrite()
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
  }, [user, updateAuthUser, setUsers, acceptUserWrite])

  const resetPassword = useCallback(async (id: string) => {
    const result = await api.users.resetPassword(id)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
    return result.temporary_password
  }, [setUsers, acceptUserWrite])

  const resetPin = useCallback(async (id: string) => {
    const result = await api.users.resetPin(id)
    acceptUserWrite()
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPinChange: true, pinSetupReason: "pin_reset" }
      : u))
    return result.temporary_pin
  }, [setUsers, acceptUserWrite])

  const updateConfig = useCallback(async (cfg: Partial<SystemConfig>) => {
    if (!configReady || configConflict || !config.revision) throw new Error("Reload saved settings before making changes")
    const apiData: ApiConfigUpdate = { expected_revision: config.revision }
    if (cfg.cameraIds !== undefined && cfg.cameraIds !== config.cameraIds) apiData.camera_ids = cfg.cameraIds
    if (cfg.cameraDeviceIds !== undefined && JSON.stringify(cfg.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds)) apiData.camera_device_ids = cfg.cameraDeviceIds
    if (cfg.confidenceThreshold !== undefined && cfg.confidenceThreshold !== config.confidenceThreshold) apiData.confidence_threshold = cfg.confidenceThreshold
    if (cfg.dataRetentionEnabled !== undefined && cfg.dataRetentionEnabled !== config.dataRetentionEnabled) apiData.data_retention_enabled = cfg.dataRetentionEnabled
    if (Object.keys(apiData).length === 1) return config
    ++configRequests.current
    try {
      const saved = await api.config.update(apiData)
      acceptConfig(saved)
      if (apiData.camera_ids !== undefined || apiData.camera_device_ids !== undefined) api.devices.list().then(res => setDevices(res.map(mapApiDevice))).catch(console.error)
      return mapConfig(saved)
    } catch (error) {
      if ((error as { status?: number }).status === 409) setConfigConflict(true)
      throw error
    }
  }, [config, configReady, configConflict, acceptConfig, setConfigConflict, setDevices])

  // ── PROFILE-01: Self-service avatar update ──────────────────────────────

  const updateOwnProfile = useCallback(async (data: { avatar?: string }) => {
    const saved = mapApiUser(await api.users.updateProfile({ avatar_url: data.avatar }))
    acceptUserWrite()
    setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)))
    if (user?.id === saved.id) {
      updateAuthUser({ avatar: saved.avatar }, user)
    }
  }, [user, updateAuthUser, setUsers, acceptUserWrite])

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
      users, usersLoading, usersReady, usersError,
      devices, devicesLoading, devicesReady, devicesError,
      activityLogs,
      activityLoading, activityReady,
      activityError,
      config, configReady, configError, configConflict, reloadConfig, acceptConfig,
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
