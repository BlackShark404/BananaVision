import { DetailSkeleton } from "@/components/LoadingState"
import { useState, useEffect } from "react"
import { useParams } from "react-router-dom"
import { api } from "@/lib/api"
import { formatSpoilageDays, spoilageDayUnit } from "@/lib/spoilageDisplay"
import { liveShelfLifeLabel } from "@/lib/inventoryRisk"
import { liveRipeness } from "@/lib/ripenessProjection"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import {
  Banana,
  Calendar,
  ChevronDown,
  Droplets,
  FlaskConical,
  Hand,
  Info,
  Leaf,
  Target,
  Thermometer,
  ScanLine,
  Loader2,
  Wind,
} from "lucide-react"
import { fingersLabel } from "@/lib/estimates"

const ripenessColor: Record<string, string> = {
  Unripe: "bg-emerald-500/15 text-emerald-700 border-emerald-200",
  "Semi Ripe": "bg-orange-500/15 text-orange-700 border-orange-200",
  Ripe: "bg-yellow-500/15 text-yellow-700 border-yellow-200",
  Overripe: "bg-red-500/15 text-red-700 border-red-200",
}

const ripenessAccent: Record<string, string> = {
  Unripe: "bg-emerald-500/15 text-emerald-600",
  "Semi Ripe": "bg-orange-500/15 text-orange-600",
  Ripe: "bg-yellow-500/15 text-yellow-600",
  Overripe: "bg-red-500/15 text-red-600",
}

type PublicScan = Awaited<ReturnType<typeof api.scans.publicTrack>>

export default function PublicScanView() {
  const { scanId } = useParams<{ scanId: string }>()
  return <PublicScanRecord key={scanId} scanId={scanId} />
}

// The page a phone opens from a scan's QR code. It shows only the scanned data: no login,
// navigation or website links, and a signed-in staff member sees the same page.
function PublicScanRecord({ scanId }: { scanId?: string }) {
  const [retry, setRetry] = useState(0)
  const [scan, setScan] = useState<PublicScan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(() => Date.now())

  // Fetch public scan data
  useEffect(() => {
    if (!scanId) return
    const controller = new AbortController()
    let cancelled = false
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      setError("Loading took too long. Please retry.")
      setLoading(false)
      controller.abort()
    }, 15_000)

    api.scans.publicTrack(scanId, controller.signal)
      .then((data) => {
        if (cancelled || timedOut) return
        setScan(data)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled || timedOut) return
        if (err instanceof DOMException && err.name === "AbortError") return
        const status = typeof err === "object" && err !== null && "status" in err ? Number((err as { status: number }).status) : 0
        setNotFound(status === 404)
        setError(err instanceof Error ? err.message : "Could not load scan data")
        setLoading(false)
      }).finally(() => window.clearTimeout(timeout))

    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort() }
  }, [scanId, retry])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const handleRetry = () => {
    setLoading(true)
    setError(null)
    setNotFound(false)
    setRetry(value => value + 1)
  }

  if (loading) return <div className="max-w-2xl mx-auto p-4"><DetailSkeleton /></div>

  // Loading / error states
  if (loading || !scan) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanLine className="w-4 h-4" />}
            </EmptyMedia>
            <EmptyTitle className="text-base sm:text-lg font-semibold mt-1" role={loading ? "status" : "alert"}>
              {loading ? "Loading scan…" : notFound ? "Scan not found" : "Could not load scan"}
            </EmptyTitle>
            <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
              {loading
                ? "Retrieving scan details."
                : notFound
                  ? "No scan record was found for this QR code."
                  : error || "Check your connection and try again."}
            </EmptyDescription>
          </EmptyHeader>
          {!loading && !notFound && <Button className="mt-4" onClick={handleRetry}>Retry</Button>}
        </Empty>
      </div>
    )
  }

  const dateObj = new Date(scan.date_time)
  const countdown = liveShelfLifeLabel(
    { remainingDays: scan.remaining_days, riskAsOf: scan.risk_as_of ?? undefined, shelfLifeWindow: scan.shelf_life_window },
    now,
  )
  const liveRip = liveRipeness(scan.ripeness_projection, now, scan.inventory_status, { ignoreClosedStatus: true })
  const displayRipeness = liveRip?.current ?? scan.ripeness
  const ripenessLabel = liveRip ? liveRip.badgeLabel : scan.ripeness

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/bananavision-logo.svg" alt="Logo" className="w-8 h-8 object-contain" />
            <div>
              <h1 className="text-sm font-bold tracking-tight">BananaVision</h1>
              <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Scan Tracking</p>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        {scan.flagged && (
          <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-700">
            <p className="text-sm font-semibold">Pending quality review</p>
            <p className="text-xs mt-0.5">This result was flagged for review. The classification and estimates shown are preliminary.</p>
          </div>
        )}

        {/* Classification Card */}
        <Card className="rounded-2xl overflow-hidden">
          <div className="h-1 bg-linear-to-r from-primary via-banana to-primary" />
          <CardContent className="p-5 space-y-4">
            {/* Ripeness + Cultivar */}
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${ripenessAccent[displayRipeness ?? ""] || "bg-primary/10 text-primary"}`}>
                  <Banana className="w-6 h-6" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-lg font-bold">{scan.cultivar ?? "Unknown"}</p>
                  <p className="text-xs text-muted-foreground">Cultivar</p>
                </div>
              </div>
              {displayRipeness && (
                <Badge variant="outline" className={`text-sm px-3 py-1 font-semibold ${ripenessColor[displayRipeness] || ""}`}>
                  {ripenessLabel}
                </Badge>
              )}
            </div>

            <Separator />

            {/* Shelf life is the value a person scans for. */}
            <div className="rounded-xl border border-border bg-muted/50 px-4 py-5 text-center">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Est. Spoilage</p>
              <p className="text-2xl font-bold mt-1">
                {countdown !== null
                  ? countdown
                  : <>{formatSpoilageDays(scan.spoilage_days, false)} <span className="text-xs text-muted-foreground font-normal">{spoilageDayUnit(scan.spoilage_days)}</span></>}
              </p>
              {countdown !== null && formatSpoilageDays(scan.spoilage_days) !== "Unknown" && (
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  Est. {formatSpoilageDays(scan.spoilage_days)} from scan
                </p>
              )}
            </div>

            <div className="flex items-center justify-center gap-2.5">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Scanned</p>
                <p className="text-sm font-bold">{dateObj.toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Secondary values stay available, without crowding the first screen. */}
        <details className="group rounded-2xl border border-border bg-card overflow-hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm font-semibold [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-2">
              <Info className="w-4 h-4 text-muted-foreground" />
              Scan details
            </span>
            <ChevronDown className="w-4 h-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-border px-5 py-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <Target className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Confidence</p>
                <p className="text-xl font-bold">{scan.confidence === null ? "—" : `${scan.confidence}%`}</p>
              </div>
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <Hand className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider" title="Estimated finger count">{fingersLabel()}</p>
                <p className="text-xl font-bold">{scan.finger_count}</p>
              </div>
            </div>

            {(scan.temperature !== null || scan.humidity !== null || scan.vpd !== null) && (
              <div className="grid grid-cols-3 gap-3">
                {scan.temperature !== null && (
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Thermometer className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p>
                    <p className="text-lg font-bold">{scan.temperature}°C</p>
                  </div>
                )}
                {scan.humidity !== null && (
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Droplets className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Humidity</p>
                    <p className="text-lg font-bold">{scan.humidity}%</p>
                  </div>
                )}
                {scan.vpd !== null && (
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Wind className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">VPD</p>
                    <p className="text-lg font-bold">{scan.vpd} <span className="text-xs font-normal">kPa</span></p>
                  </div>
                )}
              </div>
            )}

            {(scan.source_text || scan.treatment || liveRip?.progressed) && (
              <div className="flex flex-wrap gap-2">
                {liveRip?.progressed && scan.ripeness && (
                  <Badge variant="secondary" className="gap-1.5 px-3 py-1">
                    Scanned as {scan.ripeness}
                  </Badge>
                )}
                {scan.source_text && (
                  <Badge variant="secondary" className="gap-1.5 px-3 py-1">
                    <Banana className="w-3.5 h-3.5" aria-hidden="true" /> {scan.source_text}
                  </Badge>
                )}
                {scan.treatment && (
                  <Badge variant="secondary" className="gap-1.5 px-3 py-1">
                    {scan.treatment === "Ethephon"
                      ? <FlaskConical className="w-3.5 h-3.5" aria-hidden="true" />
                      : <Leaf className="w-3.5 h-3.5" aria-hidden="true" />} {scan.treatment}
                  </Badge>
                )}
              </div>
            )}

            <div className="bg-muted/50 rounded-xl p-3 border border-border">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Scan ID</p>
              <p className="font-mono text-xs font-semibold break-all mt-1">{scan.id}</p>
            </div>
          </div>
        </details>

        {/* Camera evidence stays behind staff authentication. */}

        {/* Footer */}
        <p className="text-center text-[10px] text-muted-foreground pb-4">
          BananaVision · Scan tracked at {dateObj.toLocaleString("en-PH", { timeZone: "Asia/Manila" })}
        </p>
      </main>
    </div>
  )
}
