import { useMemo, useState } from "react"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import { useAdmin } from "@/context/AdminContext"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppPageHeader } from "@/components/AppPageHeader"
import { RIPENESS_LEVELS, CULTIVARS, CultivarEnum, RipenessEnum, RoleEnum } from "@/types"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { getAnalyticsData } from "@/lib/utils"
import { parseSpoilageAvg } from "@/lib/utils"
import { BarChart3, TrendingUp, Target, AlertTriangle, Users, Calendar, Package, Clock } from "lucide-react"
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

type DateRange = "today" | "week" | "month" | "all"

const CULTIVAR_COLORS: Record<string, string> = {
  [CultivarEnum.LAKATAN]: "#f59e0b",
  [CultivarEnum.LATUNDAN]: "#fbbf24",
  [CultivarEnum.CARDABA]: "#d97706",
}

export default function Analytics() {
  const { user } = useAuth()
  const { scans } = useScans()
  const { config } = useAdmin()
  const [dateRange, setDateRange] = useState<DateRange>("week")
  const [sourceFilter, setSourceFilter] = useState<string>("all")

  const filteredScans = useMemo(() => {
    const roleFilteredScans = user?.role === RoleEnum.OPERATOR 
      ? scans.filter(s => s.operator === user.fullName)
      : scans

    const now = new Date()
    const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    
    let filtered = roleFilteredScans
    
    // Filter by date range
    switch (dateRange) {
      case "today":
        filtered = filtered.filter(s => new Date(s.dateTime) >= startOfDay)
        break
      case "week": {
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
        filtered = filtered.filter(s => new Date(s.dateTime) >= weekAgo)
        break
      }
      case "month": {
        const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
        filtered = filtered.filter(s => new Date(s.dateTime) >= monthAgo)
        break
      }
    }
    
    // Filter by source
    if (sourceFilter !== "all") {
      filtered = filtered.filter(s => s.source === sourceFilter)
    }
    
    return filtered
  }, [scans, dateRange, sourceFilter, user])

  const data = useMemo(() => getAnalyticsData(filteredScans), [filteredScans])

  const advancedMetrics = useMemo(() => {
    const lowConfidenceCount = filteredScans.filter(s => s.confidence < config.confidenceThreshold).length
    const lowConfidenceRate = filteredScans.length ? ((lowConfidenceCount / filteredScans.length) * 100).toFixed(1) : 0
    
    const spoilingSoon = filteredScans.filter(s => parseSpoilageAvg(s.spoilageDays) <= 2).length

    const operatorStats = filteredScans.reduce((acc, scan) => {
      if (!acc[scan.operator]) {
        acc[scan.operator] = { count: 0, totalConfidence: 0 }
      }
      acc[scan.operator].count++
      acc[scan.operator].totalConfidence += scan.confidence
      return acc
    }, {} as Record<string, { count: number; totalConfidence: number }>)

    const operatorPerformance = Object.entries(operatorStats)
      .map(([name, stats]) => ({
        name,
        scans: stats.count,
        avgConfidence: parseFloat((stats.totalConfidence / stats.count).toFixed(1))
      }))
      .sort((a, b) => b.scans - a.scans)

    const ripenessConfidence = RIPENESS_LEVELS.map(ripeness => {
      const ripeScans = filteredScans.filter(s => s.ripeness === ripeness)
      const avgConf = ripeScans.length 
        ? ripeScans.reduce((sum, s) => sum + s.confidence, 0) / ripeScans.length
        : 0
      return {
        ripeness,
        avgConfidence: parseFloat(avgConf.toFixed(1)),
        count: ripeScans.length
      }
    })

    const cultivarRipeness = data.cultivarCounts.map(c => {
      const cultivarScans = filteredScans.filter(s => s.cultivar === c.name)
      const unripe = cultivarScans.filter(s => s.ripeness === RipenessEnum.UNRIPE).length
      const semiRipe = cultivarScans.filter(s => s.ripeness === RipenessEnum.SEMI_RIPE).length
      const ripe = cultivarScans.filter(s => s.ripeness === RipenessEnum.RIPE).length
      const overripe = cultivarScans.filter(s => s.ripeness === RipenessEnum.OVERRIPE).length
      return { name: c.name, [RipenessEnum.UNRIPE]: unripe, [RipenessEnum.SEMI_RIPE]: semiRipe, [RipenessEnum.RIPE]: ripe, [RipenessEnum.OVERRIPE]: overripe }
    })

    const hourlyDistribution = Array.from({ length: 24 }, (_, hour) => {
      const count = filteredScans.filter(s => new Date(s.dateTime).getHours() === hour).length
      const period = hour < 12 ? "AM" : "PM"
      const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour
      return { hour: `${displayHour} ${period}`, count }
    }).filter(h => h.count > 0)

    const scansBySource = Array.from(
      filteredScans.reduce((acc, scan) => {
        const src = scan.source || "Unknown"
        acc.set(src, (acc.get(src) || 0) + 1)
        return acc
      }, new Map<string, number>())
    ).map(([name, count]) => ({ name, count }))
     .sort((a, b) => b.count - a.count)

    return {
      lowConfidenceCount,
      lowConfidenceRate,
      spoilingSoon,
      operatorPerformance,
      ripenessConfidence,
      cultivarRipeness,
      hourlyDistribution,
      scansBySource
    }
  }, [filteredScans, config.confidenceThreshold, data.cultivarCounts])

  // Build a dynamic pie chart config from the actual distribution data
  const pieChartConfig = useMemo(() => {
    const cfg: ChartConfig = {}
    data.ripenessDistribution.forEach((item) => {
      const key = item.name as keyof typeof ripenessChartConfig
      if (ripenessChartConfig[key]) {
        cfg[item.name] = ripenessChartConfig[key]
      }
    })
    cfg.value = { label: "Count" }
    return cfg
  }, [data.ripenessDistribution])

  return (
    <div className="space-y-4 sm:space-y-6 pb-4 sm:pb-6">
      <AppPageHeader
        title="Analytics"
        description="Insights from your banana classification data"
        icon={BarChart3}
        action={
          <div className="flex gap-2 w-full sm:w-auto">
            <Select value={sourceFilter} onValueChange={setSourceFilter}>
              <SelectTrigger className="w-[160px] h-10">
                <Package className="w-4 h-4 mr-2" />
                <SelectValue placeholder="All Sources" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Sources</SelectItem>
                {Array.from(new Set(scans.map(s => s.source).filter(Boolean))).map((src) => (
                  <SelectItem key={src as string} value={src as string}>
                    {src}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={dateRange} onValueChange={(v) => setDateRange(v as DateRange)}>
              <SelectTrigger className="w-[140px] h-10">
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

      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          title="Total Scans"
          value={data.totalScans}
          icon={TrendingUp}
          delay={50}
          description={sourceFilter !== "all" ? "In selected source" : "All sources"}
        />
        <AppStatsCard
          title="Avg Confidence"
          value={`${data.avgConfidence}%`}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Detection accuracy"
        />
        <AppStatsCard
          title="Low Confidence"
          value={`${advancedMetrics.lowConfidenceRate}%`}
          icon={AlertTriangle}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={150}
          description="Below threshold"
        />
        <AppStatsCard
          title="At-Risk Scans"
          value={advancedMetrics.spoilingSoon}
          icon={Clock}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={200}
          description="Spoiling in ≤2 days"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Ripeness Pie */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-5">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold">Ripeness Distribution</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={pieChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <PieChart>
                <Pie
                  data={data.ripenessDistribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={4}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                >
                  {data.ripenessDistribution.map((entry) => (
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
          </CardContent>
        </Card>

        {/* Cultivar Bar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-6">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold">Cultivar Counts</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={cultivarChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={data.cultivarCounts}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {data.cultivarCounts.map((entry) => (
                    <Cell key={entry.name} fill={CULTIVAR_COLORS[entry.name] ?? "#eab308"} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        {/* Ripeness by Cultivar */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-7">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold">Ripeness by Cultivar</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={cultivarRipenessChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={advancedMetrics.cultivarRipeness}>
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
          </CardContent>
        </Card>

        {/* Confidence by Ripeness */}
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold">Confidence by Ripeness</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={confidenceChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <ComposedChart data={advancedMetrics.ripenessConfidence}>
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
          </CardContent>
        </Card>

        {/* Scans by Source */}
        {advancedMetrics.scansBySource.length > 0 && (
          <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-8-5 lg:col-span-2">
            <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-sm sm:text-base font-semibold">Scans by Source</CardTitle>
            </CardHeader>
            <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
              <ChartContainer config={sourceChartConfig} className="h-[240px] sm:h-[280px] w-full">
                <BarChart data={advancedMetrics.scansBySource}>
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
          <CardTitle className="text-sm sm:text-base font-semibold">Scan Trend (Last 14 Days)</CardTitle>
        </CardHeader>
        <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
          <ChartContainer config={scanTrendChartConfig} className="h-[240px] sm:h-[280px] w-full">
            <LineChart data={data.scanTrend}>
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

      {/* Operator Performance */}
      {advancedMetrics.operatorPerformance.length > 0 && (
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-10">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold flex items-center gap-2">
              <Users className="w-4 h-4" />
              Operator Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pb-4 sm:pb-6">
            <div className="space-y-3">
              {advancedMetrics.operatorPerformance.map((op, idx) => (
                <div key={op.name} className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
                      #{idx + 1}
                    </div>
                    <Avatar className="w-9 h-9">
                      <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                        {op.name.split(' ').map(n => n[0]).join('').toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="font-medium text-sm">{op.name}</p>
                      <p className="text-xs text-muted-foreground">{op.scans} scans</p>
                    </div>
                  </div>
                  <Badge variant="outline" className={`${op.avgConfidence >= config.confidenceThreshold ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'}`}>
                    {op.avgConfidence}% avg
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hourly Distribution */}
      {advancedMetrics.hourlyDistribution.length > 0 && (
        <Card className="rounded-xl sm:rounded-2xl animate-fade-in stagger-11">
          <CardHeader className="pb-2 px-4 sm:px-6 pt-4 sm:pt-6">
            <CardTitle className="text-sm sm:text-base font-semibold">Peak Scanning Hours</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-6 pb-4 sm:pb-6">
            <ChartContainer config={hourlyChartConfig} className="h-[240px] sm:h-[280px] w-full">
              <BarChart data={advancedMetrics.hourlyDistribution}>
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
    </div>
  )
}
