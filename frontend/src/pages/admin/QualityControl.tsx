import { scanRetryAction } from "@/lib/scanWriteFeedback"
import { api } from "@/lib/api"
import { isScanConflict, UncertainScanWrite } from "@/lib/scanWrites"
import { ScanImage } from "@/components/ScanImage"
import BoundingBoxOverlay from "@/components/BoundingBoxOverlay"
import { useState, useMemo, useEffect, useRef } from "react"
import { useScans } from "@/context/ScanContext"
import { useAdmin } from "@/context/AdminContext"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { AppStatsCard } from "@/components/AppStatsCard"
import { ExportDropdown } from "@/components/ExportDropdown"
import { downloadCsv, downloadXlsx } from "@/lib/exportUtils"
import { Input } from "@/components/ui/input"
import { NumberField } from "@/components/ui/number-field"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Loader2, ShieldCheck, Flag, MessageSquare, Edit, AlertTriangle, CheckCircle, Banana, ChevronsLeft, ChevronsRight, Filter, Thermometer, Droplets } from "lucide-react"
import { toast } from "sonner"
import { getSpoilageDays } from "@/lib/utils"
import { formatSpoilageDays } from "@/lib/spoilageDisplay"
import { liveShelfLifeLabel } from "@/lib/inventoryRisk"
import { CULTIVARS, RIPENESS_LEVELS, type ScanResult, type Cultivar, type Ripeness } from "@/types"
import { AppChangePreview } from "@/components/AppChangePreview"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppActionButton } from "@/components/AppActionButton"
import { AppTableFilters } from "@/components/AppTableFilters"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppStatusBadge } from "@/components/AppStatusBadge"
import { inManila, manilaDayKey } from "@/lib/manilaTime"
import { fingerCountIsEstimate, fingersLabel } from "@/lib/estimates"

// Estimated columns say so; the cells stay plain numbers.
const EXPORT_HEADERS = ["Scan ID", "Date/Time", "Operator", "Cultivar", "Ripeness", "Confidence (%)", "Temperature (°C)", "Humidity (%)", "Est. Spoilage (days)", "Est. Finger Count", "Source", "Flagged", "Status"]

const PAGE_SIZE = 15

export default function QualityControl() {
  const { scans, scansLoading, scansReady, scansError, refreshScans, flagScan, addScanNote, getScanNotes, getScanNotesState, loadScanNotes, updateScanData, acceptScan } = useScans()
  const { config } = useAdmin()
  const [selectedScan, setSelectedScan] = useState<ScanResult | null>(null)
  const [noteText, setNoteText] = useState("")
  const [editBaseline, setEditBaseline] = useState<ScanResult | null>(null)
  const [editReason, setEditReason] = useState("")
  const [fingerCountEdited, setFingerCountEdited] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState<Partial<Omit<ScanResult, 'fingerCount' | 'spoilageDays'> & { fingerCount: number | string; spoilageDays: string }>>({})
  const [filterView, setFilterView] = useState<"all" | "flagged" | "low-confidence" | "overridden">("all")
  const [sourceFilter, setSourceFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [pendingWrite, setPendingWrite] = useState(false)
  const [writeFailure, setWriteFailure] = useState<{ message: string; action?: { label: string; onClick: () => Promise<void> } } | null>(null)
  const [recoveringWrite, setRecoveringWrite] = useState(false)
  // The countdown changes at Manila midnight; re-read the clock so an open dialog follows it.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  // Detail reads also enrich list rows with camera detections at the same revision.
  // Refresh the displayed record, preserving the user's correction draft and baseline.
  useEffect(() => {
    setSelectedScan(previous => {
      if (!previous) return previous
      const current = scans.find(scan => scan.id === previous.id)
      return current && (current.revision ?? 0) >= (previous.revision ?? 0) ? current : previous
    })
  }, [scans])

  const recordedCameraIds = [...new Set([
    ...(selectedScan?.images ?? []).map(image => image.camera_id),
    ...(selectedScan?.detections ?? []).map(detection => detection.camera_id),
  ])]
  const cameraViews = recordedCameraIds.map(id => {
    const detection = selectedScan?.detections?.find(item => item.camera_id === id)
    return {
      id,
      label: detection?.camera_label || id,
      imageUrl: selectedScan?.images?.find(image => image.camera_id === id)?.file_path,
      boxes: detection?.bounding_boxes ?? [],
      confidence: detection?.confidence,
    }
  })

  const activeSources = useMemo(() => {
    return Array.from(new Set(scans.map(s => s.source).filter(Boolean)))
  }, [scans])

  const filteredScans = useMemo(() => {
    let filtered = scans
    
    if (filterView === "flagged") {
      filtered = filtered.filter(s => s.flagged)
    } else if (filterView === "low-confidence") {
      filtered = filtered.filter(s => s.confidence !== null && s.confidence < config.confidenceThreshold)
    } else if (filterView === "overridden") {
      filtered = filtered.filter(s => s.isOverridden)
    }
    
    if (sourceFilter !== "all") {
      filtered = filtered.filter(s => s.source === sourceFilter)
    }
    
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter(s =>
        s.operator.toLowerCase().includes(q) ||
        s.cultivar.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q) ||
        (s.source && s.source.toLowerCase().includes(q))
      )
    }
    
    return [...filtered].sort((a, b) => new Date(b.dateTime).getTime() - new Date(a.dateTime).getTime())
  }, [scans, filterView, sourceFilter, searchQuery, config.confidenceThreshold])

  const reportWriteError = (error: unknown, scanId?: string, confirmed?: (request: Readonly<Record<string, unknown>>) => void) => {
    const message = error instanceof Error ? error.message : "Could not save changes. Please retry."
    if (scanId && selectedScan?.id === scanId) {
      const reload = async () => {
        const saved = acceptScan(await api.scans.detail(scanId))
        setSelectedScan(previous => previous?.id === scanId ? saved : previous)
        setEditBaseline(previous => previous?.id === scanId ? { ...previous, revision: saved.revision } : previous)
      }
      setWriteFailure({ message, action: isScanConflict(error) ? { label: "Reload latest", onClick: reload }
        : error instanceof UncertainScanWrite ? { label: "Retry previous", onClick: async () => {
          await error.retry()
          confirmed?.(error.request)
          // The retained write is now confirmed and cannot be replayed again. A failed
          // follow-up read must offer read recovery, not the consumed write retry.
          setWriteFailure({ message: "Previous change confirmed. Reloading the latest record…", action: { label: "Reload latest", onClick: reload } })
          await reload()
          toast.success("Previous change confirmed. Review the latest record before making another change.")
        } } : undefined })
      return
    }
    toast.error(error instanceof Error ? error.message : "Could not save changes. Please retry.", {
      action: scanRetryAction(error, request => { confirmed?.(request); if (scanId) void api.scans.detail(scanId).then(raw => { const saved = acceptScan(raw); setSelectedScan(previous => previous?.id === scanId ? saved : previous) }).catch(error => toast.error(error.message)) }) ?? (isScanConflict(error) && scanId ? { label: "Reload latest", onClick: () => {
        void api.scans.detail(scanId).then(raw => {
          const saved = acceptScan(raw)
          setSelectedScan(previous => previous?.id === scanId ? saved : previous)
          setEditBaseline(previous => previous?.id === scanId ? { ...previous, revision: saved.revision } : previous)
        }).catch(error => toast.error(error.message))
      } } : undefined),
    })
  }

  const recoverWrite = async () => {
    if (!writeFailure?.action || recoveringWrite || pendingWrite) return
    setRecoveringWrite(true)
    try {
      await writeFailure.action.onClick()
      setWriteFailure(null)
    } catch (error) {
      if (isScanConflict(error)) reportWriteError(error, selectedScan?.id)
      else {
        const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0
        const rejected = status >= 400 && status < 500 && status !== 408
        setWriteFailure(previous => previous && { ...previous,
          message: error instanceof Error ? error.message : "Could not reload this scan. Please retry.",
          action: rejected && previous.action?.label === "Retry previous" ? undefined : previous.action,
        })
      }
    } finally { setRecoveringWrite(false) }
  }

  const handleFlag = async (scan: ScanResult) => {
    if (pendingWrite || recoveringWrite) return
    setWriteFailure(null)
    const isNowFlagged = !scan.flagged
    setPendingWrite(true)
    try {
      const saved = await flagScan(scan.id, isNowFlagged, scan.revision)
      setSelectedScan(prev => prev?.id === scan.id ? saved : prev)
      toast.success(isNowFlagged ? "Scan flagged for review" : "Flag removed")
    } catch (error) {
      reportWriteError(error, scan.id)
    } finally { setPendingWrite(false) }
  }

  const handleAddNote = async () => {
    if (!selectedScan || !noteText.trim() || pendingWrite || recoveringWrite) return
    setWriteFailure(null)
    setPendingWrite(true)
    try {
      const saved = await addScanNote(selectedScan.id, noteText.trim(), selectedScan.revision)
      setSelectedScan(previous => previous?.id === selectedScan.id ? { ...previous, revision: Math.max(previous.revision ?? 0, saved.revision), hasNotes: true } : previous)
      setNoteText(current => current.trim() === saved.note.note ? "" : current)
      toast.success("Note added successfully")
    } catch (error) {
      reportWriteError(error, selectedScan.id, request => setNoteText(current => current.trim() === request.note ? "" : current))
    } finally { setPendingWrite(false) }
  }

  const handleSaveEdit = async () => {
    if (selectedScan && editData && editReason.trim() && !pendingWrite && !recoveringWrite) {
      const parsedFingerCount = typeof editData.fingerCount === 'string'
        ? Number(editData.fingerCount)
        : editData.fingerCount
      if (fingerCountEdited && (editData.fingerCount === '' || !Number.isInteger(parsedFingerCount) || parsedFingerCount === undefined || parsedFingerCount < 1)) {
        toast.error("Finger count must be at least 1")
        return
      }
      setPendingWrite(true)
      setWriteFailure(null)
      const saveData = {
        ...editData,
        fingerCount: fingerCountEdited ? parsedFingerCount : undefined,
        spoilageDays: editData.spoilageDays,
      } as Partial<ScanResult>
      try {
        await updateScanData(selectedScan.id, saveData, editReason.trim(), editBaseline ?? selectedScan)
        setEditMode(false)
        setSelectedScan(null)
        setEditData({})
        toast.success("Scan data updated successfully")
      } catch (error) {
        reportWriteError(error, selectedScan.id)
      } finally { setPendingWrite(false) }
    }
  }

  const openScanDetails = (scan: ScanResult) => {
    setWriteFailure(null)
    setSelectedScan(scan)
    setEditBaseline(scan)
    setEditMode(false)
    setEditReason("")
    setFingerCountEdited(false)
    setEditData({
      cultivar: scan.cultivar,
      ripeness: scan.ripeness,
      spoilageDays: scan.spoilageDays,
      fingerCount: scan.fingerCount,
    })
    loadScanNotes(scan.id)
  }

  const lowConfidenceCount = scans.filter(s => s.confidence !== null && s.confidence < config.confidenceThreshold).length
  // Review is the flag alone. An unflagged low-confidence scan was checked (or predates a
  // threshold raise), so it is labelled for information, never as pending review.
  const reviewLabel = (s: { flagged?: boolean; confidence: number | null }) =>
    s.flagged ? "Flagged" : s.confidence !== null && s.confidence < config.confidenceThreshold ? "Low confidence" : "Verified"
  const flaggedCount = scans.filter(s => s.flagged).length
  const sourcesWithIssues = useMemo(() => {
    const sourceNames = new Set(
      scans
        .filter(s => s.flagged || s.confidence !== null && s.confidence < config.confidenceThreshold)
        .map(s => s.source)
        .filter(Boolean)
    )
    return sourceNames.size
  }, [scans, config.confidenceThreshold])

  const sortedScansRef = useRef(filteredScans)
  const [exporting, setExporting] = useState(false)

  const handleExportCsv = () => {
    if (scansLoading || Boolean(scansError)) {
      toast.error("Wait for the complete scan history to load before exporting.")
      return
    }
    const filename = `quality-control-${manilaDayKey(Date.now())}.csv`
    const headers = EXPORT_HEADERS
    const rows = sortedScansRef.current.map(scan => [
      scan.id,
      scan.dateTime,
      scan.operator,
      scan.cultivar,
      scan.ripeness,
      scan.confidence !== null && scan.confidence !== undefined ? String(scan.confidence) : "",
      scan.temperature !== null && scan.temperature !== undefined ? String(scan.temperature) : "",
      scan.humidity !== null && scan.humidity !== undefined ? String(scan.humidity) : "",
      scan.spoilageDays !== null && scan.spoilageDays !== undefined ? String(scan.spoilageDays) : "",
      scan.fingerCount !== null && scan.fingerCount !== undefined ? String(scan.fingerCount) : "",
      scan.source || "",
      scan.flagged ? "Yes" : "No",
      reviewLabel(scan)
    ])
    downloadCsv(filename, headers, rows)
    toast.success("Export successful", { description: `${rows.length} scans exported to CSV` })
  }

  const handleExportXlsx = async () => {
    if (scansLoading || Boolean(scansError)) {
      toast.error("Wait for the complete scan history to load before exporting.")
      return
    }
    setExporting(true)
    try {
      const filename = `quality-control-${manilaDayKey(Date.now())}.xlsx`
      const headers = EXPORT_HEADERS
      const rows = sortedScansRef.current.map(scan => [
        scan.id,
        scan.dateTime,
        scan.operator,
        scan.cultivar,
        scan.ripeness,
        scan.confidence !== null && scan.confidence !== undefined ? Number(scan.confidence) : null,
        scan.temperature !== null && scan.temperature !== undefined ? Number(scan.temperature) : null,
        scan.humidity !== null && scan.humidity !== undefined ? Number(scan.humidity) : null,
        scan.spoilageDays !== null && scan.spoilageDays !== undefined ? String(scan.spoilageDays) : "",
        scan.fingerCount !== null && scan.fingerCount !== undefined ? Number(scan.fingerCount) : null,
        scan.source || null,
        scan.flagged ? "Yes" : "No",
        reviewLabel(scan)
      ])
      await downloadXlsx(filename, "Quality Control", headers, rows)
      toast.success("Export successful", { description: `${rows.length} scans exported to Excel` })
    } catch (e) {
      toast.error("Export failed", { description: e instanceof Error ? e.message : "Please try again" })
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnDef<ScanResult>[] = [
    {
      header: "Image",
      className: "w-20",
      cell: (scan) => (
        <div className="w-14">
          <AspectRatio ratio={1} className="rounded-lg overflow-hidden bg-muted/50 border">
            {scan.thumbnailUrl ? (
              <ScanImage src={scan.thumbnailUrl} alt={scan.cultivar} className="w-full h-full object-cover" />
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
      header: "Date/Time",
      sortable: true,
      sortKey: "dateTime",
      cell: (scan) => (
        <div className="text-sm">
          {new Date(scan.dateTime).toLocaleDateString("en-US", inManila({ month: "short", day: "numeric" }))}
          <br />
          <span className="text-xs text-muted-foreground">{new Date(scan.dateTime).toLocaleTimeString(undefined, inManila())}</span>
        </div>
      ),
    },
    {
      header: "Operator",
      sortable: true,
      sortKey: "operator",
      cell: (scan) => (
        <div className="flex items-center gap-2">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
              {scan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium">{scan.operator}</span>
        </div>
      ),
    },
    {
      header: "Cultivar",
      sortable: true,
      sortKey: "cultivar",
      cell: (scan) => <span className="font-medium">{scan.cultivar}</span>,
    },
    {
      header: "Ripeness",
      cell: (scan) => <AppStatusBadge type="ripeness" status={scan.ripeness} size="md" />,
    },
    {
      header: "Source",
      cell: (scan) => scan.source ? (
        <div className="text-xs">
          <p className="font-medium">{scan.source}</p>
        </div>
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
          <span className={`text-sm font-medium ${scan.confidence !== null && scan.confidence < config.confidenceThreshold ? 'text-yellow-600' : ''}`}>
            {scan.confidence === null ? "—" : `${scan.confidence}%`}
          </span>
          {scan.confidence !== null && scan.confidence < config.confidenceThreshold && (
            <AlertTriangle className="w-4 h-4 text-yellow-600" />
          )}
        </div>
      ),
    },
    {
      header: "IoT Data",
      cell: (scan) => (
        <div className="flex flex-col text-[10px] text-muted-foreground">
          {scan.temperature !== undefined ? (
            <span className="flex items-center gap-1"><Thermometer className="w-3 h-3" />{scan.temperature}°C</span>
          ) : (
            <span className="flex items-center gap-1 opacity-50"><Thermometer className="w-3 h-3" />—</span>
          )}
          {scan.humidity !== undefined ? (
            <span className="flex items-center gap-1"><Droplets className="w-3 h-3" />{scan.humidity}%</span>
          ) : (
            <span className="flex items-center gap-1 opacity-50"><Droplets className="w-3 h-3" />—</span>
          )}
        </div>
      ),
    },
    {
      header: "Status",
      cell: (scan) => (
        <div className="flex flex-wrap gap-1">
          {scan.isOverridden && (
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs mr-1.5 mb-1.5 sm:mb-0">
              <Edit className="w-3 h-3 mr-1" />
              Overridden
            </Badge>
          )}
          {scan.hasNotes && (
            <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 text-xs mr-1.5 mb-1.5 sm:mb-0">
              <MessageSquare className="w-3 h-3 mr-1" />
              Notes
            </Badge>
          )}
          {scan.flagged ? (
            <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs">
              <Flag className="w-3 h-3 mr-1" />
              Flagged
            </Badge>
          ) : scan.confidence !== null && scan.confidence < config.confidenceThreshold ? (
            <Badge variant="outline" className="bg-slate-50 text-slate-700 border-slate-200 text-xs">
              <AlertTriangle className="w-3 h-3 mr-1" />
              Low confidence
            </Badge>
          ) : (
            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">
              <CheckCircle className="w-3 h-3 mr-1" />
              Verified
            </Badge>
          )}
        </div>
      ),
    },
    {
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (scan) => (
        <AppActionButton
          tooltip={scan.flagged ? "Unflag Issue" : "Flag for Review"}
          icon={Flag}
          iconClassName={scan.flagged ? 'fill-current text-red-600' : ''}
          onClick={() => handleFlag(scan)} disabled={pendingWrite}
        />
      ),
    },
  ]

  return (
    <TooltipProvider>
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Quality Control"
        description="Review and manage scan quality"
        icon={ShieldCheck}
        action={
          <ExportDropdown
            onExportCsv={handleExportCsv}
            onExportXlsx={handleExportXlsx}
            disabled={scansLoading || Boolean(scansError)}
            exporting={exporting}
          />
        }
      />

      {(scansLoading || scansError) && (
        <Card className="rounded-2xl"><CardContent className="p-4 flex items-center justify-between gap-3" role={scansError ? "alert" : "status"}>
          <p className="text-sm text-muted-foreground">{scansError || (scansReady ? "Refreshing scan history…" : "Loading complete scan history…")}</p>
          {scansError && <Button variant="outline" size="sm" onClick={() => void refreshScans()}>Retry</Button>}
        </CardContent></Card>
      )}
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={scansLoading && !scansReady}
          title="Low Confidence"
          value={lowConfidenceCount}
          icon={AlertTriangle}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={50}
          description="Below threshold"
        />
        <AppStatsCard
          loading={scansLoading && !scansReady}
          title="Flagged"
          value={flaggedCount}
          icon={Flag}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={100}
          description="Needs review"
        />
        <AppStatsCard
          loading={scansLoading && !scansReady}
          title="Sources with Issues"
          value={sourcesWithIssues}
          icon={CheckCircle}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={150}
          description="Flagged or low confidence"
        />
      </div>

      {/* Filter Tabs */}
      <AppTableFilters 
        searchQuery={searchQuery}
        onSearchChange={(v) => { setSearchQuery(v) }}
        searchPlaceholder="Search by operator, cultivar, source, or ID..."
        hasActiveFilters={filterView !== "all" || sourceFilter !== "all" || searchQuery !== ""}
        onClearFilters={() => {
          setFilterView("all")
          setSourceFilter("all")
          setSearchQuery("")
        }}
      >
        <Select value={filterView} onValueChange={(v) => { setFilterView(v as typeof filterView) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Scans" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Scans</SelectItem>
            <SelectItem value="low-confidence">Low Confidence</SelectItem>
            <SelectItem value="flagged">Flagged</SelectItem>
            <SelectItem value="overridden">Overridden</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v) }}>
          <SelectTrigger className="w-full sm:w-47.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Sources" />
          </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              {activeSources.map((source) => (
                <SelectItem key={source as string} value={source as string}>
                  {source}
                </SelectItem>
              ))}
            </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Scans Table */}
      <AppDataTable
        loading={scansLoading && !scansReady}
        data={filteredScans}
        columns={columns}
        rowKey={(scan) => scan.id}
        onRowClick={(scan) => openScanDetails(scan)}
        pagination={{ pageSize: PAGE_SIZE }}
        onSortedData={(rows) => { sortedScansRef.current = rows }}
        emptyState={{
          icon: ShieldCheck,
          title: scansError && !scansReady ? "Scan history unavailable" : "No scans to review",
          description: scansError && !scansReady ? "Retry loading scan history." : filterView !== "all" || sourceFilter !== "all"
            ? "Try adjusting your filters"
            : "All scans have been reviewed"
        }}
      />

      {/* Scan Details Dialog */}
      <Dialog open={!!selectedScan} onOpenChange={() => { if (pendingWrite || recoveringWrite) return; setSelectedScan(null); setEditMode(false); setNoteText("") }}>
        <DialogContent className="sm:max-w-2xl rounded-2xl max-h-[90vh] flex flex-col p-0 gap-0">
          <DialogHeader className="px-6 pt-6 pb-4 border-b">
            <div className="flex items-center justify-between pr-8">
              <DialogTitle>Scan Details</DialogTitle>
              {selectedScan && (
                <div className="flex items-center gap-2">
                  {selectedScan.isOverridden && (
                    <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs">
                      <Edit className="w-3 h-3 mr-1" />
                      Overridden
                    </Badge>
                  )}
                  <Badge variant="outline" className={`text-xs ${selectedScan.flagged ? 'bg-red-50 text-red-700 border-red-200' : selectedScan.confidence !== null && selectedScan.confidence < config.confidenceThreshold ? 'bg-slate-50 text-slate-700 border-slate-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>
                    {reviewLabel(selectedScan)}
                  </Badge>
                </div>
              )}
            </div>
            <DialogDescription>
              Review and manage scan quality
            </DialogDescription>
          </DialogHeader>

          {selectedScan && (
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
              {/* Scan Metadata Section */}
              <div className="grid grid-cols-2 gap-3 p-4 bg-muted/30 rounded-xl">
                <div>
                  <Label className="text-xs text-muted-foreground">Scan ID</Label>
                  <p className="font-mono text-sm mt-0.5">{selectedScan.id}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Date/Time</Label>
                  <p className="text-sm mt-0.5">{new Date(selectedScan.dateTime).toLocaleString("en-PH", { timeZone: "Asia/Manila" })}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Operator</Label>
                  <div className="flex items-center gap-2 mt-1">
                    <Avatar className="w-7 h-7">
                      <AvatarFallback className="bg-primary/10 text-primary font-semibold text-[10px]">
                        {selectedScan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-sm font-medium">{selectedScan.operator}</span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Confidence</Label>
                  <div className="flex items-center gap-2 mt-1">
                    <p className={`text-sm font-semibold ${selectedScan.confidence !== null && selectedScan.confidence < config.confidenceThreshold ? 'text-yellow-600' : 'text-emerald-600'}`}>
                      {selectedScan.confidence === null ? "—" : `${selectedScan.confidence}%`}
                    </p>
                    {selectedScan.confidence !== null && selectedScan.confidence < config.confidenceThreshold && (
                      <AlertTriangle className="w-4 h-4 text-yellow-600" />
                    )}
                  </div>
                </div>
                {selectedScan.source && (
                  <div className="col-span-2">
                    <Label className="text-xs text-muted-foreground">Source</Label>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs font-medium">
                        {selectedScan.source}
                      </Badge>
                    </div>
                  </div>
                )}
              </div>

              {/* Camera Views Grid with Bounding Boxes */}
              <div>
                <Label className="text-sm font-semibold mb-3 block">Camera Views with Detection Boxes</Label>
                <div className="grid grid-cols-2 gap-3">
                  {cameraViews.map(camera => (
                    <div key={camera.id}>
                      <AspectRatio ratio={4/3} className="rounded-lg overflow-hidden bg-muted/50 border-2 relative group">
                        {camera.imageUrl ? (
                          <>
                            <BoundingBoxOverlay
                              src={camera.imageUrl}
                              alt={camera.label}
                              boxes={camera.boxes}
                              className="w-full h-full"
                              showLabels={true}
                              showConfidence={true}
                            />
                            <div className="absolute top-2 right-2 bg-black/60 text-white px-2 py-1 rounded text-[10px] font-medium">
                              {camera.confidence == null ? "—" : `${camera.confidence}%`}
                            </div>
                          </>
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                            <Banana className="w-12 h-12 text-muted-foreground/40" />
                            <span className="text-xs text-muted-foreground font-medium">No image available</span>
                          </div>
                        )}
                      </AspectRatio>
                      <p className="text-xs text-muted-foreground mt-1 text-center">{camera.label}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-3 p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">
                    {cameraViews.length === 0
                      ? "No camera evidence recorded"
                      : "Boxes show the recorded detections for each camera, with class and confidence labels."}
                  </p>
                </div>
              </div>

              {/* Detection Results Section */}
              <div>
                <Label className="text-sm font-semibold mb-3 block">Detection Results</Label>
                {editMode ? (
                  <div className="space-y-4 p-4 bg-muted/30 rounded-xl">
                    <h4 className="font-semibold text-sm">Edit Scan Data</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="cultivar">Cultivar</Label>
                        <Select value={editData.cultivar} onValueChange={(v) => {
                          const newCultivar = v as Cultivar;
                          setEditData({...editData, cultivar: newCultivar, spoilageDays: editData.ripeness && editData.ripeness !== "Unknown" ? getSpoilageDays(newCultivar, editData.ripeness, selectedScan?.temperature ?? undefined, selectedScan?.humidity ?? undefined) : editData.spoilageDays});
                        }}>
                          <SelectTrigger id="cultivar">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CULTIVARS.map(c => (
                              <SelectItem key={c} value={c}>{c}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="ripeness">Ripeness</Label>
                        <Select value={editData.ripeness} onValueChange={(v) => {
                          const newRipeness = v as Ripeness;
                          setEditData({...editData, ripeness: newRipeness, spoilageDays: editData.cultivar && editData.cultivar !== "Unknown" ? getSpoilageDays(editData.cultivar, newRipeness, selectedScan?.temperature ?? undefined, selectedScan?.humidity ?? undefined) : editData.spoilageDays});
                        }}>
                          <SelectTrigger id="ripeness">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {RIPENESS_LEVELS.map(r => (
                              <SelectItem key={r} value={r}>{r}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="spoilageDays">Est. Spoilage (days)</Label>
                        <Input
                          id="spoilageDays"
                          type="text"
                          value={formatSpoilageDays(editData.spoilageDays, false)}
                          readOnly
                          className="bg-muted"
                          placeholder="e.g. 2-3"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="fingers">{fingersLabel(false)}</Label>
                        <NumberField
                          id="fingers"
                          min={1}
                          max={30}
                          value={editData.fingerCount ?? ""}
                          clampOnBlur={false}
                          onChange={(value) => {
                            setFingerCountEdited(true)
                            setEditData({ ...editData, fingerCount: value })
                          }}
                        />
                      </div>
                    </div>

                    {/* Change Preview */}
                    {editData && selectedScan && (
                      <AppChangePreview 
                        originalData={selectedScan} 
                        editData={editData} 
                        className="mt-4"
                      />
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <Card className="bg-primary/5 border-primary/10">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Cultivar</Label>
                        <p className="text-lg font-bold text-primary mt-1">{selectedScan.cultivar}</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Ripeness</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.ripeness}</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Thermometer className="w-3.5 h-3.5"/> Temp</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.temperature?.toFixed(1) || '—'}°C</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Droplets className="w-3.5 h-3.5"/> Humidity</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.humidity?.toFixed(1) || '—'}%</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Est. Spoilage</Label>
                        {(() => {
                          const countdown = selectedScan.inventoryStatus === "In Stock" ? liveShelfLifeLabel(selectedScan, now) : null
                          const estimate = formatSpoilageDays(selectedScan.spoilageDays)
                          return (
                            <>
                              <p className="text-lg font-bold mt-1">{countdown ?? estimate}</p>
                              {countdown !== null && estimate !== "Unknown" && <p className="text-xs text-muted-foreground">Est. {estimate} from scan</p>}
                            </>
                          )
                        })()}
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">{fingersLabel(fingerCountIsEstimate(selectedScan))}</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.fingerCount}</p>
                      </CardContent>
                    </Card>
                  </div>
                )}
                
                {!editMode && selectedScan.isOverridden && selectedScan.originalAiResult && (
                  <AppChangePreview 
                    originalData={selectedScan.originalAiResult} 
                    editData={selectedScan} 
                  />
                )}
              </div>

              {/* Notes Section */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" />
                  Review Notes
                </Label>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {getScanNotes(selectedScan.id).map((note) => (
                    <div key={note.id} className="p-3 bg-muted/50 rounded-lg text-sm flex gap-3">
                      <Avatar className="w-7 h-7 shrink-0 mt-0.5">
                        <AvatarFallback className="bg-primary/10 text-primary font-semibold text-[10px]">
                          {note.author.split(' ').map(n => n[0]).join('').toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0">
                        <p className="text-foreground">{note.note}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {note.author} • {new Date(note.timestamp).toLocaleString("en-PH", { timeZone: "Asia/Manila" })}
                        </p>
                      </div>
                    </div>
                  ))}
                  {getScanNotesState(selectedScan.id).loading && <p role="status" className="text-sm text-muted-foreground text-center py-4"><Loader2 aria-hidden="true" className="inline h-4 w-4 animate-spin mr-2" />Loading notes…</p>}
                  {getScanNotesState(selectedScan.id).error && (
                    <div role="alert" className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                      <span>{getScanNotesState(selectedScan.id).error}</span>
                      <Button variant="outline" size="sm" onClick={() => loadScanNotes(selectedScan.id)}>Retry</Button>
                    </div>
                  )}
                  {getScanNotesState(selectedScan.id).ready && !getScanNotesState(selectedScan.id).loading && !getScanNotesState(selectedScan.id).error && getScanNotes(selectedScan.id).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No notes yet</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Add a note..."
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    className="resize-none"
                    rows={2}
                  />
                  <Button onClick={handleAddNote} disabled={!noteText.trim() || pendingWrite}>
                    {pendingWrite && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{pendingWrite ? "Saving…" : "Add"}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {editMode && <div className="px-6 pb-4"><div className="space-y-2"><Label htmlFor="qc-edit-reason">Reason for change</Label><Textarea id="qc-edit-reason" value={editReason} onChange={event => setEditReason(event.target.value)} disabled={pendingWrite} /></div></div>}
          {writeFailure && <div role="alert" className="px-6 pb-4 flex items-center justify-between gap-3 text-sm text-destructive">
            <span>{writeFailure.message}</span>
            {writeFailure.action && <Button variant="outline" size="sm" disabled={pendingWrite || recoveringWrite} onClick={() => void recoverWrite()}>
              {recoveringWrite && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}
              {recoveringWrite ? "Loading…" : writeFailure.action.label}
            </Button>}
          </div>}
          <DialogFooter className="px-6 pb-6 pt-4 border-t flex-col sm:flex-row gap-2">
            {editMode ? (
              <>
                <Button variant="outline" disabled={pendingWrite || recoveringWrite} onClick={() => { setEditMode(false); setWriteFailure(null) }}>
                  Cancel
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  disabled={
                    pendingWrite || recoveringWrite ||
                    !editReason.trim() ||
                    (fingerCountEdited && (editData.fingerCount === '' || !Number.isInteger(Number(editData.fingerCount)) || Number(editData.fingerCount) < 1))
                  }
                >
                  {pendingWrite && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{pendingWrite ? "Saving…" : "Save Changes"}
                </Button>
              </>
            ) : (
              <>
                <Button 
                  variant={selectedScan?.flagged ? "secondary" : "outline"}
                  disabled={pendingWrite || recoveringWrite}
                  onClick={() => selectedScan && handleFlag(selectedScan)}
                  className={selectedScan?.flagged ? "text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 border border-red-200" : ""}
                >
                  <Flag className={`w-4 h-4 mr-2 ${selectedScan?.flagged ? "fill-current" : ""}`} />
                  {selectedScan?.flagged ? 'Remove Flag' : 'Flag for Review'}
                </Button>
                <Button disabled={pendingWrite || recoveringWrite} onClick={() => {
                  if (!selectedScan) return
                  setWriteFailure(null)
                  setEditBaseline(selectedScan)
                  setEditData({ cultivar: selectedScan.cultivar, ripeness: selectedScan.ripeness, fingerCount: selectedScan.fingerCount, spoilageDays: selectedScan.spoilageDays, source: selectedScan.source })
                  setFingerCountEdited(false)
                  setEditReason("")
                  setEditMode(true)
                }}>
                  <Edit className="w-4 h-4 mr-2" />
                  Edit Data
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
    </TooltipProvider>
  )
}
