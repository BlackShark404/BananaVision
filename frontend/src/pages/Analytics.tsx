import { useEffect, useMemo, useState, useCallback } from "react"
import { useAuth } from "@/context/AuthContext"
import { useDashboardResource } from "@/hooks/useDashboardResource"
import type { AnalyticsRange, AnalyticsSummary } from "@/types/analytics"
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
import { BarChart3, TrendingUp, Target, AlertTriangle, Users, Calendar, Package, Clock, Loader2 } from "lucide-react"
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
  ComposedChart,
} from "recharts"

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
  count: { label: "Count", color: "#eab308" },
  avgConfidence: { label: "Avg Confidence %", color: "#22c55e" },
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

type DateRange = AnalyticsRange

const CULTIVAR_COLORS: Record<string, string> = {
  [CultivarEnum.LAKATAN]: "#f59e0b",
  [CultivarEnum.LATUNDAN]: "#fbbf24",
  [CultivarEnum.CARDABA]: "#d97706",
}

export default function Analytics() {
  const { user } = useAuth()
  return user ? <AnalyticsContent key={`${user.id}:${user.role}`} /> : null
}

function AnalyticsContent() {
  const [dateRange, setDateRange] = useState<DateRange>("week")
  const [sourceFilter, setSourceFilter] = useState("all")
  const [cultivarFilter, setCultivarFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [availableSources, setAvailableSources] = useState<AnalyticsSummary["source_options"]>([])
  const fetchAnalytics = useCallback(async (signal: AbortSignal) => {
    const response = await api.analytics.summary({ range: dateRange, source_key: sourceFilter === "all" ? undefined : sourceFilter,
      cultivar: cultivarFilter === "all" ? undefined : cultivarFilter,
      inventory_status: statusFilter === "all" ? undefined : statusFilter }, signal)
    if (!signal.aborted) setAvailableSources(response.source_options)
    return response
  }, [dateRange, sourceFilter, cultivarFilter, statusFilter])
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

  const pieChartConfig = useMemo(() => {
    if (!summary) return {} as ChartConfig
    const cfg: ChartConfig = {}
    summary.ripeness_distribution?.forEach((item) => {
      const key = item.name as keyof typeof ripenessChartConfig
      if (ripenessChartConfig[key]) {
        cfg[item.name] = ripenessChartConfig[key]
      }
    })
    cfg.value = { label: "Count" }
    return cfg
  }, [summary])

  const operatorPerformance = (summary?.operator_performance ?? []).map(op => ({
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
            <Select value={dateRange} onValueChange={(v) => setDateRange(v as DateRange)}>
              <SelectTrigger className="w-[140px] h-10" aria-label="Analytics date range">
                <Calendar className="w-4 h-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="today">Today</SelectItem>
                <SelectItem value="week">Last 7 Days</SelectItem>
                <SelectItem value="month">Last 30 Days</SelectItem>
                <SelectItem value="all">All Time</SelectItem>
              </SelectContent>
            </Select>
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
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          title="Total Scans"
          value={summary.total_scans}
          icon={TrendingUp}
          delay={50}
          description="Throughput · Selected range"
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
          <p>Business timezone: {summary.timezone}. Refreshed: {summary.generated_at}. Date window: {summary.range_start ?? "All history"} through {summary.range_end}.</p>
          {Object.entries(summary.metric_definitions).map(([key, definition]) => <p key={key}>{definition}</p>)}
          <p>{summary.incomplete_count} scans have incomplete classifications. {summary.risk_unknown_count} current-stock scans have no usable spoilage estimate.</p>
          <p>Human-verified model accuracy: unavailable. No recorded ground-truth verification is available to calculate accuracy.</p>
        </div>
      </details>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Ripeness Pie */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-5">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.classifications}>Ripeness Distribution</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {summary.classification_count === 0 ? emptyChart() : (
            <ChartContainer config={pieChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <PieChart>
                <Pie
                  data={summary.ripeness_distribution || []}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={4}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                >
                  {(summary.ripeness_distribution || []).map((entry) => (
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
            )}
          </CardContent>
        </Card>

        {/* Cultivar Bar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-6">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.classifications}>Cultivar Counts</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {summary.classification_count === 0 ? emptyChart() : (
            <ChartContainer config={cultivarChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={summary.cultivar_counts || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {(summary.cultivar_counts || []).map((entry) => (
                    <Cell key={entry.name} fill={CULTIVAR_COLORS[entry.name] ?? "#eab308"} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
            )}
          </CardContent>
        </Card>

        {/* Ripeness by Cultivar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-7">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.classifications}>Ripeness by Cultivar</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {summary.classification_count === 0 ? emptyChart() : (
            <ChartContainer config={cultivarRipenessChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={summary.cultivar_ripeness || []}>
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
            )}
          </CardContent>
        </Card>

        {/* Confidence by Ripeness */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.confidence_by_ripeness}>Confidence by Ripeness</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            {summary.confidence_sample_count === 0 ? emptyChart("No valid model-confidence results in this selection.") : (
            <ChartContainer config={confidenceChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <ComposedChart data={summary.ripeness_confidence || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ripeness" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar yAxisId="left" dataKey="count" fill="var(--color-count)" radius={[8, 8, 0, 0]} name="Count" />
                <Line yAxisId="right" type="monotone" dataKey="avgConfidence" stroke="var(--color-avgConfidence)" strokeWidth={2.5} name="Avg Confidence %" />
              </ComposedChart>
            </ChartContainer>
            )}
          </CardContent>
        </Card>

        {/* Scans by Source */}
        {summary.scans_by_source?.length > 0 && (
          <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8-5 lg:col-span-2">
            <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.sources}>Scans by Source</CardTitle>
            </CardHeader>
            <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
              <ChartContainer config={sourceChartConfig} className="h-[240px] sm:h-[280px] w-full">
                <BarChart data={summary.scans_by_source || []}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-25} textAnchor="end" height={60} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="count" fill="var(--color-count)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Scan Trend */}
      <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-9">
        <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
          <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.trend}>Scan Trend (Last 14 Days)</CardTitle>
          <p className="text-xs text-muted-foreground">Fixed period: {summary.trend_start} – {summary.trend_end}. Uses the selected source, independent of the date-range filter.</p>
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
                header: "Scans",
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
      {summary.hourly_distribution?.length > 0 && (
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-11">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold" title={summary.metric_definitions.hourly}>Peak Scanning Hours</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={hourlyChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={summary.hourly_distribution || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      )}
      </>}
    </div>
  )
}
