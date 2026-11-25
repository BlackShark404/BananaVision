import { useEffect, useMemo, useState, useCallback } from "react"
import { useAuth } from "@/context/AuthContext"
import { useDashboardResource } from "@/hooks/useDashboardResource"
import type { AnalyticsRange, AnalyticsSummary, RipenessConfidenceRow } from "@/types/analytics"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { ContentSkeleton } from "@/components/LoadingState"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppDataTable } from "@/components/AppDataTable"
import { AppPageHeader } from "@/components/AppPageHeader"
import { CultivarEnum, InventoryStatusEnum, RipenessEnum } from "@/types"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { BarChart3, TrendingUp, Target, ShieldCheck, AlertTriangle, Users, Calendar, Package, Clock, Loader2, CalendarDays, X } from "lucide-react"
import { AppDateFilter } from "@/components/AppDateFilter"
import { ANALYTICS_RANGE_LABELS, DEFAULT_ANALYTICS_PERIOD, analyticsPeriodLabel, analyticsPeriodParams, hasCustomDates, rangeChoice, type AnalyticsPeriod } from "@/lib/analyticsPeriod"
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
} from "recharts"
import { inManila } from "@/lib/manilaTime"

// --- Chart Configs ---

const ripenessChartConfig = {
  [RipenessEnum.UNRIPE]: { label: "Unripe", color: "#22c55e" },
  [RipenessEnum.SEMI_RIPE]: { label: "Semi Ripe", color: "#7c3aed" },
  [RipenessEnum.RIPE]: { label: "Ripe", color: "#eab308" },
  [RipenessEnum.OVERRIPE]: { label: "Overripe", color: "#ef4444" },
} satisfies ChartConfig

const cultivarChartConfig = {
  [CultivarEnum.LAKATAN]: { label: "Lakatan", color: "#f59e0b" },
  [CultivarEnum.LATUNDAN]: { label: "Latundan", color: "#fbbf24" },
  [CultivarEnum.CARDABA]: { label: "Cardaba", color: "#d97706" },
  count: { label: "Count" },
} satisfies ChartConfig

const cultivarRipenessChartConfig = {
  [RipenessEnum.UNRIPE]: { label: "Unripe", color: "#22c55e" },
  [RipenessEnum.SEMI_RIPE]: { label: "Semi Ripe", color: "#7c3aed" },
  [RipenessEnum.RIPE]: { label: "Ripe", color: "#eab308" },
  [RipenessEnum.OVERRIPE]: { label: "Overripe", color: "#ef4444" },
} satisfies ChartConfig

const confidenceChartConfig = {
  avgConfidence: { label: "Avg Model Confidence (%)", color: "#22c55e" },
  verifiedAccuracy: { label: "Verified Accuracy (%)", color: "#2563eb" },
} satisfies ChartConfig

const sourceChartConfig = {
  count: { label: "Scans", color: "#3b82f6" },
} satisfies ChartConfig

const scanTrendChartConfig = {
  count: { label: "Scans", color: "#eab308" },
} satisfies ChartConfig

const hourlyChartConfig = {
  count: { label: "Scans", color: "#eab308" },
} satisfies ChartConfig

const metricLabels: Record<string, string> = {
  throughput: "Total Scans",
  classifications: "Cultivar & Ripeness Charts",
  model_confidence: "Avg Confidence",
  low_confidence: "Low Confidence",
  inventory_risk: "At-Risk Scans",
  confidence_by_ripeness: "Confidence vs. Verified Accuracy",
  trend: "Scan Trend",
  sources: "Scans by Source",
  operators: "Operator Performance",
  hourly: "Peak Scanning Hours",
  human_verified_accuracy: "Verified Accuracy",
}
const manilaDate = new Intl.DateTimeFormat("en-PH", inManila({
  month: "short", day: "numeric", year: "numeric",
}))
const manilaTime = new Intl.DateTimeFormat("en-PH", inManila({
  hour: "numeric", minute: "2-digit",
}))

const CULTIVAR_COLORS: Record<string, string> = {
  [CultivarEnum.LAKATAN]: "#f59e0b",
  [CultivarEnum.LATUNDAN]: "#fbbf24",
  [CultivarEnum.CARDABA]: "#d97706",
}

export default function Analytics() {
  const { user } = useAuth()
  return user ? <AnalyticsContent key={`${user.id}:${user.role}`} /> : null
}

type AnalyticsFilterParams = { source_key?: string; cultivar?: string; inventory_status?: string }
type ChartPeriod = ReturnType<typeof useChartPeriod<unknown>>

const ripenessOf = (s: AnalyticsSummary) => s.ripeness_distribution
const cultivarsOf = (s: AnalyticsSummary) => s.cultivar_counts
const cultivarRipenessOf = (s: AnalyticsSummary) => s.cultivar_ripeness
const confidenceOf = (s: AnalyticsSummary) => s.ripeness_confidence
const sourcesOf = (s: AnalyticsSummary) => s.scans_by_source
const hoursOf = (s: AnalyticsSummary) => s.hourly_distribution

/**
 * One chart's period. It follows the page period until the user picks another one for this
 * chart; then the chart loads its own data (same source/cultivar/status filters) through the
 * shared resource hook, so stale responses are dropped and a failure is shown, never the
 * page's data under this chart's label. A chart on the page period makes no requests.
 */
function useChartPeriod<T>(
  pageData: T | undefined,
  extract: (summary: AnalyticsSummary) => T,
  pagePeriod: AnalyticsPeriod,
  filters: AnalyticsFilterParams,
) {
  const [override, setOverride] = useState<AnalyticsPeriod | null>(null)
  const load = useCallback(async (signal: AbortSignal) => {
    if (!override) return null
    return extract(await api.analytics.summary({ ...filters, ...analyticsPeriodParams(override) }, signal))
  }, [override, extract, filters])
  const resource = useDashboardResource(load, { enabled: override !== null })
  const period = override ?? pagePeriod
  return {
    overridden: override !== null,
    period,
    label: analyticsPeriodLabel(period),
    data: override ? resource.data ?? undefined : pageData,
    loading: override !== null && resource.loading,
    error: override ? resource.error : null,
    retry: () => void resource.refresh(),
    change: setOverride,
    reset: () => setOverride(null),
  }
}

/**
 * Preset + Date From + Date To, shared by the page header and every chart header. Picking a
 * preset clears the dates; picking a date keeps the other one. The X button is given by the
 * caller (page: clear the dates; chart: use the page dates).
 */
function PeriodControls({ name, period, onChange, clear, compact = false }: {
  name: string
  period: AnalyticsPeriod
  onChange: (period: AnalyticsPeriod) => void
  clear?: { label: string; title: string; onClick: () => void }
  compact?: boolean
}) {
  const size = compact ? "h-8 text-xs px-2" : "h-10"
  return (
    <>
      <Select value={rangeChoice(period)} onValueChange={v => onChange({ range: v as AnalyticsRange, from: "", to: "" })}>
        <SelectTrigger className={compact ? "h-8 min-w-[110px] text-xs px-2" : "w-[140px] h-10"} aria-label={`${name} date range`}>
          {!compact && <Calendar className="w-4 h-4 mr-2" />}
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(ANALYTICS_RANGE_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
          {hasCustomDates(period) && <SelectItem value="custom" disabled>Custom</SelectItem>}
        </SelectContent>
      </Select>
      <div className="flex items-center gap-1">
        <AppDateFilter
          value={period.from}
          onChange={from => onChange({ ...period, from })}
          label={`${name} date from`}
          emptyText="Date From"
          title="First day included (Asia/Manila)"
          disableFuture
          maxDate={period.to || undefined}
          className={compact ? `${size} min-w-[105px]` : "h-10 w-[130px] text-xs"}
        />
        <AppDateFilter
          value={period.to}
          onChange={to => onChange({ ...period, to })}
          label={`${name} date to`}
          emptyText="Date To"
          title="Last day included (Asia/Manila)"
          disableFuture
          minDate={period.from || undefined}
          className={compact ? `${size} min-w-[105px]` : "h-10 w-[130px] text-xs"}
        />
        {clear && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={compact ? "h-8 w-8 p-0 shrink-0" : "h-10 w-10 shrink-0"}
            aria-label={clear.label}
            title={clear.title}
            onClick={clear.onClick}
          >
            <X className={compact ? "size-3.5" : "size-4"} />
          </Button>
        )}
      </div>
    </>
  )
}

function ConfidenceAccuracyTooltip({ active, payload }: {
  active?: boolean
  payload?: Array<{ payload?: RipenessConfidenceRow }>
}) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null
  return (
    <div className="border-border/50 bg-background grid min-w-[12.5rem] items-start gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs shadow-xl">
      <div className="font-medium text-foreground">{row.ripeness}</div>
      <div className="grid gap-1.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ backgroundColor: confidenceChartConfig.avgConfidence.color }} />
            <span>Avg Model Confidence</span>
          </div>
          <span className="font-mono font-medium tabular-nums text-foreground">
            {row.avgConfidence != null ? `${row.avgConfidence}% (${row.count})` : "No valid predictions"}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ backgroundColor: confidenceChartConfig.verifiedAccuracy.color }} />
            <span>Verified Accuracy</span>
          </div>
          <span className="font-mono font-medium tabular-nums text-foreground">
            {row.verifiedCount > 0 && row.verifiedAccuracy != null
              ? `${row.verifiedAccuracy}% (${row.verifiedCount} verified)`
              : "No verified scans"}
          </span>
        </div>
      </div>
    </div>
  )
}

function ChartCardHeader({ title, helpText, chart }: { title: string; helpText?: string; chart: ChartPeriod }) {
  return (
    <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm sm:text-base font-semibold" title={helpText}>{title}</CardTitle>
          {chart.loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <PeriodControls
            compact
            name={title}
            period={chart.period}
            onChange={chart.change}
            clear={chart.overridden ? { label: `Use page dates for ${title}`, title: "Use page dates", onClick: chart.reset } : undefined}
          />
          <Badge variant="outline" className="text-[10px] gap-1 shrink-0 py-0.5 h-8" title={chart.overridden ? "This chart has its own dates" : "Page dates"}>
            <CalendarDays className="w-3 h-3" />
            {chart.label}{chart.overridden ? " · this chart" : ""}
          </Badge>
        </div>
      </div>
    </CardHeader>
  )
}

/**
 * Whether a chart has nothing to draw. A chart on the page dates uses the server's count for the
 * whole selection; a chart with its own dates has only its own rows.
 */
function noData<T>(chart: { overridden: boolean; data: T[] | undefined }, pageCount: number, isZero: (row: T) => boolean) {
  if (!chart.overridden) return pageCount === 0 || !chart.data?.length
  return !chart.data?.length || chart.data.every(isZero)
}

/** Loading or error state of a chart with its own dates; null when the chart can render. */
function chartStatus(chart: ChartPeriod) {
  if (!chart.overridden || chart.data !== undefined) return null
  return (
    <div className="h-[240px] sm:h-[280px] w-full flex flex-col items-center justify-center gap-3 text-sm text-muted-foreground" role={chart.error ? "alert" : "status"}>
      {chart.error ? <>
        <p>Could not load this chart for {chart.label}: {chart.error}</p>
        <Button variant="outline" size="sm" onClick={chart.retry}>Retry</Button>
      </> : <Loader2 className="w-6 h-6 animate-spin text-primary" aria-label="Loading chart" />}
    </div>
  )
}

function AnalyticsContent() {
  const [period, setPeriod] = useState<AnalyticsPeriod>(DEFAULT_ANALYTICS_PERIOD)
  const [sourceFilter, setSourceFilter] = useState("all")
  const [cultivarFilter, setCultivarFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [availableSources, setAvailableSources] = useState<AnalyticsSummary["source_options"]>([])

  const filterParams = useMemo<AnalyticsFilterParams>(() => ({
    source_key: sourceFilter === "all" ? undefined : sourceFilter,
    cultivar: cultivarFilter === "all" ? undefined : cultivarFilter,
    inventory_status: statusFilter === "all" ? undefined : statusFilter,
  }), [sourceFilter, cultivarFilter, statusFilter])

  const fetchAnalytics = useCallback(async (signal: AbortSignal) => {
    const response = await api.analytics.summary({ ...filterParams, ...analyticsPeriodParams(period) }, signal)
    if (!signal.aborted) setAvailableSources(response.source_options)
    return response
  }, [filterParams, period])
  const resource = useDashboardResource(fetchAnalytics, { keepPreviousData: true })
  // A failed request is never presented as a successful empty dataset or old filter result.
  const summary = resource.error ? null : resource.data
  const loading = resource.loading

  useEffect(() => {
    if (!summary?.next_refresh_at) return
    const delay = Date.parse(summary.next_refresh_at) - Date.now()
    if (!Number.isFinite(delay) || delay < 0) return
    const timer = window.setTimeout(() => void resource.refresh(), delay + 100)
    return () => window.clearTimeout(timer)
  }, [summary?.next_refresh_at, resource.refresh])

  // ── Derived chart data ──────────────────────────────────────────────────

  const ripenessChart = useChartPeriod(summary?.ripeness_distribution, ripenessOf, period, filterParams)
  const cultivarChart = useChartPeriod(summary?.cultivar_counts, cultivarsOf, period, filterParams)
  const cultivarRipenessChart = useChartPeriod(summary?.cultivar_ripeness, cultivarRipenessOf, period, filterParams)
  const confidenceChart = useChartPeriod(summary?.ripeness_confidence, confidenceOf, period, filterParams)
  const sourceChart = useChartPeriod(summary?.scans_by_source, sourcesOf, period, filterParams)
  const hourlyChart = useChartPeriod(summary?.hourly_distribution, hoursOf, period, filterParams)

  const currentRipenessData = ripenessChart.data
  const pieChartConfig = useMemo(() => {
    if (!currentRipenessData) return {} as ChartConfig
    const cfg: ChartConfig = {}
    currentRipenessData.forEach((item) => {
      const key = item.name as keyof typeof ripenessChartConfig
      if (ripenessChartConfig[key]) {
        cfg[item.name] = ripenessChartConfig[key]
      }
    })
    cfg.value = { label: "Count" }
    return cfg
  }, [currentRipenessData])

  type OperatorRow = {
    id: string
    name: string
    scans: number
    avgConfidence: number | null
    confidenceSamples: number
  }

  const operatorPerformance: OperatorRow[] = (summary?.operator_performance ?? []).map(op => ({
    id: op.operator_id, name: op.name, scans: op.total_scans,
    avgConfidence: op.avg_confidence, confidenceSamples: op.confidence_sample_count,
  }))
  const percent = (value: number | null | undefined) => value == null ? "—" : `${value}%`
  const emptyChart = (message = "No classified scans in this selection.") => (
    <div className="h-[240px] sm:h-[280px] w-full flex items-center justify-center text-sm text-muted-foreground" role="status">{message}</div>
  )

  return (
    <div className="space-y-4 sm:space-y-6 pb-4 sm:pb-6">
      <AppPageHeader
        title="Analytics"
        description="Insights from your banana classification data"
        icon={BarChart3}
        action={
          <div className="flex flex-wrap gap-2 w-full sm:w-auto">
            <Select value={sourceFilter} onValueChange={setSourceFilter}>
              <SelectTrigger className="w-[160px] h-10" aria-label="Analytics source">
                <Package className="w-4 h-4 mr-2" />
                <SelectValue placeholder="All Sources" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Sources</SelectItem>
                {availableSources.map((src) => (
                  <SelectItem key={src.key} value={src.key}>
                    {src.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={cultivarFilter} onValueChange={setCultivarFilter}>
              <SelectTrigger className="w-[140px] h-10" aria-label="Analytics cultivar"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Cultivars</SelectItem>
                {Object.values(CultivarEnum).map(value => <SelectItem key={value} value={value}>{value}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[140px] h-10" aria-label="Analytics stock status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                {Object.values(InventoryStatusEnum).map(value => <SelectItem key={value} value={value}>{value}</SelectItem>)}
              </SelectContent>
            </Select>
            <PeriodControls
              name="Analytics"
              period={period}
              onChange={setPeriod}
              clear={hasCustomDates(period) ? { label: "Clear custom dates", title: "Clear dates", onClick: () => setPeriod({ ...period, from: "", to: "" }) } : undefined}
            />
          </div>
        }
      />

      {summary && (loading || resource.isPreviousData) && <div role="status" className="rounded-lg border p-3 text-sm text-muted-foreground">
        {resource.isPreviousData ? "Showing results for the previous selection." : "Showing the last successful results."} {loading ? <><Loader2 className="inline size-4 animate-spin" /> Updating analytics…</> : null}
      </div>}
      {!summary ? loading ? <ContentSkeleton label="Loading analytics…" chart /> : (
        <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground" role={resource.error ? "alert" : "status"}>
          {loading ? <Loader2 className="w-8 h-8 animate-spin text-primary" /> : <><BarChart3 className="w-12 h-12 mb-4" /><p>{resource.error || "Analytics unavailable."}</p><Button variant="outline" className="mt-4" onClick={() => void resource.refresh()}>Retry</Button></>}
        </div>
      ) : <>
      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 sm:gap-4">
        <AppStatsCard
          title="Total Scans"
          value={summary.total_scans}
          icon={TrendingUp}
          delay={50}
          description="Scans · Selected range"
          helpText={summary.metric_definitions.throughput}
        />
        <AppStatsCard
          title="Avg Confidence"
          value={percent(summary.avg_confidence)}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description={`Original AI confidence · ${summary.confidence_sample_count} valid results`}
          helpText={summary.metric_definitions.model_confidence}
        />
        <AppStatsCard
          title="Verified Accuracy"
          value={percent(summary.human_verified_accuracy)}
          icon={ShieldCheck}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={125}
          description={
            summary.verified_scan_count > 0
              ? `${summary.verified_correct_count} of ${summary.verified_scan_count} verified scans`
              : "No verified scans in range"
          }
          helpText={summary.metric_definitions.human_verified_accuracy}
        />
        <AppStatsCard
          title="Low Confidence"
          value={percent(summary.low_confidence_rate)}
          icon={AlertTriangle}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={150}
          description={`Model confidence · Below ${summary.confidence_threshold}%`}
          helpText={summary.metric_definitions.low_confidence}
        />
        <AppStatsCard
          title="At-Risk Scans"
          value={summary.at_risk_count}
          icon={Clock}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={200}
          description="Current stock · ≤2 days remaining"
          helpText={summary.metric_definitions.inventory_risk}
        />
      </div>

      {summary.total_scans === 0 && <p className="text-sm text-muted-foreground" role="status">No scans match this source and date range with the selected cultivar/status. The trend below uses the same filters for its separate 14-day period.</p>}
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Metric definitions</summary>
        <div className="space-y-2 mt-2">
          <p>Metrics use your selected filters and date range. Scan Trend always uses the last 14 days.</p>
          <p>Period: {summary.range_start ? manilaDate.format(new Date(summary.range_start)) : "All history"} – {manilaDate.format(new Date(summary.range_end))}. Updated: {manilaTime.format(new Date(summary.generated_at))} ({summary.timezone}).</p>
          {Object.entries(summary.metric_definitions).map(([key, definition]) => <p key={key}><strong className="font-medium">{metricLabels[key] ?? key.replaceAll("_", " ")}: </strong>{definition}</p>)}
          <p>Missing data: {summary.incomplete_count} incomplete classifications; {summary.risk_unknown_count} stock scans without a spoilage estimate.</p>
        </div>
      </details>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Ripeness Pie */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-5">
          <ChartCardHeader
            title="Ripeness Distribution"
            helpText={summary.metric_definitions.classifications}
            chart={ripenessChart}
          />
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {chartStatus(ripenessChart) ?? (noData(ripenessChart, summary.classification_count, d => d.value === 0) ? emptyChart() : (
            <ChartContainer config={pieChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <PieChart>
                <Pie
                  data={ripenessChart.data}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={4}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                >
                  {(ripenessChart.data ?? []).map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={ripenessChartConfig[entry.name as keyof typeof ripenessChartConfig]?.color ?? "#888"}
                    />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent nameKey="name" />} />
                <ChartLegend content={<ChartLegendContent />} />
              </PieChart>
            </ChartContainer>
            ))}
          </CardContent>
        </Card>

        {/* Cultivar Bar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-6">
          <ChartCardHeader
            title="Cultivar Counts"
            helpText={summary.metric_definitions.classifications}
            chart={cultivarChart}
          />
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {chartStatus(cultivarChart) ?? (noData(cultivarChart, summary.classification_count, d => d.count === 0) ? emptyChart() : (
            <ChartContainer config={cultivarChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={cultivarChart.data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {(cultivarChart.data ?? []).map((entry) => (
                    <Cell key={entry.name} fill={CULTIVAR_COLORS[entry.name] ?? "#eab308"} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
            ))}
          </CardContent>
        </Card>

        {/* Ripeness by Cultivar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-7">
          <ChartCardHeader
            title="Ripeness by Cultivar"
            helpText={summary.metric_definitions.classifications}
            chart={cultivarRipenessChart}
          />
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {chartStatus(cultivarRipenessChart) ?? (noData(cultivarRipenessChart, summary.classification_count, d => d.Unripe === 0 && d["Semi Ripe"] === 0 && d.Ripe === 0 && d.Overripe === 0) ? emptyChart() : (
            <ChartContainer config={cultivarRipenessChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={cultivarRipenessChart.data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey={RipenessEnum.UNRIPE} stackId="a" fill={cultivarRipenessChartConfig[RipenessEnum.UNRIPE].color} radius={[0, 0, 0, 0]} />
                <Bar dataKey={RipenessEnum.SEMI_RIPE} stackId="a" fill={cultivarRipenessChartConfig[RipenessEnum.SEMI_RIPE].color} radius={[0, 0, 0, 0]} />
                <Bar dataKey={RipenessEnum.RIPE} stackId="a" fill={cultivarRipenessChartConfig[RipenessEnum.RIPE].color} radius={[0, 0, 0, 0]} />
                <Bar dataKey={RipenessEnum.OVERRIPE} stackId="a" fill={cultivarRipenessChartConfig[RipenessEnum.OVERRIPE].color} radius={[8, 8, 0, 0]} />
              </BarChart>
            </ChartContainer>
            ))}
          </CardContent>
        </Card>

        {/* Confidence vs. Verified Accuracy */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8">
          <ChartCardHeader
            title="Confidence vs. Verified Accuracy"
            helpText={summary.metric_definitions.confidence_by_ripeness}
            chart={confidenceChart}
          />
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {chartStatus(confidenceChart) ?? (noData(confidenceChart, summary.confidence_sample_count + summary.verified_scan_count, d => d.count === 0 && d.verifiedCount === 0) ? emptyChart("No valid confidence or verified results in this selection.") : (
            <ChartContainer config={confidenceChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={confidenceChart.data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ripeness" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
                <ChartTooltip content={<ConfidenceAccuracyTooltip />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="avgConfidence" fill="var(--color-avgConfidence)" radius={[6, 6, 0, 0]} name="Avg Model Confidence (%)" />
                <Bar dataKey="verifiedAccuracy" fill="var(--color-verifiedAccuracy)" radius={[6, 6, 0, 0]} name="Verified Accuracy (%)" />
              </BarChart>
            </ChartContainer>
            ))}
          </CardContent>
        </Card>

        {/* Scans by Source */}
        {(sourceChart.overridden || (sourceChart.data?.length ?? 0) > 0) && (
          <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8-5 lg:col-span-2">
            <ChartCardHeader
              title="Scans by Source"
              helpText={summary.metric_definitions.sources}
              chart={sourceChart}
            />
            <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
              {chartStatus(sourceChart) ?? (!sourceChart.data?.length ? emptyChart("No scans in this selection.") : (
              <ChartContainer config={sourceChartConfig} className="h-[240px] sm:h-[280px] w-full">
                <BarChart data={sourceChart.data}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-25} textAnchor="end" height={60} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="count" fill="var(--color-count)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ChartContainer>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Scan Trend */}
      <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-9">
        <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.trend}>Scan Trend (Last 14 Days)</CardTitle>
              <p className="text-xs text-muted-foreground">{summary.trend_start} – {summary.trend_end} · Uses source, cultivar and stock-status filters, regardless of the date range.</p>
            </div>
            <Badge variant="outline" className="text-[10px] gap-1 shrink-0 py-0.5 h-7">
              <CalendarDays className="w-3 h-3" />
              {summary.trend_start} – {summary.trend_end}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
          <ChartContainer config={scanTrendChartConfig} className="h-[240px] sm:h-[280px] w-full">
            <LineChart data={summary.scan_trend || []}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line
                type="monotone"
                dataKey="count"
                stroke="var(--color-count)"
                strokeWidth={2.5}
                dot={{ fill: "var(--color-count)", strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ChartContainer>
        </CardContent>
      </Card>

      {/* Operator Performance Table */}
      {operatorPerformance.length > 0 && (
        <div className="space-y-3 animate-fade-in stagger-10">
          <div className="flex items-center gap-2 px-1">
            <Users className="w-4 h-4" />
            <h3 className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.operators}>Operator Performance Table</h3>
          </div>
          <AppDataTable
            data={operatorPerformance}
            rowKey={(op) => op.id}
            columns={[
              {
                header: "#",
                className: "w-12",
                cell: (_op, idx) => (
                  <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
                    {idx + 1}
                  </div>
                ),
              },
              {
                header: "Operator",
                sortable: true,
                sortKey: "name",
                cell: (op) => (
                  <div className="flex items-center gap-3">
                    <Avatar className="w-8 h-8">
                      <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                        {op.name.split(' ').map(n => n[0]).join('').toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="font-medium text-sm">{op.name}</span>
                  </div>
                ),
              },
              {
                header: "Total Scans",
                sortable: true,
                sortKey: "scans",
                cell: (op) => <span className="text-sm">{op.scans}</span>,
              },
              {
                header: "Avg Confidence",
                sortable: true,
                sortKey: "avgConfidence",
                className: "text-right",
                cell: (op) => (
                  <Badge title={`${op.confidenceSamples} valid model-confidence results`} variant="outline" className={`${op.avgConfidence !== null && op.avgConfidence >= summary.confidence_threshold ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'}`}>
                    {percent(op.avgConfidence)}
                  </Badge>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* Hourly Distribution */}
      {(hourlyChart.overridden || (hourlyChart.data?.length ?? 0) > 0) && (
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-11">
          <ChartCardHeader
            title="Peak Scanning Hours"
            helpText={summary.metric_definitions.hourly}
            chart={hourlyChart}
          />
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {chartStatus(hourlyChart) ?? (!hourlyChart.data?.length ? emptyChart("No scans in this selection.") : (
            <ChartContainer config={hourlyChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={hourlyChart.data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ChartContainer>
            ))}
          </CardContent>
        </Card>
      )}
      </>}
    </div>
  )
}
