import React, { createContext, useContext, useState, useCallback, useEffect } from "react"
import { api } from "@/lib/api"
import { collectScanPages, storedTimestamp } from "@/lib/scanData"
import { useAuth } from "@/context/AuthContext"
import type { User, Device, ActivityLog, SystemConfig } from "@/types"
import { useLocation } from "react-router-dom"

// ── Types ───────────────────────────────────────────────────────────────────

interface AdminContextType {
  users: User[]
  devices: Device[]
  activityLogs: ActivityLog[]
  activityLoading: boolean
  activityError: string | null
  config: SystemConfig
  addUser: (user: Omit<User, "id">) => Promise<User>
  updateUser: (id: string, data: Partial<User>) => Promise<User>
  resetPassword: (id: string) => Promise<void>
  resetPin: (id: string) => Promise<void>
  updateConfig: (cfg: Partial<SystemConfig>) => Promise<SystemConfig>
  /** Called by ScanContext WebSocket handler when a device:status event arrives. */
  updateDeviceFromWs: (cameraId: string, status: string, lastSeen?: string) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const AdminContext = createContext<AdminContextType | null>(null)

// ── Mappers ─────────────────────────────────────────────────────────────────

const mapApiUser = (u: any): User => ({
  id: u.id,
  username: u.username,
  fullName: u.full_name || u.fullName || "",
  role: u.role,
  status: u.status || "Active",
  lastActive: u.last_active || u.lastActive || "Never",
  avatar: u.avatar_url || u.avatar,
  requiresPasswordChange: u.requires_password_change ?? u.requiresPasswordChange,
  passwordSetupReason: u.password_setup_reason || u.passwordSetupReason,
  requiresPinChange: u.requires_pin_change ?? u.requiresPinChange,
  pinSetupReason: u.pin_setup_reason || u.pinSetupReason,
})

const mapApiDevice = (d: any): Device => ({
  id: d.id,
  cameraId: d.camera_id || d.cameraId,
  label: d.label,
  status: d.status,
  resolution: d.resolution,
  lastSeen: d.last_seen || d.lastSeen || new Date().toISOString(),
})

const mapApiActivityLog = (a: any): ActivityLog => ({
  id: a.id,
  timestamp: storedTimestamp(a.created_at ?? a.timestamp),
  user: a.user_name || a.user || "System",
  action: a.action,
  details: a.details,
  ipAddress: a.ip_address || a.ipAddress,
})

// ── Provider ────────────────────────────────────────────────────────────────

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const { user, updateAuthUser } = useAuth()
  const { pathname } = useLocation()

  const [users, setUsers] = useState<User[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([])
  const [activityLoading, setActivityLoading] = useState(false)
  const [activityError, setActivityError] = useState<string | null>(null)
  const [config, setConfig] = useState<SystemConfig>({ cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85, dataRetentionEnabled: true })

  // ── Load data on mount / navigation ─────────────────────────────────────

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    setActivityLoading(true)
    setActivityError(null)

    const loadData = async () => {
      try {
        const [usersRes, devicesRes, activityRes, configRes] = await Promise.allSettled([
          api.users.list(),
          api.devices.list(),
          collectScanPages((page, page_size, signal) => api.activity.list({ page, page_size }, signal), controller.signal),
          api.config.get(),
        ])
        if (controller.signal.aborted) return

        if (usersRes.status === "fulfilled") {
          const raw = usersRes.value.items || usersRes.value as any
          setUsers(Array.isArray(raw) ? raw.map(mapApiUser) : [])
        } else {
          console.warn("[AdminContext] Users API unavailable")
        }

        if (devicesRes.status === "fulfilled") {
          setDevices((devicesRes.value as any[]).map(mapApiDevice))
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
        console.warn("[AdminContext] Backend unreachable", err)
      }
    }

    void loadData()
    return () => controller.abort()
  }, [user, pathname])

  // ── Reset on logout ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) {
      setUsers([])
      setDevices([])
      setActivityLogs([])
      setActivityLoading(false)
      setActivityError(null)
    }
  }, [user])

  // ── CRUD Operations ─────────────────────────────────────────────────────

  const addUser = useCallback(async (data: Omit<User, "id">) => {
    const apiData = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      status: data.status,
      password: data.password || "banana123",
      pin: data.pin
    }
    const savedUser = mapApiUser(await api.users.create(apiData))
    setUsers((prev) => [...prev, savedUser])
    return savedUser
  }, [])

  const updateUser = useCallback(async (id: string, data: Partial<User>) => {
    const apiData: any = { ...data }
    if (data.fullName !== undefined) apiData.full_name = data.fullName
    if (data.requiresPasswordChange !== undefined) apiData.requires_password_change = data.requiresPasswordChange
    if (data.passwordSetupReason !== undefined) apiData.password_setup_reason = data.passwordSetupReason
    if (data.requiresPinChange !== undefined) apiData.requires_pin_change = data.requiresPinChange
    if (data.pinSetupReason !== undefined) apiData.pin_setup_reason = data.pinSetupReason
    if (data.avatar !== undefined) {
      apiData.avatar_url = data.avatar
      delete apiData.avatar
    }

    const mapped = mapApiUser(await api.users.update(id, apiData))
    setUsers((prev) => prev.map((u) => (u.id === id ? mapped : u)))
    if (user?.id === id) {
      updateAuthUser({
        username: mapped.username,
        fullName: mapped.fullName,
        role: mapped.role,
        avatar: mapped.avatar,
      })
    }
    return mapped
  }, [user, updateAuthUser])

  const resetPassword = useCallback(async (id: string) => {
    await api.users.resetPassword(id, "banana123")
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPasswordChange: true, passwordSetupReason: "password_reset" }
      : u))
  }, [])

  const resetPin = useCallback(async (id: string) => {
    await api.users.resetPin(id, "1234")
    setUsers(prev => prev.map(u => u.id === id
      ? { ...u, requiresPinChange: true, pinSetupReason: "pin_reset" }
      : u))
  }, [])

  const updateConfig = useCallback(async (cfg: Partial<SystemConfig>) => {
    const apiData: Record<string, unknown> = {
      camera_ids: cfg.cameraIds,
      confidence_threshold: cfg.confidenceThreshold,
      data_retention_enabled: cfg.dataRetentionEnabled,
    }
    // Remove undefined
    Object.keys(apiData).forEach(k => apiData[k] === undefined && delete apiData[k])

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
  }, [])

  // ── WebSocket handler for device status ─────────────────────────────────

  const updateDeviceFromWs = useCallback((cameraId: string, status: string, lastSeen?: string) => {
    setDevices((prev) =>
      prev.map((d) =>
        d.cameraId === cameraId
          ? { ...d, status: status as any, lastSeen: lastSeen || new Date().toISOString() }
          : d
      )
    )
  }, [])

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
