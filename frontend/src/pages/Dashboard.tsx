import { useState, useEffect, useCallback, useRef } from "react"
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { useDashboardResource } from "@/hooks/useDashboardResource"
import { DashboardRecords } from "@/components/DashboardRecords"
import { useWebSocket } from "@/hooks/useWebSocket"
import { api, BASE_URL } from "@/lib/api"
import { buildScanLogsUrl } from "@/lib/scanLogFilters"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AppStatsCard } from "@/components/AppStatsCard"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { AppPageHeader } from "@/components/AppPageHeader"
import {
  ScanLine,
  Camera,
  AlertCircle,
  Package,
  Target,
  TrendingUp,
  Users,
  Activity,
  ArrowRight,
  LayoutDashboard,
  RefreshCw,
  Loader2,
  ClipboardCheck,
  Clock
} from "lucide-react"
import { AppStatusBadge } from "@/components/AppStatusBadge"

const manilaTime = new Intl.DateTimeFormat("en-PH", {
  timeZone: "Asia/Manila", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit",
})
const manilaDate = (time: number) => new Date(time + 28_800_000).toISOString().slice(0, 10)

function legacyScanLogsUrl(params: URLSearchParams, selectedDate: string): string | null {
  const view = params.get("view")
  if (!view || !["today", "confidence", "all", "review", "expiring"].includes(view)) return null
  const sourceKey = params.get("source_key") || undefined
  const operatorId = params.get("operator_id") || undefined
  return buildScanLogsUrl({
    date: view === "today" || view === "confidence" || (view === "all" && (sourceKey || operatorId)) ? selectedDate : undefined,
    source_key: sourceKey,
    operator_id: operatorId,
    attention: view === "expiring" ? "at-risk" : view === "review" ? "review" : undefined,
    sort: view === "confidence" || params.get("sort") === "confidence" ? "confidence" : undefined,
    direction: view === "confidence" || params.get("direction") === "asc" ? "asc" : params.get("direction") === "desc" ? "desc" : undefined,
  })
}

export default function Dashboard() {
  const { user } = useAuth()
  // A changed account/role must never inherit another account's snapshot or requests.
  return user ? <DashboardContent key={`${user.id}:${user.role}`} /> : null
}

function DashboardContent() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const urlBusinessDate = params.get("business_date") || undefined
  const fetchSummary = useCallback((signal: AbortSignal) => api.dashboard.summary(signal, urlBusinessDate), [urlBusinessDate])
  const metrics = useDashboardResource(fetchSummary)
  const cameras = useDashboardResource(api.cameras.list)
  const { refresh: refreshMetrics } = metrics
  const { refresh: refreshCameras } = cameras
  const [now, setNow] = useState(() => Date.now())
  const eventTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEvent = useCallback((event: string) => {
    if (event.startsWith("scan:") || event === "device:status" || event === "notification") {
      if (eventTimer.current) clearTimeout(eventTimer.current)
      // Completion currently broadcasts before commit; fetch a settled snapshot.
      eventTimer.current = setTimeout(() => {
        void refreshMetrics()
        void refreshCameras()
      }, 750)
    }
  }, [refreshMetrics, refreshCameras])
  const { status: connectionStatus } = useWebSocket({ rooms: ["dashboard", "devices"], onEvent })
  useEffect(() => {
    if (connectionStatus === "connected") {
      void refreshMetrics()
      void refreshCameras()
    }
  }, [connectionStatus, refreshMetrics, refreshCameras])

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 15_000)
    let midnightTimer: ReturnType<typeof setTimeout>
    const scheduleMidnight = () => {
      const nextMidnight = (Math.floor((Date.now() + 28_800_000) / 86_400_000) + 1) * 86_400_000 - 28_800_000
      midnightTimer = setTimeout(() => {
        setNow(Date.now())
        void refreshMetrics()
        scheduleMidnight()
      }, Math.max(1, nextMidnight - Date.now()))
    }
    scheduleMidnight()
    return () => {
      clearInterval(interval)
      clearTimeout(midnightTimer)
      if (eventTimer.current) clearTimeout(eventTimer.current)
    }
  }, [refreshMetrics])

  const summary = metrics.data
  const selectedBusinessDate = params.get("business_date") || summary?.business_date || manilaDate(now)
  const groupView = params.get("view") === "sources" || params.get("view") === "operators"
  useEffect(() => {
    if (!groupView || params.get("business_date")) return
    const next = new URLSearchParams(params)
    next.set("business_date", selectedBusinessDate)
    setParams(next, { replace: true })
  }, [groupView, params, selectedBusinessDate, setParams])
  const previousDay = !!summary && summary.business_date !== manilaDate(now)
  const staleMetrics = !!summary && (!!metrics.error || previousDay || (metrics.receivedAt !== null && now - metrics.receivedAt > 90_000))
  const staleCameras = !!cameras.data && (!!cameras.error || (cameras.receivedAt !== null && now - cameras.receivedAt > 90_000))
  const activeSourcesList = summary?.sources ?? []
  const recentScans = summary?.recent_scans ?? []
  const devices = cameras.data ?? []
  const onlineCameras = devices.filter(device => device.online).length
  const metricValue = (value: string | number | undefined) => summary ? value ?? "—" : metrics.loading ? "…" : "—"
  const metricDescription = (description: string) => summary ? description : metrics.loading ? "Loading…" : "Unavailable · refresh to retry"
  const operatorMetric = user?.role === "Operator" ? {
    value: summary?.success_rate == null ? "N/A" : `${summary.success_rate.toFixed(1)}%`,
    label: "Scan Success Rate", icon: ClipboardCheck, desc: "Auto-approved scans",
  } : {
    value: summary?.active_operator_count, label: "Active Operators", icon: Users, desc: "Operators with scan records today",
  }
  const openRecords = (view: string, filters?: { source_key?: string; operator_id?: string; business_date?: string }) => {
    const date = filters?.business_date ?? summary?.business_date ?? selectedBusinessDate
    if (view === "sources" || view === "operators") {
      setParams(new URLSearchParams({ view, business_date: date }))
      return
    }
    navigate(buildScanLogsUrl({
      date: view === "review" || view === "expiring" ? undefined : date,
      source_key: filters?.source_key,
      operator_id: filters?.operator_id,
      attention: view === "expiring" ? "at-risk" : view === "review" ? "review" : undefined,
      sort: view === "confidence" ? "confidence" : undefined,
      direction: view === "confidence" ? "asc" : undefined,
    }))
  }
  const refreshAll = () => { void refreshMetrics(); void refreshCameras() }
  const legacyTarget = legacyScanLogsUrl(params, selectedBusinessDate)
  if (legacyTarget) return <Navigate to={legacyTarget} replace />

  return (
    <div className="space-y-4 sm:space-y-6 pb-4 sm:pb-6">
      {/* Header */}
      <AppPageHeader
        title={user?.role === "Operator" ? "My Dashboard" : "Admin Dashboard"}
        description={user?.role === "Operator" ? "Performance overview and recent scans" : "High-level overview of system operations and daily metrics"}
        icon={LayoutDashboard}
        action={<Button variant="outline" onClick={refreshAll} disabled={metrics.loading || cameras.loading}>
          {metrics.loading || cameras.loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {metrics.loading || cameras.loading ? "Refreshing…" : "Refresh"}
        </Button>}
      />

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" role="status" aria-live="polite">
        <Badge variant={staleMetrics || metrics.error ? "destructive" : "secondary"}>
          {staleMetrics ? "Stale Data" : !summary ? metrics.loading ? "Loading" : "Unavailable" : "Updated"}
        </Badge>
        <span>{summary ? `Last refreshed ${manilaTime.format(new Date(summary.generated_at))}` : "No successful refresh yet"}</span>
        <span aria-hidden="true">·</span>
        <span>{connectionStatus === "connected" ? "Live updates connected" : connectionStatus === "connecting" ? "Connecting live updates" : "Live updates disconnected"}</span>
      </div>
      {metrics.error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <strong>{summary ? "Dashboard refresh failed." : "Dashboard unavailable."}</strong> {metrics.error}
        {summary && " Showing the last successful snapshot."}
        <Button variant="link" size="sm" onClick={() => void refreshMetrics()}>Retry metrics</Button>
      </div>}
      {previousDay && <p className="text-xs text-amber-700">Showing {summary.business_date} while today's totals refresh.</p>}
      {connectionStatus !== "connected" && <p className="text-xs text-muted-foreground">Live changes may be delayed. Checking for updates every 30 seconds and on reconnection.</p>}

      {/* KPI StatsRow */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          title={previousDay ? `Scans · ${summary.business_date}` : "Scans Today"}
          value={metricValue(summary?.total_scans)}
          icon={TrendingUp}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={50}
          description={metricDescription("Scan records today")}
          onClick={() => openRecords("today")}
          disabled={!summary}
        />
        <AppStatsCard
          title={operatorMetric.label}
          value={metricValue(operatorMetric.value)}
          icon={operatorMetric.icon}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description={metricDescription(operatorMetric.desc)}
          onClick={user?.role === "Operator" ? undefined : () => openRecords("operators")}
          disabled={!summary}
        />
        <AppStatsCard
          title={user?.role === "Operator" ? "My Sources" : "Active Sources"}
          value={metricValue(summary?.active_source_count ?? summary?.sources.length)}
          icon={Package}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={150}
          description={metricDescription(user?.role === "Operator" ? "Sources processed today" : "Sources with scan records today")}
          onClick={() => openRecords("sources")}
          disabled={!summary}
        />
        <AppStatsCard
          title="System Health"
          value={cameras.data ? devices.length ? `${onlineCameras}/${devices.length}` : "—" : cameras.loading ? "…" : "—"}
          icon={Activity}
          iconColor={!staleCameras && onlineCameras === devices.length && devices.length > 0 ? "text-emerald-600" : "text-amber-600"}
          iconBgColor={!staleCameras && onlineCameras === devices.length && devices.length > 0 ? "bg-emerald-500/10" : "bg-amber-500/10"}
          delay={200}
          description={cameras.data ? devices.length ? staleCameras ? "Last known cameras online" : "Cameras online" : "No cameras configured" : cameras.loading ? "Loading camera status…" : "Camera status unavailable"}
          onClick={() => navigate("/devices")}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={!summary} onClick={() => openRecords("review")}>
          <ClipboardCheck className="w-4 h-4 text-amber-600" /> Pending quality reviews
          <Badge variant="secondary">{metricValue(summary?.pending_review_count)}</Badge>
        </Button>
        <Button variant="outline" disabled={!summary} onClick={() => openRecords("expiring")}>
          <Clock className="w-4 h-4 text-rose-600" /> Expiring stock
          <Badge variant="secondary">{metricValue(summary?.expiring_stock_count)}</Badge>
        </Button>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        
        {/* Recent Scans Table (Takes up 2 columns) */}
        <Card className="col-span-1 lg:col-span-2 rounded-xl sm:rounded-2xl shadow-sm overflow-hidden flex flex-col">
          <CardHeader className="pb-3 flex flex-row items-center justify-between border-b bg-muted/10">
            <div>
              <CardTitle className="text-base sm:text-lg">Recent Scans</CardTitle>
              <CardDescription className="text-xs">Latest classification results</CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => navigate("/logs")} className="hidden sm:flex text-muted-foreground hover:text-primary">
              View All Logs <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </CardHeader>
          <div className="flex-1">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="font-semibold w-[140px]">Date/Time</TableHead>
                  <TableHead className="font-semibold">Cultivar</TableHead>
                  <TableHead className="font-semibold">Ripeness</TableHead>
                  <TableHead className="font-semibold">Confidence</TableHead>
                  <TableHead className="font-semibold">Source</TableHead>
                  {user?.role !== "Operator" && <TableHead className="font-semibold text-right">Operator</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {!summary ? (
                  <TableRow><TableCell colSpan={user?.role === "Operator" ? 5 : 6} className="h-48 text-center text-muted-foreground">
                    {metrics.loading ? "Loading recent scans…" : "Recent scans unavailable. Retry the dashboard refresh."}
                  </TableCell></TableRow>
                ) : recentScans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={user?.role === "Operator" ? 5 : 6} className="h-48 text-center">
                      <Empty>
                        <EmptyHeader>
                          <EmptyMedia variant="icon" className="size-10 rounded-full bg-primary/10 text-primary [&_svg]:size-5">
                            <ScanLine className="w-4 h-4" />
                          </EmptyMedia>
                          <EmptyTitle className="text-sm font-medium mt-1">No recent scans</EmptyTitle>
                        </EmptyHeader>
                      </Empty>
                    </TableCell>
                  </TableRow>
                ) : (
                  recentScans.map((scan) => (
                    <TableRow key={scan.id} className="hover:bg-muted/50">
                      <TableCell className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                        <Link to="/logs" className="underline underline-offset-4 focus-visible:outline-primary">{manilaTime.format(new Date(scan.date_time))}</Link>
                      </TableCell>
                      <TableCell className="font-medium text-sm">{scan.cultivar}</TableCell>
                      <TableCell>
                        <AppStatusBadge type="ripeness" status={scan.ripeness ?? "Unknown"} size="sm" />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium">{scan.confidence === null ? "—" : `${scan.confidence}%`}</span>
                          <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden hidden sm:block">
                            <div className="h-full bg-primary rounded-full" style={{ width: `${scan.confidence ?? 0}%` }} />
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="font-medium text-xs text-muted-foreground whitespace-nowrap">
                        {scan.source_name}
                      </TableCell>
                      {user?.role !== "Operator" && (
                        <TableCell className="text-right text-xs truncate max-w-[100px]">
                          {scan.operator_name}
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Card>

        {/* Today's Sources Side Panel */}
        <Card className="col-span-1 rounded-xl sm:rounded-2xl shadow-sm flex flex-col">
          <CardHeader className="pb-3 border-b bg-muted/10 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base sm:text-lg">Today's Sources</CardTitle>
              <CardDescription className="text-xs">Suppliers &amp; Sources with Activity</CardDescription>
            </div>
            <Button variant="ghost" size="icon" aria-label="Open Today's Sources in Scan Logs" onClick={() => navigate("/logs")} className="h-8 w-8 text-muted-foreground hover:text-primary">
              <ArrowRight className="w-4 h-4" />
            </Button>
          </CardHeader>
          <CardContent className="p-0 flex-1">
            {!summary ? <p className="p-8 text-center text-sm text-muted-foreground">{metrics.loading ? "Loading sources…" : "Source data unavailable."}</p> : activeSourcesList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                <Package className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-sm">No active sources</p>
              </div>
            ) : (
              <div className="divide-y overflow-y-auto" style={{ maxHeight: "400px" }}>
                {activeSourcesList.map((sourceItem) => (
                  <Link key={sourceItem.key} to={buildScanLogsUrl({ source_key: sourceItem.key })} className="p-4 flex items-center justify-between hover:bg-muted/30 transition-colors focus-visible:outline-2 focus-visible:outline-primary">
                    <div className="min-w-0 pr-4">
                      <p className="text-sm font-semibold truncate text-foreground/90">{sourceItem.name}</p>
                    </div>
                    <div className="flex flex-col items-end shrink-0">
                      <Badge variant="secondary" className="bg-primary/10 text-primary hover:bg-primary/20 border-primary/20">
                        {sourceItem.count} scans
                      </Badge>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

      </div>

      {/* Camera Frames Section */}
      <div>
        <h2 className="text-base sm:text-lg font-semibold mb-3 flex items-center gap-2 px-1">
          <Camera className="w-4 h-4 sm:w-5 sm:h-5 text-muted-foreground" /> Hardware Monitoring
        </h2>
        <p className="text-xs text-muted-foreground mb-3">{cameras.receivedAt ? `${staleCameras ? "Stale Data · " : ""}Last checked ${manilaTime.format(cameras.receivedAt)}` : "No camera status received yet"}</p>
        {cameras.error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 mb-3 text-sm">{cameras.data ? "Camera status refresh failed; showing last known status." : "Camera status unavailable."} <Button variant="link" size="sm" onClick={() => void refreshCameras()}>Retry cameras</Button></div>}
        {cameras.data && devices.length > 0 && onlineCameras === 0 && <p className="text-sm text-muted-foreground mb-3">No cameras are currently online. <Link to="/devices" className="underline">Check Device Status</Link> to troubleshoot.</p>}
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {cameras.data ? devices.length ? devices.map((camera, index) => (
            <DashboardCamera key={`${camera.device_id}:${camera.online}`} camera={camera} cameraId={camera.camera_id} stale={staleCameras} />
          )) : <Card className="col-span-full rounded-lg sm:rounded-xl"><CardContent className="py-6 text-center text-sm text-muted-foreground">No cameras configured. <Link to="/devices" className="underline">Open Device Status</Link> to review the setup.</CardContent></Card> : <p className="col-span-full py-6 text-center text-sm text-muted-foreground">{cameras.loading ? "Loading cameras…" : "Camera status unavailable."}</p>}
        </div>
      </div>
      <DashboardRecords summary={summary} view={params.get("view")} onClose={() => setParams({})} onSelectView={openRecords}
        businessDate={params.get("business_date") || undefined} revision={metrics.receivedAt ?? 0} />
    </div>
  )
}


type CameraInfo = Awaited<ReturnType<typeof api.cameras.list>>[number]
function DashboardCamera({ camera, cameraId, stale }: { camera: CameraInfo; cameraId: string; stale: boolean }) {
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  return (
    <Card className="rounded-lg sm:rounded-xl overflow-hidden group">
      <div className={`aspect-video relative flex items-center justify-center ${camera.online ? "bg-black" : "bg-destructive/5"}`}>
        {camera.online && !failed ? <>
          <img src={`${BASE_URL}/api/v1/cameras/preview/${camera.device_id}?fps=5&retry=${attempt}`} alt={`Live Camera Feed - ${cameraId}: ${camera.label}`}
            className="inset-0 w-full h-full object-cover z-0 absolute animate-fade-in" onError={() => setFailed(true)} />
          <div className="absolute inset-0 bg-linear-to-b from-transparent to-black/40 z-0 pointer-events-none" />
        </> : <div className="text-center space-y-1.5 sm:space-y-2 relative z-10 p-2">
          <AlertCircle className={`w-6 h-6 sm:w-8 sm:h-8 mx-auto ${camera.online ? "text-white/40" : "text-destructive/40"}`} />
          <p className={`text-[10px] sm:text-xs font-medium ${camera.online ? "text-white/60" : "text-destructive/60"}`}>{failed ? "Preview unavailable" : `${cameraId} Offline`}</p>
          {failed && camera.online && <Button size="sm" variant="secondary" onClick={() => { setFailed(false); setAttempt(value => value + 1) }}>Retry preview</Button>}
        </div>}
        {camera.online && <>
          <div className="absolute top-1.5 sm:top-2 right-1.5 sm:right-2 z-10">
            <Badge variant="outline" className={`${stale || failed ? "bg-amber-500/90" : "bg-emerald-500/90"} text-white border-0 text-[9px] sm:text-[10px] px-1 sm:px-1.5 h-4 sm:h-auto`}>
              {stale ? "LAST KNOWN ONLINE" : failed ? "PREVIEW ERROR" : "ONLINE"}
            </Badge>
          </div>
          <div className="absolute bottom-1.5 sm:bottom-2 left-1.5 sm:left-2 z-10">
            <span className="text-[9px] sm:text-[10px] text-white/90 bg-black/50 px-1.5 sm:px-2 py-0.5 rounded backdrop-blur-sm shadow-sm font-medium">{cameraId}</span>
          </div>
        </>}
      </div>
    </Card>
  )
}
