import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react"
import {
  generateScanResults,
  generateUsers,
  generateDevices,
  generateActivityLogs,
  generateIntakes,
  generateSuppliers,
} from "@/lib/mock-data"
import { getSpoilageDays, getBananaImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import {
  getToken,
  setToken,
  clearAuth,
  getStoredUser,
  setStoredUser,
  type AuthUser,
} from "@/lib/auth"
import { useWebSocket } from "@/hooks/useWebSocket"
import type {
  ScanResult,
  User,
  Device,
  ActivityLog,
  Cultivar,
  Ripeness,
  Role,
  InventoryStatus,
  DailyIntake,
  Supplier,
  ScanNote,
  SystemConfig,
} from "@/types"

interface ScanState {
  isScanning: boolean
  scanStep: number
  scanStepLabel: string
  scanProgress: number
  lastResult: ScanResult | null
}

interface AppContextType {
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
  changePasswordAndLogin: (username: string, newPassword?: string) => Promise<boolean>
  changePinAndLogin: (username: string, newPin?: string) => Promise<boolean>
  logout: () => void
  switchOperator: (username: string, pin: string) => Promise<"success" | "failed" | "inactive" | "requires_pin_change" | "requires_pin_change_new_account" | "requires_pin_change_reset">
  scanState: ScanState
  startScan: (source?: string) => void
  scans: ScanResult[]
  users: User[]
  devices: Device[]
  activityLogs: ActivityLog[]
  addUser: (user: Omit<User, "id">) => void
  updateUser: (id: string, data: Partial<User>) => void
  flagScan: (id: string, flagged: boolean) => void
  addScanNote: (scanId: string, note: string) => void
  getScanNotes: (scanId: string) => ScanNote[]
  updateScanData: (id: string, data: Partial<ScanResult>) => void
  config: SystemConfig
  updateConfig: (cfg: Partial<SystemConfig>) => void
  intakes: DailyIntake[]
  startIntake: (supplierId: string, batchNumber: string) => Promise<DailyIntake | undefined>
  activeIntake: DailyIntake | null
  setActiveIntake: (intake: DailyIntake | null) => void
  bulkUpdateIntakeInventory: (intakeId: string, status: InventoryStatus) => void
  suppliers: Supplier[]
  addSupplier: (supplierData: Omit<Supplier, "id" | "dateAdded">) => void
  updateSupplier: (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => void
  updateSupplierStatus: (id: string, status: "Active" | "Inactive") => void
}

// ── Mock fallback data (used when backend is unreachable) ───────────────────
const FALLBACK_SCANS = generateScanResults(40)
const FALLBACK_INTAKES = generateIntakes(FALLBACK_SCANS)

const AppContext = createContext<AppContextType | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())

  const [scans, setScans] = useState<ScanResult[]>([])
  const [intakes, setIntakes] = useState<DailyIntake[]>([])
  const [activeIntake, setActiveIntake] = useState<DailyIntake | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([])

  const [config, setConfig] = useState<SystemConfig>({ cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85 })
  const [scanNotes, setScanNotes] = useState<ScanNote[]>([])
  const [scanState, setScanState] = useState<ScanState>({
    isScanning: false,
    scanStep: 0,
    scanStepLabel: "",
    scanProgress: 0,
    lastResult: null,
  })

  const scanTimeoutRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const dataLoadedRef = useRef(false)

  // ── Map backend snake_case user to frontend camelCase ──────────────────
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

  const mapApiSupplier = (s: any): Supplier => ({
    id: s.id,
    name: s.name,
    contactPerson: s.contact_person || s.contactPerson,
    contactPhone: s.contact_phone || s.contactPhone,
    status: s.status,
    dateAdded: s.date_added || s.dateAdded || new Date().toISOString(),
  })

  const mapApiIntake = useCallback((i: any): DailyIntake => ({
    id: i.id,
    supplierId: i.supplier_id || i.supplierId,
    supplierName: i.supplier_name || i.supplierName || i.source || "Unknown",
    batchNumber: i.batch_number || i.batchNumber,
    qrCode: i.qr_code || i.qrCode,
    date: i.intake_date || i.date || new Date().toISOString().split("T")[0],
    status: i.status as "Active" | "Depleted",
    scanCount: i.scan_count || i.scanCount || 0,
  }), [])

  const mapApiActivityLog = (a: any): ActivityLog => ({
    id: a.id,
    timestamp: a.created_at || a.timestamp || new Date().toISOString(),
    user: a.user_name || a.user || "System",
    action: a.action,
    details: a.details,
    ipAddress: a.ip_address || a.ipAddress,
  })

  const mapApiScan = (s: any): ScanResult => ({
    id: s.id,
    dateTime: s.scanned_at || s.dateTime || new Date().toISOString(),
    cultivar: s.cultivar,
    ripeness: s.ripeness,
    confidence: s.confidence,
    temperature: s.temperature,
    humidity: s.humidity,
    spoilageDays: s.spoilage_days || s.spoilageDays,
    fingerCount: s.finger_count || s.fingerCount,
    operator: s.operator_name || s.operator || "Unknown",
    source: s.supplier_name || s.source,
    thumbnailUrl: s.thumbnail_url || s.thumbnailUrl,
    intakeId: s.intake_id || s.intakeId,
    inventoryStatus: s.inventory_status || s.inventoryStatus || "In Stock",
    statusUpdatedAt: s.status_updated_at || s.statusUpdatedAt || new Date().toISOString(),
    flagged: s.flagged,
    isOverridden: s.is_overridden || s.isOverridden,
    originalAiResult: s.original_ai_result || s.originalAiResult,
  })

  // ── Load initial data from API on mount ─────────────────────────────────
  useEffect(() => {
    if (!user || dataLoadedRef.current) return
    dataLoadedRef.current = true

    const loadData = async () => {
      try {
        const [scansRes, usersRes, devicesRes, suppliersRes, intakesRes, activityRes] = await Promise.allSettled([
          api.scans.list({ per_page: 100 }),
          api.users.list(),
          api.devices.list(),
          api.suppliers.list(),
          api.intakes.list(),
          api.activity.list({ per_page: 100 }),
        ])

        if (scansRes.status === "fulfilled") {
          const raw = scansRes.value.items || scansRes.value as any
          setScans(Array.isArray(raw) ? raw.map(mapApiScan) : FALLBACK_SCANS)
        }
        else { console.warn("[AppContext] Scans API unavailable, using mock data"); setScans(FALLBACK_SCANS) }

        if (usersRes.status === "fulfilled") {
          const raw = usersRes.value.items || usersRes.value as any
          setUsers(Array.isArray(raw) ? raw.map(mapApiUser) : [])
        }
        else { console.warn("[AppContext] Users API unavailable, using mock data"); setUsers(generateUsers()) }

        if (devicesRes.status === "fulfilled") {
          setDevices((devicesRes.value as any[]).map(mapApiDevice))
        }
        else { console.warn("[AppContext] Devices API unavailable, using mock data"); setDevices(generateDevices()) }

        if (suppliersRes.status === "fulfilled") {
          setSuppliers((suppliersRes.value as any[]).map(mapApiSupplier))
        }
        else { console.warn("[AppContext] Suppliers API unavailable, using mock data"); setSuppliers(generateSuppliers()) }

        if (intakesRes.status === "fulfilled") {
          setIntakes((intakesRes.value as any[]).map(mapApiIntake))
        }
        else { console.warn("[AppContext] Intakes API unavailable, using mock data"); setIntakes(FALLBACK_INTAKES) }

        if (activityRes.status === "fulfilled") {
          const raw = (activityRes.value as any).items || activityRes.value as any
          setActivityLogs(Array.isArray(raw) ? raw.map(mapApiActivityLog) : [])
        }
        else { console.warn("[AppContext] Activity API unavailable, using mock data"); setActivityLogs(generateActivityLogs()) }

      } catch (err) {
        console.warn("[AppContext] Backend unreachable — loading mock data", err)
        setScans(FALLBACK_SCANS)
        setUsers(generateUsers())
        setDevices(generateDevices())
        setSuppliers(generateSuppliers())
        setIntakes(FALLBACK_INTAKES)
        setActivityLogs(generateActivityLogs())
      }
    }

    loadData()
  }, [user])

  // ── Reset data when user logs out ───────────────────────────────────────
  useEffect(() => {
    if (!user) {
      dataLoadedRef.current = false
    }
  }, [user])

  // ── WebSocket — real-time updates ───────────────────────────────────────
  const handleWsEvent = useCallback((event: string, data: any) => {
    switch (event) {
      case "scan:started":
        setScanState({ isScanning: true, scanStep: 1, scanStepLabel: "Capturing...", scanProgress: 20, lastResult: null })
        break

      case "scan:capturing":
        setScanState((s) => ({ ...s, scanStep: 1, scanStepLabel: `Capturing ${data.camera_label || ""}...`, scanProgress: 20 + (data.index / data.total) * 20 }))
        break

      case "scan:captured":
        setScanState((s) => ({ ...s, scanProgress: Math.min(s.scanProgress + 5, 50) }))
        break

      case "scan:detecting":
        setScanState((s) => ({ ...s, scanStep: 2, scanStepLabel: "Detecting...", scanProgress: 60 }))
        break

      case "scan:detected":
        setScanState((s) => ({ ...s, scanProgress: 70 }))
        break

      case "scan:analyzing":
        setScanState((s) => ({ ...s, scanStep: 3, scanStepLabel: "Analyzing...", scanProgress: 80 }))
        break

      case "scan:completed": {
        const result = data.result || data
        const scanResult: ScanResult = {
          id: result.id || result.scan_id,
          dateTime: result.scanned_at || result.dateTime || new Date().toISOString(),
          cultivar: result.cultivar,
          ripeness: result.ripeness,
          confidence: result.confidence,
          temperature: result.temperature,
          humidity: result.humidity,
          spoilageDays: result.spoilage_days || result.spoilageDays,
          fingerCount: result.finger_count || result.fingerCount,
          operator: result.operator || user?.fullName || "Unknown",
          source: result.source,
          thumbnailUrl: result.thumbnail_url || getBananaImageUrl(result.cultivar, result.ripeness),
          intakeId: result.intake_id || result.intakeId,
          inventoryStatus: result.inventory_status || "In Stock",
          statusUpdatedAt: result.status_updated_at || new Date().toISOString(),
        }
        setScans((prev) => [scanResult, ...prev])
        setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: scanResult })
        break
      }

      case "scan:failed":
        setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: null })
        break

      case "sensor:update":
        // Could update a sensor state atom here if needed
        break

      case "device:status":
        setDevices((prev) =>
          prev.map((d) =>
            d.cameraId === data.camera_id
              ? { ...d, status: data.status, lastSeen: data.last_seen || new Date().toISOString() }
              : d
          )
        )
        break
    }
  }, [user])

  useWebSocket({
    rooms: ["kiosk", "dashboard", "devices"],
    onEvent: handleWsEvent,
    enabled: !!user,
  })

  // ── Auth ────────────────────────────────────────────────────────────────

  const login = useCallback(async (username: string, password?: string) => {
    try {
      const res = await api.auth.login(username, password || "")

      // Check status for password change requirements
      if (res.status === "requires_password_change") {
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
      // Fallback: try local mock login
      const mockUsers = generateUsers()
      const found = mockUsers.find((u) => u.username === username)
      if (found && password === found.password) {
        if (found.status === "Inactive") return "inactive" as const
        const authUser: AuthUser = { id: found.id, username: found.username, fullName: found.fullName, role: found.role }
        setStoredUser(authUser)
        setUser(authUser)
        return "success" as const
      }
      return "failed" as const
    }
  }, [])

  const switchOperator = useCallback(async (username: string, pin: string) => {
    try {
      const res = await api.auth.swap(username, pin)

      // Check status for PIN change requirements
      if (res.status === "requires_pin_change") {
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
      // Fallback: local mock
      const mockUsers = generateUsers()
      const found = mockUsers.find((u) => u.username === username)
      if (found && found.pin === pin) {
        if (found.status === "Inactive") return "inactive" as const
        if (found.requiresPinChange) {
          if (found.pinSetupReason === "new_account") return "requires_pin_change_new_account" as const
          if (found.pinSetupReason === "pin_reset") return "requires_pin_change_reset" as const
          return "requires_pin_change" as const
        }
        const authUser: AuthUser = { id: found.id, username: found.username, fullName: found.fullName, role: found.role }
        setStoredUser(authUser)
        setUser(authUser)
        return "success" as const
      }
      return "failed" as const
    }
  }, [])

  const logout = useCallback(() => {
    api.auth.logout().catch(() => {})
    clearAuth()
    setUser(null)
    setScans([])
    setUsers([])
    setDevices([])
    setActivityLogs([])
    setSuppliers([])
    setIntakes([])
  }, [])

  const changePasswordAndLogin = useCallback(async (username: string, newPassword?: string) => {
    if (!newPassword) return false
    try {
      const res = await api.auth.changePassword(username, "", newPassword)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      // Fallback: local mock
      const mockUsers = generateUsers()
      const found = mockUsers.find((u) => u.username === username)
      if (found) {
        const authUser: AuthUser = { id: found.id, username: found.username, fullName: found.fullName, role: found.role }
        setStoredUser(authUser)
        setUser(authUser)
        return true
      }
      return false
    }
  }, [])

  const changePinAndLogin = useCallback(async (username: string, newPin?: string) => {
    if (!newPin) return false
    try {
      const res = await api.auth.changePin(username, newPin)
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])

  // ── Scan Pipeline ───────────────────────────────────────────────────────

  const startScan = useCallback((source?: string, simulate?: boolean) => {
    if (scanState.isScanning) return
    setScanState({ isScanning: true, scanStep: 1, scanStepLabel: "Capturing...", scanProgress: 20, lastResult: null })

    // Try backend API first
    const reqData = activeIntake ? { intake_id: activeIntake.id } : { source }
    api.scans.trigger(reqData)
      .then(() => {
        // WebSocket events will drive the progress from here
      })
      .catch(() => {
        // Backend unavailable — run mock pipeline
        console.warn("[AppContext] Scan API unavailable, running mock pipeline")

        const t1 = setTimeout(() => {
          setScanState((s) => ({ ...s, scanStep: 2, scanStepLabel: "Detecting...", scanProgress: 60 }))
        }, 1500)

        const t2 = setTimeout(() => {
          setScanState((s) => ({ ...s, scanStep: 3, scanStepLabel: "Analyzing...", scanProgress: 80 }))
        }, 3000)

        const t3 = setTimeout(() => {
          setScanState((s) => ({ ...s, scanProgress: 100, scanStepLabel: "Complete!" }))
        }, 4000)

        const t4 = setTimeout(() => {
          const cultivars: Cultivar[] = ["Lakatan", "Latundan", "Saba"]
          const ripenessLevels: Ripeness[] = ["Unripe", "Ripe", "Overripe", "Rotten"]
          const cultivar = cultivars[Math.floor(Math.random() * cultivars.length)]
          const ripeness = ripenessLevels[Math.floor(Math.random() * ripenessLevels.length)]
          const temperature = parseFloat((Math.random() * 10 + 20).toFixed(1))
          const humidity = parseFloat((Math.random() * 30 + 50).toFixed(1))

          let activeIntakeId: string | undefined
          if (source) {
            const todayDate = new Date().toISOString().split("T")[0]
            const existing = intakes.find((i) => i.source === source && i.date === todayDate && i.status === "Active")
            if (existing) {
              activeIntakeId = existing.id
            } else {
              activeIntakeId = `INT-${Math.random().toString(36).substring(2, 8).toUpperCase()}`
              setIntakes((prev) => [{ id: activeIntakeId as string, source, date: todayDate, status: "Active" }, ...prev])
            }
          }

          const newScan: ScanResult = {
            id: Math.random().toString(36).substring(2, 10),
            dateTime: new Date().toISOString(),
            cultivar,
            ripeness,
            confidence: parseFloat((Math.random() * 10 + 90).toFixed(1)),
            temperature,
            humidity,
            spoilageDays: getSpoilageDays(cultivar, ripeness, temperature, humidity),
            fingerCount: Math.floor(Math.random() * 10) + 5,
            operator: user?.fullName || "Unknown",
            source: source || undefined,
            thumbnailUrl: getBananaImageUrl(cultivar, ripeness),
            intakeId: activeIntakeId,
            inventoryStatus: "In Stock",
            statusUpdatedAt: new Date().toISOString(),
          }
          setScans((prev) => [newScan, ...prev])
          setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: newScan })
        }, 4800)

        scanTimeoutRef.current = [t1, t2, t3, t4]
      })
  }, [scanState.isScanning, user, intakes, activeIntake])

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

    api.users.update(id, apiData)
      .then((updated) => {
        const mapped = mapApiUser(updated)
        setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...mapped } : u)))
        setUser((prev) => {
          if (prev && prev.id === id) {
            const newUser = { ...prev, ...data }
            setStoredUser(newUser)
            return newUser
          }
          return prev
        })
      })
      .catch(() => {
        setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...data } : u)))
        setUser((prev) => {
          if (prev && prev.id === id) {
            const newUser = { ...prev, ...data }
            setStoredUser(newUser)
            return newUser
          }
          return prev
        })
      })
  }, [])

  const flagScan = useCallback((id: string, flagged: boolean) => {
    api.scans.flag(id, flagged)
      .then(() => setScans((prev) => prev.map((s) => (s.id === id ? { ...s, flagged } : s))))
      .catch(() => setScans((prev) => prev.map((s) => (s.id === id ? { ...s, flagged } : s))))
  }, [])

  const addScanNote = useCallback((scanId: string, note: string) => {
    const tempNote: ScanNote = {
      id: Math.random().toString(36).substring(2, 10),
      scanId,
      note,
      author: user?.fullName || "Unknown",
      timestamp: new Date().toISOString(),
    }
    setScanNotes((prev) => [...prev, tempNote])
    api.scans.notes.add(scanId, note).catch(() => {})
  }, [user])

  const getScanNotes = useCallback((scanId: string) => {
    return scanNotes.filter((n) => n.scanId === scanId)
  }, [scanNotes])

  const updateScanData = useCallback((id: string, data: Partial<ScanResult>) => {
    const apiData = {
      cultivar: data.cultivar,
      ripeness: data.ripeness,
      finger_count: data.fingerCount,
      spoilage_days: data.spoilageDays,
    }
    api.scans.override(id, apiData)
      .then(() => setScans((prev) => prev.map((s) => (s.id === id ? { ...s, ...data } : s))))
      .catch(() => setScans((prev) => prev.map((s) => (s.id === id ? { ...s, ...data } : s))))
  }, [])

  const updateConfig = useCallback((cfg: Partial<SystemConfig>) => {
    api.config.update(cfg).catch(() => {})
    setConfig((prev) => ({ ...prev, ...cfg }))
  }, [])

  const startIntake = useCallback(async (supplierId: string, batchNumber: string) => {
    try {
      const resp = await api.intakes.create({ supplier_id: supplierId, batch_number: batchNumber, source: "Kiosk" })
      const newIntake = mapApiIntake(resp)
      setIntakes((prev) => [newIntake, ...prev])
      setActiveIntake(newIntake)
      return newIntake
    } catch (error) {
      console.error("[AppContext] Failed to create intake", error)
    }
  }, [mapApiIntake])

  const bulkUpdateIntakeInventory = useCallback((intakeId: string, status: InventoryStatus) => {
    const intakeStatus = status === "In Stock" ? "Active" : "Depleted"
    api.intakes.update(intakeId, { status: intakeStatus, inventory_status: status }).catch(() => {})
    setIntakes((prev) => prev.map((i) => (i.id === intakeId ? { ...i, status: intakeStatus } : i)))
    setScans((prev) =>
      prev.map((s) => {
        if (s.intakeId === intakeId) {
          if (s.inventoryStatus !== "Sold" && s.inventoryStatus !== "Spoiled") {
            return { ...s, inventoryStatus: status, statusUpdatedAt: new Date().toISOString() }
          }
        }
        return s
      })
    )
  }, [])

  const addSupplier = useCallback((supplierData: Omit<Supplier, "id" | "dateAdded">) => {
    const apiData = {
      name: supplierData.name,
      contact_person: supplierData.contactPerson,
      contact_phone: supplierData.contactPhone,
      status: supplierData.status,
    }
    api.suppliers.create(apiData)
      .then((newSup) => setSuppliers((prev) => [...prev, mapApiSupplier(newSup)]))
      .catch(() => {
        const newSupplier: Supplier = {
          ...supplierData,
          id: `SUP-${Math.floor(Math.random() * 1000000)}`.padStart(11, "0"),
          dateAdded: new Date().toISOString(),
        }
        setSuppliers((prev) => [...prev, newSupplier])
      })
  }, [])

  const updateSupplier = useCallback((id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => {
    const apiData: any = { ...data }
    if (data.contactPerson !== undefined) apiData.contact_person = data.contactPerson
    if (data.contactPhone !== undefined) apiData.contact_phone = data.contactPhone

    api.suppliers.update(id, apiData)
      .then((updated) => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...mapApiSupplier(updated) } : s))))
      .catch(() => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...data } : s))))
  }, [])

  const updateSupplierStatus = useCallback((id: string, status: "Active" | "Inactive") => {
    api.suppliers.update(id, { status })
      .then((updated) => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...mapApiSupplier(updated) } : s))))
      .catch(() => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s))))
  }, [])

  return (
    <AppContext
      value={{
        user,
        login,
        changePasswordAndLogin,
        changePinAndLogin,
        logout,
        switchOperator,
        scanState,
        startScan,
        scans,
        users,
        devices,
        activityLogs,
        addUser,
        updateUser,
        flagScan,
        addScanNote,
        getScanNotes,
        updateScanData,
        config,
        updateConfig,
        intakes,
        startIntake,
        activeIntake,
        setActiveIntake,
        bulkUpdateIntakeInventory,
        suppliers,
        addSupplier,
        updateSupplier,
        updateSupplierStatus,
      }}
    >
      {children}
    </AppContext>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp must be inside AppProvider")
  return ctx
}
