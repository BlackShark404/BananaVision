import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react"
import { getBananaImageUrl, getImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import { scanWrite, scanRevision } from "@/lib/scanWrites"
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
  flagScan: (id: string, flagged: boolean, revision?: number) => Promise<ScanResult>
  addScanNote: (scanId: string, note: string, revision?: number) => Promise<{ note: ScanNote; revision: number }>
  getScanNotes: (scanId: string) => ScanNote[]
  loadScanNotes: (scanId: string) => void
  updateScanData: (id: string, data: Partial<ScanResult>, reason: string, baseline?: ScanResult) => Promise<ScanResult>
  acceptScan: (data: ApiScan) => ScanResult
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
  const knownScans = useRef(new Map<string, ScanResult>())
  const noteRequests = useRef(new Map<string, number>())

  const acceptScan = useCallback((raw: ApiScan) => {
    const incoming = mapApiScan(raw, getImageUrl)
    const known = knownScans.current.get(incoming.id)
    if ((known?.revision ?? 0) > (incoming.revision ?? 0)) return known!
    const saved = { ...known, ...incoming,
      images: raw.images === undefined ? known?.images : incoming.images,
      detections: raw.detections === undefined ? known?.detections : incoming.detections,
      notes: raw.notes === undefined ? known?.notes : incoming.notes,
      history: raw.history === undefined ? known?.history : incoming.history,
    }
    if (!mounted.current) return saved
    knownScans.current.set(saved.id, saved)
    setScans(previous => previous.map(scan => scan.id === saved.id ? saved : scan))
    setScanState(previous => previous.lastResult?.id === saved.id ? { ...previous, lastResult: saved } : previous)
    if (saved.notes) setScanNotes(previous => [...previous.filter(note => note.scanId !== saved.id), ...saved.notes!])
    return saved
  }, [])

  const refreshScans = useCallback(async () => {
    historyRequest.current?.abort()
    if (!user) return
    const controller = new AbortController()
    historyRequest.current = controller
    setScansLoading(true)
    setScansError(null)
    try {
      const raw = await collectScanPages((page, page_size, signal) => api.scans.list({ page, page_size }, signal), controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      const mapped = raw.map(record => acceptScan(record))
      if (!controller.signal.aborted && mounted.current) setScans(mapped)
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) {
        setScansError(error instanceof Error ? error.message : "Scan history could not be loaded. Please retry.")
      }
    } finally {
      if (!controller.signal.aborted && mounted.current) setScansLoading(false)
    }
  }, [user, acceptScan])

  useEffect(() => {
    mounted.current = true
    void refreshScans()
    return () => { mounted.current = false; historyRequest.current?.abort() }
  }, [refreshScans, pathname])

  const acceptCompletedScan = useCallback(async (result: ApiScan) => {
    const scanResult = acceptScan(result)
    if (!scanResult.thumbnailUrl) scanResult.thumbnailUrl = getBananaImageUrl(scanResult.cultivar, scanResult.ripeness)
    try { scanResult.qrCode = await generateQRCodeDataUrl(scanResult) } catch { /* The persisted result is still usable without a QR preview. */ }
    if (!mounted.current) return
    setScans(prev => [scanResult, ...prev.filter(scan => scan.id !== scanResult.id)])
    setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: scanResult })
    void refreshScans()
  }, [refreshScans, acceptScan])

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

  const flagScan = useCallback(async (id: string, flagged: boolean, revision?: number) => {
    const body = { flagged, expected_revision: scanRevision(revision ?? knownScans.current.get(id)?.revision) }
    const raw = await scanWrite(`${user?.id}:${id}:flag`, body, payload => api.scans.flag(id, payload))
    return acceptScan(raw)
  }, [user?.id, acceptScan])

  const addScanNote = useCallback(async (scanId: string, note: string, revision?: number) => {
    const raw = await scanWrite(`${user?.id}:${scanId}:note`, {
      note, expected_revision: scanRevision(revision ?? knownScans.current.get(scanId)?.revision),
    }, payload => api.scans.notes.add(scanId, payload))
    const saved = mapApiScanNote(raw)
    if (mounted.current) {
      noteRequests.current.set(scanId, (noteRequests.current.get(scanId) ?? 0) + 1)
      const known = knownScans.current.get(scanId)
      if (known && (known.revision ?? 0) <= raw.revision) {
        const updated = { ...known, revision: raw.revision, hasNotes: true,
          notes: [...(known.notes ?? []).filter(item => item.id !== saved.id), saved] }
        knownScans.current.set(scanId, updated)
        setScans(previous => previous.map(scan => scan.id === scanId ? updated : scan))
      }
      setScanNotes(previous => [...previous.filter(item => item.id !== saved.id), saved])
    }
    return { note: saved, revision: raw.revision }
  }, [user?.id])

  const getScanNotes = useCallback((scanId: string) => scanNotes.filter(note => note.scanId === scanId), [scanNotes])

  const loadScanNotes = useCallback((scanId: string) => {
    const sequence = (noteRequests.current.get(scanId) ?? 0) + 1
    noteRequests.current.set(scanId, sequence)
    api.scans.detail(scanId).then(raw => {
      if (mounted.current && noteRequests.current.get(scanId) === sequence) acceptScan(raw)
    }).catch(() => {
      if (mounted.current && noteRequests.current.get(scanId) === sequence) toast.error("Review notes could not be loaded. Please retry.")
    })
  }, [acceptScan])

  const updateScanData = useCallback(async (id: string, data: Partial<ScanResult>, reason: string, baseline?: ScanResult) => {
    const before = baseline ?? knownScans.current.get(id)
    const changes: { cultivar?: string; ripeness?: string; finger_count?: number; spoilage_days?: string; source_text?: string } = {}
    if (data.cultivar !== undefined && data.cultivar !== before?.cultivar) changes.cultivar = data.cultivar
    if (data.ripeness !== undefined && data.ripeness !== before?.ripeness) changes.ripeness = data.ripeness
    if (data.fingerCount !== undefined && data.fingerCount !== before?.fingerCount) changes.finger_count = data.fingerCount
    if (data.spoilageDays !== undefined && data.spoilageDays !== before?.spoilageDays) changes.spoilage_days = data.spoilageDays
    if (data.source !== undefined && data.source !== before?.source) changes.source_text = data.source
    const raw = await scanWrite(`${user?.id}:${id}:correction`, {
      ...changes, reason, expected_revision: scanRevision(before?.revision),
    }, payload => api.scans.override(id, payload))
    return acceptScan(raw)
  }, [user?.id, acceptScan])

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
      acceptScan,
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
