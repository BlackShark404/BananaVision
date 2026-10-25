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
import { notifyLiveResumed, notifyNotificationsChanged, notifyScansAdded, notifyScanUpdated, notifyIntakeChanged, notifySupplierChanged, newEventId, type ScanUpdateDetail } from "@/lib/liveEvents"

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
  scansReady: boolean
  getScanNotesState: (scanId: string) => { loading: boolean; error: string | null; ready: boolean }
  scansLoading: boolean
  scansError: string | null
  refreshScans: () => Promise<void>
  /** Update inventory status on scans belonging to an intake. Used by InventoryContext. */
  updateScansForIntake: (scanIds: string[], status: InventoryStatus, statusUpdatedAt: string, revisions: Record<string, number>) => void
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


  const [scansReady, setScansReady] = useState(false)
  const [notesState, setNotesState] = useState<Record<string, { loading: boolean; error: string | null; ready: boolean }>>({})
  const [scansLoading, setScansLoading] = useState(Boolean(user))
  const [scansError, setScansError] = useState<string | null>(null)
  const historyRequest = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  const knownScans = useRef(new Map<string, ScanResult>())
  const noteRequests = useRef(new Map<string, number>())
  const completedScans = useRef(new Set<string>())
  const seenScanEvents = useRef(new Set<string>())

  const acceptScan = useCallback((raw: ApiScan) => {
    const incoming = mapApiScan(raw, getImageUrl)
    const known = knownScans.current.get(incoming.id)
    const previousRevision = known?.revision ?? 0
    if (previousRevision > (incoming.revision ?? 0)) return known!
    const saved = { ...known, ...incoming,
      printJob: raw.print_job == null ? known?.printJob : incoming.printJob,
      printError: raw.print_error == null ? known?.printError : incoming.printError,
      images: raw.images === undefined ? known?.images : incoming.images,
      detections: raw.detections === undefined ? known?.detections : incoming.detections,
      notes: raw.notes === undefined ? known?.notes : incoming.notes,
      history: raw.history === undefined ? known?.history : incoming.history,
    }
    if (!mounted.current) return saved
    knownScans.current.set(saved.id, saved)
    setScans(previous => previous.map(scan => scan.id === saved.id ? saved : scan))
    setScanState(previous => previous.lastResult?.id === saved.id ? { ...previous, lastResult: saved } : previous)
    if (saved.notes) {
      setScanNotes(previous => [...previous.filter(note => note.scanId !== saved.id), ...saved.notes!])
      setNotesState(previous => ({ ...previous, [saved.id]: { loading: false, error: null, ready: true } }))
    }
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
      const raw = await collectScanPages((page, page_size, signal, snapshot_id) => api.scans.list({ page, page_size, stable: true, snapshot_id }, signal), controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      const mapped = raw.map(record => acceptScan(record))
      if (!controller.signal.aborted && mounted.current) { setScans(mapped); setScansReady(true) }
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
    // The same completion can arrive from both the kiosk and dashboard rooms,
    // plus the HTTP response. Merge happens in acceptScan; only the first copy
    // may prepend, render a QR, or refresh history.
    if (completedScans.current.has(scanResult.id)) return
    if (completedScans.current.size >= 100) {
      const oldest = completedScans.current.values().next().value
      if (oldest) completedScans.current.delete(oldest)
    }
    completedScans.current.add(scanResult.id)
    if (!scanResult.thumbnailUrl) scanResult.thumbnailUrl = getBananaImageUrl(scanResult.cultivar, scanResult.ripeness)
    try { scanResult.qrCode = await generateQRCodeDataUrl(scanResult) } catch { /* The persisted result is still usable without a QR preview. */ }
    if (!mounted.current) return
    const latest = knownScans.current.get(scanResult.id) ?? scanResult
    if (scanResult.qrCode) {
      const withQr = { ...latest, qrCode: scanResult.qrCode }
      knownScans.current.set(scanResult.id, withQr)
    }
    const saved = knownScans.current.get(scanResult.id) ?? latest
    setScans(prev => [saved, ...prev.filter(scan => scan.id !== saved.id)])
    setScanState({ isScanning: false, scanStep: 0, scanStepLabel: "", scanProgress: 0, lastResult: saved })
    // A completion adds a row; edits use notifyScanUpdated so frozen page 2+
    // snapshots are never replaced unless the user asks for the latest scans.
    notifyScansAdded()
    notifyNotificationsChanged()
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

      case "scan:changed": {
        const eventId = typeof data?.event_id === "string" ? data.event_id : ""
        if (eventId) {
          if (seenScanEvents.current.has(eventId)) break
          seenScanEvents.current.add(eventId)
          if (seenScanEvents.current.size > 200) {
            const oldest = seenScanEvents.current.values().next().value
            if (oldest) seenScanEvents.current.delete(oldest)
          }
        }
        const incoming = data?.scan
        if (data?.deleted && incoming?.id) {
          knownScans.current.delete(incoming.id)
          setScans(previous => previous.filter(scan => scan.id !== incoming.id))
          setScanState(previous => previous.lastResult?.id === incoming.id
            ? { ...previous, lastResult: null }
            : previous)
          notifyScanUpdated({
            eventId: eventId || newEventId(), scanId: incoming.id,
            revision: Number(data.revision) || 0, kind: data.kind || "deleted",
            actorId: data.actor_id || "", changed: [], partial: true,
            deleted: true, scan: incoming,
          })
          break
        }
        if (!incoming?.id) break
        const previous = knownScans.current.get(incoming.id)
        if (data.partial) {
          if (!previous || !Number.isInteger(incoming.revision)
            || incoming.revision <= (previous.revision ?? 0)) break
          const updated = {
            ...previous,
            revision: incoming.revision,
            inventoryStatus: incoming.inventory_status ?? previous.inventoryStatus,
            statusUpdatedAt: incoming.status_updated_at ?? previous.statusUpdatedAt,
            inventoryEligible: incoming.inventory_eligible ?? previous.inventoryEligible,
            remainingDays: incoming.remaining_days ?? previous.remainingDays,
            riskAsOf: incoming.risk_as_of ?? previous.riskAsOf,
          }
          knownScans.current.set(incoming.id, updated)
          setScans(current => current.map(scan => scan.id === incoming.id ? updated : scan))
          setScanState(current => current.lastResult?.id === incoming.id
            ? { ...current, lastResult: updated }
            : current)
          notifyScanUpdated({
            eventId: eventId || newEventId(), scanId: incoming.id,
            revision: incoming.revision, kind: data.kind || "changed",
            actorId: data.actor_id || "",
            changed: Array.isArray(data.changed) ? data.changed : [],
            partial: true, scan: incoming,
          })
          break
        }
        const saved = acceptScan(incoming)
        if (!previous) {
          // The row is outside the loaded history window; reconcile rather than
          // inventing a position in the list.
          void refreshScans()
        } else if ((saved.revision ?? 0) > (previous.revision ?? 0)) {
          notifyScanUpdated({
            eventId: eventId || newEventId(), scanId: saved.id,
            revision: saved.revision ?? 0, kind: data.kind || "changed",
            actorId: data.actor_id || "",
            changed: Array.isArray(data.changed) ? data.changed : [],
            partial: false, scan: incoming,
          })
        }
        break
      }

      case "intake:changed":
        notifyIntakeChanged(data ?? {})
        break

      case "supplier:changed":
        notifySupplierChanged(data ?? {})
        break

      case "notification":
        notifyNotificationsChanged()
        break

      case "sensor:update":
        // Could update a sensor state atom here if needed
        break

      case "device:status":
        updateDeviceFromWs(data.camera_id, data.status, data.last_seen)
        break
    }
  }, [acceptCompletedScan, acceptScan, refreshScans, updateDeviceFromWs])

  const handleWsReconnect = useCallback(() => {
    // Events may have been missed while the socket was down. Resync history,
    // notifications and any open snapshot views instead of assuming silence.
    notifyLiveResumed()
    notifyNotificationsChanged()
    void refreshScans()
  }, [refreshScans])

  useWebSocket({
    rooms: ["kiosk", "dashboard", "devices"],
    onEvent: handleWsEvent,
    onReconnect: handleWsReconnect,
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
    const { saved, raw } = await scanWrite(`${user?.id}:${id}:flag`, body, async payload => {
      const response = await api.scans.flag(id, payload)
      return { raw: response, saved: acceptScan(response) }
    })
    notifyScanUpdated({
      eventId: newEventId(), scanId: id, revision: raw.revision, kind: "flag",
      actorId: user?.id ?? "", changed: ["flagged"], partial: false, scan: raw,
    })
    return saved
  }, [user?.id, acceptScan])

  const addScanNote = useCallback(async (scanId: string, note: string, revision?: number) => {
    return scanWrite(`${user?.id}:${scanId}:note`, {
      note, expected_revision: scanRevision(revision ?? knownScans.current.get(scanId)?.revision),
    }, async payload => {
      const raw = await api.scans.notes.add(scanId, payload)
      const saved = mapApiScanNote(raw)
      if (mounted.current) {
        noteRequests.current.set(scanId, (noteRequests.current.get(scanId) ?? 0) + 1)
        setNotesState(previous => ({ ...previous, [scanId]: { loading: false, error: null, ready: true } }))
        const known = knownScans.current.get(scanId)
        if (known && (known.revision ?? 0) <= raw.revision) {
          const updated = { ...known, revision: raw.revision, hasNotes: true,
            notes: [...(known.notes ?? []).filter(item => item.id !== saved.id), saved] }
          knownScans.current.set(scanId, updated)
          setScans(previous => previous.map(scan => scan.id === scanId ? updated : scan))
        }
        setScanNotes(previous => [...previous.filter(item => item.id !== saved.id), saved])
      }
      notifyScanUpdated({
        eventId: newEventId(), scanId, revision: raw.revision, kind: "note",
        actorId: user?.id ?? "", changed: ["note"], partial: true,
        scan: { id: scanId, revision: raw.revision, has_notes: true },
      })
      return { note: saved, revision: raw.revision }
    })
  }, [user?.id])

  const getScanNotes = useCallback((scanId: string) => scanNotes.filter(note => note.scanId === scanId), [scanNotes])

  const getScanNotesState = useCallback((scanId: string) => notesState[scanId] ?? { loading: false, error: null, ready: false }, [notesState])

  const loadScanNotes = useCallback((scanId: string) => {
    const sequence = (noteRequests.current.get(scanId) ?? 0) + 1
    noteRequests.current.set(scanId, sequence)
    setNotesState(previous => ({ ...previous, [scanId]: { loading: true, error: null, ready: previous[scanId]?.ready ?? false } }))
    api.scans.detail(scanId, AbortSignal.timeout(15_000)).then(raw => {
      if (mounted.current && noteRequests.current.get(scanId) === sequence) {
        acceptScan(raw)
        setNotesState(previous => ({ ...previous, [scanId]: { loading: false, error: null, ready: true } }))
      }
    }).catch(() => {
      if (mounted.current && noteRequests.current.get(scanId) === sequence) {
        setNotesState(previous => ({ ...previous, [scanId]: { loading: false, error: "Review notes could not be loaded. Please retry.", ready: previous[scanId]?.ready ?? false } }))
      }
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
    return scanWrite(`${user?.id}:${id}:correction`, {
      ...changes, reason, expected_revision: scanRevision(before?.revision),
    }, async payload => {
      const raw = await api.scans.override(id, payload)
      const saved = acceptScan(raw)
      notifyScanUpdated({
        eventId: newEventId(), scanId: id, revision: raw.revision, kind: "correction",
        actorId: user?.id ?? "", changed: Object.keys(changes), partial: false, scan: raw,
      })
      return saved
    })
  }, [user?.id, acceptScan])

  // ── Cross-context helper for InventoryContext ───────────────────────────

  const updateScansForIntake = useCallback((scanIds: string[], status: InventoryStatus, statusUpdatedAt: string, revisions: Record<string, number>) => {
    if (!mounted.current) return
    const updates: ScanUpdateDetail[] = []
    for (const id of scanIds) {
      const known = knownScans.current.get(id)
      const revision = revisions[id]
      if (known && Number.isInteger(revision) && revision > (known.revision ?? 0)) {
        knownScans.current.set(id, { ...known, revision, inventoryStatus: status, statusUpdatedAt,
          inventoryEligible: status === "In Stock" ? known.inventoryEligible : false })
        updates.push({
          eventId: newEventId(), scanId: id, revision, kind: "status",
          actorId: user?.id ?? "", changed: ["inventory_status"], partial: true,
          scan: {
            id, revision, inventory_status: status, status_updated_at: statusUpdatedAt,
            inventory_eligible: status === "In Stock" ? known.inventoryEligible : false,
          },
        })
      }
    }
    setScans(previous => previous.map(scan => knownScans.current.get(scan.id) ?? scan))
    setScanState(previous => previous.lastResult ? { ...previous, lastResult: knownScans.current.get(previous.lastResult.id) ?? previous.lastResult } : previous)
    for (const update of updates) notifyScanUpdated(update)
    void refreshScans()
  }, [refreshScans, user?.id])

  return (
    <ScanContext value={{
      scans,
      scansReady,
      getScanNotesState,
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
