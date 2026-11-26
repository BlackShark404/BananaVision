import { TableSkeleton } from "@/components/LoadingState"
import { scanRetryAction } from "@/lib/scanWriteFeedback"
import { ScanImage } from "@/components/ScanImage"
import { useState, useCallback, useRef, useEffect } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { ExportDropdown } from "@/components/ExportDropdown"
import { CULTIVARS, RIPENESS_LEVELS } from "@/types"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuLabel, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu"
import { ScrollText, Filter, Banana, TrendingUp, Target, Package, Users, Clock, MoreVertical, Box, DollarSign, Settings, AlertTriangle, Thermometer, Droplets, Wind, QrCode, X, Edit, Flag, Loader2, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { getImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import { scanWrite, scanRevision, isScanConflict } from "@/lib/scanWrites"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { normalizeScanLogSearch, scanLogParams, selectedScanLogDay, VALID_PAGE_SIZES } from "@/lib/scanLogFilters"
import { useDashboardResource } from "@/hooks/useDashboardResource"
import type { ScanLogRow, ScanLogParams, ScanLogReconciliation } from "@/types/scanLogs"
import { AppDateFilter } from "@/components/AppDateFilter"
import { Badge } from "@/components/ui/badge"
import { generateQRCodeDataUrl } from "@/lib/qrcode"
import { ScanLabelPrint } from "@/components/ScanLabelPrint"
import type { InventoryStatus, ScanResult } from "@/types"
import { AppStatusBadge } from "@/components/AppStatusBadge"
import { collectScanPages, type ApiScan } from "@/lib/scanData"
import { closedStockSpoilageLabel, formatSpoilageDays } from "@/lib/spoilageDisplay"
import { inventoryStatusChangeNote } from "@/lib/inventoryStatusChange"
import { liveShelfLifeLabel } from "@/lib/inventoryRisk"
import { liveRipeness } from "@/lib/ripenessProjection"
import { LIVE_RESUMED_EVENT, SCAN_UPDATED_EVENT, SCANS_ADDED_EVENT, newEventId, type ScanUpdateDetail } from "@/lib/liveEvents"
import { fingersLabel } from "@/lib/estimates"

type LogScan = Omit<ScanResult, "cultivar" | "ripeness" | "confidence"> & {
  cultivar: string
  ripeness: string
  confidence: number | null
  remainingDays: number | null
  atRisk: boolean
  operatorId?: string
  sourceKey?: string
}

async function mapScan(row: ScanLogRow, atRisk: boolean, asOf: string): Promise<LogScan> {
  const scan: LogScan = {
    id: row.id, revision: row.revision, dateTime: row.date_time, cultivar: row.cultivar ?? "Unknown", ripeness: row.ripeness ?? "Unknown",
    confidence: row.confidence, temperature: row.temperature ?? undefined, humidity: row.humidity ?? undefined,
    vpd: row.vpd ?? undefined,
    spoilageDays: row.spoilage_days ?? "Unknown", fingerCount: row.finger_count, operator: row.operator_name,
    source: row.source_name, intakeId: row.intake_id ?? undefined, inventoryStatus: row.inventory_status as InventoryStatus,
    statusUpdatedAt: row.status_updated_at ?? undefined, flagged: row.flagged, isOverridden: row.is_overridden,
    thumbnailUrl: row.thumbnail_url ? getImageUrl(row.thumbnail_url) : undefined, remainingDays: row.remaining_days,
    riskAsOf: asOf, shelfLifeWindow: row.shelf_life_window ?? null, ripenessProjection: row.ripeness_projection ?? null,
    atRisk, operatorId: row.operator_id, sourceKey: row.source_key,
  }
  // A QR rendering failure must not hide the scan history.
  try { scan.qrCode = await generateQRCodeDataUrl(scan) } catch { /* Thumbnail fallback remains available. */ }
  return scan
}

/** Replacing rows while a control is focused would interrupt an active edit. */
function isEditingTarget() {
  const target = document.activeElement
  return target instanceof HTMLElement
    && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
}

function newScanNotice(count: number) {
  return `${count} new Kiosk ${count === 1 ? "scan" : "scans"} available.`
}

function recordChangedNotice(count: number) {
  return `${count} scan ${count === 1 ? "record has" : "records have"} changed outside this view.`
}

/** The review queue is the flagged scans: low-confidence scans are flagged when saved. */
function isReview(scan: Pick<LogScan, "flagged">) {
  return scan.flagged === true
}

function mergeScanRow(row: LogScan, detail: ScanUpdateDetail): LogScan {
  const raw = detail.scan ?? {}
  const next: LogScan = { ...row }
  if (Number.isInteger(raw.revision)) next.revision = raw.revision
  if ("date_time" in raw && raw.date_time) next.dateTime = raw.date_time
  if ("cultivar" in raw) next.cultivar = raw.cultivar ?? "Unknown"
  if ("ripeness" in raw) next.ripeness = raw.ripeness ?? "Unknown"
  if ("confidence" in raw) next.confidence = raw.confidence ?? null
  if ("temperature" in raw) next.temperature = raw.temperature ?? undefined
  if ("humidity" in raw) next.humidity = raw.humidity ?? undefined
  if ("vpd" in raw) next.vpd = raw.vpd ?? undefined
  if ("spoilage_days" in raw) next.spoilageDays = raw.spoilage_days ?? "Unknown"
  if ("finger_count" in raw && typeof raw.finger_count === "number") next.fingerCount = raw.finger_count
  if ("operator_name" in raw) next.operator = raw.operator_name ?? "Unknown"
  if ("operator_id" in raw) next.operatorId = raw.operator_id ?? undefined
  if ("source_key" in raw) next.sourceKey = raw.source_key ?? undefined
  if ("source_name" in raw || "source_text" in raw) {
    next.source = raw.source_name ?? raw.source_text ?? undefined
  }
  if ("inventory_status" in raw && raw.inventory_status) next.inventoryStatus = raw.inventory_status
  if ("status_updated_at" in raw) next.statusUpdatedAt = raw.status_updated_at ?? undefined
  if ("flagged" in raw) next.flagged = raw.flagged === true
  if ("is_overridden" in raw) next.isOverridden = raw.is_overridden === true
  if ("intake_id" in raw) next.intakeId = raw.intake_id ?? undefined
  if ("remaining_days" in raw) next.remainingDays = raw.remaining_days ?? null
  if ("inventory_eligible" in raw) next.inventoryEligible = raw.inventory_eligible === true
  if ("risk_as_of" in raw) next.riskAsOf = raw.risk_as_of ?? undefined
  if ("shelf_life_window" in raw) next.shelfLifeWindow = raw.shelf_life_window ?? null
  if ("ripeness_projection" in raw) next.ripenessProjection = raw.ripeness_projection ?? null
  if ("has_notes" in raw) next.hasNotes = raw.has_notes === true
  if ("thumbnail_url" in raw) next.thumbnailUrl = raw.thumbnail_url ? getImageUrl(raw.thumbnail_url) : undefined
  // remaining_days is rounded for transport. The reconciliation response owns
  // the exact <=2-day decision; do not invent risk from a rounded event value.
  if (next.inventoryEligible === false) next.atRisk = false
  return next
}

/** Ambiguous search membership waits for the authorized reconciliation read. */
function filterMembership(
  scan: LogScan,
  params: ScanLogParams,
  sourceKeyKnown: boolean,
): "in" | "out" | "unknown" {
  if (params.inventory_status && scan.inventoryStatus !== params.inventory_status) return "out"
  if (params.flagged_only && scan.flagged !== true) return "out"
  if (params.cultivar && scan.cultivar !== params.cultivar) return "out"
  if (params.ripeness) {
    if (params.ripeness_scope === "current") {
      if (!scan.ripenessProjection) return "unknown"
      const current = liveRipeness(scan.ripenessProjection, Date.now(), scan.inventoryStatus)?.current
      if (current !== params.ripeness) return "out"
    } else if (scan.ripeness !== params.ripeness) {
      return "out"
    }
  }
  if (params.intake_id && scan.intakeId !== params.intake_id) return "out"
  if (params.operator_id) {
    if (!scan.operatorId) return "unknown"
    if (scan.operatorId !== params.operator_id) return "out"
  }
  if (params.stock_eligible && scan.inventoryEligible !== true) return "out"
  if (params.attention === "at-risk" && !scan.atRisk) return "out"
  if (params.attention === "review" && !isReview(scan)) return "out"
  // Successful = not under review with a recorded confidence (the server rule).
  if (params.attention === "success" && (isReview(scan) || scan.confidence === null)) return "out"
  if (params.source_key) {
    if (!sourceKeyKnown) return "unknown"
    if (scan.sourceKey !== params.source_key) return "out"
  }
  if (params.source) return "unknown"
  if (params.search) return "unknown"
  return "in"
}

export default function Logs() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  // The legacy review link becomes Status Flagged before the first request, so the old
  // query is never loaded.
  const canonical = normalizeScanLogSearch(searchParams)?.toString() ?? null
  useEffect(() => {
    if (canonical !== null) setSearchParams(new URLSearchParams(canonical), { replace: true })
  }, [canonical, setSearchParams])
  if (!user || canonical !== null) return null
  return <LogsContent key={`${user.id}:${user.role}`} />
}

function LogsContent() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useAuth()
  const queryKey = searchParams.toString()
  const requestParams = scanLogParams(searchParams)
  const search = searchParams.get("search") || ""
  const cultivarFilter = searchParams.get("cultivar") || "all"
  const ripenessFilter = searchParams.get("ripeness") || "all"
  const sourceFilter = searchParams.get("source_key") || (searchParams.get("source") ? `legacy:${searchParams.get("source")}` : "all")
  const operatorFilter = searchParams.get("operator_id") || "all"
  const intakeFilter = searchParams.get("intake") || "all"
  const statusFilter = searchParams.get("status") || "all"
  // "" means every date ("all", or a filtered link without a date).
  const dateFilter = selectedScanLogDay(searchParams)
  const cardFilter = requestParams.attention === "all" ? null : requestParams.attention
  const [qrModalScan, setQrModalScan] = useState<LogScan | null>(null)
  const [exporting, setExporting] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const [pendingScans, setPendingScans] = useState<Set<string>>(new Set())
  const inFlight = useRef(new Set<string>())
  const [statusAction, setStatusAction] = useState<{ scan: LogScan; status: InventoryStatus } | null>(null)
  const [statusReason, setStatusReason] = useState("")
  const snapshot = useRef<{ key: string; id: string; riskIds: Set<string> } | null>(null)
  const [newScanCount, setNewScanCount] = useState(0)
  const [newScanDismissed, setNewScanDismissed] = useState(false)
  const [changedIds, setChangedIds] = useState<Set<string>>(new Set())
  const [changedDismissed, setChangedDismissed] = useState(false)
  const seenScanEvents = useRef(new Set<string>())
  const pendingRequest = useRef<AbortController | null>(null)
  // Read at check time so a notice never replaces rows during an active edit.
  const pendingUi = useRef({ page: 1, blocked: false, loading: false })
  const interactionBlocked = useRef(false)
  const displayedRows = useRef<{ key: string; rows: LogScan[] } | null>(null)
  const deferredRows = useRef(false)
  const scheduleReconciliation = useRef<() => void>(() => {})

  const load = useCallback(async (signal: AbortSignal) => {
    const params = scanLogParams(new URLSearchParams(queryKey))
    const key = JSON.stringify({ ...params, page: undefined })
    const parentKey = JSON.stringify({ ...params, attention: "all", page: undefined })
    const cached = snapshot.current?.key === key
      || (params.attention === "at-risk" && snapshot.current?.key === parentKey)
      ? snapshot.current : null
    let result
    let live: ScanLogReconciliation | null = null
    let riskIds = cached?.riskIds
    try {
      result = await api.scanLogs.list({ ...params, stable: true, snapshot_id: cached?.id }, signal)
      if (cached && result.snapshot_id) {
        live = await api.scanLogs.reconcile({ ...params, snapshot_id: result.snapshot_id }, signal)
        if (live.snapshot_id !== result.snapshot_id) throw new Error("Browse snapshot changed. Please refresh.")
      }
    } catch (error) {
      const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0
      if (!signal.aborted && [409, 410].includes(status)) snapshot.current = null
      // An expired or superseded snapshot should not surface as a failed poll.
      if (!cached || signal.aborted || ![409, 410].includes(status)) throw error
      riskIds = undefined
      live = null
      result = await api.scanLogs.list({ ...params, stable: true }, signal)
    }
    try {
      if (!riskIds) {
        riskIds = new Set<string>()
        // Reuse the server's stock policy and exact numeric threshold at the same
        // snapshot time. No risk fields or formatted-range parsing in the API contract.
        if (params.attention !== "at-risk" && result.at_risk_count > 0) {
          if (!result.snapshot_id) throw new Error("Refresh to obtain a browse snapshot.")
          const snapshotId = result.snapshot_id
          const risk = await collectScanPages(async (page, page_size) => {
            const subset = await api.scanLogs.list({
              ...params, snapshot_id: snapshotId, attention: "at-risk",
              stable: true, page, page_size,
            }, signal)
            if (subset.snapshot_id !== snapshotId) throw new Error("Browse snapshot changed. Please refresh.")
            return subset
          }, signal)
          riskIds = new Set(risk.map(row => row.id))
        }
      }
    } catch (error) {
      if (!signal.aborted && typeof error === "object" && error !== null && "status" in error && [409, 410].includes(Number(error.status))) snapshot.current = null
      throw error
    }
    if (!signal.aborted && result.snapshot_id) snapshot.current = { key, id: result.snapshot_id, riskIds }
    const liveRisk = new Set(live?.at_risk_ids ?? [])
    const asOf = live?.generated_at ?? result.generated_at
    let rows = await Promise.all((live?.items ?? result.items).map(row => mapScan(
      row, live ? liveRisk.has(row.id) : params.attention === "at-risk" || riskIds.has(row.id), asOf,
    )))
    const previous = displayedRows.current?.key === queryKey ? displayedRows.current.rows : null
    const blocked = interactionBlocked.current || isEditingTarget()
    if (live && previous) {
      const old = new Map(previous.map(row => [row.id, row]))
      // Never keep a row the authoritative read has removed. Only defer value
      // changes during interaction; a newer committed event also beats this read.
      rows = rows.map(row => {
        const prior = old.get(row.id)
        return prior && (blocked || (prior.revision ?? 0) > (row.revision ?? 0)) ? prior : row
      })
      if (blocked) deferredRows.current = true
    }
    return { result, rows, live }
  }, [queryKey])
  const resource = useDashboardResource(load, { keepPreviousData: true })
  const refreshResource = resource.refresh
  displayedRows.current = resource.data && !resource.isPreviousData ? { key: queryKey, rows: resource.data.rows } : null
  interactionBlocked.current = exporting || !!statusAction || !!qrModalScan || pendingScans.size > 0
    || !!document.querySelector('[role="menu"], [role="listbox"]')
  // Coalesce bursts (including bulk mutations) into one bounded live read.
  // The resource owns cancellation, sequencing, errors and the existing 30s fallback.
  useEffect(() => {
    let timer: number | undefined
    const schedule = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        timer = undefined
        deferredRows.current = false
        void refreshResource()
      }, 200)
    }
    const onBlur = () => { if (deferredRows.current) schedule() }
    scheduleReconciliation.current = schedule
    window.addEventListener(SCANS_ADDED_EVENT, schedule)
    document.addEventListener("focusout", onBlur)
    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      scheduleReconciliation.current = () => {}
      window.removeEventListener(SCANS_ADDED_EVENT, schedule)
      document.removeEventListener("focusout", onBlur)
    }
  }, [refreshResource])
  useEffect(() => {
    if (deferredRows.current && !interactionBlocked.current && !isEditingTarget()) {
      deferredRows.current = false
      scheduleReconciliation.current()
    }
  })
  const refreshSnapshot = useCallback(() => {
    pendingRequest.current?.abort()
    pendingRequest.current = null
    snapshot.current = null
    setNewScanCount(0)
    setNewScanDismissed(false)
    setChangedIds(new Set())
    setChangedDismissed(false)
    return refreshResource()
  }, [refreshResource])
  const response = resource.data?.result
  const filtered = resource.data?.rows ?? []
  const liveTotals = resource.data?.live ?? response
  const stats = { avgConfidence: liveTotals?.avg_confidence, spoilingSoon: liveTotals?.at_risk_count, reviewCount: liveTotals?.review_count ?? 0 }
  const operators = response?.options.operators ?? []
  const sources = response?.options.sources ?? []

  // Row patches use the resource updater so concurrent renders cannot overwrite
  // a newer revision with an event payload that arrived slightly earlier.
  const latestResource = useRef(resource)
  latestResource.current = resource
  const applyScanUpdate = useCallback((detail: ScanUpdateDetail) => {
    if (!detail.scanId) return
    if (detail.eventId) {
      if (seenScanEvents.current.has(detail.eventId)) return
      seenScanEvents.current.add(detail.eventId)
      if (seenScanEvents.current.size > 200) {
        const oldest = seenScanEvents.current.values().next().value
        if (oldest) seenScanEvents.current.delete(oldest)
      }
    }
    scheduleReconciliation.current()
    const current = latestResource.current.data
    const row = current?.rows.find(item => item.id === detail.scanId)
    if (!current || !row) return
    const params = scanLogParams(new URLSearchParams(queryKey))
    const sourceKeyKnown = !params.source_key
      || current.result.options.sources.some(source => source.key === params.source_key)
    // Once this account's own write commits, applying its filter membership is
    // safe. Only an unrelated remote event waits for an active edit to finish.
    const local = detail.actorId === user?.id
    const blocked = !local && (pendingUi.current.blocked || isEditingTarget())
    if (!blocked) {
      if (detail.deleted) {
        latestResource.current.patch(previous => previous && previous.rows.some(item => item.id === detail.scanId)
          ? {
              ...previous,
              rows: previous.rows.filter(item => item.id !== detail.scanId),
            }
          : previous)
      } else {
        if (!Number.isInteger(detail.revision) || detail.revision <= (row.revision ?? 0)) return
        latestResource.current.patch(previous => {
          const visible = previous?.rows.find(item => item.id === detail.scanId)
          if (!previous || !visible || detail.revision <= (visible.revision ?? 0)) return previous
          const merged = mergeScanRow(visible, detail)
          const membership = filterMembership(merged, params, sourceKeyKnown)
          if (membership === "out") {
            return {
              ...previous,
              rows: previous.rows.filter(item => item.id !== detail.scanId),
            }
          }
          return {
            ...previous,
            rows: previous.rows.map(item => item.id === detail.scanId ? merged : item),
          }
        })
      }
    }
    // The acting tab already sees its own optimistic row; only remote edits need
    // a notice explaining that totals and filtered membership may be stale.
    if (detail.actorId === user?.id) return
    setChangedIds(previous => {
      if (previous.has(detail.scanId)) return previous
      const next = new Set(previous)
      next.add(detail.scanId)
      return next
    })
    setChangedDismissed(false)
  }, [queryKey, user?.id])
  const latestApplyScanUpdate = useRef(applyScanUpdate)
  useEffect(() => { latestApplyScanUpdate.current = applyScanUpdate }, [applyScanUpdate])
  useEffect(() => {
    const onScanUpdated = (event: Event) => {
      const detail = (event as CustomEvent<ScanUpdateDetail>).detail
      if (detail) latestApplyScanUpdate.current(detail)
    }
    window.addEventListener(SCAN_UPDATED_EVENT, onScanUpdated)
    return () => window.removeEventListener(SCAN_UPDATED_EVENT, onScanUpdated)
  }, [])

  useEffect(() => {
    pendingUi.current = {
      page: response?.page ?? requestParams.page,
      blocked: resource.isPreviousData || resource.loading || exporting || !!statusAction
        || !!qrModalScan || pendingScans.size > 0
        || !!document.querySelector('[role="menu"], [role="listbox"]'),
      loading: resource.loading || resource.isPreviousData,
    }
  })

  const checkPendingScans = useCallback(async () => {
    const current = snapshot.current
    if (!current || pendingUi.current.loading) return
    const params = scanLogParams(new URLSearchParams(queryKey))
    const key = JSON.stringify({ ...params, page: undefined })
    const parentKey = JSON.stringify({ ...params, attention: "all", page: undefined })
    // A query change owns a different snapshot; never count against a stale one.
    if (current.key !== key && !(params.attention === "at-risk" && current.key === parentKey)) return
    pendingRequest.current?.abort()
    const controller = new AbortController()
    pendingRequest.current = controller
    try {
      const pending = await api.scanLogs.pending(
        { ...params, stable: true, snapshot_id: current.id }, controller.signal,
      )
      if (controller.signal.aborted || snapshot.current?.id !== current.id) return
      if (pending.new_count <= 0) {
        setNewScanCount(0)
        setNewScanDismissed(false)
        return
      }
      // Page 1 may show the latest rows only when no control is mid-edit.
      // Page 2+ and blocked page 1 keep the frozen rows and offer the notice.
      const blockedNow = pendingUi.current.blocked || isEditingTarget()
        || !!document.querySelector('[role="menu"], [role="listbox"]')
      if (pendingUi.current.page === 1 && !blockedNow && !pendingUi.current.loading
        && !document.hidden) {
        setNewScanCount(0)
        setNewScanDismissed(false)
        snapshot.current = null
        await refreshResource()
        return
      }
      setNewScanCount(pending.new_count)
    } catch {
      // The notice is advisory; the next poll, event or reconnect retries.
    } finally {
      if (pendingRequest.current === controller) pendingRequest.current = null
    }
  }, [queryKey, refreshResource])
  const latestCheckPending = useRef(checkPendingScans)
  useEffect(() => { latestCheckPending.current = checkPendingScans }, [checkPendingScans])
  useEffect(() => {
    const onNewScans = () => { void latestCheckPending.current() }
    window.addEventListener(SCANS_ADDED_EVENT, onNewScans)
    window.addEventListener(LIVE_RESUMED_EVENT, onNewScans)
    return () => {
      window.removeEventListener(SCANS_ADDED_EVENT, onNewScans)
      window.removeEventListener(LIVE_RESUMED_EVENT, onNewScans)
      pendingRequest.current?.abort()
    }
  }, [])
  // Polling keeps the frozen rows but still notices scans committed without
  // a delivered event (for example while another client was disconnected).
  useEffect(() => {
    if (!resource.receivedAt || resource.isPreviousData || !response?.snapshot_id) return
    void latestCheckPending.current()
  }, [resource.receivedAt, resource.isPreviousData, response?.snapshot_id])
  // A fresh snapshot already contains every committed scan it was built from.
  useEffect(() => {
    setNewScanCount(0)
    setNewScanDismissed(false)
    setChangedIds(new Set())
    setChangedDismissed(false)
  }, [response?.snapshot_id])

  const updateFilters = (changes: Record<string, string | undefined>, replace = false) => {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(changes)) {
        if (!value || (value === "all" && key !== "date")) next.delete(key)
        else next.set(key, value)
      }
      if (!("page" in changes)) next.delete("page")
      return next
    }, { replace })
  }
  // The default view: no filters, every date.
  const clearAllFilters = () => setSearchParams({})
  const setSearch = (value: string) => updateFilters({ search: value }, true)
  const setCultivarFilter = (value: string) => updateFilters({ cultivar: value })
  const setRipenessFilter = (value: string) => updateFilters({ ripeness: value, ripeness_scope: undefined })
  const setSourceFilter = (value: string) => updateFilters({ source_key: value, source: undefined })
  const setOperatorFilter = (value: string) => updateFilters({ operator_id: value })
  const setStatusFilter = (value: string) => updateFilters({ status: value })
  const setCardFilter = (value: string | null) => updateFilters({ attention: value ?? undefined })
  const reviewQueue = statusFilter === "Flagged" || cardFilter === "review"
  const clearReviewFilter = () => updateFilters({
    ...(statusFilter === "Flagged" ? { status: undefined } : {}),
    ...(cardFilter === "review" ? { attention: undefined } : {}),
  })

  const viewLatestScans = () => {
    pendingRequest.current?.abort()
    pendingRequest.current = null
    snapshot.current = null
    setNewScanCount(0)
    setNewScanDismissed(false)
    setChangedIds(new Set())
    setChangedDismissed(false)
    // Keep every applicable filter and sort, but a new snapshot starts at page 1.
    if (requestParams.page !== 1) updateFilters({ page: undefined })
    else void refreshResource()
  }

  // A deletion/status change can shrink the final page while this view is open.
  useEffect(() => {
    if (!resource.isPreviousData && response && response.page > 1 && response.items.length === 0) {
      setSearchParams(previous => {
        const next = new URLSearchParams(previous)
        next.set("page", String(Math.max(1, Math.ceil(response.total / requestParams.page_size))))
        return next
      }, { replace: true })
    }
  }, [response, resource.isPreviousData, requestParams.page_size, setSearchParams])

  const handleStatusUpdate = async () => {
    if (resource.isPreviousData || !statusAction || !statusReason.trim() || inFlight.current.has(statusAction.scan.id)) return
    const { scan, status } = statusAction
    inFlight.current.add(scan.id)
    setPendingScans(new Set(inFlight.current))
    const patchDetail = (saved: ApiScan) => applyScanUpdate({
      eventId: newEventId(), scanId: scan.id, revision: saved.revision, kind: "status",
      actorId: user?.id ?? "", changed: ["inventory_status"], partial: false, scan: saved,
    })
    try {
      const saved = await scanWrite(`${user?.id}:${scan.id}:status`, {
        expected_revision: scanRevision(scan.revision), inventory_status: status, reason: statusReason.trim(),
      }, body => api.scans.updateStatus(scan.id, body))
      // Patch the visible row instead of rebuilding the frozen browse snapshot.
      patchDetail(saved)
      toast.success(`Scan marked as ${status}`)
      setStatusAction(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Status update failed", {
        action: scanRetryAction(error, () => { setStatusAction(null); void api.scans.detail(scan.id)
          .then(saved => patchDetail(saved))
          .catch(error => toast.error(error.message)) }) ?? (isScanConflict(error) ? { label: "Reload latest", onClick: () => {
          void api.scans.detail(scan.id).then(saved => {
            setStatusAction(current => current?.scan.id === scan.id ? { ...current, scan: { ...current.scan,
              revision: saved.revision, inventoryStatus: saved.inventory_status } } : current)
            patchDetail(saved)
          }).catch(error => toast.error(error.message))
        } } : undefined),
      })
    }
    finally { inFlight.current.delete(scan.id); setPendingScans(new Set(inFlight.current)) }
  }

  const getStatus = (scan: LogScan) => {
    return (
      <div className="flex items-center gap-1.5">
        {scan.flagged && (
          <span className="relative flex" title="Flagged for QC Review">
            <Flag className="w-3.5 h-3.5 text-red-500 fill-red-500" />
          </span>
        )}
        <AppStatusBadge status={scan.inventoryStatus || "In Stock"} type="inventory" />
      </div>
    )
  }

  const exportLogs = async (format: "xlsx" | "pdf") => {
    if (resource.isPreviousData || resource.loading) return
    setExporting(true)
    try {
      await api.scanLogs.export({ ...requestParams, snapshot_id: response?.snapshot_id, format }, AbortSignal.timeout(300_000))
      toast.success(`Exported all matching scan records to ${format === "xlsx" ? "Excel" : "PDF"}`)
    } catch (error) { toast.error(error instanceof Error ? error.message : "Export failed. Check connection or narrow date range.") }
    finally { setExporting(false) }
  }

const columns: ColumnDef<LogScan>[] = [
    {
      header: "Image",
      className: "w-20",
      cell: (scan) => (
        <div className="w-14">
          <AspectRatio ratio={1} className="rounded-lg overflow-hidden bg-muted/50 border">
            {scan.thumbnailUrl ? (
              <ScanImage src={scan.thumbnailUrl} alt={scan.cultivar} defer loading="lazy" decoding="async" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Banana className="w-6 h-6 text-muted-foreground/40" />
              </div>
            )}
          </AspectRatio>
        </div>
      ),
    },
    {
      header: "QR Code",
      className: "w-16",
      stopPropagation: true,
      cell: (scan) => scan.qrCode ? (
        <button
          className="w-10 h-10 rounded-lg overflow-hidden border bg-white hover:ring-2 hover:ring-primary/30 transition-all cursor-pointer"
          title="View QR Code"
          onClick={() => setQrModalScan(scan)}
        >
          <img src={scan.qrCode} alt="QR" className="w-full h-full object-contain" />
        </button>
      ) : (
        <div className="w-10 h-10 rounded-lg border bg-muted/50 flex items-center justify-center">
          <QrCode className="w-5 h-5 text-muted-foreground/40" />
        </div>
      ),
    },
    {
      header: "Date/Time",
      sortable: true,
      sortKey: "date_time",
      cell: (scan) => (
        <div className="text-sm">
          <Link to={`/scans/${scan.id}`} className="hover:underline focus-visible:underline">{new Date(scan.dateTime).toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })}</Link>
          <br />
          <span className="text-xs text-muted-foreground">{new Date(scan.dateTime).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila" })}</span>
        </div>
      ),
    },
    {
      header: "Cultivar",
      sortable: true,
      sortKey: "cultivar",
      cell: (scan) => (
        <div className="flex items-center gap-1.5">
          <span className="font-medium">{scan.cultivar}</span>
          {scan.isOverridden && <span title="Overridden"><Edit className="w-3.5 h-3.5 text-amber-500" /></span>}
        </div>
      ),
    },
    {
      header: "Ripeness",
      cell: (scan) => {
        const live = liveRipeness(scan.ripenessProjection, now, scan.inventoryStatus)
        const display = live?.current ?? scan.ripeness
        const progressed = live?.progressed ?? false
        return (
          <div className="space-y-0.5">
            <AppStatusBadge
              type="ripeness"
              status={display}
              label={live ? live.badgeLabel : display}
              size="md"
            />
            {progressed && (
              <span
                className="block text-[10px] text-muted-foreground"
                title="Observed ripeness when scanned; current stage is projected from elapsed days and scan conditions"
              >
                {scan.ripeness} at scan
              </span>
            )}
          </div>
        )
      },
    },
    {
      header: "Source",
      cell: (scan) => scan.source ? (
        <span className="font-medium text-sm">{scan.source}</span>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      ),
    },
    {
      header: "Confidence",
      sortable: true,
      sortKey: "confidence",
      cell: (scan) => (
        <div className="flex items-center gap-2">
          <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
            <div className="h-full bg-primary rounded-full" style={{ width: `${scan.confidence ?? 0}%` }} />
          </div>
          <span className="text-sm">{scan.confidence === null ? "—" : `${scan.confidence}%`}</span>
        </div>
      ),
    },
    {
      header: "IoT Data",
      cell: (scan) => (
        <div className="flex flex-col gap-1 text-xs">
          {scan.temperature != null ? (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Thermometer className="h-3.5 w-3.5" />
              <span>{scan.temperature.toFixed(1)}°C</span>
            </div>
          ) : null}
          {scan.humidity != null ? (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Droplets className="h-3.5 w-3.5" />
              <span>{scan.humidity.toFixed(1)}%</span>
            </div>
          ) : null}
          <div role="group" aria-label="Vapor pressure deficit" title="Vapor Pressure Deficit recorded for this scan" className="flex items-center gap-1.5 text-muted-foreground">
            <Wind aria-hidden="true" className="h-3.5 w-3.5" />
            <span>VPD {scan.vpd != null && Number.isFinite(scan.vpd)
              ? `${scan.vpd.toFixed(3)} kPa`
              : <span aria-label="VPD unavailable">—</span>}</span>
          </div>
        </div>
      ),
    },
    {
      header: "Est. Spoilage",
      sortable: true,
      sortKey: "spoilage_days",
      cell: (scan) => {
        // In-stock rows lead with the live countdown and sold, spoiled or processed rows with
        // their outcome; the stored estimate stays beneath either.
        const countdown = scan.inventoryStatus === "In Stock" ? liveShelfLifeLabel(scan, now) : null
        const outcome = countdown === null ? closedStockSpoilageLabel(scan.inventoryStatus) : null
        const lead = countdown ?? outcome
        const estimate = formatSpoilageDays(scan.spoilageDays)
        const meaning = countdown !== null
          ? "Live remaining shelf life from the scan's prediction"
          : outcome !== null ? "No countdown: this stock is no longer in inventory" : "Estimate when scanned"
        return (
          <div className="text-sm">
            <span
              className={scan.atRisk ? "inline-flex items-center gap-1 text-orange-600" : undefined}
              title={scan.atRisk ? `At risk: eligible stock whose estimate midpoint is 2 days or less away, or already passed, at this snapshot. ${meaning}.` : meaning}
            >
              {scan.atRisk && <AlertTriangle role="img" aria-label="At-risk scan" className="h-3.5 w-3.5 shrink-0" />}
              {lead ?? estimate}
            </span>
            {lead !== null && estimate !== "Unknown" && (
              <span className="block text-[10px] text-muted-foreground" title="Estimate when scanned">
                Est. {estimate} from scan
              </span>
            )}
          </div>
        )
      },
    },
    {
      header: fingersLabel(),
      sortable: true,
      sortKey: "finger_count",
      cell: (scan) => <span className="text-sm">{scan.fingerCount}</span>,
    },
    ...(user?.role === "Admin" ? [{
      header: "Operator",
      cell: (scan: LogScan) => (
        <div className="flex items-center gap-2">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
              {scan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <span className="text-sm">{scan.operator}</span>
        </div>
      ),
    }] : []),
    {
      header: "Status",
      cell: (scan) => getStatus(scan),
    },
    ...(user?.role === "Admin" ? [{
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (scan: LogScan) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <span className="sr-only">Open menu</span>
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>Update Status</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {([
              { actionStatus: "In Stock" as InventoryStatus, icon: Box, color: "text-blue-500" },
              { actionStatus: "For Processing" as InventoryStatus, icon: Settings, color: "text-purple-500" },
              { actionStatus: "Sold" as InventoryStatus, icon: DollarSign, color: "text-emerald-500" },
              { actionStatus: "Spoiled" as InventoryStatus, icon: AlertTriangle, color: "text-red-500" },
            ] as const).map(({ actionStatus, icon: ItemIcon, color }) => {
              const isDisabled = resource.isPreviousData || scan.inventoryStatus === actionStatus || pendingScans.has(scan.id)
              return (
                <DropdownMenuItem
                  key={actionStatus}
                  onClick={() => { if (!isDisabled) { setStatusAction({ scan, status: actionStatus }); setStatusReason("") } }}
                  disabled={isDisabled}
                  className={isDisabled ? "opacity-40 cursor-not-allowed" : ""}
                >
                  <ItemIcon className={`mr-2 h-4 w-4 ${isDisabled ? "text-muted-foreground" : color}`} />
                  <span>Mark {actionStatus}</span>
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    }] : []),
  ]

  return (
    <>
    <div className="space-y-6">
      <Dialog open={!!statusAction} onOpenChange={open => { if (!open && !pendingScans.size) setStatusAction(null) }}>
        <DialogContent className="rounded-2xl">
          <DialogHeader><DialogTitle>Mark scan as {statusAction?.status}?</DialogTitle><DialogDescription>{statusAction ? inventoryStatusChangeNote(statusAction.scan.inventoryStatus || "In Stock", statusAction.status) : null}</DialogDescription></DialogHeader>
          <Label htmlFor="status-reason">Reason for change</Label>
          <Textarea id="status-reason" value={statusReason} onChange={event => setStatusReason(event.target.value)} disabled={!!pendingScans.size} />
          <DialogFooter><Button variant="outline" disabled={!!pendingScans.size} onClick={() => setStatusAction(null)}>Cancel</Button><Button disabled={resource.isPreviousData || !statusReason.trim() || !!pendingScans.size} onClick={() => void handleStatusUpdate()}>{!!pendingScans.size && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{pendingScans.size ? "Saving…" : "Save Changes"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <AppPageHeader
        title={intakeFilter !== "all" ? `Logs for Intake ${intakeFilter.substring(0, 8)}` : "Scan Logs"}
        description={intakeFilter !== "all" ? "Viewing scans grouped under this delivery" : "View all banana scan results"}
        icon={ScrollText}
        action={
          <div className="flex items-center gap-2 w-full sm:w-auto">
            {intakeFilter !== "all" && (
              <Button variant="ghost" onClick={() => { updateFilters({ intake: undefined }) }}>
                Clear Intake Filter
              </Button>
            )}
            <ExportDropdown
              onExportXlsx={() => void exportLogs("xlsx")}
              onExportPdf={() => void exportLogs("pdf")}
              disabled={exporting || resource.loading || resource.isPreviousData}
              exporting={exporting}
            />
          </div>
        }
      />

      {resource.isPreviousData && <p role="status" className="text-sm text-muted-foreground">Showing results for the previous selection. {resource.loading ? "Updating records…" : "Retry to load the selected filters."}</p>}
      {resource.error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <strong>{response ? "Scan Logs refresh failed. Showing the last successful results." : "Scan Logs unavailable."}</strong> {resource.error}
        <Button variant="link" size="sm" onClick={() => void refreshSnapshot()}>Retry</Button>
      </div>}

      {newScanCount > 0 && !newScanDismissed && (
        <div role="status" aria-live="polite" className="flex flex-col gap-3 rounded-lg border border-primary/25 bg-primary/5 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <RefreshCw aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            <p><strong>{newScanNotice(newScanCount)}</strong> Would you like to refresh Scan Logs?</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:ml-4">
            <Button size="sm" onClick={viewLatestScans}>View Latest Scans</Button>
            <Button size="sm" variant="ghost" onClick={() => setNewScanDismissed(true)}>Later</Button>
          </div>
        </div>
      )}
      {newScanCount > 0 && newScanDismissed && (
        <div role="status" className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw aria-hidden="true" className="size-3.5" />
          <span>{newScanNotice(newScanCount)}</span>
          <Button variant="link" size="sm" className="h-auto p-0" onClick={viewLatestScans}>Show latest scans</Button>
        </div>
      )}
      {changedIds.size > 0 && !changedDismissed && (
        <div role="status" aria-live="polite" className="flex flex-col gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <RefreshCw aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <p><strong>{recordChangedNotice(changedIds.size)}</strong> Totals update automatically. Row changes wait while you edit; Refresh rebuilds the page order and export.</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:ml-4">
            <Button size="sm" onClick={() => void refreshSnapshot()}>Refresh</Button>
            <Button size="sm" variant="ghost" onClick={() => setChangedDismissed(true)}>Later</Button>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
        <AppStatsCard
          loading={!response && resource.loading}
          title="Total Scans"
          value={liveTotals ? liveTotals.total : resource.loading ? "…" : "—"}
          icon={TrendingUp}
          delay={50}
          description={response ? "Live matching records · click to reset filters" : resource.loading ? "Loading…" : "Unavailable"}
          onClick={clearAllFilters}
        />
        <AppStatsCard
          loading={!response && resource.loading}
          title="Avg Confidence"
          value={response ? stats.avgConfidence == null ? "—" : `${stats.avgConfidence.toFixed(1)}%` : resource.loading ? "…" : "—"}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Current classification confidence"
        />
        <AppStatsCard
          loading={!response && resource.loading}
          title="At-Risk Scans"
          value={response ? stats.spoilingSoon ?? 0 : resource.loading ? "…" : "—"}
          icon={Clock}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={150}
          description="In stock: ≤2 days or overdue"
          onClick={() => setCardFilter(cardFilter === "at-risk" ? null : "at-risk")}
          active={cardFilter === "at-risk"}
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search by cultivar, operator, or ID..."
        hasActiveFilters={search !== "" || cultivarFilter !== "all" || ripenessFilter !== "all" || sourceFilter !== "all" || operatorFilter !== "all" || statusFilter !== "all" || intakeFilter !== "all" || cardFilter !== null || dateFilter !== "" || requestParams.stock_eligible}
        onClearFilters={clearAllFilters}
      >
        <Select value={cultivarFilter} onValueChange={(v) => { setCultivarFilter(v) }}>
          <SelectTrigger className="w-full sm:w-35 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Cultivar" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Cultivars</SelectItem>
            {CULTIVARS.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={ripenessFilter} onValueChange={(v) => { setRipenessFilter(v) }}>
          <SelectTrigger className="w-full sm:w-35 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Ripeness" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Ripeness</SelectItem>
            {RIPENESS_LEVELS.map((r) => (
              <SelectItem key={r} value={r}>{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v) }}>
          <SelectTrigger className="w-full sm:w-47.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {sourceFilter !== "all" && !sources.some(source => source.key === sourceFilter) && <SelectItem value={sourceFilter}>{searchParams.get("source") || "Selected source"}</SelectItem>}
            {sources.map(source => <SelectItem key={source.key} value={source.key}>{source.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {user?.role === "Admin" && (
          <Select value={operatorFilter} onValueChange={(v) => { setOperatorFilter(v) }}>
            <SelectTrigger className="w-full sm:w-45 h-10!">
              <Users className="w-3.5 h-3.5 mr-1.5" />
              <SelectValue placeholder="Operator" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Operators</SelectItem>
              {operatorFilter !== "all" && !operators.some(operator => operator.operator_id === operatorFilter) && <SelectItem value={operatorFilter}>Selected operator</SelectItem>}
              {operators.map(operator => <SelectItem key={operator.operator_id} value={operator.operator_id}>{operator.name} (@{operator.username})</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v) }}>
          <SelectTrigger className="w-full sm:w-37.5 h-10!">
            <Package className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="In Stock">In Stock</SelectItem>
            <SelectItem value="Sold">Sold</SelectItem>
            <SelectItem value="For Processing">For Processing</SelectItem>
            <SelectItem value="Spoiled">Spoiled</SelectItem>
            <SelectItem value="Flagged">Flagged</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex w-full sm:w-auto items-center gap-1">
          <AppDateFilter value={dateFilter} onChange={value => updateFilters({ date: value || undefined })}
            label="Scan date" emptyText="All dates" title="Filter by calendar date in Asia/Manila" className="w-full sm:w-44" />
          {dateFilter && <Button type="button" variant="ghost" size="icon" aria-label="Clear scan date" title="All dates" onClick={() => updateFilters({ date: undefined })}><X className="size-4" /></Button>}
        </div>
      </AppTableFilters>

      {cardFilter === "at-risk" && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">At-Risk Scans</Badge>
        <span className="text-xs text-muted-foreground">In stock with estimated spoilage in 2 days or less, including overdue estimates.</span>
        <Button variant="ghost" size="sm" onClick={() => setCardFilter(null)}>Clear risk filter</Button>
      </div>}

      {reviewQueue && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">Pending Quality Reviews</Badge>
        <span className="text-xs text-muted-foreground">Scans flagged for review. Remove a scan's flag after checking it to clear it from this queue.</span>
        <Button variant="ghost" size="sm" onClick={clearReviewFilter}>Clear review filter</Button>
      </div>}

      {cardFilter === "success" && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">Auto-approved scans</Badge>
        <span className="text-xs text-muted-foreground">Unflagged scans with a recorded confidence; new scans below the confidence threshold are flagged when saved. This is not measured accuracy.</span>
        <Button variant="ghost" size="sm" onClick={() => setCardFilter(null)}>Clear success filter</Button>
      </div>}

      {requestParams.stock_eligible && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">Eligible stock only</Badge>
        <span className="text-xs text-muted-foreground">In-stock scans linked to an active intake or valid unlinked provenance.</span>
        <Button variant="ghost" size="sm" onClick={() => updateFilters({ stock: undefined })}>Clear stock filter</Button>
      </div>}

      {requestParams.ripeness_scope === "current" && requestParams.ripeness && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">Est. Current Ripeness: {requestParams.ripeness}</Badge>
        <span className="text-xs text-muted-foreground">Showing scans projected to be {requestParams.ripeness} today (Asia/Manila).</span>
        <Button variant="ghost" size="sm" onClick={() => updateFilters({ ripeness_scope: undefined })}>Switch to scanned ripeness</Button>
      </div>}

      {/* Table */}
      {!response ? resource.loading ? <TableSkeleton columns={8} label="Loading scan records…" /> : <Card className="p-10 text-center text-muted-foreground" role="status">{resource.loading ? <span className="inline-flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Loading scan records…</span> : "Records could not be loaded. Retry above."}</Card> : (
      <AppDataTable
        data={filtered}
        columns={columns}
        rowKey={(scan) => scan.id}
        onRowClick={(scan) => navigate(`/scans/${scan.id}`)}
        pagination={{
          pageSize: requestParams.page_size,
          pageSizeOptions: [...VALID_PAGE_SIZES],
          onPageSizeChange: (newPageSize) => {
            if (!resource.isPreviousData) {
              updateFilters({ limit: String(newPageSize), page_size: String(newPageSize), page: "1" })
            }
          },
        }}
        serverState={{ page: response.page, total: response.total, sort: { key: requestParams.sort, direction: requestParams.direction },
          onPageChange: page => { if (!resource.isPreviousData) updateFilters({ page: String(page) }) },
          onSortChange: (sort, direction) => { if (!resource.isPreviousData) updateFilters({ sort, direction }) },
        }}
        rowClassName={(scan) => scan.flagged ? 'border-l-3 border-l-red-500 bg-red-500/[0.03]' : ''}
        emptyState={{
          icon: Banana,
          title: "No scans match your filters",
          description: "Try adjusting your search or filter criteria"
        }}
      />
      )}
    </div>

      {/* QR Code Modal */}
      {qrModalScan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in" onClick={() => setQrModalScan(null)}>
          <div
            className="relative bg-background rounded-2xl shadow-2xl p-6 max-w-xs w-full mx-4 max-h-[90dvh] overflow-y-auto animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="absolute top-3 right-3 p-1.5 rounded-full hover:bg-muted transition-colors"
              onClick={() => setQrModalScan(null)}
            >
              <X className="w-4 h-4" />
            </button>
            <div className="text-center space-y-4">
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                <QrCode className="w-4 h-4" />
                Scan QR Code
              </div>
              <ScanLabelPrint key={qrModalScan.id} scanId={qrModalScan.id}>
                <div>
                  <p className="font-semibold">{qrModalScan.cultivar}</p>
                  <p className="text-xs text-muted-foreground font-mono uppercase">ID: {qrModalScan.id}</p>
                </div>
              </ScanLabelPrint>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
