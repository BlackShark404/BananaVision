import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react"
import { api } from "@/lib/api"
import { setStoredUser } from "@/lib/auth"
import { useAuth } from "@/context/AuthContext"
import type { User, Device, ActivityLog, SystemConfig } from "@/types"

// ── Types ───────────────────────────────────────────────────────────────────

interface AdminContextType {
  users: User[]
  devices: Device[]
  activityLogs: ActivityLog[]
  config: SystemConfig
  addUser: (user: Omit<User, "id">) => void
  updateUser: (id: string, data: Partial<User>) => void
  updateConfig: (cfg: Partial<SystemConfig>) => void
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
  timestamp: a.created_at || a.timestamp || new Date().toISOString(),
  user: a.user_name || a.user || "System",
  action: a.action,
  details: a.details,
  ipAddress: a.ip_address || a.ipAddress,
})

// ── Provider ────────────────────────────────────────────────────────────────

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const { user, updateAuthUser } = useAuth()

  const [users, setUsers] = useState<User[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([])
  const [config, setConfig] = useState<SystemConfig>({ cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85, dataRetentionEnabled: true })

  const dataLoadedRef = useRef(false)

  // ── Load data on mount ──────────────────────────────────────────────────

  useEffect(() => {
    if (!user || dataLoadedRef.current) return
    dataLoadedRef.current = true

    const loadData = async () => {
      try {
        const [usersRes, devicesRes, activityRes, configRes] = await Promise.allSettled([
          api.users.list(),
          api.devices.list(),
          api.activity.list({ per_page: 100 }),
          api.config.get(),
        ])

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
          const raw = (activityRes.value as any).items || activityRes.value as any
          setActivityLogs(Array.isArray(raw) ? raw.map(mapApiActivityLog) : [])
        } else {
          console.warn("[AdminContext] Activity API unavailable")
        }

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

    loadData()
  }, [user])

  // ── Reset on logout ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) {
      dataLoadedRef.current = false
      setUsers([])
      setDevices([])
      setActivityLogs([])
    }
  }, [user])

  // ── CRUD Operations ─────────────────────────────────────────────────────

  const addUser = useCallback((data: Omit<User, "id">) => {
    const apiData = {
      username: data.username,
      full_name: data.fullName,
      role: data.role,
      password: data.password || "banana123",
      pin: data.pin
    }
    api.users.create(apiData)
      .then((newUser) => setUsers((prev) => [...prev, mapApiUser(newUser)]))
      .catch(() => setUsers((prev) => [...prev, { ...data, id: Math.random().toString(36).substring(2, 10) } as User]))
  }, [])

  const updateUser = useCallback((id: string, data: Partial<User>) => {
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

    const applyLocally = () => {
      setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...data } : u)))
      // Update auth user if editing own profile
      if (user && user.id === id) {
        updateAuthUser(data as any)
      }
    }

    api.users.update(id, apiData)
      .then((updated) => {
        const mapped = mapApiUser(updated)
        setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...mapped } : u)))
        if (user && user.id === id) {
          updateAuthUser(data as any)
        }
      })
      .catch(() => applyLocally())
  }, [user, updateAuthUser])

  const updateConfig = useCallback((cfg: Partial<SystemConfig>) => {
    const apiData: Record<string, unknown> = {
      camera_ids: cfg.cameraIds,
      confidence_threshold: cfg.confidenceThreshold,
      data_retention_enabled: cfg.dataRetentionEnabled,
    }
    // Remove undefined
    Object.keys(apiData).forEach(k => apiData[k] === undefined && delete apiData[k])

    api.config.update(apiData)
      .then(() => {
        // Try to fetch updated devices from backend
        api.devices.list().then(res => setDevices((res as any[]).map(mapApiDevice))).catch(console.error)
      })
      .catch(() => {
        console.warn("[AdminContext] Config update failed")
      })
    setConfig((prev) => ({ ...prev, ...cfg }))
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
      config,
      addUser,
      updateUser,
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
