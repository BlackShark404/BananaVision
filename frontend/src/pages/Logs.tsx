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
import { CULTIVARS, RIPENESS_LEVELS } from "@/types"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuLabel, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu"
import { ScrollText, Filter, Download, Banana, TrendingUp, Target, ChevronsLeft, ChevronsRight, Package, Users, Clock, MoreVertical, Box, DollarSign, Settings, AlertTriangle, Thermometer, Droplets, QrCode, X, Printer, Edit, Flag, Calendar, RefreshCw, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { getImageUrl } from "@/lib/utils"
import { api } from "@/lib/api"
import { scanWrite, scanRevision, isScanConflict } from "@/lib/scanWrites"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { scanLogParams } from "@/lib/scanLogFilters"
import { useDashboardResource } from "@/hooks/useDashboardResource"
import type { ScanLogRow, ScanLogParams } from "@/types/scanLogs"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { generateQRCodeDataUrl, printQRTag } from "@/lib/qrcode"
import type { Cultivar, Ripeness, InventoryStatus, ScanResult } from "@/types"
import { AppStatusBadge } from "@/components/AppStatusBadge"

const PAGE_SIZE = 10

type LogScan = Omit<ScanResult, "cultivar" | "ripeness" | "confidence"> & {
  cultivar: string
  ripeness: string
  confidence: number | null
  remainingDays: number | null
}

async function mapScan(row: ScanLogRow): Promise<LogScan> {
  const scan: LogScan = {
    id: row.id, revision: row.revision, dateTime: row.date_time, cultivar: row.cultivar ?? "Unknown", ripeness: row.ripeness ?? "Unknown",
    confidence: row.confidence, temperature: row.temperature ?? undefined, humidity: row.humidity ?? undefined,
    spoilageDays: row.spoilage_days ?? "Unknown", fingerCount: row.finger_count, operator: row.operator_name,
    source: row.source_name, intakeId: row.intake_id ?? undefined, inventoryStatus: row.inventory_status as InventoryStatus,
    statusUpdatedAt: row.status_updated_at ?? undefined, flagged: row.flagged, isOverridden: row.is_overridden,
    thumbnailUrl: row.thumbnail_url ? getImageUrl(row.thumbnail_url) : undefined, remainingDays: row.remaining_days,
  }
  // A QR rendering failure must not hide the scan history.
  try { scan.qrCode = await generateQRCodeDataUrl(scan) } catch { /* Thumbnail fallback remains available. */ }
  return scan
}

export default function Logs() {
  const { user } = useAuth()
  return user ? <LogsContent key={`${user.id}:${user.role}`} /> : null
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
  const dateFilter = searchParams.get("date") || ""
  const cardFilter = requestParams.attention === "all" ? null : requestParams.attention
  const [qrModalScan, setQrModalScan] = useState<LogScan | null>(null)
  const [exporting, setExporting] = useState(false)
  const [pendingScans, setPendingScans] = useState<Set<string>>(new Set())
  const inFlight = useRef(new Set<string>())
  const [statusAction, setStatusAction] = useState<{ scan: LogScan; status: InventoryStatus } | null>(null)
  const [statusReason, setStatusReason] = useState("")

  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.scanLogs.list(scanLogParams(new URLSearchParams(queryKey)), signal)
    const rows = await Promise.all(result.items.map(mapScan))
    return { result, rows }
  }, [queryKey])
  const resource = useDashboardResource(load)
  const latestRefresh = useRef(resource.refresh)
  useEffect(() => { latestRefresh.current = resource.refresh }, [resource.refresh])
  const response = resource.data?.result
  const filtered = resource.data?.rows ?? []
  const stats = { avgConfidence: response?.avg_confidence, spoilingSoon: response?.at_risk_count, reviewCount: response?.review_count ?? 0 }
  const operators = response?.options.operators ?? []
  const sources = response?.options.sources ?? []

  const updateFilters = (changes: Record<string, string | undefined>, replace = false) => {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(changes)) {
        if (!value || value === "all") next.delete(key)
        else next.set(key, value)
      }
      if (!("page" in changes)) next.delete("page")
      return next
    }, { replace })
  }
  const clearAllFilters = () => setSearchParams({})
  const setSearch = (value: string) => updateFilters({ search: value }, true)
  const setCultivarFilter = (value: string) => updateFilters({ cultivar: value })
  const setRipenessFilter = (value: string) => updateFilters({ ripeness: value })
  const setSourceFilter = (value: string) => updateFilters({ source_key: value, source: undefined })
  const setOperatorFilter = (value: string) => updateFilters({ operator_id: value })
  const setStatusFilter = (value: string) => updateFilters({ status: value })
  const setCardFilter = (value: string | null) => updateFilters({ attention: value ?? undefined })

  // A deletion/status change can shrink the final page while this view is open.
  useEffect(() => {
    if (response && response.page > 1 && response.items.length === 0) {
      setSearchParams(previous => {
        const next = new URLSearchParams(previous)
        next.set("page", String(Math.max(1, Math.ceil(response.total / PAGE_SIZE))))
        return next
      }, { replace: true })
    }
  }, [response, setSearchParams])

  const handleStatusUpdate = async () => {
    if (!statusAction || !statusReason.trim() || inFlight.current.has(statusAction.scan.id)) return
    const { scan, status } = statusAction
    inFlight.current.add(scan.id)
    setPendingScans(new Set(inFlight.current))
    try {
      await scanWrite(`${user?.id}:${scan.id}:status`, {
        expected_revision: scanRevision(scan.revision), inventory_status: status, reason: statusReason.trim(),
      }, body => api.scans.updateStatus(scan.id, body))
      toast.success(`Scan marked as ${status}`)
      setStatusAction(null)
      await latestRefresh.current()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Status update failed", {
        action: isScanConflict(error) ? { label: "Reload latest", onClick: () => {
          void api.scans.detail(scan.id).then(saved => {
            setStatusAction(current => current?.scan.id === scan.id ? { ...current, scan: { ...current.scan,
              revision: saved.revision, inventoryStatus: saved.inventory_status } } : current)
            void latestRefresh.current()
          }).catch(error => toast.error(error.message))
        } } : undefined,
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

  const exportToCSV = async () => {
    setExporting(true)
    try {
      await api.scanLogs.export(requestParams, AbortSignal.timeout(60_000))
      toast.success("Exported all matching scan records")
    } catch (error) { toast.error(error instanceof Error ? error.message : "Export failed") }
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
      cell: (scan) => <AppStatusBadge type="ripeness" status={scan.ripeness} size="md" />,
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
          {scan.temperature == null && scan.humidity == null && (
             <span className="text-muted-foreground">—</span>
          )}
        </div>
      ),
    },
    {
      header: "Est. Spoilage",
      sortable: true,
      sortKey: "spoilage_days",
      cell: (scan) => <div className="text-sm"><span title="Estimate when scanned">{scan.spoilageDays} days</span>{scan.remainingDays !== null && <span className="block text-xs text-muted-foreground">{scan.remainingDays <= 0 ? "Estimated expiry reached" : `${scan.remainingDays.toFixed(1)} days left`}</span>}</div>,
    },
    {
      header: "Est. Fingers",
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
              const isDisabled = scan.inventoryStatus === actionStatus || pendingScans.has(scan.id)
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
          <DialogHeader><DialogTitle>Mark scan as {statusAction?.status}?</DialogTitle><DialogDescription>This change will be recorded in the scan history.</DialogDescription></DialogHeader>
          <Label htmlFor="status-reason">Reason for change</Label>
          <Textarea id="status-reason" value={statusReason} onChange={event => setStatusReason(event.target.value)} disabled={!!pendingScans.size} />
          <DialogFooter><Button variant="outline" disabled={!!pendingScans.size} onClick={() => setStatusAction(null)}>Cancel</Button><Button disabled={!statusReason.trim() || !!pendingScans.size} onClick={() => void handleStatusUpdate()}>Save Changes</Button></DialogFooter>
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
            <Button variant="outline" className="gap-2 w-full sm:w-auto" onClick={exportToCSV} disabled={exporting || !response}>
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">{exporting ? "Exporting…" : "Export CSV"}</span>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" role="status" aria-live="polite">
        <span>{resource.error ? response ? "Stale Data" : "Unavailable" : resource.loading ? "Loading…" : "Updated"}</span>
        {response && <span>Last refreshed {new Date(response.generated_at).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila" })}</span>}
        <Button variant="ghost" size="sm" onClick={() => void resource.refresh()} disabled={resource.loading}><RefreshCw className="size-3.5" /> Refresh</Button>
      </div>
      {resource.error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <strong>{response ? "Scan Logs refresh failed. Showing the last successful results." : "Scan Logs unavailable."}</strong> {resource.error}
        <Button variant="link" size="sm" onClick={() => void resource.refresh()}>Retry</Button>
      </div>}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
        <AppStatsCard
          title="Total Scans"
          value={response ? response.total : resource.loading ? "…" : "—"}
          icon={TrendingUp}
          delay={50}
          description={response ? "Matching records · click to reset filters" : resource.loading ? "Loading…" : "Unavailable"}
          onClick={clearAllFilters}
        />
        <AppStatsCard
          title="Avg Confidence"
          value={response ? stats.avgConfidence == null ? "—" : `${stats.avgConfidence.toFixed(1)}%` : resource.loading ? "…" : "—"}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Model confidence"
        />
        <AppStatsCard
          title="At-Risk Scans"
          value={response ? stats.spoilingSoon ?? 0 : resource.loading ? "…" : "—"}
          icon={Clock}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={150}
          description="Spoiling in ≤2 days"
          onClick={() => setCardFilter(cardFilter === "at-risk" ? null : "at-risk")}
          active={cardFilter === "at-risk"}
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search by cultivar, operator, or ID..."
        hasActiveFilters={search !== "" || cultivarFilter !== "all" || ripenessFilter !== "all" || sourceFilter !== "all" || operatorFilter !== "all" || statusFilter !== "all" || intakeFilter !== "all" || cardFilter !== null || dateFilter !== ""}
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
          <label htmlFor="scan-date" className="sr-only">Scan date</label>
          <Input id="scan-date" type="date" value={dateFilter} onChange={event => updateFilters({ date: event.target.value })}
            className="w-full sm:w-44 h-10" title="Filter by calendar date in Asia/Manila" />
          {dateFilter && <Button type="button" variant="ghost" size="icon" aria-label="Clear scan date" title="All dates" onClick={() => updateFilters({ date: undefined })}><X className="size-4" /></Button>}
        </div>
      </AppTableFilters>

      {cardFilter === "at-risk" && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">At-Risk Scans</Badge>
        <span className="text-xs text-muted-foreground">In stock with estimated spoilage in 2 days or less, including overdue estimates.</span>
        <Button variant="ghost" size="sm" onClick={() => setCardFilter(null)}>Clear risk filter</Button>
      </div>}

      {/* Table */}
      {!response ? <Card className="p-10 text-center text-muted-foreground" role="status">{resource.loading ? <span className="inline-flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Loading scan records…</span> : "Records could not be loaded. Retry above."}</Card> : (
      <AppDataTable
        data={filtered}
        columns={columns}
        rowKey={(scan) => scan.id}
        onRowClick={(scan) => navigate(`/scans/${scan.id}`)}
        pagination={{ pageSize: PAGE_SIZE }}
        serverState={{ page: response.page, total: response.total, sort: { key: requestParams.sort, direction: requestParams.direction },
          onPageChange: page => updateFilters({ page: String(page) }),
          onSortChange: (sort, direction) => updateFilters({ sort, direction }),
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
            className="relative bg-background rounded-2xl shadow-2xl p-6 max-w-xs w-full mx-4 animate-in zoom-in-95"
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
              <div className="bg-white rounded-xl p-4 border">
                {qrModalScan.qrCode ? (
                  <img src={qrModalScan.qrCode} alt="QR Code" className="w-full h-auto" />
                ) : (
                  <div className="w-full aspect-square flex items-center justify-center text-muted-foreground">
                    <QrCode className="w-16 h-16" />
                  </div>
                )}
              </div>
              <div>
                <p className="font-semibold">{qrModalScan.cultivar}</p>
                <p className="text-xs text-muted-foreground font-mono uppercase">ID: {qrModalScan.id}</p>
              </div>
              <Button
                variant="outline"
                className="w-full gap-2"
                onClick={() => printQRTag(qrModalScan)}
              >
                <Printer className="w-4 h-4" />
                Print Tag
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
