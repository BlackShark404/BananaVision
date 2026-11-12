import { DetailSkeleton } from "@/components/LoadingState"
import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { api, BASE_URL } from "@/lib/api"
import { formatSpoilageDays, spoilageDayUnit } from "@/lib/spoilageDisplay"
import { remainingStockDays, shelfLifeLabel } from "@/lib/inventoryRisk"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import {
  Banana,
  Calendar,
  Hand,
  Target,
  ScanLine,
  Loader2,
  LogIn,
  ArrowRight,
} from "lucide-react"

const ripenessColor: Record<string, string> = {
  Unripe: "bg-emerald-500/15 text-emerald-700 border-emerald-200",
  "Semi Ripe": "bg-orange-500/15 text-orange-700 border-orange-200",
  Ripe: "bg-yellow-500/15 text-yellow-700 border-yellow-200",
  Overripe: "bg-red-500/15 text-red-700 border-red-200",
}

const ripenessIcon: Record<string, string> = {
  Unripe: "🟢",
  "Semi Ripe": "🟠",
  Ripe: "🟡",
  Overripe: "🔴",
}

type PublicScan = Awaited<ReturnType<typeof api.scans.publicTrack>>

export default function PublicScanView() {
  const { scanId } = useParams<{ scanId: string }>()
  return <PublicScanRecord key={scanId} scanId={scanId} />
}

function PublicScanRecord({ scanId }: { scanId?: string }) {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [retry, setRetry] = useState(0)
  const [scan, setScan] = useState<PublicScan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)
  const [activeImage, setActiveImage] = useState(0)
  const [now, setNow] = useState(() => Date.now())

  // Authenticated users get redirected to the full detail page
  useEffect(() => {
    if (user && scanId) {
      navigate(`/scans/${scanId}`, { replace: true })
    }
  }, [user, scanId, navigate])

  // Fetch public scan data
  useEffect(() => {
    if (!scanId || user) return
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
  }, [scanId, user, retry])

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

  // Build image URL from backend path
  const getImageUrl = (path: string) => {
    if (!path) return ""
    if (path.startsWith("http://") || path.startsWith("https://")) return path
    const normalizedPath = path.startsWith("/") ? path : `/${path}`
    return `${BASE_URL}${normalizedPath}`
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
          {!loading && (
            <Button variant="outline" className="mt-4 gap-2" onClick={() => navigate("/login")}>
              <LogIn className="w-4 h-4" /> Log in
            </Button>
          )}
        </Empty>
      </div>
    )
  }

  const dateObj = new Date(scan.date_time)
  const remaining = remainingStockDays(
    { remainingDays: scan.remaining_days, riskAsOf: scan.risk_as_of ?? undefined },
    now,
  )

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
          <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => navigate("/login")}>
            <LogIn className="w-3.5 h-3.5" /> Log in
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        {/* Scan ID Header */}
        <div className="text-center space-y-1">
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Scan Record</p>
          <p className="font-mono text-sm font-bold uppercase text-foreground/80">{scan.id}</p>
        </div>

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
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-2xl">
                  {ripenessIcon[scan.ripeness ?? ""] || "🍌"}
                </div>
                <div>
                  <p className="text-lg font-bold">{scan.cultivar ?? "Unknown"}</p>
                  <p className="text-xs text-muted-foreground">Cultivar</p>
                </div>
              </div>
              {scan.ripeness && (
                <Badge variant="outline" className={`text-sm px-3 py-1 font-semibold ${ripenessColor[scan.ripeness] || ""}`}>
                  {scan.ripeness}
                </Badge>
              )}
            </div>

            <Separator />

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <Target className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Confidence</p>
                <p className="text-xl font-bold">{scan.confidence === null ? "—" : `${scan.confidence}%`}</p>
              </div>
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <Hand className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Finger Count</p>
                <p className="text-xl font-bold">{scan.finger_count}</p>
              </div>
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <p className="text-xl mx-auto mb-1">⏳</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Est. Spoilage</p>
                <p className="text-xl font-bold">
                  {remaining !== null
                    ? shelfLifeLabel(remaining)
                    : <>{formatSpoilageDays(scan.spoilage_days, false)} <span className="text-xs text-muted-foreground font-normal">{spoilageDayUnit(scan.spoilage_days)}</span></>}
                </p>
                {remaining !== null && scan.spoilage_days != null && (
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Est. {formatSpoilageDays(scan.spoilage_days)} from scan
                  </p>
                )}
              </div>
              <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                <Calendar className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Scanned</p>
                <p className="text-sm font-bold">{dateObj.toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })}</p>
              </div>
            </div>

            {/* Environmental data */}
            {(scan.temperature !== null || scan.humidity !== null || scan.vpd !== null) && (
              <>
                <Separator />
                <div className="grid grid-cols-3 gap-3">
                  {scan.temperature !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-lg mx-auto mb-0.5">🌡️</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p>
                      <p className="text-lg font-bold">{scan.temperature}°C</p>
                    </div>
                  )}
                  {scan.humidity !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-lg mx-auto mb-0.5">💧</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Humidity</p>
                      <p className="text-lg font-bold">{scan.humidity}%</p>
                    </div>
                  )}
                  {scan.vpd !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-lg mx-auto mb-0.5">💨</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">VPD</p>
                      <p className="text-lg font-bold">{scan.vpd} <span className="text-xs font-normal">kPa</span></p>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Source + Treatment + Inventory */}
            {(scan.source_text || scan.treatment || scan.inventory_status) && (
              <>
                <Separator />
                <div className="flex flex-wrap gap-2">
                  {scan.source_text && (
                    <Badge variant="secondary" className="gap-1.5 px-3 py-1">
                      <Banana className="w-3.5 h-3.5" /> {scan.source_text}
                    </Badge>
                  )}
                  {scan.treatment && (
                    <Badge variant="secondary" className="gap-1.5 px-3 py-1">
                      {scan.treatment === "Ethephon" ? "🧪" : "🌿"} {scan.treatment}
                    </Badge>
                  )}
                  {scan.inventory_status && (
                    <Badge variant="outline" className="gap-1.5 px-3 py-1">
                      {scan.inventory_status}
                    </Badge>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Camera Images */}
        {scan.images.length > 0 && (
          <Card className="rounded-2xl">
            <CardContent className="p-5 space-y-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Camera Images</p>

              {/* Main image */}
              <div className="rounded-xl overflow-hidden border border-border bg-muted/50">
                <img
                  src={getImageUrl(scan.images[activeImage]?.file_path)}
                  alt={`Camera ${scan.images[activeImage]?.camera_id}`}
                  className="w-full aspect-[4/3] object-cover"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              </div>

              {/* Thumbnails */}
              {scan.images.length > 1 && (
                <div className="grid grid-cols-4 gap-2">
                  {scan.images.map((img, idx) => (
                    <button
                      key={img.camera_id}
                      onClick={() => setActiveImage(idx)}
                      className={`relative rounded-lg overflow-hidden border-2 transition-all duration-200 ${
                        activeImage === idx
                          ? "border-primary ring-2 ring-primary/20"
                          : "border-transparent hover:border-muted-foreground/30"
                      }`}
                    >
                      <div className="aspect-square bg-muted/50">
                        <img
                          src={getImageUrl(img.file_path)}
                          alt={img.camera_id}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <span className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[8px] font-medium py-0.5 text-center">
                        {img.camera_id}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Login CTA */}
        <Card className="rounded-2xl bg-primary/5 border-primary/20">
          <CardContent className="p-5 text-center space-y-3">
            <p className="text-sm font-semibold">Need more details?</p>
            <p className="text-xs text-muted-foreground">
              Log in to access full scan details, detection overlays, quality control, and editing.
            </p>
            <Button className="gap-2" onClick={() => navigate("/login")}>
              Log in to BananaVision <ArrowRight className="w-4 h-4" />
            </Button>
          </CardContent>
        </Card>

        {/* Footer */}
        <p className="text-center text-[10px] text-muted-foreground pb-4">
          BananaVision · Scan tracked at {dateObj.toLocaleString("en-PH", { timeZone: "Asia/Manila" })}
        </p>
      </main>
    </div>
  )
}
