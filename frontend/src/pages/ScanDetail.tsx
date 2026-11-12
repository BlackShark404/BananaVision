import { DetailSkeleton } from "@/components/LoadingState"
import { scanRetryAction } from "@/lib/scanWriteFeedback"
import { ScanImage } from "@/components/ScanImage"
import { InventoryProvenanceReview } from "@/components/InventoryProvenanceReview"
import { useState, useEffect, useMemo } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
import { useAdmin } from "@/context/AdminContext"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NumberField } from "@/components/ui/number-field"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Separator } from "@/components/ui/separator"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu"
import {
  ArrowLeft,
  Banana,
  Calendar,
  Clock,
  User,
  Target,
  AlertTriangle,
  Hand,
  Package,
  Layers,
  ScanLine,
  Flag,
  MessageSquare,
  Edit,
  CheckCircle,
  ShieldCheck,
  Save,
  X,
  QrCode,
  Download,
  Printer,
  Eye,
  EyeOff,
  Box,
  Loader2,
  DollarSign,
  Settings,
  ChevronDown,
  ExternalLink,
} from "lucide-react"
import { toast } from "sonner"
import { getSpoilageDays } from "@/lib/utils"
import { generateQRCodeDataUrl, printQRTag } from "@/lib/qrcode"
import { CULTIVARS, RIPENESS_LEVELS, type Cultivar, type Ripeness, type ScanResult, type ScanDetection, type BoundingBox, type InventoryStatus } from "@/types"
import { AppChangePreview } from "@/components/AppChangePreview"
import { AppStatusBadge } from "@/components/AppStatusBadge"
import BoundingBoxOverlay from "@/components/BoundingBoxOverlay"
import { scanWrite, scanRevision, isScanConflict } from "@/lib/scanWrites"
import { api } from "@/lib/api"
import { formatSpoilageDays, spoilageDayUnit } from "@/lib/spoilageDisplay"
import { remainingStockDays, shelfLifeLabel } from "@/lib/inventoryRisk"

const EMPTY_DETECTIONS: ScanDetection[] = []

// Valid transitions: key = current status, value = allowed target statuses
const VALID_TRANSITIONS: Record<string, InventoryStatus[]> = {
  "In Stock": ["Sold", "For Processing", "Spoiled"],
  "For Processing": ["Sold", "Spoiled"],
  "Sold": [],
  "Spoiled": [],
}

const TERMINAL_STATUSES: InventoryStatus[] = ["Sold", "Spoiled"]

const STATUS_ACTIONS: { status: InventoryStatus; icon: typeof Box; color: string }[] = [
  { status: "In Stock", icon: Box, color: "text-blue-500" },
  { status: "For Processing", icon: Settings, color: "text-purple-500" },
  { status: "Sold", icon: DollarSign, color: "text-emerald-500" },
  { status: "Spoiled", icon: AlertTriangle, color: "text-red-500" },
]

export default function ScanDetail() {
  const { scanId } = useParams<{ scanId: string }>()
  const { user } = useAuth()
  return user ? <ScanDetailRecord key={`${user.id}:${user.role}:${scanId}`} scanId={scanId} /> : null
}

function ScanDetailRecord({ scanId }: { scanId?: string }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { flagScan, addScanNote, getScanNotes, updateScanData, acceptScan } = useScans()
  const { suppliers } = useInventory()
  const { config } = useAdmin()
  const [noteText, setNoteText] = useState("")
  const [provenanceReason, setProvenanceReason] = useState("")
  const [editBaseline, setEditBaseline] = useState<ScanResult | null>(null)
  const [editReason, setEditReason] = useState("")
  const [fingerCountEdited, setFingerCountEdited] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState<Partial<{ cultivar: Cultivar; ripeness: Ripeness; spoilageDays: string; fingerCount: number | string; source: string }>>({})
  const [activeCamera, setActiveCamera] = useState(0)
  const [showBoxes, setShowBoxes] = useState(true)
  const [retry, setRetry] = useState(0)
  const [detail, setDetail] = useState<{ retry: number; scan: ScanResult | null; error: string | null; notFound: boolean; status?: number } | null>(null)
  const [flagPending, setFlagPending] = useState(false)
  const [notePending, setNotePending] = useState(false)
  const [editPending, setEditPending] = useState(false)
  const [statusAction, setStatusAction] = useState<InventoryStatus | null>(null)
  const [statusReason, setStatusReason] = useState("")
  const [statusPending, setStatusPending] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const currentDetail = detail?.retry === retry ? detail : null
  const scan = currentDetail?.scan
  const scanDetections = scan?.detections ?? EMPTY_DETECTIONS
  const remaining = scan && scan.inventoryStatus === "In Stock" ? remainingStockDays(scan, now) : null
  const notes = scan ? getScanNotes(scan.id) : []
  const isAdmin = user?.role === "Admin"

  // Historical scan links load independently of the latest page in ScanContext.
  useEffect(() => {
    if (!scanId) return
    const controller = new AbortController()
    let cancelled = false
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      if (!cancelled) setDetail({ retry, scan: null, notFound: false, error: "Loading took too long. Please retry." })
      controller.abort()
    }, 15_000)
    api.scans.detail(scanId, controller.signal)
      .then(data => {
        if (cancelled || timedOut) return
        const record = acceptScan(data)
        setDetail({ retry, scan: record, error: null, notFound: false })
        generateQRCodeDataUrl(record).then(qrCode => {
          if (!cancelled) setDetail(previous => previous?.scan ? { ...previous, scan: { ...previous.scan, qrCode } } : previous)
        }).catch(() => {})
      })
      .catch((error: unknown) => {
        if (cancelled || timedOut) return
        const notFound = typeof error === "object" && error !== null && "status" in error && error.status === 404
        const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : undefined
        setDetail({ retry, scan: null, notFound, status, error: error instanceof Error ? error.message : "Check your connection and try again." })
      })
      .finally(() => window.clearTimeout(timeout))
    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort() }
  }, [scanId, retry, acceptScan])

  // Keep an open record current without disturbing active edits or dialogs.
  useEffect(() => {
    if (!scanId || currentDetail?.notFound) return
    const controller = new AbortController()
    let disposed = false
    let timer: number | undefined
    const refresh = () => {
      if (document.hidden || flagPending || notePending || editPending || statusPending || editMode || statusAction) return
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        timer = undefined
        if (document.hidden || flagPending || notePending || editPending || statusPending || editMode || statusAction) return
        void api.scans.detail(scanId, controller.signal)
          .then(data => {
            if (disposed || controller.signal.aborted) return
            const record = acceptScan(data)
            setDetail(previous => previous?.scan?.id === scanId
              ? { ...previous, scan: { ...record, qrCode: previous.scan.qrCode } }
              : previous)
          })
          .catch(() => { /* Preserve the open record when a background refresh fails. */ })
      }, 150)
    }
    window.addEventListener("focus", refresh)
    document.addEventListener("visibilitychange", refresh)
    const interval = window.setInterval(() => {
      if (!document.hidden) refresh()
    }, 30_000)
    return () => {
      disposed = true
      controller.abort()
      window.removeEventListener("focus", refresh)
      document.removeEventListener("visibilitychange", refresh)
      window.clearInterval(interval)
      if (timer) window.clearTimeout(timer)
    }
  }, [scanId, currentDetail?.notFound, flagPending, notePending, editPending, statusPending, editMode, statusAction, acceptScan])

  const recordedCameraIds = [...new Set([...(scan?.images ?? []).map(image => image.camera_id), ...scanDetections.map(detection => detection.camera_id)])]
  const cameraViews = recordedCameraIds.map(id => ({ id, label: scanDetections.find(detection => detection.camera_id === id)?.camera_label || id }))

  // Resolve the image URL for a given camera — no fallback to avoid showing a duplicate
  const getCameraImageUrl = (cameraId: string): string | undefined => {
    const match = scan?.images?.find(
      (img) => img.camera_id === cameraId
    )
    return match?.file_path
  }

  // Get bounding boxes for a given camera ID
  const getCameraBoundingBoxes = (cameraId: string): BoundingBox[] => {
    const detection = scanDetections.find((d) => d.camera_id === cameraId)
    return detection?.bounding_boxes || []
  }

  const activeCameraView = cameraViews[activeCamera]
  const activeImageUrl = activeCameraView ? getCameraImageUrl(activeCameraView.id) : undefined
  const activeBoxes = showBoxes && activeCameraView ? getCameraBoundingBoxes(activeCameraView.id) : []

  // Compute unique detection classes for legend
  const detectionLegend = useMemo(() => {
    const allBoxes = scanDetections.flatMap((d) => d.bounding_boxes || [])
    const classMap = new Map<string, { count: number; avgConf: number }>()
    for (const box of allBoxes) {
      const existing = classMap.get(box.cls)
      if (existing) {
        existing.count++
        existing.avgConf = (existing.avgConf * (existing.count - 1) + box.conf) / existing.count
      } else {
        classMap.set(box.cls, { count: 1, avgConf: box.conf })
      }
    }
    return Array.from(classMap.entries()).map(([cls, data]) => ({
      cls,
      label: cls.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" "),
      count: data.count,
      avgConf: Math.round(data.avgConf * 100),
    }))
  }, [scanDetections])

  const reportWriteError = (error: unknown, confirmed?: (request: Readonly<Record<string, unknown>>) => void) => {
    toast.error(error instanceof Error ? error.message : "Could not save changes. Please retry.", {
      action: scanRetryAction(error, request => { confirmed?.(request); setRetry(value => value + 1) }) ?? (isScanConflict(error) ? { label: "Reload latest", onClick: () => setRetry(value => value + 1) } : undefined),
    })
  }

  const handleFlag = async () => {
    if (!scan || flagPending) return
    const isNowFlagged = !scan.flagged
    setFlagPending(true)
    try {
      const saved = await flagScan(scan.id, isNowFlagged, scan.revision)
      setDetail(previous => previous?.scan ? { ...previous, scan: { ...saved, qrCode: previous.scan.qrCode } } : previous)
      toast.success(isNowFlagged ? "Scan flagged for review" : "Flag removed")
    } catch (error) {
      reportWriteError(error)
    } finally {
      setFlagPending(false)
    }
  }

  const handleAddNote = async () => {
    if (!scan || !noteText.trim() || notePending) return
    setNotePending(true)
    try {
      const saved = await addScanNote(scan.id, noteText.trim(), scan.revision)
      setDetail(previous => previous?.scan ? { ...previous, scan: { ...previous.scan, revision: Math.max(previous.scan.revision ?? 0, saved.revision), hasNotes: true } } : previous)
      void api.scans.detail(scan.id).then(raw => {
        const updated = acceptScan(raw)
        setDetail(previous => previous?.scan && (previous.scan.revision ?? 0) <= (updated.revision ?? 0) ? { ...previous, scan: updated } : previous)
      }).catch(() => {})
      setNoteText(current => current.trim() === saved.note.note ? "" : current)
      toast.success("Note added successfully")
    } catch (error) {
      reportWriteError(error, request => setNoteText(current => current.trim() === request.note ? "" : current))
    } finally {
      setNotePending(false)
    }
  }

  const startEdit = () => {
    if (!scan) return
    setEditBaseline(scan)
    setEditData({
      cultivar: scan.cultivar === "Unknown" ? undefined : scan.cultivar,
      ripeness: scan.ripeness === "Unknown" ? undefined : scan.ripeness,
      spoilageDays: scan.spoilageDays,
      fingerCount: scan.fingerCount,
      source: scan.source,
    })
    setEditReason("")
    setFingerCountEdited(false)
    setEditMode(true)
  }

  const handleSaveEdit = async () => {
    if (scan && editData && editReason.trim() && !editPending) {
      const parsedFingerCount = typeof editData.fingerCount === 'string'
        ? Number(editData.fingerCount)
        : editData.fingerCount
      if (fingerCountEdited && (editData.fingerCount === '' || !Number.isInteger(parsedFingerCount) || parsedFingerCount === undefined || parsedFingerCount < 1)) {
        toast.error("Finger count must be at least 1")
        return
      }
      setEditPending(true)
      const saveData = {
        ...editData,
        fingerCount: fingerCountEdited ? parsedFingerCount : undefined,
        spoilageDays: editData.spoilageDays,
      } as Partial<ScanResult>
      try {
        const saved = await updateScanData(scan.id, saveData, editReason.trim(), { ...(editBaseline ?? scan), revision: scan.revision })
        setDetail(previous => previous?.scan ? { ...previous, scan: { ...previous.scan, ...saved, images: previous.scan.images, detections: previous.scan.detections, qrCode: previous.scan.qrCode } } : previous)
        setEditMode(false)
        toast.success("Scan data updated successfully")
      } catch (error) {
        reportWriteError(error)
      } finally {
        setEditPending(false)
      }
    }
  }

  const handleStatusUpdate = async () => {
    if (!scan || !statusAction || !statusReason.trim() || statusPending) return
    setStatusPending(true)
    try {
      const saved = await scanWrite(`${user?.id}:${scan.id}:status`, {
        expected_revision: scanRevision(scan.revision), inventory_status: statusAction, reason: statusReason.trim(),
      }, body => api.scans.updateStatus(scan.id, body))
      const accepted = acceptScan(saved)
      setDetail(previous => previous?.scan ? { ...previous, scan: { ...previous.scan, ...accepted, images: previous.scan.images, detections: previous.scan.detections, qrCode: previous.scan.qrCode } } : previous)
      toast.success(`Scan marked as ${statusAction}`)
      setStatusAction(null)
      setStatusReason("")
      // Reload to get updated history
      void api.scans.detail(scan.id).then(raw => {
        const updated = acceptScan(raw)
        setDetail(previous => previous?.scan && (previous.scan.revision ?? 0) <= (updated.revision ?? 0) ? { ...previous, scan: { ...updated, qrCode: previous.scan.qrCode } } : previous)
      }).catch(() => {})
    } catch (error) {
      reportWriteError(error, () => {
        setStatusAction(null)
        setStatusReason("")
        setRetry(value => value + 1)
      })
    } finally {
      setStatusPending(false)
    }
  }

  if (!scan) {
    const loading = Boolean(scanId) && !currentDetail
    if (loading) return <DetailSkeleton />
    const notFound = !scanId || currentDetail?.notFound
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanLine className="w-4 h-4" />}
            </EmptyMedia>
            <EmptyTitle className="text-base sm:text-lg font-semibold mt-1" role={loading ? "status" : "alert"}>{loading ? "Loading scan…" : notFound ? "Scan not found" : currentDetail?.status === 403 ? "Scan access denied" : currentDetail?.status === 410 ? "Scan deleted" : "Scan could not be loaded"}</EmptyTitle>
            <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
              {loading ? "Retrieving the stored scan and camera images." : notFound ? "No scan record was found for this ID." : currentDetail?.status === 403 ? "You do not have access to this scan." : currentDetail?.status === 410 ? "This scan was deleted. Its record is no longer available." : currentDetail?.error || "Check your connection and try again."}
            </EmptyDescription>
          </EmptyHeader>
          {!loading && !notFound && ![403, 410].includes(currentDetail?.status ?? 0) && <Button className="mt-4" onClick={() => setRetry(value => value + 1)}>Retry</Button>}
          <Button variant="outline" className="mt-4 gap-2" onClick={() => navigate(-1)}>
            <ArrowLeft className="w-4 h-4" /> Go Back
          </Button>
        </Empty>
      </div>
    )
  }

  const dateObj = new Date(scan.dateTime)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <Button variant="ghost" size="icon" className="w-9 h-9 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
            <ScanLine className="w-7 h-7" /> Scan Details
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Scan ID: <span className="font-mono uppercase">{scan.id}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {scan.isOverridden && (
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs gap-1">
              <Edit className="w-3 h-3" />
              Overridden
            </Badge>
          )}
          {scan.flagged ? (
            <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs gap-1">
              <Flag className="w-3 h-3 fill-current" />
              Flagged
            </Badge>
          ) : scan.confidence !== null && scan.confidence < config.confidenceThreshold ? (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 text-xs gap-1">
              <AlertTriangle className="w-3 h-3" />
              Needs Review
            </Badge>
          ) : (
            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs gap-1">
              <CheckCircle className="w-3 h-3" />
              Verified
            </Badge>
          )}
        </div>
      </div>

      {/* Inventory Status Update Dialog */}
      <Dialog open={!!statusAction} onOpenChange={open => { if (!open && !statusPending) { setStatusAction(null); setStatusReason("") } }}>
        <DialogContent className="rounded-2xl">
          <DialogHeader>
            <DialogTitle>Mark scan as {statusAction}?</DialogTitle>
            <DialogDescription>
              {TERMINAL_STATUSES.includes(statusAction as InventoryStatus)
                ? "This is a terminal status and cannot be easily undone. This change will be recorded in the scan history."
                : "This change will be recorded in the scan history."}
            </DialogDescription>
          </DialogHeader>
          <Label htmlFor="scan-status-reason">Reason for change</Label>
          <Textarea id="scan-status-reason" value={statusReason} onChange={event => setStatusReason(event.target.value)} disabled={statusPending} placeholder="Describe why you are changing the status..." />
          <DialogFooter>
            <Button variant="outline" disabled={statusPending} onClick={() => { setStatusAction(null); setStatusReason("") }}>Cancel</Button>
            <Button disabled={!statusReason.trim() || statusPending} onClick={() => void handleStatusUpdate()}>
              {statusPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}
              {statusPending ? "Saving…" : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <InventoryProvenanceReview scan={scan} reason={provenanceReason} setReason={setProvenanceReason} onSaved={saved => setDetail(previous => previous ? { ...previous, scan: saved } : previous)} onConflict={() => setRetry(value => value + 1)} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Left Column — Camera Views */}
        <Card className="rounded-2xl lg:col-span-1 lg:sticky lg:top-20">
          <CardContent className="p-4 sm:p-6">
            {/* Main Camera View */}
            <Dialog>
              <AspectRatio ratio={4/3} className="rounded-xl overflow-hidden bg-muted/50 border-2 relative group">
                {activeImageUrl ? (
                  <>
                    <DialogTrigger asChild>
                      <button
                        type="button"
                        aria-label={`Enlarge ${cameraViews[activeCamera].label} camera image`}
                        className="block w-full h-full cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                      >
                        <BoundingBoxOverlay
                          src={activeImageUrl}
                          alt={cameraViews[activeCamera].label}
                          boxes={activeBoxes}
                          className="w-full h-full"
                          showLabels={true}
                          showConfidence={true}
                        />
                      </button>
                    </DialogTrigger>
                    <div className="pointer-events-none absolute top-2 left-2 bg-black/60 text-white px-2 py-1 rounded-md text-[10px] font-medium flex items-center gap-1">
                      {cameraViews[activeCamera]?.id || "CAM"}
                    </div>
                    <div className="pointer-events-none absolute bottom-2 left-2 bg-black/60 text-white px-2 py-1 rounded-md text-xs font-medium">
                      {cameraViews[activeCamera]?.label || "View"}
                    </div>
                    <div className="absolute top-2 right-2 flex items-center gap-1.5">
                      {scanDetections.length > 0 && (
                        <button
                          onClick={() => setShowBoxes(!showBoxes)}
                          className="bg-black/60 hover:bg-black/80 text-white px-2 py-1 rounded-md text-[10px] font-medium flex items-center gap-1 transition-colors"
                          title={showBoxes ? "Hide bounding boxes" : "Show bounding boxes"}
                        >
                          {showBoxes ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                          {showBoxes ? "Boxes" : "Boxes"}
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-3">
                    <Banana className="w-16 h-16 text-muted-foreground/30" />
                    <span className="text-sm text-muted-foreground/50">No image available</span>
                  </div>
                )}
              </AspectRatio>
              <DialogContent className="rounded-2xl sm:max-w-5xl max-h-[90dvh] overflow-y-auto">
                <DialogHeader className="pr-8">
                  <DialogTitle>{cameraViews[activeCamera]?.label} camera image</DialogTitle>
                  <DialogDescription>{cameraViews[activeCamera]?.id} · Enlarged scan image</DialogDescription>
                </DialogHeader>
                {activeImageUrl && (
                  <BoundingBoxOverlay
                    src={activeImageUrl}
                    alt={cameraViews[activeCamera].label}
                    boxes={activeBoxes}
                    className="w-full rounded-xl bg-muted/50"
                    showLabels={true}
                    showConfidence={true}
                  />
                )}
              </DialogContent>
            </Dialog>

            {/* Camera Thumbnails */}
            <div className="grid grid-cols-4 gap-2 mt-3">
              {cameraViews.map((cam, idx) => {
                const thumbUrl = getCameraImageUrl(cam.id)
                return (
                  <button
                    key={cam.id}
                    onClick={() => setActiveCamera(idx)}
                    className={`relative rounded-lg overflow-hidden border-2 transition-all duration-200 ${
                      activeCamera === idx
                        ? 'border-primary ring-2 ring-primary/20'
                        : 'border-transparent hover:border-muted-foreground/30'
                    }`}
                  >
                    <AspectRatio ratio={1} className="bg-muted/50">
                      {thumbUrl ? (
                        <ScanImage src={thumbUrl} alt={cam.label} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Banana className="w-5 h-5 text-muted-foreground/30" />
                        </div>
                      )}
                    </AspectRatio>
                    <span className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[8px] font-medium py-0.5 text-center">
                      {cam.id}
                    </span>
                  </button>
                )
              })}
            </div>


            {/* Detection Legend */}
            {detectionLegend.length > 0 && (
              <>
                <Separator className="my-4" />
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold">
                    <Box className="w-3.5 h-3.5 text-primary" />
                    YOLO Detections
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 rounded-full ml-auto">
                      {scanDetections.reduce((acc, d) => acc + (d.bounding_boxes?.length || 0), 0)} boxes
                    </Badge>
                  </div>
                  <div className="space-y-1.5">
                    {detectionLegend.map(({ cls, label, count, avgConf }) => (
                      <div key={cls} className="flex items-center justify-between text-xs p-2 rounded-lg bg-muted/50">
                        <div className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: `hsl(${(cls.charCodeAt(0) * 37 + cls.charCodeAt(cls.length - 1) * 53) % 360}, 70%, 55%)` }} />
                          <span className="font-medium">{label}</span>
                        </div>
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <span>{count}×</span>
                          <span className="font-mono">{avgConf}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* QR Code Section — inside camera card */}
            {scan.qrCode && (
              <>
                <Separator className="my-4" />
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold">
                      <QrCode className="w-3.5 h-3.5 text-primary" />
                      QR Tracking
                    </div>
                    <div className="flex items-center gap-0.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1 text-[10px] h-6 px-2"
                        onClick={() => {
                          const link = document.createElement('a')
                          link.href = scan.qrCode!
                          link.download = `qr-${scan.id}.png`
                          link.click()
                        }}
                      >
                        <Download className="w-3 h-3" />
                        Save
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1 text-[10px] h-6 px-2"
                        onClick={() => printQRTag(scan)}
                      >
                        <Printer className="w-3 h-3" />
                        Print Tag
                      </Button>
                    </div>
                  </div>
                  <div className="bg-white rounded-xl p-3 border flex items-center justify-center">
                    <img src={scan.qrCode} alt="QR Code" className="w-full max-w-[140px] h-auto" />
                  </div>
                  <p className="text-center text-[10px] text-muted-foreground font-mono uppercase">
                    {scan.id}
                  </p>
                  <p className="text-center text-[10px] text-muted-foreground">
                    Scan with phone to track this banana
                  </p>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Right Column — Details */}
        <div className="lg:col-span-2 space-y-4">
          {/* Classification Card */}
          <Card className="rounded-2xl">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="w-4 h-4 text-primary" /> Classification
                </CardTitle>
                {isAdmin && !editMode && (
                  <Button variant="ghost" size="sm" className="gap-1.5 text-xs h-8" onClick={startEdit}>
                    <Edit className="w-3.5 h-3.5" /> Edit
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {editMode ? (
                <div className="space-y-4 p-4 bg-muted/30 rounded-xl">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="sm:col-span-2">
                      <Label htmlFor="edit-source" className="text-xs">Source</Label>
                      <Select value={editData.source} onValueChange={(v) => setEditData({...editData, source: v})}>
                        <SelectTrigger id="edit-source" className="rounded-xl mt-1">
                          <SelectValue placeholder="Select a Source" />
                        </SelectTrigger>
                        <SelectContent>
                          {suppliers.filter(s => s.status === "Active").map(s => s.name).sort().map((src) => (
                            <SelectItem key={src} value={src}>{src}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="edit-cultivar" className="text-xs">Cultivar</Label>
                      <Select value={editData.cultivar} onValueChange={(v) => {
                        const newCultivar = v as Cultivar;
                        setEditData({...editData, cultivar: newCultivar, spoilageDays: editData.ripeness ? getSpoilageDays(newCultivar, editData.ripeness, scan.temperature ?? undefined, scan.humidity ?? undefined) : editData.spoilageDays})
                      }}>
                        <SelectTrigger id="edit-cultivar" className="rounded-xl mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CULTIVARS.map((c) => (
                            <SelectItem key={c} value={c}>{c}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="edit-ripeness" className="text-xs">Ripeness</Label>
                      <Select value={editData.ripeness} onValueChange={(v) => {
                        const newRipeness = v as Ripeness;
                        setEditData({...editData, ripeness: newRipeness, spoilageDays: editData.cultivar ? getSpoilageDays(editData.cultivar, newRipeness, scan.temperature ?? undefined, scan.humidity ?? undefined) : editData.spoilageDays})
                      }}>
                        <SelectTrigger id="edit-ripeness" className="rounded-xl mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {RIPENESS_LEVELS.map((r) => (
                            <SelectItem key={r} value={r}>{r}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="edit-spoilage" className="text-xs">Est. Spoilage (days)</Label>
                      <Input
                        id="edit-spoilage"
                        type="text"
                        value={formatSpoilageDays(editData.spoilageDays, false)}
                        readOnly
                        className="rounded-xl mt-1 bg-muted"
                        placeholder="e.g. 2-3"
                      />
                    </div>
                    <div>
                      <Label htmlFor="edit-fingers" className="text-xs">Est. Finger Count</Label>
                      <NumberField
                        id="edit-fingers"
                        min={1}
                        max={30}
                        value={editData.fingerCount ?? ""}
                        clampOnBlur={false}
                        onChange={(value) => {
                          setFingerCountEdited(true)
                          setEditData({ ...editData, fingerCount: value })
                        }}
                        className="rounded-xl mt-1"
                      />
                    </div>
                  </div>

                    {editData && scan && (
                      <AppChangePreview 
                        originalData={scan} 
                        editData={editData} 
                        className="mt-4"
                      />
                    )}
                    <div className="space-y-2"><Label htmlFor="edit-reason">Reason for change</Label><Textarea id="edit-reason" value={editReason} onChange={event => setEditReason(event.target.value)} disabled={editPending} /></div>
                  <div className="flex justify-end gap-2 pt-2">
                    <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setEditMode(false)}>
                      <X className="w-3.5 h-3.5" /> Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="gap-1.5"
                      onClick={handleSaveEdit}
                      disabled={
                        editPending ||
                        !editReason.trim() ||
                        (fingerCountEdited && (editData.fingerCount === '' || !Number.isInteger(Number(editData.fingerCount)) || Number(editData.fingerCount) < 1))
                      }
                    >
                      {editPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} {editPending ? "Saving…" : "Save Changes"}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Cultivar</p>
                      <p className="font-semibold">{scan.cultivar}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Ripeness</p>
                      <AppStatusBadge type="ripeness" status={scan.ripeness} size="md" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${scan.confidence !== null && scan.confidence < config.confidenceThreshold ? 'bg-yellow-500' : 'bg-primary'}`}
                            style={{ width: `${scan.confidence ?? 0}%` }}
                          />
                        </div>
                        <span className={`font-semibold text-sm ${scan.confidence !== null && scan.confidence < config.confidenceThreshold ? 'text-yellow-600' : ''}`}>{scan.confidence === null ? "—" : `${scan.confidence}%`}</span>
                      </div>
                      {scan.confidence !== null && scan.confidence < config.confidenceThreshold && (
                        <p className="text-[10px] text-yellow-600 mt-1 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> Below {config.confidenceThreshold}% threshold
                        </p>
                      )}
                    </div>
                  </div>
                  
                  {scan.isOverridden && scan.originalAiResult && (
                    <AppChangePreview 
                      originalData={scan.originalAiResult} 
                      editData={scan} 
                    />
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Details Card */}
          <Card className="rounded-2xl">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Banana className="w-4 h-4 text-primary" /> Scan Details
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Banana Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-4 rounded-xl bg-muted/40 space-y-1">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Hand className="w-3.5 h-3.5" /> Finger Count
                  </div>
                  <p className="text-2xl font-bold">{scan.fingerCount}</p>
                </div>
                <div className="p-4 rounded-xl bg-muted/40 space-y-1">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <AlertTriangle className="w-3.5 h-3.5" /> Est. Spoilage
                  </div>
                  <p className="text-2xl font-bold">
                    {remaining !== null
                      ? shelfLifeLabel(remaining)
                      : <>{formatSpoilageDays(scan.spoilageDays, false)} <span className="text-sm font-normal text-muted-foreground">{spoilageDayUnit(scan.spoilageDays)}</span></>}
                  </p>
                  {remaining !== null && (
                    <p className="text-xs text-muted-foreground">Est. {formatSpoilageDays(scan.spoilageDays)} from scan</p>
                  )}
                </div>
              </div>

              <Separator />

              {/* Environment */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Environment</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {scan.temperature !== undefined && (
                    <div className="p-4 rounded-xl bg-muted/40 space-y-1">
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span>🌡️</span> Temperature
                      </div>
                      <p className="text-2xl font-bold">{scan.temperature}<span className="text-sm font-normal text-muted-foreground">°C</span></p>
                    </div>
                  )}
                  {scan.humidity !== undefined && (
                    <div className="p-4 rounded-xl bg-muted/40 space-y-1">
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span>💧</span> Humidity
                      </div>
                      <p className="text-2xl font-bold">{scan.humidity}<span className="text-sm font-normal text-muted-foreground">%</span></p>
                    </div>
                  )}
                  <div role="group" aria-label="Vapor pressure deficit" title="Vapor Pressure Deficit recorded for this scan" className="p-4 rounded-xl bg-muted/40 space-y-1">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <span>💨</span> VPD
                    </div>
                    <p className="text-2xl font-bold">{scan.vpd != null && Number.isFinite(scan.vpd)
                      ? <>{scan.vpd.toFixed(3)}<span className="text-sm font-normal text-muted-foreground"> kPa</span></>
                      : <span aria-label="VPD unavailable">—</span>}</p>
                  </div>
                  {scan.treatment && (
                    <div className="p-4 rounded-xl bg-muted/40 space-y-1">
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span>{scan.treatment === "Ethephon" ? "🧪" : "🌿"}</span> Treatment
                      </div>
                      <p className="text-lg font-bold">{scan.treatment}</p>
                    </div>
                  )}
                </div>
              </div>

              <Separator />

              {/* Inventory & Logistics */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Inventory & Logistics</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-4 rounded-xl bg-muted/40 space-y-2">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Package className="w-3.5 h-3.5" /> Inventory Status
                    </div>
                    <div className="flex items-center gap-1.5">
                      <AppStatusBadge type="inventory" status={scan.inventoryStatus || "In Stock"} size="md" />
                      {isAdmin && (() => {
                        const currentStatus = scan.inventoryStatus || "In Stock"
                        const allowed = VALID_TRANSITIONS[currentStatus] || []
                        if (allowed.length === 0) return null
                        return (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" className="h-7 w-7 p-0" disabled={statusPending}>
                                <ChevronDown className="w-3.5 h-3.5" />
                                <span className="sr-only">Update status</span>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="start" className="w-48">
                              <DropdownMenuLabel>Update Status</DropdownMenuLabel>
                              <DropdownMenuSeparator />
                              {STATUS_ACTIONS.map(({ status, icon: StatusIcon, color }) => {
                                const isDisabled = !allowed.includes(status)
                                return (
                                  <DropdownMenuItem
                                    key={status}
                                    onClick={() => { if (!isDisabled) { setStatusAction(status); setStatusReason("") } }}
                                    disabled={isDisabled}
                                    className={isDisabled ? "opacity-40 cursor-not-allowed" : ""}
                                  >
                                    <StatusIcon className={`mr-2 h-4 w-4 ${isDisabled ? "text-muted-foreground" : color}`} />
                                    <span>Mark {status}</span>
                                  </DropdownMenuItem>
                                )
                              })}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )
                      })()}
                    </div>
                  </div>
                  {scan.source && (
                    <div
                      className="p-4 rounded-xl bg-muted/40 space-y-1 hover:bg-muted/60 transition-colors cursor-pointer group"
                      onClick={() => navigate(`/logs?source=${encodeURIComponent(scan.source!)}`)}
                      title="View all scans from this source"
                    >
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5"><Package className="w-3.5 h-3.5" /> Source</span>
                        <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <p className="font-semibold text-sm group-hover:text-primary transition-colors">{scan.source}</p>
                    </div>
                  )}
                  {scan.intakeId && (
                    <div
                      className="p-4 rounded-xl bg-muted/40 space-y-1 hover:bg-muted/60 transition-colors cursor-pointer group"
                      onClick={() => navigate(`/logs?intake=${encodeURIComponent(scan.intakeId!)}`)}
                      title="View all scans for this delivery intake"
                    >
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" /> Intake</span>
                        <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <p className="font-semibold text-sm font-mono break-all group-hover:text-primary transition-colors">{scan.intakeId}</p>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Quality Control Card */}
          {isAdmin && (
            <Card className="rounded-2xl">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-primary" /> Quality Control
                  </CardTitle>
                  <Button
                    variant={scan.flagged ? "secondary" : "outline"}
                    size="sm"
                    className={`gap-1.5 text-xs h-8 ${scan.flagged ? 'text-red-600 bg-red-50 hover:bg-red-100 border border-red-200' : ''}`}
                    onClick={handleFlag}
                    disabled={flagPending}
                  >
                    {flagPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Flag className={`w-3.5 h-3.5 ${scan.flagged ? 'fill-current' : ''}`} />}
                    {scan.flagged ? 'Remove Flag' : 'Flag for Review'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Review Notes */}
                <div className="space-y-3">
                  <Label className="text-sm font-semibold flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Review Notes
                    {notes.length > 0 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 rounded-full">
                        {notes.length}
                      </Badge>
                    )}
                  </Label>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {notes.map((note) => (
                      <div key={note.id} className="p-3 bg-muted/50 rounded-lg text-sm flex gap-3">
                        <Avatar className="w-7 h-7 shrink-0 mt-0.5">
                          <AvatarFallback className="bg-primary/10 text-primary font-semibold text-[10px]">
                            {note.author.split(' ').map(n => n[0]).join('').toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="text-foreground">{note.note}</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {note.author} • {new Date(note.timestamp).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    ))}
                    {notes.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">No notes yet</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Add a review note..."
                      value={noteText}
                      disabled={notePending}
                      onChange={(e) => setNoteText(e.target.value)}
                      className="rounded-xl resize-none"
                      rows={2}
                    />
                    <Button onClick={handleAddNote} disabled={!noteText.trim() || notePending} className="self-end">
                      {notePending && <Loader2 className="size-4 animate-spin" />} {notePending ? "Adding…" : "Add"}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="rounded-2xl">
            <CardHeader><CardTitle className="text-base flex items-center gap-2"><Clock className="w-4 h-4 text-primary" />Scan History</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {scan.history?.length ? scan.history.map(event => <div key={event.id} className="p-3 bg-muted/50 rounded-lg text-sm space-y-1">
                <p className="font-medium">{event.kind === 'correction' ? 'Scan correction' : event.kind === 'created' ? 'Scan created' : event.kind === 'status' ? 'Inventory status' : event.kind === 'note' ? 'Review note' : 'Review flag'}</p>
                <p className="text-xs text-muted-foreground">{event.actor_name ?? 'Actor not recorded'} · {new Date(event.timestamp).toLocaleString('en-PH', { timeZone: 'Asia/Manila' })}</p>
                {Object.entries(event.new_values).map(([key, value]) => {
                  const display = (item: unknown) => item == null ? 'Not recorded' : key === 'spoilage_days' ? formatSpoilageDays(item) : String(item)
                  return <p key={key} className="break-words">{key.replaceAll('_', ' ')}: {event.previous_values && key in event.previous_values ? `${display(event.previous_values[key])} → ` : ''}{display(value)}</p>
                })}
                {event.reason && <p>{event.reason}</p>}
                {event.legacy && <p className="text-xs text-muted-foreground">Historical record; additional change details were not recorded.</p>}
              </div>) : <p className="text-sm text-muted-foreground">No recorded history is available.</p>}
            </CardContent>
          </Card>

          {/* Metadata Card */}
          <Card className="rounded-2xl">
            <CardContent className="p-4 sm:p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                {user?.role === "Admin" && (
                  <>
                    <div className="flex items-center gap-3">
                      <Avatar className="w-10 h-10">
                        <AvatarFallback className="bg-primary/10 text-primary font-semibold">
                          {scan.operator.split(" ").map((n) => n[0]).join("").toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                          <User className="w-3.5 h-3.5" /> Operator
                        </div>
                        <p className="font-semibold">{scan.operator}</p>
                      </div>
                    </div>
                    <Separator orientation="vertical" className="hidden sm:block h-10" />
                  </>
                )}

                <div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                    <Calendar className="w-3.5 h-3.5" /> Date
                  </div>
                  <p className="font-semibold">
                    {dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </p>
                </div>

                <Separator orientation="vertical" className="hidden sm:block h-10" />

                <div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                    <Clock className="w-3.5 h-3.5" /> Time
                  </div>
                  <p className="font-semibold">{dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</p>
                </div>

              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
