import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
import { useAdmin } from "@/context/AdminContext"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { BASE_URL, api } from "@/lib/api"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp"
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
  ChevronLeft,
  ChevronRight,
} from "lucide-react"
import { toast } from "sonner"
import { AppStatusBadge } from "@/components/AppStatusBadge"

const ripenessIcon: Record<string, string> = {
  Unripe: "🟢",
  "Semi Ripe": "🟠",
  Ripe: "🟡",
  Overripe: "🔴",
}



export default function Kiosk() {
  const { user, switchOperator, changePinAndLogin } = useAuth()
  const { scanState, startScan, scans, flagScan } = useScans()
  const { suppliers, activeIntake, startIntake } = useInventory()
  const { users, config } = useAdmin()
  const { isScanning, scanStep, scanProgress, lastResult } = scanState
  const [currentTime, setCurrentTime] = useState(new Date())
  const activeSuppliers = suppliers.filter(s => s.status === "Active")
  const [showSourceModal, setShowSourceModal] = useState(false)
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null)
  const [selectedTreatment, setSelectedTreatment] = useState<"Natural" | "Ethephon">("Natural")

  const [kioskOperatorsList, setKioskOperatorsList] = useState<{ id: string; username: string; fullName: string; role: string; status: string; avatar?: string }[]>([])
  const [kioskOperator, setKioskOperator] = useState<string | null>(null)

  // Fetch operators from public endpoint on mount (no auth required).
  // This ensures the kiosk selection modal is populated even on fresh sessions.
  useEffect(() => {
    api.auth.kioskOperators()
      .then((ops) => {
        setKioskOperatorsList(ops.map(o => ({
          id: o.id,
          username: o.username,
          fullName: o.full_name,
          role: o.role,
          status: o.status,
          avatar: o.avatar_url,
        })))
      })
      .catch((err) => console.warn("[Kiosk] Failed to fetch operators", err))
  }, [])

  // Use the publicly-fetched list; fall back to AdminContext users if populated
  const adminOperators = users.filter(u => u.status === "Active" && u.role === "Operator")
  const activeOperators = kioskOperatorsList.length > 0 ? kioskOperatorsList : adminOperators
  const [showSwapModal, setShowSwapModal] = useState(true)
  const [swapTarget, setSwapTarget] = useState<string | null>(null)
  const [pinInput, setPinInput] = useState("")
  const [requiresNewPin, setRequiresNewPin] = useState(false)
  const [pinChangeMessage, setPinChangeMessage] = useState("Please set your new secure 4-digit PIN.")
  const [newPinInput, setNewPinInput] = useState("")
  const [confirmPinInput, setConfirmPinInput] = useState("")
  const [scanAction, setScanAction] = useState<{ id: string, action: 'accepted' | 'flagged' } | null>(null)

  // Angle labels for each camera position (expandable for more cameras)
  const cameraAngles = ["Front", "Left", "Right", "Top", "Rear", "Bottom"]

  // Generate cameras dynamically from database configuration
  const cameras = config.cameraIds.split(",").map(s => s.trim()).filter(Boolean).map((id, index) => ({
    id: index + 1,
    label: id,
    angle: cameraAngles[index] || `Angle ${index + 1}`,
  }))

  // --- Live webcam switch state ---
  const [activeCameraIndex, setActiveCameraIndex] = useState(0)

  const goToNextCamera = useCallback(() => {
    if (cameras.length === 0) return
    setActiveCameraIndex(prev => (prev + 1) % cameras.length)
  }, [cameras.length])

  const goToPrevCamera = useCallback(() => {
    if (cameras.length === 0) return
    setActiveCameraIndex(prev => (prev - 1 + cameras.length) % cameras.length)
  }, [cameras.length])

  const selectCamera = useCallback((index: number) => {
    setActiveCameraIndex(index)
  }, [])

  // Clamp activeCameraIndex if cameras change
  useEffect(() => {
    if (cameras.length > 0 && activeCameraIndex >= cameras.length) {
      setActiveCameraIndex(0)
    }
  }, [cameras.length, activeCameraIndex])

  // Determine which camera is actively capturing during scan step 1
  const activeCaptureCamera = isScanning && scanStep === 1
    ? Math.min(cameras.length, Math.floor((scanProgress / 33) * cameras.length) + 1)
    : 0

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
  }

  // Count scans for today
  const todayScansCount = scans.filter(s => new Date(s.dateTime).toDateString() === new Date().toDateString()).length

  return (
    <div className="h-screen flex flex-col bg-background text-foreground overflow-hidden relative">

      {/* Swap Operator Modal */}
      <Dialog open={showSwapModal} onOpenChange={(open) => { if (!open && !kioskOperator) return; setShowSwapModal(open); if (!open) { setSwapTarget(null); setPinInput(""); setRequiresNewPin(false); setNewPinInput(""); setConfirmPinInput(""); } }}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle>{!swapTarget ? (kioskOperator ? "Switch Operator" : "Select Operator to Begin") : requiresNewPin ? "Create New Kiosk PIN" : "Enter PIN"}</DialogTitle>
            {!swapTarget && !kioskOperator && (
              <DialogDescription className="text-sm text-muted-foreground">Please select an operator and authenticate to use the kiosk.</DialogDescription>
            )}
          </DialogHeader>
          {!swapTarget ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
              {activeOperators.map(op => (
                <button
                  key={op.id}
                  onClick={() => setSwapTarget(op.id)}
                  className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-colors ${op.id === user?.id ? 'bg-primary/10 border-primary' : 'bg-muted/50 border-border hover:bg-accent'}`}
                >
                  <Avatar className="w-12 h-12">
                    <AvatarFallback className="bg-primary/10 text-primary font-bold">
                      {op.fullName.split(" ").map(n => n[0]).join("").toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="text-center w-full">
                    <p className="text-xs font-semibold truncate px-1">{op.fullName}</p>
                    <p className="text-[10px] text-muted-foreground">{op.role}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : requiresNewPin ? (
            <div className="mt-4 space-y-4">
              <div className="flex items-center gap-3 p-3 bg-amber-500/10 rounded-xl border border-amber-500/20">
                <Avatar className="w-10 h-10">
                  <AvatarFallback className="bg-amber-500/20 text-amber-600 font-bold">
                    {activeOperators.find(o => o.id === swapTarget)?.fullName.split(" ").map(n => n[0]).join("").toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="text-sm font-semibold">{activeOperators.find(o => o.id === swapTarget)?.fullName}</p>
                  <p className="text-[11px] text-amber-600 font-medium tracking-tight leading-tight">
                    {pinChangeMessage}
                  </p>
                </div>
              </div>
              <div className="space-y-4 pt-2">
                <div className="flex flex-col items-center gap-2 py-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase">{newPinInput.length === 4 ? "Confirm New PIN" : "Create a new 4-digit PIN"}</p>
                  <InputOTP
                    maxLength={4}
                    value={newPinInput.length === 4 ? confirmPinInput : newPinInput}
                    onChange={async (val) => {
                      if (newPinInput.length < 4) {
                        setNewPinInput(val);
                      } else {
                        setConfirmPinInput(val);
                        if (val.length === 4) {
                          if (newPinInput === val) {
                            const targetUser = activeOperators.find(o => o.id === swapTarget);
                            if (!targetUser) return;

                            const success = await changePinAndLogin(targetUser.username, val);

                            if (success) {
                              toast.success(`PIN updated and swapped to ${targetUser.fullName}`);
                              setKioskOperator(targetUser.id);
                              setShowSwapModal(false);
                              setSwapTarget(null);
                              setRequiresNewPin(false);
                              setNewPinInput("");
                              setConfirmPinInput("");
                            } else {
                              toast.error("Failed to update PIN. Try again.");
                              setNewPinInput("");
                              setConfirmPinInput("");
                            }
                          } else {
                            toast.error("PINs do not match. Try again.");
                            setNewPinInput("");
                            setConfirmPinInput("");
                          }
                        }
                      }
                    }}
                    autoFocus
                  >
                    <InputOTPGroup className="gap-2">
                      <InputOTPSlot index={0} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={1} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={2} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={3} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                    </InputOTPGroup>
                  </InputOTP>
                </div>
                <Button variant="ghost" className="w-full text-muted-foreground h-10" onClick={() => { setSwapTarget(null); setPinInput(""); setRequiresNewPin(false); setNewPinInput(""); setConfirmPinInput(""); }}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-xl border">
                <Avatar className="w-10 h-10">
                  <AvatarFallback className="bg-primary/10 text-primary font-bold">
                    {activeOperators.find(o => o.id === swapTarget)?.fullName.split(" ").map(n => n[0]).join("").toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="text-sm font-semibold">{activeOperators.find(o => o.id === swapTarget)?.fullName}</p>
                  <p className="text-xs text-muted-foreground">Please enter 4-digit PIN</p>
                </div>
              </div>
              <div className="space-y-4 pt-2">
                <div className="flex justify-center py-2">
                  <InputOTP
                    maxLength={4}
                    value={pinInput}
                    onChange={async (val) => {
                      setPinInput(val);
                      if (val.length === 4) {
                        const success = await switchOperator(activeOperators.find(o => o.id === swapTarget)?.username || "", val);
                        if (success === "success") {
                          toast.success(`Swapped to ${activeOperators.find(o => o.id === swapTarget)?.fullName}`);
                          setKioskOperator(swapTarget);
                          setShowSwapModal(false);
                          setSwapTarget(null);
                          setPinInput("");
                        } else if (success === "requires_pin_change" || success === "requires_pin_change_new_account" || success === "requires_pin_change_reset") {
                          if (success === "requires_pin_change_new_account") {
                            setPinChangeMessage("Welcome! An Admin created this account. Please set your new secure PIN.");
                          } else if (success === "requires_pin_change_reset") {
                            setPinChangeMessage("Welcome back! Your PIN was recently reset. Please set your new secure PIN.");
                          } else {
                            setPinChangeMessage("Please set a new secure 4-digit PIN to continue.");
                          }
                          setRequiresNewPin(true);
                          setPinInput("");
                        } else if (success === "inactive") {
                          toast.error("Account Inactive", { description: "Your account is inactive. Please contact an administrator." });
                          setPinInput("");
                        } else {
                          toast.error("Invalid PIN code");
                          setPinInput("");
                        }
                      }
                    }}
                    autoFocus
                  >
                    <InputOTPGroup className="gap-2">
                      <InputOTPSlot index={0} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={1} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={2} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      <InputOTPSlot index={3} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                    </InputOTPGroup>
                  </InputOTP>
                </div>
                <Button variant="ghost" className="w-full text-muted-foreground h-10" onClick={() => { setSwapTarget(null); setPinInput(""); }}>
                  Cancel & Back to Users
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Select Source Modal */}
      <Dialog open={showSourceModal} onOpenChange={setShowSourceModal}>
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
                  <span className="text-lg">🌿</span>
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
                  <span className="text-lg">🧪</span>
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
              disabled={!selectedSupplierId}
              onClick={async () => {
                if (!selectedSupplierId) return;
                const generatedBatch = `BCH-${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
                await startIntake(selectedSupplierId, generatedBatch, selectedTreatment);
                toast.success("Started new delivery intake!");
                setShowSourceModal(false);
              }}
            >
              Start Intake Session
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
              {currentTime.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
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
        <div className="lg:flex-3 flex flex-col gap-3 lg:gap-4 shrink-0 lg:shrink lg:min-h-0">
          {/* Main Camera View */}
          <Card className="shrink-0 lg:shrink h-50 sm:h-70 lg:flex-1 lg:h-auto bg-card border-border rounded-2xl overflow-hidden relative lg:min-h-50">
            <CardContent className="p-0 h-full flex flex-col relative">
              {/* Main Feed */}
              <div className="flex-1 w-full flex items-center justify-center relative bg-black rounded-2xl overflow-hidden">
                {isScanning ? (
                  <div className="text-center space-y-4 animate-pulse z-10">
                    <div className="w-20 h-20 lg:w-24 lg:h-24 rounded-full bg-primary/20 flex items-center justify-center mx-auto border-2 border-primary/40">
                      <Loader2 className="w-10 h-10 lg:w-12 lg:h-12 text-primary animate-spin" />
                    </div>
                    <p className="text-white text-sm lg:text-base font-medium drop-shadow-md">{scanState.scanStepLabel}</p>
                  </div>
                ) : (
                  <>
                    {/* Render all camera feeds, only show the active one */}
                    {cameras.map((cam, idx) => (
                      <img
                        key={cam.id}
                        src={`${BASE_URL}/api/v1/cameras/preview/${idx}`}
                        alt={`Live Camera Feed - ${cam.label}`}
                        className={`w-full h-full object-cover transition-opacity duration-500 z-0 absolute ${idx === activeCameraIndex ? 'opacity-90' : 'opacity-0 pointer-events-none'
                          }`}
                        onError={(e) => {
                          if (idx === activeCameraIndex) {
                            e.currentTarget.style.display = 'none';
                            const fallback = e.currentTarget.parentElement?.querySelector('[data-camera-fallback]');
                            if (fallback) (fallback as HTMLElement).style.display = 'flex';
                          }
                        }}
                        onLoad={(e) => {
                          if (idx === activeCameraIndex) {
                            e.currentTarget.style.display = '';
                            const fallback = e.currentTarget.parentElement?.querySelector('[data-camera-fallback]');
                            if (fallback) (fallback as HTMLElement).style.display = 'none';
                          }
                        }}
                      />
                    ))}
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

                {/* Camera cycling controls — bottom overlay */}
                {!isScanning && cameras.length > 1 && (
                  <div className="absolute bottom-3 left-0 right-0 flex items-center justify-center gap-2 z-20">
                    <div className="flex items-center gap-1.5 bg-background/70 backdrop-blur-md rounded-full px-2 py-1.5 border border-border/50 shadow-lg">
                      {/* Prev button */}
                      <button
                        onClick={(e) => { e.stopPropagation(); goToPrevCamera(); }}
                        className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                        title="Previous camera"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>

                      {/* Camera dots */}
                      <div className="flex items-center gap-1.5 px-1">
                        {cameras.map((_, idx) => (
                          <button
                            key={idx}
                            onClick={(e) => { e.stopPropagation(); selectCamera(idx); }}
                            className="w-2.5 h-2.5 rounded-full transition-all duration-300 hover:scale-125"
                            title={cameras[idx]?.label}
                          >
                            <div className={`w-full h-full rounded-full transition-all duration-300 ${idx === activeCameraIndex
                                ? 'bg-primary scale-110'
                                : 'bg-muted-foreground/40 hover:bg-muted-foreground/60'
                              }`} />
                          </button>
                        ))}
                      </div>

                      {/* Next button */}
                      <button
                        onClick={(e) => { e.stopPropagation(); goToNextCamera(); }}
                        className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                        title="Next camera"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Camera counter — top right */}
                {!isScanning && cameras.length > 1 && (
                  <div className="absolute top-3 right-3 z-20">
                    <Badge variant="outline" className="bg-background/80 backdrop-blur-sm border-border text-xs gap-1.5 py-1">
                      <Camera className="w-3 h-3" />
                      {cameras[activeCameraIndex]?.angle}
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

          {/* Camera Status Indicators — clickable to switch live view */}
          <div className={`grid gap-2 lg:gap-3 shrink-0 ${cameras.length > 4 ? 'grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6' : 'grid-cols-2 sm:grid-cols-4'}`}>
            {cameras.length === 0 ? (
              <div className="col-span-full text-center text-muted-foreground text-xs py-4 border rounded-xl border-dashed">
                No cameras configured. Go to Settings to add cameras.
              </div>
            ) : cameras.map((cam, idx) => {
              const isCapturing = isScanning && scanStep === 1 && activeCaptureCamera === cam.id
              const isCaptured = isScanning && scanStep === 1 && activeCaptureCamera > cam.id
              const isDoneCapture = isScanning && scanStep > 1
              const isActiveView = !isScanning && idx === activeCameraIndex

              // Find the captured image for this camera from the last scan result
              const scanImage = !isScanning && lastResult?.images?.find(i => i.camera_id === String(cam.label) || i.camera_id === String(cam.id))?.file_path

              return (
                <button
                  key={cam.id}
                  onClick={() => { if (!isScanning) selectCamera(idx); }}
                  className={`relative aspect-video rounded-xl border-2 transition-all duration-300 overflow-hidden flex items-center justify-center bg-card ${isCapturing
                      ? "border-primary shadow-lg shadow-primary/30 ring-2 ring-primary/20"
                      : isActiveView
                        ? "border-primary/60 ring-1 ring-primary/20 shadow-md shadow-primary/10"
                        : (isCaptured || isDoneCapture || scanImage)
                          ? "border-emerald-500/40"
                          : "border-border hover:border-primary/30 hover:shadow-sm"
                    } ${!isScanning ? 'cursor-pointer active:scale-95' : ''}`}
                  disabled={isScanning}
                >
                  {/* Camera content — prominent position number */}
                  {scanImage ? (
                    <img src={scanImage} alt={cam.label} className="w-full h-full object-cover" />
                  ) : (
                    <div className="text-center flex flex-col items-center justify-center">
                      {isCapturing ? (
                        <Loader2 className="w-5 h-5 lg:w-6 lg:h-6 text-primary animate-spin" />
                      ) : (isCaptured || isDoneCapture) ? (
                        <CheckCircle2 className="w-5 h-5 lg:w-6 lg:h-6 text-emerald-500" />
                      ) : (
                        <span className={`text-xs lg:text-sm font-bold transition-colors leading-tight ${isActiveView ? 'text-primary' : 'text-muted-foreground/30'
                          }`}>{cam.angle}</span>
                      )}
                    </div>
                  )}

                  {/* Label */}
                  <div className="absolute bottom-1 left-1 right-1 flex items-center justify-between">
                    <span className={`text-[9px] lg:text-[10px] font-medium transition-colors ${isActiveView ? 'text-primary' : 'text-muted-foreground'
                      }`}>{cam.label}</span>
                    <div className={`w-1.5 h-1.5 rounded-full ${isCapturing ? "bg-red-500 animate-pulse"
                        : isActiveView ? "bg-primary animate-pulse"
                          : (isCaptured || isDoneCapture) ? "bg-emerald-500"
                            : "bg-emerald-500/50"
                      }`} />
                  </div>

                  {/* Active view indicator with position number */}
                  {isActiveView && (
                    <div className="absolute top-1 right-1">
                      <div className="w-4 h-4 rounded-full bg-primary/20 flex items-center justify-center">
                        <Camera className="w-2.5 h-2.5 text-primary" />
                      </div>
                    </div>
                  )}

                  {/* Capturing pulse ring */}
                  {isCapturing && (
                    <div className="absolute inset-0 rounded-[10px] border-2 border-primary animate-ping opacity-20 pointer-events-none" />
                  )}
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
              disabled={isScanning || !activeIntake || !kioskOperator}
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
        <div className="lg:flex-2 flex flex-col gap-4 shrink-0 lg:shrink lg:min-h-0 lg:overflow-y-auto kiosk-scroll">

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
                      <p className="text-sm font-bold">Scan Complete</p>
                      <p className="text-[10px] text-muted-foreground">{new Date(lastResult.dateTime).toLocaleTimeString()}</p>
                    </div>
                  </div>
                  <AppStatusBadge type="ripeness" status={lastResult.ripeness} size="lg" />
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-primary/10 rounded-xl p-3 text-center border border-primary/20">
                    <Banana className="w-5 h-5 text-primary mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Cultivar</p>
                    <p className="text-lg font-bold text-primary">{lastResult.cultivar}</p>
                  </div>
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Target className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Confidence</p>
                    <p className="text-lg font-bold">{lastResult.confidence}%</p>
                    <Progress value={lastResult.confidence} className="h-1 mt-1.5" />
                  </div>
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <CalendarClock className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Est. Spoilage</p>
                    <p className="text-lg font-bold">
                      {lastResult.spoilageDays} <span className="text-xs text-muted-foreground">days</span>
                    </p>
                  </div>
                  <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                    <Hand className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Est. Fingers</p>
                    <p className="text-lg font-bold">{lastResult.fingerCount}</p>
                  </div>
                  {lastResult.temperature !== undefined && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-xl mx-auto mb-1">🌡️</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p>
                      <p className="text-lg font-bold">{lastResult.temperature}°C</p>
                    </div>
                  )}
                  {lastResult.humidity !== undefined && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-xl mx-auto mb-1">💧</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Humidity</p>
                      <p className="text-lg font-bold">{lastResult.humidity}%</p>
                    </div>
                  )}
                  {lastResult.dewPoint !== undefined && lastResult.dewPoint !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-xl mx-auto mb-1">🌫️</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dew Point</p>
                      <p className="text-lg font-bold">{lastResult.dewPoint}°C</p>
                    </div>
                  )}
                  {lastResult.vpd !== undefined && lastResult.vpd !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-xl mx-auto mb-1">💨</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">VPD</p>
                      <p className="text-lg font-bold">{lastResult.vpd} kPa</p>
                    </div>
                  )}
                  {lastResult.heatIndex !== undefined && lastResult.heatIndex !== null && (
                    <div className="bg-muted/50 rounded-xl p-3 text-center border border-border">
                      <p className="text-xl mx-auto mb-1">🔥</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Heat Index</p>
                      <p className="text-lg font-bold">{lastResult.heatIndex}°C</p>
                    </div>
                  )}
                </div>


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
                <div className="flex gap-3 pt-2">
                  <Button
                    size="lg"
                    disabled={lastResult.id === scanAction?.id}
                    className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-white gap-2 font-bold h-12 lg:h-14 text-sm lg:text-base"
                    onClick={() => {
                      if (lastResult && lastResult.id !== scanAction?.id) {
                        setScanAction({ id: lastResult.id, action: 'accepted' })
                        toast.success("Scan accepted", { description: "Result saved to intake." })
                      }
                    }}
                  >
                    <CheckCircle2 className="w-4 h-4 lg:w-5 lg:h-5" />
                    {lastResult.id === scanAction?.id && scanAction?.action === 'accepted' ? "Accepted" : "Accept"}
                  </Button>
                  <Button
                    size="lg"
                    variant="outline"
                    disabled={lastResult.id === scanAction?.id}
                    className="flex-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/20 gap-2 font-bold h-12 lg:h-14 text-sm lg:text-base"
                    onClick={() => {
                      if (lastResult && lastResult.id !== scanAction?.id) {
                        flagScan(lastResult.id, true)
                        setScanAction({ id: lastResult.id, action: 'flagged' })
                        toast.success("Flagged for review", { description: "Item routed to quality control dashboard." })
                      }
                    }}
                  >
                    <Flag className="w-4 h-4 lg:w-5 lg:h-5" />
                    {lastResult.id === scanAction?.id && scanAction?.action === 'flagged' ? "Flagged" : "Flag for Review"}
                  </Button>
                </div>
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
                recentScans.map((scan, i) => (
                  <Card
                    key={scan.id}
                    className="bg-card border-border rounded-xl animate-fade-in-row"
                    style={{ animationDelay: `${i * 40}ms` }}
                  >
                    <CardContent className="p-3 flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm shrink-0 ${scan.ripeness === "Unripe" ? "bg-emerald-500/20" :
                          scan.ripeness === "Ripe" ? "bg-yellow-500/20" :
                            scan.ripeness === "Overripe" ? "bg-red-500/20" : "bg-violet-500/20"
                        }`}>
                        {ripenessIcon[scan.ripeness]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold">{scan.cultivar}</span>
                          <AppStatusBadge type="ripeness" status={scan.ripeness} size="sm" />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {new Date(scan.dateTime).toLocaleTimeString()} · {scan.confidence}% confidence
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="flex flex-col items-end">
                          <p className="text-sm font-bold text-rose-500">{scan.spoilageDays} days</p>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{scan.fingerCount} fingers</p>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
