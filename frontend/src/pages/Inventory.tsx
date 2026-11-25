import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
import { remainingStockDays, shelfLifeLabel } from "@/lib/inventoryRisk"
import { effectiveRipeness, liveRipeness } from "@/lib/ripenessProjection"
import { buildScanLogsUrl } from "@/lib/scanLogFilters"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ContentSkeleton } from "@/components/LoadingState"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Progress } from "@/components/ui/progress"
import { Package, AlertTriangle, TrendingDown, CheckCircle, Clock, Banana, ExternalLink } from "lucide-react"
import { InventoryStatusEnum, RipenessEnum, CultivarEnum, type ScanResult } from "@/types"
import { estimateText, fingerCountIsEstimate, fingerCountText } from "@/lib/estimates"

/** A group's finger total, marked as an estimate while any count in it is the AI value. */
function fingersOf(list: ScanResult[]): string {
  return fingerCountText(list.reduce((sum, s) => sum + s.fingerCount, 0), list.some(fingerCountIsEstimate))
}

export default function Inventory() {
  const navigate = useNavigate()
  const { scans, scansReady, scansLoading, scansError, refreshScans } = useScans()
  const { intakesReady, intakesLoading, intakesError, intakesStale, refreshIntakes } = useInventory()
  const [sourceFilter, setSourceFilter] = useState<string>("all")
  const scanLogsLink = (filters: Parameters<typeof buildScanLogsUrl>[0]) =>
    buildScanLogsUrl({ ...(sourceFilter !== "all" ? { source: sourceFilter } : {}), ...filters })
  const [asOf, setAsOf] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setAsOf(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const inventory = useMemo(() => {
    let activeScans = scans

    if (sourceFilter !== "all") {
      activeScans = activeScans.filter(s => s.source === sourceFilter)
    }

    const inStock = activeScans.filter(s => s.inventoryEligible === true && s.inventoryStatus === InventoryStatusEnum.IN_STOCK)
    const unknownRisk = inStock.filter(s => remainingStockDays(s, asOf) === null).length

    // Group in-stock hands by projected current ripeness (anchored to scanned stage on Day 0).
    const ripenessOf = (s: ScanResult) => effectiveRipeness(s, asOf)
    const isProgressed = (s: ScanResult) => liveRipeness(s.ripenessProjection, asOf, s.inventoryStatus)?.progressed === true
    const unripe = inStock.filter(s => ripenessOf(s) === RipenessEnum.UNRIPE)
    const ripe = inStock.filter(s => ripenessOf(s) === RipenessEnum.RIPE)
    const overripe = inStock.filter(s => ripenessOf(s) === RipenessEnum.OVERRIPE)
    const semiRipe = inStock.filter(s => ripenessOf(s) === RipenessEnum.SEMI_RIPE)
    const ripenessProgressed = {
      [RipenessEnum.UNRIPE]: unripe.some(isProgressed),
      [RipenessEnum.SEMI_RIPE]: semiRipe.some(isProgressed),
      [RipenessEnum.RIPE]: ripe.some(isProgressed),
      [RipenessEnum.OVERRIPE]: overripe.some(isProgressed),
    }

    // Calculate total hands and fingers
    const totalHands = inStock.length
    const totalFingers = inStock.reduce((sum, s) => sum + s.fingerCount, 0)
    // A total reads as an estimate while any scan in it still has the AI count.
    const fingersEstimated = inStock.some(fingerCountIsEstimate)

    // Spoilage alerts (will spoil in 2 days or less) - Grouped by intake, cultivar, and current ripeness
    const spoilageAlertsMap = new Map<string, { id: string; intakeId: string; source: string; cultivar: string; ripeness: string; ripenessProgressed: boolean; spoilageDays: string; daysNum: number; count: number; fingers: number; fingersEstimated: boolean; oldestScanDate: Date }>()

    inStock.forEach(s => {
      const daysNum = remainingStockDays(s, asOf)
      if (daysNum === null || daysNum > 2) return
      const currentRipeness = ripenessOf(s)
      const progressed = isProgressed(s)

      const key = `${s.intakeId ?? s.source ?? s.id}-${s.cultivar}-${currentRipeness}`
      const existing = spoilageAlertsMap.get(key)
      if (existing) {
        existing.count += 1
        existing.fingers += s.fingerCount
        existing.fingersEstimated ||= fingerCountIsEstimate(s)
        existing.ripenessProgressed ||= progressed
        const scanDate = new Date(s.dateTime)
        if (scanDate < existing.oldestScanDate) existing.oldestScanDate = scanDate
        if (daysNum < existing.daysNum) {
          existing.daysNum = daysNum
          existing.spoilageDays = shelfLifeLabel(daysNum)
        }
      } else {
        spoilageAlertsMap.set(key, {
          id: key,
          intakeId: s.intakeId || "unknown",
          source: s.source || "Unknown Supplier",
          cultivar: s.cultivar,
          ripeness: currentRipeness,
          ripenessProgressed: progressed,
          spoilageDays: shelfLifeLabel(daysNum),
          daysNum,
          count: 1,
          fingers: s.fingerCount,
          fingersEstimated: fingerCountIsEstimate(s),
          oldestScanDate: new Date(s.dateTime)
        })
      }
    })

    const spoilingSoon = Array.from(spoilageAlertsMap.values()).sort((a, b) => a.daysNum - b.daysNum)

    // Group by cultivar
    const byCultivar = {
      [CultivarEnum.LAKATAN]: inStock.filter(s => s.cultivar === CultivarEnum.LAKATAN).length,
      [CultivarEnum.LATUNDAN]: inStock.filter(s => s.cultivar === CultivarEnum.LATUNDAN).length,
      [CultivarEnum.CARDABA]: inStock.filter(s => s.cultivar === CultivarEnum.CARDABA).length,
    }

    // FIFO recommendations (oldest first, grouped by Intake)
    const intakeGroups = new Map<string, { intakeId: string, source: string, date: Date, hands: number, fingers: number, fingersEstimated: boolean, earliestSpoilage: number, spoilageDays: string }>()

    inStock.forEach(s => {
      const groupId = s.intakeId ?? `unlinked:${s.id}`
      const existing = intakeGroups.get(groupId)
      const scanDate = new Date(s.dateTime)
      const spoilageNum = remainingStockDays(s, asOf) ?? Number.POSITIVE_INFINITY

      if (existing) {
        existing.hands += 1
        existing.fingers += s.fingerCount
        existing.fingersEstimated ||= fingerCountIsEstimate(s)
        if (scanDate < existing.date) existing.date = scanDate
        if (spoilageNum < existing.earliestSpoilage) {
          existing.earliestSpoilage = spoilageNum
          existing.spoilageDays = shelfLifeLabel(spoilageNum)
        }
      } else {
        intakeGroups.set(groupId, {
          intakeId: groupId,
          source: s.source || "Unknown Supplier",
          date: scanDate,
          hands: 1,
          fingers: s.fingerCount,
          fingersEstimated: fingerCountIsEstimate(s),
          earliestSpoilage: spoilageNum,
          spoilageDays: shelfLifeLabel(Number.isFinite(spoilageNum) ? spoilageNum : null)
        })
      }
    })

    const fifoList = Array.from(intakeGroups.values())
      .sort((a, b) => a.date.getTime() - b.date.getTime())
      .slice(0, 10)

    // Status summary
    const sold = activeScans.filter(s => s.inventoryStatus === InventoryStatusEnum.SOLD).length
    const forProcessing = activeScans.filter(s => s.inventoryStatus === InventoryStatusEnum.FOR_PROCESSING).length
    const spoiled = activeScans.filter(s => s.inventoryStatus === InventoryStatusEnum.SPOILED).length

    return {
      totalHands,
      totalFingers,
      fingersEstimated,
      unripe,
      ripe,
      overripe,
      semiRipe,
      ripenessProgressed,
      spoilingSoon,
      byCultivar,
      fifoList,
      sold,
      forProcessing,
      spoiled,
      unknownRisk,
    }
  }, [scans, sourceFilter, asOf])

  const isLoading = scansLoading || intakesLoading
  const loadError = scansError || (!intakesLoading && intakesError && !intakesStale ? intakesError : null)

  if (!scansReady || !intakesReady) {
    return (
      <div className="space-y-4 sm:space-y-6">
        <AppPageHeader title="Inventory" description="Track stock levels and manage banana inventory" icon={Package} />
        {isLoading ? <ContentSkeleton label="Loading inventory…" chart /> : <Card className="rounded-xl sm:rounded-2xl">
          <CardContent className="p-4 sm:p-6" role={loadError ? "alert" : "status"}>
            <p className="text-sm text-muted-foreground">
              {loadError ? `${scansError ? "Complete scan history is unavailable." : "Intake data is unavailable."} Refresh to view stock and FIFO recommendations.` : intakesLoading ? "Loading intake data…" : "Loading complete scan history…"}
            </p>
            {loadError && <Button variant="outline" className="mt-3" onClick={() => { if (scansError) { void refreshScans() } else { refreshIntakes() } }}>Retry</Button>}
          </CardContent>
        </Card>}
      </div>
    )
  }


  return (
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Inventory"
        description="Track stock levels and manage banana inventory"
        icon={Package}
        action={
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-45 h-10">
              <Package className="w-4 h-4 mr-2" />
              <SelectValue placeholder="All Sources" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              {Array.from(new Set(scans.map(s => s.source).filter(Boolean))).sort().map((src) => (
                <SelectItem key={src} value={src as string}>{src}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      {isLoading && <p role="status" className="text-sm text-muted-foreground">Refreshing inventory… Showing the last successful snapshot.</p>}
      {scansError && <div role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm">Scan history refresh failed. Showing the last successful snapshot. <Button variant="link" onClick={() => void refreshScans()}>Retry scan history</Button></div>}
      {intakesStale && <Card className="rounded-xl sm:rounded-2xl">
        <CardContent className="p-4 sm:p-6" role="alert">
          <p className="text-sm text-muted-foreground">Intake data is stale. The last successful intake snapshot is retained.</p>
          <Button variant="outline" className="mt-3" onClick={refreshIntakes}>Retry intake data</Button>
        </CardContent>
      </Card>}

      {/* Overview Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          title="Total Hands"
          value={inventory.totalHands}
          icon={Package}
          delay={50}
          description="In stock"
          onClick={() => navigate(scanLogsLink({ status: "In Stock", stock: "eligible" }))}
          helpText="View all in-stock hands in Scan Logs"
        />
        <AppStatsCard
          title={inventory.fingersEstimated ? "Est. Total Fingers" : "Total Fingers"}
          value={inventory.totalFingers}
          icon={Banana}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={100}
          description={inventory.totalHands === 0 ? "No stock" : inventory.fingersEstimated ? "Estimated count" : "Corrected counts"}
          onClick={() => navigate(scanLogsLink({ status: "In Stock", stock: "eligible" }))}
          helpText="View all in-stock bananas in Scan Logs"
        />
        <AppStatsCard
          title="Spoiling Soon"
          value={inventory.spoilingSoon.length}
          icon={AlertTriangle}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={150}
          description="≤2 days left"
          onClick={() => navigate(scanLogsLink({ attention: "at-risk", stock: "eligible" }))}
          helpText="View scans with high spoilage risk"
        />
        <AppStatsCard
          title="Sold"
          value={inventory.sold}
          icon={CheckCircle}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={200}
          description="All time"
          onClick={() => navigate(scanLogsLink({ status: "Sold" }))}
          helpText="View sold banana logs"
        />
      </div>

      {/* Ripeness Distribution */}
      <Card className="rounded-xl sm:rounded-2xl">
        <CardContent className="p-4 sm:p-6">
          <div className="flex items-center justify-between gap-2 mb-4">
            <h3 className="text-base font-semibold">Stock by Ripeness</h3>
            {Object.values(inventory.ripenessProgressed).some(Boolean) && (
              <span className="text-xs text-muted-foreground">Includes Est. time-progressed stages</span>
            )}
          </div>
          <div className="space-y-4">
            <div
              className="p-2 -mx-2 rounded-lg hover:bg-muted/40 transition-colors cursor-pointer group/ripeness"
              onClick={() => navigate(scanLogsLink({ status: "In Stock", ripeness: RipenessEnum.UNRIPE, ripeness_scope: "current", stock: "eligible" }))}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-500" />
                  <span className="text-sm font-medium group-hover/ripeness:text-primary transition-colors flex items-center gap-1.5">
                    Unripe
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover/ripeness:opacity-100 transition-opacity text-muted-foreground" />
                  </span>
                </div>
                <span className="text-sm font-bold">{inventory.unripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.unripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {fingersOf(inventory.unripe)} • Store in controlled temperature
              </p>
            </div>

            <div
              className="p-2 -mx-2 rounded-lg hover:bg-muted/40 transition-colors cursor-pointer group/ripeness"
              onClick={() => navigate(scanLogsLink({ status: "In Stock", ripeness: RipenessEnum.SEMI_RIPE, ripeness_scope: "current", stock: "eligible" }))}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-violet-500" />
                  <span className="text-sm font-medium group-hover/ripeness:text-primary transition-colors flex items-center gap-1.5">
                    {inventory.ripenessProgressed[RipenessEnum.SEMI_RIPE] ? "Est. Semi Ripe" : "Semi Ripe"}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover/ripeness:opacity-100 transition-opacity text-muted-foreground" />
                  </span>
                </div>
                <span className="text-sm font-bold">{inventory.semiRipe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.semiRipe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {fingersOf(inventory.semiRipe)} • Transitioning ripeness
              </p>
            </div>

            <div
              className="p-2 -mx-2 rounded-lg hover:bg-muted/40 transition-colors cursor-pointer group/ripeness"
              onClick={() => navigate(scanLogsLink({ status: "In Stock", ripeness: RipenessEnum.RIPE, ripeness_scope: "current", stock: "eligible" }))}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-yellow-500" />
                  <span className="text-sm font-medium group-hover/ripeness:text-primary transition-colors flex items-center gap-1.5">
                    {inventory.ripenessProgressed[RipenessEnum.RIPE] ? "Est. Ripe" : "Ripe"}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover/ripeness:opacity-100 transition-opacity text-muted-foreground" />
                  </span>
                </div>
                <span className="text-sm font-bold">{inventory.ripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.ripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {fingersOf(inventory.ripe)} • Ready for distribution
              </p>
            </div>

            <div
              className="p-2 -mx-2 rounded-lg hover:bg-muted/40 transition-colors cursor-pointer group/ripeness"
              onClick={() => navigate(scanLogsLink({ status: "In Stock", ripeness: RipenessEnum.OVERRIPE, ripeness_scope: "current", stock: "eligible" }))}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <span className="text-sm font-medium group-hover/ripeness:text-primary transition-colors flex items-center gap-1.5">
                    {inventory.ripenessProgressed[RipenessEnum.OVERRIPE] ? "Est. Overripe" : "Overripe"}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover/ripeness:opacity-100 transition-opacity text-muted-foreground" />
                  </span>
                </div>
                <span className="text-sm font-bold">{inventory.overripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.overripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {fingersOf(inventory.overripe)} • Prioritize for immediate sale
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Cultivar Breakdown */}
        <Card className="rounded-xl sm:rounded-2xl">
          <CardContent className="p-4 sm:p-6">
            <h3 className="text-base font-semibold mb-4">Stock by Cultivar</h3>
            <div className="space-y-3">
              {Object.entries(inventory.byCultivar).map(([cultivar, count]) => (
                <div
                  key={cultivar}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer group/cultivar"
                  onClick={() => navigate(scanLogsLink({ status: "In Stock", cultivar, stock: "eligible" }))}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Banana className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <p className="font-medium text-sm group-hover/cultivar:text-primary transition-colors">{cultivar}</p>
                        <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover/cultivar:opacity-100 transition-opacity" />
                      </div>
                      <p className="text-xs text-muted-foreground">{count} hands in stock</p>
                    </div>
                  </div>
                  <Badge variant="outline" className="font-mono">
                    {inventory.totalHands ? ((count / inventory.totalHands) * 100).toFixed(0) : 0}%
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Spoilage Alerts */}
        <Card className="rounded-xl sm:rounded-2xl">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-base font-semibold">Spoilage Alerts</h3>
                <p className="text-xs text-muted-foreground">{inventory.unknownRisk ? `${inventory.unknownRisk} hands have unknown remaining shelf life` : "Items expiring soon"}</p>
              </div>
              {inventory.spoilingSoon.length > 0 && (
                <Badge variant="destructive" className="ml-auto">
                  {inventory.spoilingSoon.length}
                </Badge>
              )}
            </div>
            {inventory.spoilingSoon.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle className="w-12 h-12 text-emerald-600 mx-auto mb-2" />
                <p className="text-sm font-medium text-emerald-900">No immediate spoilage concerns</p>
                <p className="text-xs text-muted-foreground mt-1">{inventory.unknownRisk ? "Unknown estimates need review" : "No known estimates within two days"}</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {inventory.spoilingSoon.map((group) => (
                  <div key={group.id} className="p-3 rounded-lg bg-muted/30 border hover:bg-muted/50 transition-colors cursor-pointer group/alert" onClick={() => {
                    const intakeId = group.intakeId !== "unknown" ? group.intakeId : undefined
                    if (intakeId) navigate(`/logs?intake=${encodeURIComponent(intakeId)}`)
                    else navigate(scanLogsLink({ status: "In Stock", cultivar: group.cultivar, ripeness: group.ripeness, ripeness_scope: "current", stock: "eligible" }))
                  }}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-semibold text-sm group-hover/alert:text-primary transition-colors">{group.source} — {group.cultivar}</p>
                          <Badge variant="outline" className={`text-[10px] ${group.ripeness === RipenessEnum.SEMI_RIPE
                              ? "bg-violet-50 text-violet-700 border-violet-200"
                              : group.ripeness === RipenessEnum.OVERRIPE
                                ? "bg-red-50 text-red-700 border-red-200"
                                : group.ripeness === RipenessEnum.UNRIPE
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : "bg-yellow-50 text-yellow-700 border-yellow-200"
                            }`}>
                            {group.ripenessProgressed ? `Est. ${group.ripeness}` : group.ripeness}
                          </Badge>
                          <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover/alert:opacity-100 transition-opacity ml-auto shrink-0" />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {group.count} hands ({fingerCountText(group.fingers, group.fingersEstimated)})
                        </p>
                        <p className="text-[10px] sm:text-xs text-muted-foreground mt-1">
                          Scanned: {group.oldestScanDate.toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric" })}
                        </p>
                      </div>
                      <Badge
                        variant="destructive"
                        className={`h-auto rounded-lg font-mono text-center flex-col items-center justify-center py-1.5 px-2.5 text-[10px] sm:text-xs whitespace-nowrap shrink-0 text-white border-transparent ${group.daysNum === 0
                            ? "bg-red-600 hover:bg-red-700"
                            : group.daysNum === 1
                              ? "bg-orange-600 hover:bg-orange-700"
                              : "bg-yellow-600 hover:bg-yellow-700"
                          }`}
                      >
                        <div className="flex items-center justify-center mb-0.5">
                          <Clock className="w-3 h-3 mr-1" />
                          {estimateText(group.spoilageDays)}
                        </div>
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* FIFO Recommendations */}
      <Card className="rounded-xl sm:rounded-2xl">
        <CardContent className="p-4 sm:p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-5 h-5 text-primary" />
            <h3 className="text-base font-semibold">FIFO Recommendations</h3>
            <Badge variant="outline" className="ml-auto text-xs">First In, First Out</Badge>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Sell these items first to minimize waste and maximize freshness
          </p>
          <div className="space-y-2">
            {inventory.fifoList.map((intake, idx) => (
              <div
                key={intake.intakeId}
                className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer group/fifo"
                onClick={() => {
                  if (intake.intakeId.startsWith("unlinked:")) {
                    const scanId = intake.intakeId.replace("unlinked:", "")
                    navigate(`/scans/${scanId}`)
                  } else {
                    navigate(`/logs?intake=${encodeURIComponent(intake.intakeId)}`)
                  }
                }}
              >
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary shrink-0">
                  #{idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="font-medium text-sm group-hover/fifo:text-primary transition-colors">{intake.source}</p>
                    <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover/fifo:opacity-100 transition-opacity shrink-0" />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Scanned: {intake.date.toLocaleDateString("en-US", { timeZone: "Asia/Manila" })} • {intake.hands} hands ({fingerCountText(intake.fingers, intake.fingersEstimated)})
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant="outline" className={`text-[10px] sm:text-xs ${intake.earliestSpoilage <= 2 ? "bg-red-50 text-red-700 border-red-200" :
                      intake.earliestSpoilage <= 4 ? "bg-yellow-50 text-yellow-700 border-yellow-200" :
                        "bg-emerald-50 text-emerald-700 border-emerald-200"
                    }`}>
                    {!Number.isFinite(intake.earliestSpoilage) ? "Risk unknown" : intake.earliestSpoilage <= 2 ? "Sell immediately" : "Stock is stable"}
                  </Badge>
                  <span className="text-[9px] sm:text-[10px] text-muted-foreground font-mono mt-1">
                    Earliest spoilage: <span className="font-bold text-rose-600">{estimateText(intake.spoilageDays)}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
