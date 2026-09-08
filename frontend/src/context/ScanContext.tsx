import React, { createContext, useContext, useState, useCallback, useEffect } from "react"
import { getBananaImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { useAdmin } from "@/context/AdminContext"
import { useWebSocket } from "@/hooks/useWebSocket"
import { generateQRCodeDataUrl } from "@/lib/qrcode"
import { toast } from "sonner"
import { useLocation } from "react-router-dom"
import type { ScanResult, ScanNote, InventoryStatus } from "@/types"

// ── Types ───────────────────────────────────────────────────────────────────

interface ScanState {
  isScanning: boolean
  scanStep: number
  scanStepLabel: string
  scanProgress: number
  lastResult: ScanResult | null
}

interface ScanContextType {
  scans: ScanResult[]
  scanState: ScanState
  startScan: (source?: string, intakeId?: string) => void
  flagScan: (id: string, flagged: boolean) => void
  addScanNote: (scanId: string, note: string) => void
  getScanNotes: (scanId: string) => ScanNote[]
  loadScanNotes: (scanId: string) => void
  updateScanData: (id: string, data: Partial<ScanResult>) => void
  /** Update inventory status on scans belonging to an intake. Used by InventoryContext. */
  updateScansForIntake: (intakeId: string, status: InventoryStatus) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const ScanContext = createContext<ScanContextType | null>(null)

// ── Mapper ──────────────────────────────────────────────────────────────────

const mapApiScan = (s: any): ScanResult => ({
  id: s.id,
  dateTime: s.scanned_at || s.dateTime || new Date().toISOString(),
  cultivar: s.cultivar,
  ripeness: s.ripeness,
  confidence: s.confidence,
  temperature: s.temperature,
  humidity: s.humidity,
  dewPoint: s.dew_point ?? s.dewPoint,
  vpd: s.vpd,
  heatIndex: s.heat_index ?? s.heatIndex,
  treatment: s.treatment,
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
  hasNotes: s.has_notes || s.hasNotes || false,
})

// ── Provider ────────────────────────────────────────────────────────────────

export function ScanProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { updateDeviceFromWs } = useAdmin()
  const { pathname } = useLocation()

  const [scans, setScans] = useState<ScanResult[]>([])
  const [scanNotes, setScanNotes] = useState<ScanNote[]>([])
  const [scanState, setScanState] = useState<ScanState>({
    isScanning: false,
    scanStep: 0,
    scanStepLabel: "",
    scanProgress: 0,
    lastResult: null,
  })


  // ── Load scans on mount / navigation ────────────────────────────────────

  useEffect(() => {
    if (!user) return

    const loadData = async () => {
      try {
        const scansRes = await api.scans.list({ per_page: 100 })
        const raw = scansRes.items || scansRes as any
        const mapped = Array.isArray(raw) ? raw.map(mapApiScan) : []
        const withQr = await Promise.all(mapped.map(async (s: ScanResult) => ({ ...s, qrCode: await generateQRCodeDataUrl(s) })))
        setScans(withQr)
      } catch {
        console.warn("[ScanContext] Scans API unavailable")
      }
    }

    loadData()
  }, [user, pathname])

  // ── Reset on logout ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) {
      setScans([])
      setScanNotes([])
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
          dewPoint: result.dew_point ?? result.dewPoint,
          vpd: result.vpd,
          heatIndex: result.heat_index ?? result.heatIndex,
          treatment: result.treatment,
          spoilageDays: result.spoilage_days || result.spoilageDays,
          fingerCount: result.finger_count || result.fingerCount,
          operator: result.operator || user?.fullName || "Unknown",
          source: result.source,
          thumbnailUrl: result.thumbnail_url || getBananaImageUrl(result.cultivar, result.ripeness),
          intakeId: result.intake_id || result.intakeId,
          inventoryStatus: result.inventory_status || "In Stock",
          statusUpdatedAt: result.status_updated_at || new Date().toISOString(),
        }
        generateQRCodeDataUrl(scanResult).then((qrCode) => {
          const scanWithQR = { ...scanResult, qrCode }
          setScans((prev) => [scanWithQR, ...prev])
          setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: scanWithQR })
        })
        break
      }

      case "scan:failed":
        setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: null })
        toast.error(data?.error || "Scan failed. Please try again.")
        break

      case "sensor:update":
        // Could update a sensor state atom here if needed
        break

      case "device:status":
        updateDeviceFromWs(data.camera_id, data.status, data.last_seen)
        break
    }
  }, [user, updateDeviceFromWs])

  useWebSocket({
    rooms: ["kiosk", "dashboard", "devices"],
    onEvent: handleWsEvent,
    enabled: !!user,
  })

  // ── Scan Pipeline ───────────────────────────────────────────────────────

  const startScan = useCallback((source?: string, intakeId?: string) => {
    if (scanState.isScanning) return
    setScanState({ isScanning: true, scanStep: 1, scanStepLabel: "Capturing...", scanProgress: 20, lastResult: null })

    // Try backend API first
    const reqData = intakeId ? { intake_id: intakeId } : { source }
    api.scans.trigger(reqData)
      .then(() => {
        // WebSocket events will drive the progress from here
      })
      .catch((err: Error) => {
        console.warn("[ScanContext] Scan API error:", err.message)
        setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: null })
        toast.error(err.message || "Scan failed. Please try again.")
      })
  }, [scanState.isScanning])

  // ── CRUD Operations ─────────────────────────────────────────────────────

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
    setScans((prev) => prev.map((s) => (s.id === scanId ? { ...s, hasNotes: true } : s)))
    api.scans.notes.add(scanId, note).catch(() => {})
  }, [user])

  const getScanNotes = useCallback((scanId: string) => {
    return scanNotes.filter((n) => n.scanId === scanId)
  }, [scanNotes])

  const loadScanNotes = useCallback((scanId: string) => {
    api.scans.notes.list(scanId)
      .then((notes) => {
        setScanNotes((prev) => {
          const others = prev.filter((n) => n.scanId !== scanId)
          return [
            ...others,
            ...notes.map((n: any) => ({
              id: n.id,
              scanId: n.scan_id || scanId,
              note: n.text || n.note,
              author: n.author_name || "Unknown",
              timestamp: n.timestamp || new Date().toISOString()
            }))
          ]
        })
      })
      .catch(() => {})
  }, [])

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

  // ── Cross-context helper for InventoryContext ───────────────────────────

  const updateScansForIntake = useCallback((intakeId: string, status: InventoryStatus) => {
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

  return (
    <ScanContext value={{
      scans,
      scanState,
      startScan,
      flagScan,
      addScanNote,
      getScanNotes,
      loadScanNotes,
      updateScanData,
      updateScansForIntake,
    }}>
      {children}
    </ScanContext>
  )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useScans() {
  const ctx = useContext(ScanContext)
  if (!ctx) throw new Error("useScans must be inside ScanProvider")
  return ctx
}
