import { scanRetryAction } from "@/lib/scanWriteFeedback"
import { ScanImage } from "@/components/ScanImage"
import { cultivarCameraConflict } from "@/lib/scanData"
import { formatSpoilageDays, spoilageDayUnit } from "@/lib/spoilageDisplay"
import { liveShelfLifeLabel } from "@/lib/inventoryRisk"
import { useState, useEffect, useCallback, useRef } from "react"
import KioskOperatorSwap from "@/components/KioskOperatorSwap"
import { useAuth } from "@/context/AuthContext"
import { OOD_REJECTED, useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
import { useAdmin } from "@/context/AdminContext"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { BASE_URL, api, withMediaToken } from "@/lib/api"
import {
  Banana,
  ScanLine,
  Camera,
  Loader2,
  CheckCircle2,
  Target,
  CalendarClock,
  Hand,
  Package,
  Clock,
  Flag,
  Eye,
  EyeOff,
  SearchX,
  TriangleAlert,
  Thermometer,
  Droplets,
  Wind,
  Leaf,
  FlaskConical,
} from "lucide-react"
import { toast } from "sonner"
import { AppStatusBadge } from "@/components/AppStatusBadge"
import BoundingBoxOverlay from "@/components/BoundingBoxOverlay"
import { getImageUrl } from "@/lib/utils"
import type { BoundingBox, ScanDetection } from "@/types"
import { KioskPrintStatus } from "@/components/KioskPrintStatus"
import { inManila } from "@/lib/manilaTime"
import { estimateText, fingerCountIsEstimate, fingerCountText, fingersLabel } from "@/lib/estimates"

export default function Kiosk() {
  const { user } = useAuth()
  const { scanState, startScan, scans, flagScan } = useScans()
  const { suppliers, activeIntake, startIntake } = useInventory()
  const { users, config } = useAdmin()
  const { isScanning, scanStep, scanProgress, lastResult, rejection } = scanState
  const cultivarConflict = lastResult ? cultivarCameraConflict(lastResult) : null
  const [currentTime, setCurrentTime] = useState(new Date())
  const activeSuppliers = suppliers.filter(s => s.status === "Active")
  const [showSourceModal, setShowSourceModal] = useState(false)
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null)
  const [selectedTreatment, setSelectedTreatment] = useState<"Natural" | "Ethephon">("Natural")
  const [startingIntake, setStartingIntake] = useState(false)
  const [flaggingScan, setFlaggingScan] = useState(false)
  const notifiedConflict = useRef<string | null>(null)

  useEffect(() => {
    if (!lastResult || !cultivarConflict || notifiedConflict.current === lastResult.id) return
    notifiedConflict.current = lastResult.id
    toast.warning("Cultivar uncertain", {
      description: `${cultivarConflict}. Flag this scan for review; estimates stay hidden until the cultivar is corrected.`,
      duration: 8000,
    })
  }, [lastResult, cultivarConflict])

  const [kioskOperatorsList, setKioskOperatorsList] = useState<{ id: string; username: string; fullName: string; role: string; status: string; avatar?: string }[]>([])
  const [operatorsLoading, setOperatorsLoading] = useState(true)
  const [operatorsError, setOperatorsError] = useState<string | null>(null)
  const [operatorRequest, setOperatorRequest] = useState(0)
  const [kioskOperator, setKioskOperator] = useState<string | null>(null)

  // Fetch operators from public endpoint on mount (no auth required).
  // This ensures the kiosk selection modal is populated even on fresh sessions.
  useEffect(() => {
    let active = true
    setOperatorsLoading(true); setOperatorsError(null)
    api.auth.kioskOperators()
      .then((ops) => {
        if (!active) return
        setKioskOperatorsList(ops.map(o => ({
          id: o.id,
          username: o.username,
          fullName: o.full_name,
          role: o.role,
          status: o.status,
          avatar: o.avatar_url,
        })))
      })
      .catch(() => { if (active) setOperatorsError("Operator list unavailable. Check the station connection and retry.") })
      .finally(() => { if (active) setOperatorsLoading(false) })
    return () => { active = false }
  }, [operatorRequest])

  // Use the publicly-fetched list; fall back to AdminContext users if populated
  const adminOperators = users.filter(u => u.status === "Active" && u.role === "Operator")
  const activeOperators = kioskOperatorsList.length > 0 ? kioskOperatorsList : adminOperators
  const [showSwapModal, setShowSwapModal] = useState(true)
  const [scanAction, setScanAction] = useState<{ id: string, action: 'accepted' | 'flagged' } | null>(null)
  const [showKioskBoxes, setShowKioskBoxes] = useState(true)
  const [kioskActiveDetImg, setKioskActiveDetImg] = useState(0)
  const [showDetectionModal, setShowDetectionModal] = useState(false)

  // Backend camera list with actual device IDs (excludes laptop camera)
  const [backendCameras, setBackendCameras] = useState<{ device_id: number; camera_id: string; label: string; online: boolean }[]>([])

  // Fetch camera list from backend on mount to get actual device IDs
  useEffect(() => {
    api.cameras.list()
      .then(setBackendCameras)
      .catch((err) => console.warn("[Kiosk] Failed to fetch cameras", err))
  }, [])

  // Angle labels for each camera position (expandable for more cameras)
  const cameraAngles = ["Top", "Left", "Right", "Rear"]

  // Generate cameras from backend device list (preferred) or fall back to config labels
  const cameras = backendCameras.length > 0
    ? backendCameras.map((cam, index) => ({
      id: cam.camera_id,
      deviceId: cam.device_id,
      label: cam.label,
      angle: cameraAngles[index] || `Angle ${index + 1}`,
    }))
    : config.cameraIds.split(",").map(s => s.trim()).filter(Boolean).map((id, index) => ({
      id: id,
      deviceId: index,
      label: id,
      angle: cameraAngles[index] || `Angle ${index + 1}`,
    }))

  // --- Live webcam switch state ---
  const [activeCameraIndex, setActiveCameraIndex] = useState(0)

  const selectCamera = useCallback((index: number) => {
    setActiveCameraIndex(index)
  }, [])

  // Clamp activeCameraIndex if cameras change
  useEffect(() => {
    if (cameras.length > 0 && activeCameraIndex >= cameras.length) {
      setActiveCameraIndex(0)
    }
  }, [cameras.length, activeCameraIndex])

  // Determine which camera index is actively capturing during scan step 1 (0-based)
  const activeCaptureIndex = isScanning && scanStep === 1
    ? Math.min(cameras.length - 1, Math.floor((scanProgress / 33) * cameras.length))
    : -1

  // Update clock every second
  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])

  // Get recent scans (last 5)
  const recentScans = scans.slice(0, 5)

  const handleScan = () => {
    if (!kioskOperator) {
      toast.error("Please select an operator first")
      setShowSwapModal(true)
      return
    }
    if (!activeIntake) {
      toast.error("Please start an active delivery intake first")
      setShowSourceModal(true)
      return
    }
    startScan(undefined, activeIntake?.id)
    setKioskActiveDetImg(0)
  }

  // Count scans for today
  const todayScansCount = scans.filter(s => new Date(s.dateTime).toLocaleDateString("en-PH", { timeZone: "Asia/Manila" }) === new Date().toLocaleDateString("en-PH", { timeZone: "Asia/Manila" })).length

  return (
    <div className="h-screen flex flex-col bg-background text-foreground overflow-hidden relative">

      {/* Swap Operator Modal */}
      <KioskOperatorSwap
        open={showSwapModal}
        onOpenChange={setShowSwapModal}
        operators={activeOperators}
        operatorsLoading={operatorsLoading}
        operatorsError={operatorsError}
        onRetryOperators={() => setOperatorRequest(value => value + 1)}
        currentOperatorId={kioskOperator}
        onSwapSuccess={(id) => setKioskOperator(id)}
      />

      {/* Select Source Modal */}
      <Dialog open={showSourceModal} onOpenChange={(open) => { if (!startingIntake) setShowSourceModal(open) }}>
        <DialogContent className="sm:max-w-2xl max-h-[90dvh] flex flex-col gap-0 p-0 overflow-hidden">
          <DialogHeader className="text-center sm:text-center p-6 pb-4 shrink-0 border-b">
            <div className="mx-auto w-12 h-12 bg-primary/10 text-primary rounded-xl flex items-center justify-center mb-4">
              <Package className="w-6 h-6" />
            </div>
            <DialogTitle className="text-2xl font-bold">Select Delivery Source</DialogTitle>
            <DialogDescription className="text-base">
              Please confirm the active delivery source for scanning operations.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 p-6 overflow-y-auto flex-1 kiosk-scroll">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {activeSuppliers.map((supplier) => (
                <button
                  key={supplier.id}
                  onClick={() => setSelectedSupplierId(supplier.id)}
                  className={`
                    flex flex-col items-start p-6 rounded-xl border-2 transition-all duration-200 text-left
                    ${selectedSupplierId === supplier.id
                      ? 'border-primary bg-primary/5 shadow-md scale-[1.02]'
                      : 'border-border bg-card hover:border-primary/50 hover:bg-accent hover:shadow-sm'}
                  `}
                >
                  <span className="text-lg font-bold text-foreground mb-2">{supplier.name}</span>
                  {activeIntake?.supplierId === supplier.id && (
                    <span className="text-sm text-primary font-medium flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                      Currently Active Intake
                    </span>
                  )}
                  {supplier.contactPerson && (
                    <span className="text-xs text-muted-foreground/70 mt-3 pt-3 border-t w-full">
                      Contact: {supplier.contactPerson}
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div className="mt-4 p-4 rounded-xl bg-muted/50 border border-border flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-sm font-semibold">Batch Tracking</span>
                <span className="text-xs text-muted-foreground">A secure batch number will be automatically generated.</span>
              </div>
              <Badge variant="secondary" className="font-mono text-xs">AUTO-ASSIGNED</Badge>
            </div>

            {/* Treatment Selection */}
            <div className="mt-4 p-4 rounded-xl bg-muted/50 border border-border">
              <span className="text-sm font-semibold">Ripening Treatment</span>
              <p className="text-xs text-muted-foreground mb-3">Select how this batch was ripened — affects spoilage prediction accuracy.</p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setSelectedTreatment("Natural")}
                  className={`p-3 rounded-xl border-2 text-center transition-all ${selectedTreatment === "Natural"
                    ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                    : "border-border hover:border-primary/40"
                    }`}
                >
                  <Leaf className="w-5 h-5 mx-auto text-emerald-600" aria-hidden="true" />
                  <p className="text-sm font-semibold mt-1">Natural</p>
                  <p className="text-[10px] text-muted-foreground">Ambient ripening</p>
                </button>
                <button
                  onClick={() => setSelectedTreatment("Ethephon")}
                  className={`p-3 rounded-xl border-2 text-center transition-all ${selectedTreatment === "Ethephon"
                    ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                    : "border-border hover:border-primary/40"
                    }`}
                >
                  <FlaskConical className="w-5 h-5 mx-auto text-amber-600" aria-hidden="true" />
                  <p className="text-sm font-semibold mt-1">Ethephon</p>
                  <p className="text-[10px] text-muted-foreground">Chemical ripening</p>
                </button>
              </div>
            </div>
          </div>

          <div className="p-6 pt-4 shrink-0 border-t bg-background">
            <Button
              className="w-full h-14 text-lg font-bold rounded-xl"
              size="lg"
              disabled={!selectedSupplierId || startingIntake}
              onClick={async () => {
                if (!selectedSupplierId || startingIntake) return
                setStartingIntake(true)
                try {
                  const generatedBatch = `BCH-${Math.random().toString(36).substring(2, 8).toUpperCase()}`
                  await startIntake(selectedSupplierId, generatedBatch, selectedTreatment)
                  toast.success("Started new delivery intake!")
                  setShowSourceModal(false)
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Failed to start delivery intake")
                } finally {
                  setStartingIntake(false)
                }
              }}
            >
              {startingIntake && <Loader2 className="w-5 h-5 animate-spin mr-2" />}
              {startingIntake ? "Starting Intake Session…" : "Start Intake Session"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Top Bar */}
      <header className="flex items-center justify-between px-4 lg:px-6 py-3 border-b border-border bg-card/50 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center">
            <img src="/bananavision-logo.svg" alt="Logo" className="w-10 h-10 object-contain" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight">BananaVision</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Kiosk Mode</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Clock */}
          <div className="hidden sm:flex items-center gap-2 text-muted-foreground">
            <Clock className="w-4 h-4" />
            <span className="text-sm font-mono">
              {currentTime.toLocaleTimeString("en-US", inManila({ hour: "2-digit", minute: "2-digit", second: "2-digit" }))}
            </span>
          </div>

          {/* Today's Stats */}
          <div className="hidden sm:flex items-center gap-1.5 p-1.5 pr-3 rounded-full hover:bg-accent transition-colors">
            <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30 gap-1.5 py-1 px-2.5">
              <Package className="w-3.5 h-3.5 shrink-0" />
              <span className="text-xs">Today's Intake:</span>
              <span className="font-bold">{todayScansCount}</span>
            </Badge>
          </div>

          {/* Operator - Clickable to Swap */}
          <button
            className="flex items-center gap-2 lg:gap-3 p-1.5 pr-3 rounded-full hover:bg-accent transition-colors text-left"
            onClick={() => setShowSwapModal(true)}
            title="Swap Operator"
          >
            <Avatar className="h-8 w-8 lg:h-9 lg:w-9 border border-border">
              {kioskOperator ? (
                <>
                  <AvatarImage src={user?.avatar || undefined} className="object-cover" />
                  <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
                    {user?.fullName?.split(" ").map(n => n[0]).join("").toUpperCase() || "?"}
                  </AvatarFallback>
                </>
              ) : (
                <AvatarFallback className="bg-muted text-muted-foreground text-xs font-bold">?</AvatarFallback>
              )}
            </Avatar>
            <div className="hidden sm:block">
              {kioskOperator ? (
                <>
                  <p className="text-xs font-semibold leading-tight">{user?.fullName}</p>
                  <div className="flex items-center gap-1 mt-0.5 text-[10px] text-muted-foreground">
                    <span>{user?.role}</span>
                    <span className="w-1 h-1 rounded-full bg-border"></span>
                    <span className="text-primary hover:underline font-medium">Swap</span>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-xs font-semibold leading-tight text-muted-foreground">No Operator</p>
                  <p className="text-[10px] text-primary font-medium">Tap to select</p>
                </>
              )}
            </div>
          </button>


        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex flex-col lg:flex-row gap-4 lg:gap-6 p-4 lg:p-6 overflow-y-auto lg:overflow-hidden kiosk-scroll">

        {/* Left Panel — Camera + Scan */}
        <div className="lg:flex-[4] flex flex-col gap-3 lg:gap-4 shrink-0 lg:shrink lg:min-h-0">
          {/* Main Camera View */}
          <Card className="shrink-0 lg:shrink h-64 sm:h-80 lg:flex-[2] lg:h-auto bg-black border-border rounded-2xl overflow-hidden relative lg:min-h-64 py-0 gap-0">
            <CardContent className="p-0 h-full flex flex-col relative">
              {/* Main Feed */}
              <div className="flex-1 w-full flex items-center justify-center relative overflow-hidden">
                {isScanning ? (
                  <div className="text-center space-y-4 animate-pulse z-10">
                    <div className="w-20 h-20 lg:w-24 lg:h-24 rounded-full bg-primary/20 flex items-center justify-center mx-auto border-2 border-primary/40">
                      <Loader2 className="w-10 h-10 lg:w-12 lg:h-12 text-primary animate-spin" />
                    </div>
                    <p className="text-white text-sm lg:text-base font-medium drop-shadow-md">{scanState.scanStepLabel}</p>
                  </div>
                ) : (
                  <>
                    {/* Render only the active camera feed to save bandwidth */}
                    {cameras.length > 0 && (
                      <img
                        key={`cam-feed-${activeCameraIndex}`}
                        src={withMediaToken(`${BASE_URL}/api/v1/cameras/preview/${cameras[activeCameraIndex]?.deviceId ?? activeCameraIndex}`)}
                        alt={`Live Camera Feed - ${cameras[activeCameraIndex]?.label}`}
                        className="inset-0 w-full h-full object-contain z-0 absolute animate-fade-in"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                          const fallback = e.currentTarget.parentElement?.querySelector('[data-camera-fallback]');
                          if (fallback) (fallback as HTMLElement).style.display = 'flex';
                        }}
                        onLoad={(e) => {
                          e.currentTarget.style.display = '';
                          const fallback = e.currentTarget.parentElement?.querySelector('[data-camera-fallback]');
                          if (fallback) (fallback as HTMLElement).style.display = 'none';
                        }}
                      />
                    )}
                    {/* Fallback for when no cameras or stream fails */}
                    {cameras.length === 0 && (
                      <div className="text-center space-y-3 z-10 flex flex-col items-center justify-center">
                        <div className="w-20 h-20 lg:w-24 lg:h-24 rounded-full bg-muted flex items-center justify-center mx-auto border-2 border-border shadow-sm">
                          <Camera className="w-10 h-10 lg:w-12 lg:h-12 text-muted-foreground/50" />
                        </div>
                        <p className="text-muted-foreground/70 text-sm">No cameras configured</p>
                      </div>
                    )}
                  </>
                )}

                {/* Fallback UI if camera stream fails */}
                {!isScanning && cameras.length > 0 && (
                  <div data-camera-fallback className="text-center space-y-3 z-10 items-center justify-center flex-col" style={{ display: 'none' }}>
                    <div className="w-20 h-20 lg:w-24 lg:h-24 rounded-full bg-muted flex items-center justify-center mx-auto border-2 border-border shadow-sm">
                      <Camera className="w-10 h-10 lg:w-12 lg:h-12 text-muted-foreground/50" />
                    </div>
                    <p className="text-muted-foreground/70 text-sm">Camera offline</p>
                  </div>
                )}

                {/* Camera label overlay — top left */}
                <div className="absolute top-3 left-3 flex items-center gap-2 z-20">
                  <Badge variant="outline" className="bg-background/80 backdrop-blur-sm border-border text-xs gap-1.5 py-1">
                    <div className={`w-2 h-2 rounded-full ${isScanning ? "bg-red-500 animate-pulse" : "bg-emerald-500"}`} />
                    {isScanning ? "CAPTURING" : cameras.length > 0 ? cameras[activeCameraIndex]?.label : "NO CAM"}
                  </Badge>
                </div>



                {/* Camera counter — top right */}
                {!isScanning && cameras.length > 1 && (
                  <div className="absolute top-3 right-3 z-20">
                    <Badge variant="outline" className="bg-background/80 backdrop-blur-sm border-border text-xs gap-1.5 py-1">
                      <Camera className="w-3 h-3" />
                      {cameras[activeCameraIndex]?.id}
                    </Badge>
                  </div>
                )}
              </div>

              {/* Scan Progress Bar (inline) */}
              {isScanning && (
                <div className="absolute bottom-0 left-0 right-0 p-4 bg-linear-to-t from-background/80 to-transparent">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground">{scanState.scanStepLabel}</span>
                    <span className="text-xs text-primary font-bold">{scanProgress}%</span>
                  </div>
                  <div className="relative h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-linear-to-r from-primary to-emerald-500 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${scanProgress}%` }}
                    />
                  </div>

                  {/* Step Indicators */}
                  <div className="flex items-center justify-center gap-6 mt-3">
                    {[
                      { label: "Capture", step: 1, icon: Camera },
                      { label: "Detect", step: 2, icon: Target },
                      { label: "Analyze", step: 3, icon: ScanLine },
                    ].map(({ label, step, icon: Icon }) => (
                      <div key={step} className="flex items-center gap-1.5">
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${scanStep > step
                          ? "bg-emerald-500 text-white"
                          : scanStep === step
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground"
                          }`}>
                          {scanStep > step ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3 h-3" />}
                        </div>
                        <span className={`text-[10px] ${scanStep >= step ? "text-foreground/80" : "text-muted-foreground"}`}>
                          {label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Camera Status Indicators — compact horizontal strip */}
          <div className="flex gap-2 shrink-0">
            {cameras.length === 0 ? (
              <div className="flex-1 text-center text-muted-foreground text-xs py-3 border rounded-xl border-dashed">
                No cameras configured. Go to Settings to add cameras.
              </div>
            ) : cameras.map((cam, idx) => {
              const isCapturing = isScanning && scanStep === 1 && activeCaptureIndex === idx
              const isCaptured = isScanning && scanStep === 1 && activeCaptureIndex > idx
              const isDoneCapture = isScanning && scanStep > 1
              const isActiveView = !isScanning && idx === activeCameraIndex

              return (
                <button
                  key={cam.id}
                  onClick={() => { if (!isScanning) selectCamera(idx); }}
                  className={`relative flex-1 h-9 rounded-lg border transition-all duration-200 flex items-center justify-center gap-1.5 text-xs font-medium ${isCapturing
                    ? "border-primary bg-primary/10 text-primary shadow-sm shadow-primary/20"
                    : isActiveView
                      ? "border-primary/60 bg-primary/5 text-primary"
                      : (isCaptured || isDoneCapture)
                        ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-600"
                        : "border-border bg-card text-muted-foreground hover:border-primary/30 hover:bg-accent"
                    } ${!isScanning ? 'cursor-pointer active:scale-95' : ''}`}
                  disabled={isScanning}
                >
                  {isCapturing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (isCaptured || isDoneCapture) ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  ) : isActiveView ? (
                    <Camera className="w-3.5 h-3.5" />
                  ) : (
                    <div className={`w-1.5 h-1.5 rounded-full ${isCapturing ? "bg-red-500 animate-pulse" : "bg-emerald-500/50"}`} />
                  )}
                  <span>{cam.angle}</span>
                </button>
              )
            })}
          </div>

          {/* Scan Actions */}
          <div className="flex flex-col gap-3 shrink-0">
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground ml-1 uppercase tracking-wider">Source / Supplier Tag</label>
              <Button
                variant="outline"
                onClick={() => setShowSourceModal(true)}
                disabled={isScanning}
                className="w-full h-14 bg-card hover:bg-muted text-left flex justify-between items-center px-4 rounded-xl border-border shadow-sm text-base font-medium"
              >
                <span>{activeIntake ? `${activeIntake.supplierName}${activeIntake.batchNumber ? ` (${activeIntake.batchNumber})` : ''}` : "Select Source"}</span>
                <span className="text-sm text-muted-foreground bg-muted/50 px-2 py-1 rounded-md">Change</span>
              </Button>
            </div>

            <Button
              size="lg"
              className="h-14 lg:h-16 text-base lg:text-xl font-bold rounded-2xl shadow-xl shadow-primary/20 gap-3 transition-all duration-300 hover:scale-[1.01] active:scale-[0.99]"
              disabled={isScanning || !kioskOperator || !activeIntake}
              onClick={handleScan}
            >
              {isScanning ? (
                <>
                  <Loader2 className="w-6 h-6 lg:w-7 lg:h-7 animate-spin" />
                  Scanning...
                </>
              ) : (
                <>
                  <ScanLine className="w-6 h-6 lg:w-7 lg:h-7" />
                  Scan Now
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Right Panel — Results + History */}
        <div className="lg:flex-[3] flex flex-col gap-4 shrink-0 lg:shrink lg:min-h-0 lg:overflow-y-auto kiosk-scroll">

          {/* Last Scan Result */}
          {lastResult ? (
            <Card className="bg-card border-border rounded-2xl overflow-hidden animate-fade-in shrink-0">
              <div className="h-1 bg-linear-to-r from-primary via-banana to-primary" />
              <CardContent className="p-4 lg:p-5 space-y-4">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
                      <CheckCircle2 className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-bold">{lastResult.flagged || cultivarConflict ? "Scan Complete - Review Needed" : "Scan Complete"}</p>
                      <p className="text-[10px] text-muted-foreground">{new Date(lastResult.dateTime).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila" })}</p>
                    </div>
                  </div>
                  <AppStatusBadge type="ripeness" status={lastResult.ripeness} size="lg" />
                </div>

                {cultivarConflict && (
                  <p role="status" className="text-xs text-muted-foreground">
                    Cameras disagree. {cultivarConflict}. Review cultivar before accepting.
                  </p>
                )}

                {/* Metrics Grid — Primary */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-primary/10 rounded-xl p-3 text-center border border-primary/20">
                    <Banana className="w-5 h-5 text-primary mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Cultivar</p>
                    <p className="text-lg font-bold text-primary" title={cultivarConflict ? `Stored AI candidate: ${lastResult.cultivar}` : undefined}>{cultivarConflict ? "Uncertain" : lastResult.cultivar}</p>
                  </div>
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Target className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider" title={cultivarConflict ? "No cultivar consensus across camera views." : "Model prediction score; this is not measured accuracy."}>Confidence</p>
                    <p className="text-lg font-bold">{cultivarConflict || lastResult.confidence === null ? "—" : `${lastResult.confidence}%`}</p>
                    <Progress value={cultivarConflict ? null : lastResult.confidence} className="h-1 mt-1.5" />
                  </div>
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <CalendarClock className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Est. Spoilage</p>
                    <p className="text-lg font-bold">
                      {cultivarConflict ? "—" : <>{formatSpoilageDays(lastResult.spoilageDays, false)} <span className="text-xs text-muted-foreground">{spoilageDayUnit(lastResult.spoilageDays)}</span></>}
                    </p>
                  </div>
                </div>

                {/* Metrics Grid — Environment (evenly distributed) */}
                {(() => {
                  const envCards: React.ReactNode[] = []
                  envCards.push(
                    <div key="fingers" className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <Hand className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider" title={fingerCountIsEstimate(lastResult) ? "Estimated finger count; confirm the physical total before accepting." : "Finger count corrected by staff."}>{fingersLabel(fingerCountIsEstimate(lastResult))}</p>
                      <p className="text-lg font-bold">{lastResult.fingerCount}</p>
                    </div>
                  )
                  if (lastResult.temperature !== undefined) {
                    envCards.push(
                      <div key="temp" className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                        <Thermometer className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p>
                        <p className="text-lg font-bold">{lastResult.temperature}°C</p>
                      </div>
                    )
                  }
                  if (lastResult.humidity !== undefined) {
                    envCards.push(
                      <div key="humidity" className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                        <Droplets className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Humidity</p>
                        <p className="text-lg font-bold">{lastResult.humidity}%</p>
                      </div>
                    )
                  }
                  if (lastResult.vpd !== undefined && lastResult.vpd !== null) {
                    envCards.push(
                      <div key="vpd" className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                        <Wind className="w-5 h-5 text-muted-foreground mx-auto mb-1" aria-hidden="true" />
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">VPD</p>
                        <p className="text-lg font-bold">{lastResult.vpd.toFixed(3)} kPa</p>
                      </div>
                    )
                  }
                  // Choose column count to evenly fill: use the card count itself (up to 4)
                  const cols = envCards.length <= 4 ? envCards.length : 4
                  return (
                    <div className="space-y-2">
                      <div
                        className="grid gap-3"
                        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
                      >
                        {envCards}
                      </div>
                      {lastResult.temperature === undefined && lastResult.humidity === undefined && (
                        <p className="text-[11px] text-muted-foreground text-center">
                          DHT22 sensor unavailable or stale at scan time — shelf life uses 25.0°C / 65.0% RH baseline.
                        </p>
                      )}
                    </div>
                  )
                })()}

                {/* Detection Images — Compact Grid + Lightbox */}
                {lastResult.detections && lastResult.detections.length > 0 && lastResult.images && lastResult.images.length > 0 && (
                  <>
                    <div className="grid grid-cols-4 gap-2">
                      {lastResult.images.map((img: { camera_id: string; file_path: string }, idx: number) => {
                        const detection = lastResult.detections?.find((d: ScanDetection) => d.camera_id === img.camera_id)
                        const imgUrl = img.file_path.startsWith('http') ? img.file_path : getImageUrl(img.file_path)
                        const boxCount = detection?.finger_count || detection?.bounding_boxes?.length || 0
                        return (
                          <button
                            key={img.camera_id}
                            onClick={() => { setKioskActiveDetImg(idx); setShowDetectionModal(true) }}
                            className="relative rounded-xl overflow-hidden border-2 border-border hover:border-primary/60 transition-all duration-200 cursor-pointer group"
                          >
                            <ScanImage
                              src={imgUrl}
                              alt={`${img.camera_id} detection`}
                              className="w-full aspect-square object-cover"
                            />
                            {/* Dark overlay on hover */}
                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-200" />
                            {/* Camera label */}
                            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pt-4 pb-1.5">
                              <p className="text-[9px] text-white font-medium truncate">{detection?.camera_label || img.camera_id}</p>
                            </div>
                            {/* Detection count badge */}
                            {boxCount > 0 && (
                              <div className="absolute top-1 right-1 bg-primary text-white min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-[9px] font-bold shadow-sm" title="Estimated fingers detected in this camera view">
                                {boxCount}
                              </div>
                            )}
                          </button>
                        )
                      })}
                    </div>

                    {/* Detection Lightbox Modal */}
                    <Dialog open={showDetectionModal} onOpenChange={setShowDetectionModal}>
                      <DialogContent className="sm:max-w-3xl max-h-[90dvh] flex flex-col gap-0 p-0 overflow-hidden">
                        <DialogHeader className="p-4 pb-3 pr-14 shrink-0 border-b">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <Target className="w-4 h-4 text-primary shrink-0" />
                              <DialogTitle className="text-sm font-bold truncate">YOLO Detection</DialogTitle>
                              <Badge variant="secondary" className="text-[9px] px-1.5 py-0 h-4 rounded-full shrink-0">
                                {lastResult.detections.reduce((acc: number, d: ScanDetection) => acc + (d.finger_count || d.bounding_boxes?.length || 0), 0)} boxes
                              </Badge>
                            </div>
                            <button
                              type="button"
                              onClick={() => setShowKioskBoxes(!showKioskBoxes)}
                              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5 px-2.5 py-1 rounded-md hover:bg-muted border border-border/60 shrink-0"
                            >
                              {showKioskBoxes ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                              <span>{showKioskBoxes ? "Hide" : "Show"} Boxes</span>
                            </button>
                          </div>
                          <DialogDescription className="sr-only">Detection bounding box viewer</DialogDescription>
                        </DialogHeader>

                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                          {/* Camera tabs */}
                          <div className="flex gap-1.5">
                            {lastResult.images.map((img: { camera_id: string; file_path: string }, idx: number) => {
                              const det = lastResult.detections?.find((d: ScanDetection) => d.camera_id === img.camera_id)
                              return (
                                <button
                                  key={img.camera_id}
                                  onClick={() => setKioskActiveDetImg(idx)}
                                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                                    kioskActiveDetImg === idx
                                      ? 'bg-primary text-primary-foreground shadow-sm'
                                      : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
                                  }`}
                                >
                                  {det?.camera_label || img.camera_id}
                                  {det?.bounding_boxes && det.bounding_boxes.length > 0 && (
                                    <span title="Estimated fingers detected in this camera view" className={`min-w-[16px] h-4 flex items-center justify-center rounded-full text-[9px] font-bold ${
                                      kioskActiveDetImg === idx ? 'bg-white/20 text-white' : 'bg-primary/10 text-primary'
                                    }`}>
                                      {det.finger_count || det.bounding_boxes.length}
                                    </span>
                                  )}
                                </button>
                              )
                            })}
                          </div>

                          {/* Active detection image */}
                          {lastResult.images[kioskActiveDetImg] && (() => {
                            const activeImg = lastResult.images![kioskActiveDetImg]
                            const activeDet = lastResult.detections?.find((d: ScanDetection) => d.camera_id === activeImg.camera_id)
                            const activeBoxes: BoundingBox[] = showKioskBoxes ? (activeDet?.bounding_boxes || []) : []
                            const activeUrl = activeImg.file_path.startsWith('http') ? activeImg.file_path : getImageUrl(activeImg.file_path)
                            return (
                              <div className="rounded-xl overflow-hidden border border-border relative">
                                <BoundingBoxOverlay
                                  src={activeUrl}
                                  alt={`${activeImg.camera_id} detection expanded`}
                                  boxes={activeBoxes}
                                  className="w-full"
                                  showLabels={true}
                                  showConfidence={true}
                                />
                              </div>
                            )
                          })()}
                        </div>
                      </DialogContent>
                    </Dialog>
                  </>
                )}

                {/* QR Code Preview */}
                {lastResult.qrCode && (
                  <div className="flex items-center gap-3 bg-muted/30 rounded-xl p-3 border border-border">
                    <div className="bg-white rounded-lg p-1.5 border shadow-sm shrink-0">
                      <img src={lastResult.qrCode} alt="QR Code" className="w-14 h-14 lg:w-16 lg:h-16" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        QR Code Generated
                      </div>
                      <p className="text-[10px] text-muted-foreground font-mono uppercase mt-0.5">{lastResult.id}</p>
                    </div>
                  </div>
                )}

                {/* Action Buttons — Accept / Reject only */}
                {lastResult.printJob && <KioskPrintStatus
                  key={`${lastResult.id}:${lastResult.printJob.id}`}
                  scanId={lastResult.id} initialJob={lastResult.printJob} />}
                {lastResult.printError && <p role="alert" className="text-xs text-destructive">{lastResult.printError}</p>}
                <div className="flex gap-3 pt-2">
                  <Button
                    size="lg"
                    disabled={lastResult.id === scanAction?.id || flaggingScan || Boolean(cultivarConflict)}
                    title={cultivarConflict ? "Cameras disagree on the cultivar. Flag this scan for review or correct it in Scan Logs." : undefined}
                    className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-white gap-2 font-bold h-12 lg:h-14 text-sm lg:text-base"
                    onClick={() => {
                      if (lastResult && lastResult.id !== scanAction?.id) {
                        setScanAction({ id: lastResult.id, action: 'accepted' })
                        toast.success("Scan accepted", {
                          description: "Result recorded. No further action is needed.",
                        })
                      }
                    }}
                  >
                    <CheckCircle2 className="w-4 h-4 lg:w-5 lg:h-5" />
                    {cultivarConflict ? "Review required" : lastResult.id === scanAction?.id && scanAction?.action === 'accepted' ? "Accepted" : "Accept"}
                  </Button>
                  <Button
                    size="lg"
                    variant="outline"
                    disabled={lastResult.id === scanAction?.id || flaggingScan}
                    className="flex-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/20 gap-2 font-bold h-12 lg:h-14 text-sm lg:text-base"
                    onClick={async () => {
                      if (lastResult && lastResult.id !== scanAction?.id && !flaggingScan) {
                        setFlaggingScan(true)
                        try {
                          await flagScan(lastResult.id, true)
                          setScanAction({ id: lastResult.id, action: 'flagged' })
                          toast.success("Flagged for review", { description: "Item routed to quality control dashboard." })
                        } catch (error) {
                          toast.error(error instanceof Error ? error.message : "Failed to flag scan", { action: scanRetryAction(error, () => setScanAction({ id: lastResult.id, action: "flagged" })) })
                        } finally {
                          setFlaggingScan(false)
                        }
                      }
                    }}
                  >
                    {flaggingScan ? (
                      <Loader2 className="w-4 h-4 lg:w-5 lg:h-5 animate-spin" />
                    ) : (
                      <Flag className="w-4 h-4 lg:w-5 lg:h-5" />
                    )}
                    {flaggingScan ? "Flagging..." : lastResult.id === scanAction?.id && scanAction?.action === 'flagged' ? "Flagged" : "Flag for Review"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : rejection?.code === OOD_REJECTED ? (
            <Card role="status" className="bg-card border-border rounded-2xl shrink-0 animate-fade-in">
              <CardContent className="p-8 lg:p-12 text-center">
                <div className="w-16 h-16 rounded-full bg-amber-500/10 flex items-center justify-center mx-auto mb-4 border border-amber-500/30">
                  <SearchX className="w-8 h-8 text-amber-500" aria-hidden="true" />
                </div>
                <p className="text-sm font-semibold">No Lakatan, Latundan, or Cardaba detected</p>
                <p className="text-muted-foreground text-xs mt-1">Place a supported banana hand on the tray and scan again.</p>
                <p className="text-muted-foreground text-xs mt-1">Nothing was saved.</p>
              </CardContent>
            </Card>
          ) : rejection ? (
            <Card role="alert" className="bg-card border-border rounded-2xl shrink-0 animate-fade-in">
              <CardContent className="p-8 lg:p-12 text-center">
                <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mx-auto mb-4 border border-destructive/30">
                  <TriangleAlert className="w-8 h-8 text-destructive" aria-hidden="true" />
                </div>
                <p className="text-sm font-semibold">Scan could not run</p>
                <p className="text-muted-foreground text-xs mt-1">{rejection.message}</p>
                <p className="text-muted-foreground text-xs mt-1">Nothing was saved.</p>
              </CardContent>
            </Card>
          ) : (
            <Card className="bg-card border-border rounded-2xl shrink-0">
              <CardContent className="p-8 lg:p-12 text-center">
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mx-auto mb-4 border border-border">
                  <ScanLine className="w-8 h-8 text-muted-foreground/50" />
                </div>
                <p className="text-muted-foreground text-sm font-medium">No scans yet</p>
                <p className="text-muted-foreground/60 text-xs mt-1">Ready to scan items</p>
              </CardContent>
            </Card>
          )}

          {/* Recent Scans */}
          <div className="flex-1 min-h-0">
            <div className="flex items-center justify-between mb-3 px-1">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Recent Scans</h3>
              <span className="text-[10px] text-muted-foreground/60">{recentScans.length} shown</span>
            </div>
            <div className="space-y-2 overflow-y-auto max-h-75 lg:max-h-none kiosk-scroll">
              {recentScans.length === 0 ? (
                <p className="text-center text-muted-foreground/50 text-xs py-6">No recent scans</p>
              ) : (
                recentScans.map((scan, i) => {
                  const conflict = cultivarCameraConflict(scan)
                  return (
                    <Card
                      key={scan.id}
                      className="bg-card border-border rounded-xl animate-fade-in-row"
                      style={{ animationDelay: `${i * 40}ms` }}
                    >
                      <CardContent className="p-3 flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${scan.ripeness === "Unripe" ? "bg-emerald-500/20 text-emerald-600" :
                          scan.ripeness === "Ripe" ? "bg-yellow-500/20 text-yellow-600" :
                            scan.ripeness === "Overripe" ? "bg-red-500/20 text-red-600" : "bg-violet-500/20 text-violet-600"
                          }`}>
                          <Banana className="w-4 h-4" aria-hidden="true" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold">{conflict ? "Uncertain" : scan.cultivar}</span>
                            <AppStatusBadge type="ripeness" status={scan.ripeness} size="sm" />
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {new Date(scan.dateTime).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila" })} · {conflict ? "Review needed" : scan.confidence === null ? "Unknown confidence" : `${scan.confidence}% confidence`}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="flex flex-col items-end">
                            <p className="text-sm font-bold text-rose-500">{conflict ? "—" : estimateText((scan.inventoryStatus === "In Stock" ? liveShelfLifeLabel(scan, currentTime.getTime()) : null) ?? formatSpoilageDays(scan.spoilageDays))}</p>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">{fingerCountText(scan.fingerCount, fingerCountIsEstimate(scan))}</p>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
