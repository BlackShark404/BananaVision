import { useEffect, useMemo, useState } from "react"
import { useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
import { remainingStockDays, shelfLifeLabel } from "@/lib/inventoryRisk"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ContentSkeleton } from "@/components/LoadingState"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Progress } from "@/components/ui/progress"
import { Package, AlertTriangle, TrendingDown, CheckCircle, Clock, Banana } from "lucide-react"
import { InventoryStatusEnum, RipenessEnum, CultivarEnum } from "@/types"

export default function Inventory() {
  const { scans, scansReady, scansLoading, scansError, refreshScans } = useScans()
  const { intakesReady, intakesLoading, intakesError, intakesStale, refreshIntakes } = useInventory()
  const [sourceFilter, setSourceFilter] = useState<string>("all")
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

    // Group by ripeness
    const unripe = inStock.filter(s => s.ripeness === RipenessEnum.UNRIPE)
    const ripe = inStock.filter(s => s.ripeness === RipenessEnum.RIPE)
    const overripe = inStock.filter(s => s.ripeness === RipenessEnum.OVERRIPE)
    const semiRipe = inStock.filter(s => s.ripeness === RipenessEnum.SEMI_RIPE)

    // Calculate total hands and fingers
    const totalHands = inStock.length
    const totalFingers = inStock.reduce((sum, s) => sum + s.fingerCount, 0)

    // Spoilage alerts (will spoil in 2 days or less) - Grouped by intake, cultivar, and ripeness
    const spoilageAlertsMap = new Map<string, { id: string; intakeId: string; source: string; cultivar: string; ripeness: string; spoilageDays: string; daysNum: number; count: number; fingers: number; oldestScanDate: Date }>()

    inStock.forEach(s => {
      const daysNum = remainingStockDays(s, asOf)
      if (daysNum === null || daysNum > 2) return

      const key = `${s.intakeId ?? s.source ?? s.id}-${s.cultivar}-${s.ripeness}`
      const existing = spoilageAlertsMap.get(key)
      if (existing) {
        existing.count += 1
        existing.fingers += s.fingerCount
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
          ripeness: s.ripeness,
          spoilageDays: shelfLifeLabel(daysNum),
          daysNum,
          count: 1,
          fingers: s.fingerCount,
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
    const intakeGroups = new Map<string, { intakeId: string, source: string, date: Date, hands: number, fingers: number, earliestSpoilage: number, spoilageDays: string }>()

    inStock.forEach(s => {
      const groupId = s.intakeId ?? `unlinked:${s.id}`
      const existing = intakeGroups.get(groupId)
      const scanDate = new Date(s.dateTime)
      const spoilageNum = remainingStockDays(s, asOf) ?? Number.POSITIVE_INFINITY

      if (existing) {
        existing.hands += 1
        existing.fingers += s.fingerCount
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
      unripe,
      ripe,
      overripe,
      semiRipe,
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
        />
        <AppStatsCard
          title="Total Fingers"
          value={inventory.totalFingers}
          icon={Banana}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={100}
          description="Estimated count"
        />
        <AppStatsCard
          title="Spoiling Soon"
          value={inventory.spoilingSoon.length}
          icon={AlertTriangle}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={150}
          description="≤2 days left"
        />
        <AppStatsCard
          title="Sold"
          value={inventory.sold}
          icon={CheckCircle}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={200}
          description="All time"
        />
      </div>

      {/* Ripeness Distribution */}
      <Card className="rounded-xl sm:rounded-2xl">
        <CardContent className="p-4 sm:p-6">
          <h3 className="text-base font-semibold mb-4">Stock by Ripeness</h3>
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-500" />
                  <span className="text-sm font-medium">Unripe</span>
                </div>
                <span className="text-sm font-bold">{inventory.unripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.unripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {inventory.unripe.reduce((sum, s) => sum + s.fingerCount, 0)} fingers • Store in controlled temperature
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-violet-500" />
                  <span className="text-sm font-medium">Semi Ripe</span>
                </div>
                <span className="text-sm font-bold">{inventory.semiRipe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.semiRipe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {inventory.semiRipe.reduce((sum, s) => sum + s.fingerCount, 0)} fingers • Transitioning ripeness
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-yellow-500" />
                  <span className="text-sm font-medium">Ripe</span>
                </div>
                <span className="text-sm font-bold">{inventory.ripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.ripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {inventory.ripe.reduce((sum, s) => sum + s.fingerCount, 0)} fingers • Ready for distribution
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <span className="text-sm font-medium">Overripe</span>
                </div>
                <span className="text-sm font-bold">{inventory.overripe.length} hands</span>
              </div>
              <Progress value={inventory.totalHands ? (inventory.overripe.length / inventory.totalHands) * 100 : 0} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                {inventory.overripe.reduce((sum, s) => sum + s.fingerCount, 0)} fingers • Prioritize for immediate sale
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
                <div key={cultivar} className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Banana className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{cultivar}</p>
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
                  <div key={group.id} className="p-3 rounded-lg bg-muted/30 border hover:bg-muted/50 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-semibold text-sm">{group.source} — {group.cultivar}</p>
                          <Badge variant="outline" className={`text-[10px] ${group.ripeness === RipenessEnum.SEMI_RIPE
                              ? "bg-violet-50 text-violet-700 border-violet-200"
                              : group.ripeness === RipenessEnum.OVERRIPE
                                ? "bg-red-50 text-red-700 border-red-200"
                                : "bg-yellow-50 text-yellow-700 border-yellow-200"
                            }`}>
                            {group.ripeness}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {group.count} hands ({group.fingers} fingers)
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
                          {group.spoilageDays}
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
              <div key={intake.intakeId} className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary shrink-0">
                  #{idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm">{intake.source}</p>
                  <p className="text-xs text-muted-foreground">
                    Scanned: {intake.date.toLocaleDateString("en-US", { timeZone: "Asia/Manila" })} • {intake.hands} hands ({intake.fingers} fingers)
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
                    Earliest spoilage: <span className="font-bold text-rose-600">{intake.spoilageDays}</span>
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
