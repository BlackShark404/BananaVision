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
import { useLocalStorage } from "@/hooks/useLocalStorage"

interface AuthUser {
  id: string
  username: string
  fullName: string
  role: Role
  avatar?: string
}

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
    | "success"
    | "failed"
    | "requires_password_change"
    | "requires_password_change_new_account"
    | "requires_password_change_reset"
  changePasswordAndLogin: (username: string, newPassword?: string) => boolean
  logout: () => void
  switchOperator: (username: string, pin: string) => "success" | "failed" | "requires_pin_change" | "requires_pin_change_new_account" | "requires_pin_change_reset"
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
  bulkUpdateIntakeInventory: (intakeId: string, status: InventoryStatus) => void
  suppliers: Supplier[]
  addSupplier: (supplierData: Omit<Supplier, "id" | "dateAdded">) => void
  updateSupplier: (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => void
  updateSupplierStatus: (id: string, status: "Active" | "Inactive") => void
}

const INITIAL_SCANS = generateScanResults(40)
const INITIAL_INTAKES = generateIntakes(INITIAL_SCANS)

const AppContext = createContext<AppContextType | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useLocalStorage<AuthUser | null>("bananavision_user", null)

  const [scans, setScans] = useState<ScanResult[]>(() => INITIAL_SCANS)
  const [intakes, setIntakes] = useState<DailyIntake[]>(() => INITIAL_INTAKES)
  const [suppliers, setSuppliers] = useState<Supplier[]>(() => generateSuppliers())
  
  const [users, setUsers] = useLocalStorage<User[]>("bananavision_users", () => generateUsers())

  const [devices] = useState<Device[]>(() => generateDevices())
  const [activityLogs] = useState<ActivityLog[]>(() => generateActivityLogs())

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

  const login = useCallback((username: string, password?: string) => {
    const found = users.find((u) => u.username === username)
    if (found) {
      if (found.requiresPasswordChange && password === found.password) {
        if (found.passwordSetupReason === "new_account") {
          return "requires_password_change_new_account"
        }
        if (found.passwordSetupReason === "password_reset") {
          return "requires_password_change_reset"
        }
        return "requires_password_change"
      }
      if (!found.requiresPasswordChange && password === found.password) {
        setUser({ id: found.id, username: found.username, fullName: found.fullName, role: found.role, avatar: found.avatar })
        return "success"
      }
    }
    return "failed"
  }, [users, setUser])



  const switchOperator = useCallback((username: string, pin: string) => {
    const found = users.find((u) => u.username === username)
    if (found && found.pin === pin) {
      if (found.requiresPinChange) {
        if (found.pinSetupReason === "new_account") return "requires_pin_change_new_account"
        if (found.pinSetupReason === "pin_reset") return "requires_pin_change_reset"
        return "requires_pin_change"
      }
      setUser({ id: found.id, username: found.username, fullName: found.fullName, role: found.role, avatar: found.avatar })
      return "success"
    }
    return "failed"
  }, [users, setUser])

  const logout = useCallback(() => setUser(null), [])

  const startScan = useCallback((source?: string) => {
    if (scanState.isScanning) return
    setScanState({ isScanning: true, scanStep: 1, scanStepLabel: "Capturing...", scanProgress: 20, lastResult: null })

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
        const todayDate = new Date().toISOString().split('T')[0]
        const existing = intakes.find(i => i.source === source && i.date === todayDate && i.status === "Active")
        if (existing) {
          activeIntakeId = existing.id
        } else {
          activeIntakeId = `INT-${Math.random().toString(36).substring(2, 8).toUpperCase()}`
          setIntakes(prev => [{
            id: activeIntakeId as string,
            source,
            date: todayDate,
            status: "Active"
          }, ...prev])
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
  }, [scanState.isScanning, user, intakes])

  const addUser = useCallback((data: Omit<User, "id">) => {
    setUsers((prev) => [...prev, { ...data, id: Math.random().toString(36).substring(2, 10) }])
  }, [])

  const updateUser = useCallback((id: string, data: Partial<User>) => {
    setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...data } : u)))
    setUser((prev) => (prev && prev.id === id ? { ...prev, ...data } : prev))
  }, [])

  const changePasswordAndLogin = useCallback((username: string, newPassword?: string) => {
    const found = users.find(u => u.username === username)
    if (found && newPassword) {
      updateUser(found.id, {
        requiresPasswordChange: false,
        passwordSetupReason: undefined,
        password: newPassword,
      })
      setUser({ id: found.id, username: found.username, fullName: found.fullName, role: found.role, avatar: found.avatar })
      return true
    }
    return false
  }, [users, updateUser])

  const flagScan = useCallback((id: string, flagged: boolean) => {
    setScans((prev) => prev.map((s) => (s.id === id ? { ...s, flagged } : s)))
  }, [])

  const addScanNote = useCallback((scanId: string, note: string) => {
    const newNote: ScanNote = {
      id: Math.random().toString(36).substring(2, 10),
      scanId,
      note,
      author: user?.fullName || "Unknown",
      timestamp: new Date().toISOString(),
    }
    setScanNotes((prev) => [...prev, newNote])
  }, [user])

  const getScanNotes = useCallback((scanId: string) => {
    return scanNotes.filter((n) => n.scanId === scanId)
  }, [scanNotes])

  const updateScanData = useCallback((id: string, data: Partial<ScanResult>) => {
    setScans((prev) => prev.map((s) => (s.id === id ? { ...s, ...data } : s)))
  }, [])

  const updateConfig = useCallback((cfg: Partial<SystemConfig>) => {
    setConfig((prev) => ({ ...prev, ...cfg }))
  }, [])

  const bulkUpdateIntakeInventory = useCallback((intakeId: string, status: InventoryStatus) => {
    const intakeStatus = status === "In Stock" ? "Active" : "Depleted"
    setIntakes((prev) => prev.map((i) => (i.id === intakeId ? { ...i, status: intakeStatus } : i)))
    setScans((prev) => prev.map((s) => {
      if (s.intakeId === intakeId) {
        if (s.inventoryStatus !== "Sold" && s.inventoryStatus !== "Spoiled") {
          return { ...s, inventoryStatus: status, statusUpdatedAt: new Date().toISOString() }
        }
      }
      return s
    }))
  }, [])

  const addSupplier = useCallback((supplierData: Omit<Supplier, "id" | "dateAdded">) => {
    const newSupplier: Supplier = {
      ...supplierData,
      id: `SUP-${Math.floor(Math.random() * 1000000)}`.padStart(11, '0'),
      dateAdded: new Date().toISOString()
    }
    setSuppliers((prev) => [...prev, newSupplier])
  }, [])

  const updateSupplier = useCallback((id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => {
    setSuppliers((prev) => prev.map(s => s.id === id ? { ...s, ...data } : s))
  }, [])

  const updateSupplierStatus = useCallback((id: string, status: "Active" | "Inactive") => {
    setSuppliers((prev) => prev.map(s => s.id === id ? { ...s, status } : s))
  }, [])

  return (
    <AppContext
      value={{ 
        user, 
        login, 
        changePasswordAndLogin,
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
        bulkUpdateIntakeInventory,
        suppliers,
        addSupplier,
        updateSupplier,
        updateSupplierStatus
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
