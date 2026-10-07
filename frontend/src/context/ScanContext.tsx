import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react"
import { getBananaImageUrl, getImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { useAdmin } from "@/context/AdminContext"
import { useWebSocket } from "@/hooks/useWebSocket"
import { generateQRCodeDataUrl } from "@/lib/qrcode"
import { toast } from "sonner"
import { useLocation } from "react-router-dom"
import type { ScanResult, ScanNote, InventoryStatus } from "@/types"
import { collectScanPages, mapApiScan, mapApiScanNote, type ApiScan } from "@/lib/scanData"

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
  flagScan: (id: string, flagged: boolean) => Promise<void>
  addScanNote: (scanId: string, note: string) => Promise<void>
  getScanNotes: (scanId: string) => ScanNote[]
  loadScanNotes: (scanId: string) => void
  updateScanData: (id: string, data: Partial<ScanResult>) => Promise<ScanResult>
  scansLoading: boolean
  scansError: string | null
  refreshScans: () => Promise<void>
  /** Update inventory status on scans belonging to an intake. Used by InventoryContext. */
  updateScansForIntake: (scanIds: string[], status: InventoryStatus, statusUpdatedAt: string) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const ScanContext = createContext<ScanContextType | null>(null)

// ── Provider ────────────────────────────────────────────────────────────────

export function ScanProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  return <ScanStore key={user ? `${user.id}:${user.role}` : "anonymous"}>{children}</ScanStore>
}

function ScanStore({ children }: { children: React.ReactNode }) {
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


  const [scansLoading, setScansLoading] = useState(Boolean(user))
  const [scansError, setScansError] = useState<string | null>(null)
  const historyRequest = useRef<AbortController | null>(null)
  const mounted = useRef(true)

  const refreshScans = useCallback(async () => {
    historyRequest.current?.abort()
    if (!user) return
    const controller = new AbortController()
    historyRequest.current = controller
    setScansLoading(true)
    setScansError(null)
    try {
      const raw = await collectScanPages((page, page_size, signal) => api.scans.list({ page, page_size }, signal), controller.signal)
      const mapped = raw.map(record => mapApiScan(record, getImageUrl))
      if (!controller.signal.aborted && mounted.current) setScans(mapped)
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) {
        setScansError(error instanceof Error ? error.message : "Scan history could not be loaded. Please retry.")
      }
    } finally {
      if (!controller.signal.aborted && mounted.current) setScansLoading(false)
    }
  }, [user])

  useEffect(() => {
    mounted.current = true
    void refreshScans()
    return () => { mounted.current = false; historyRequest.current?.abort() }
  }, [refreshScans, pathname])

  const acceptCompletedScan = useCallback(async (result: ApiScan) => {
    const scanResult = mapApiScan(result, getImageUrl)
    if (!scanResult.thumbnailUrl) scanResult.thumbnailUrl = getBananaImageUrl(scanResult.cultivar, scanResult.ripeness)
    try { scanResult.qrCode = await generateQRCodeDataUrl(scanResult) } catch { /* The persisted result is still usable without a QR preview. */ }
    if (!mounted.current) return
    setScans(prev => [scanResult, ...prev.filter(scan => scan.id !== scanResult.id)])
    setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: scanResult })
    void refreshScans()
  }, [refreshScans])

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
        void acceptCompletedScan({ ...result, id: result.id ?? result.scan_id, source_text: result.source_text ?? result.supplier ?? result.source }).catch(() => {
          setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: null })
          toast.error("The completed scan could not be loaded. Please refresh Scan Logs.")
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
  }, [acceptCompletedScan, updateDeviceFromWs])

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
      .then(acceptCompletedScan)
      .catch((err: Error) => {
        console.warn("[ScanContext] Scan API error:", err.message)
        setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: null })
        toast.error(err.message || "Scan failed. Please try again.")
      })
  }, [scanState.isScanning, acceptCompletedScan])

  // ── CRUD Operations ─────────────────────────────────────────────────────

  const flagScan = useCallback(async (id: string, flagged: boolean) => {
    await api.scans.flag(id, flagged)
    if (!mounted.current) return
    setScans(prev => prev.map(scan => scan.id === id ? { ...scan, flagged } : scan))
    setScanState(previous => previous.lastResult?.id === id ? { ...previous, lastResult: { ...previous.lastResult, flagged } } : previous)
    void refreshScans()
  }, [refreshScans])

  const addScanNote = useCallback(async (scanId: string, note: string) => {
    const saved = mapApiScanNote(await api.scans.notes.add(scanId, note))
    if (!mounted.current) return
    setScanNotes(prev => [...prev.filter(existing => existing.id !== saved.id), saved])
    setScans(prev => prev.map(scan => scan.id === scanId ? { ...scan, hasNotes: true } : scan))
  }, [])

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
            ...notes.map(mapApiScanNote)
          ]
        })
      })
      .catch(() => toast.error("Review notes could not be loaded. Please retry."))
  }, [])

  const updateScanData = useCallback(async (id: string, data: Partial<ScanResult>) => {
    const saved = mapApiScan(await api.scans.override(id, {
      cultivar: data.cultivar,
      ripeness: data.ripeness,
      finger_count: data.fingerCount,
      spoilage_days: data.spoilageDays,
      source_text: data.source,
    }), getImageUrl)
    if (mounted.current) {
      setScans(prev => prev.map(scan => scan.id === id ? { ...scan, ...saved, images: scan.images, detections: scan.detections } : scan))
      void refreshScans()
    }
    return saved
  }, [refreshScans])

  // ── Cross-context helper for InventoryContext ───────────────────────────

  const updateScansForIntake = useCallback((scanIds: string[], status: InventoryStatus, statusUpdatedAt: string) => {
    const ids = new Set(scanIds)
    setScans(prev => prev.map(scan => ids.has(scan.id) ? { ...scan, inventoryStatus: status, statusUpdatedAt } : scan))
    void refreshScans()
  }, [refreshScans])

  return (
    <ScanContext value={{
      scans,
      scansLoading,
      scansError,
      refreshScans,
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
