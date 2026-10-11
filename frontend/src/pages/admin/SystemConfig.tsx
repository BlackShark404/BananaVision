import { useState, useEffect, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import { StationBackupControls } from "@/components/StationBackupControls"
import { Input } from "@/components/ui/input"
import type { MaintenanceStatus } from "@/types/api"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Settings, Save, RefreshCw, Cpu, Database, Camera, Power, Download, Edit2, AlertTriangle, Undo2 } from "lucide-react"
import { toast } from "sonner"
import {
  Alert,
  AlertTitle,
  AlertDescription
} from "@/components/ui/alert"
import { CameraCalibrationModal } from "@/components/CameraCalibrationModal"

export default function SystemConfig() {
  const { config, updateConfig, configReady, configError, configConflict, reloadConfig, acceptConfig } = useAdmin()
  const [localConfig, setLocalConfig] = useState(config)
  const previousConfig = useRef(config)
  const [maintenance, setMaintenance] = useState<MaintenanceStatus | null>(null)
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [powerPending, setPowerPending] = useState(false)
  const [powerAccepted, setPowerAccepted] = useState(false)
  const [powerMessage, setPowerMessage] = useState("")
  const [recoveryPassword, setRecoveryPassword] = useState("")
  const powerId = useRef<string | null>(null)
  const powerFlight = useRef(false)
  const configFlight = useRef(false)
  const disabled = !configReady || configConflict || archiveBusy || powerPending || powerAccepted || Boolean(maintenance && maintenance.state !== "ready")
  useEffect(() => {
    let live = true
    let seq = 0
    const refresh = async () => {
      const mySeq = ++seq
      try {
        const result = await api.config.maintenance()
        if (live && mySeq === seq) { setMaintenance(result); setMaintenanceError(null) }
      } catch {
        if (live && mySeq === seq) setMaintenanceError("Maintenance status unavailable")
      }
      if (live) setTimeout(refresh, 5000)
    }
    void refresh()
    return () => { live = false }
  }, [])
  const [saving, setSaving] = useState(false)
  const [showShutdownDialog, setShowShutdownDialog] = useState(false)
  const [showRestartDialog, setShowRestartDialog] = useState(false)
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null)
  const [editCameraValue, setEditCameraValue] = useState("")

  useEffect(() => {
    const previous = previousConfig.current
    previousConfig.current = config
    setLocalConfig(draft => ({
      ...config,
      cameraIds: draft.cameraIds === previous.cameraIds ? config.cameraIds : draft.cameraIds,
      confidenceThreshold: draft.confidenceThreshold === previous.confidenceThreshold ? config.confidenceThreshold : draft.confidenceThreshold,
      dataRetentionEnabled: draft.dataRetentionEnabled === previous.dataRetentionEnabled ? config.dataRetentionEnabled : draft.dataRetentionEnabled,
    }))
  }, [config])

  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)

  const activeCameraIds = localConfig.cameraIds.split(",").map(s => s.trim()).filter(Boolean)

  const startEditingCameraId = (idToEdit: string) => {
    if (disabled || saving) return
    setEditingCameraId(idToEdit)
    setEditCameraValue(idToEdit)
  }

  const saveEditedCameraId = () => {
    if (editingCameraId) {
      const trimmed = editCameraValue.trim()
      
      if (!trimmed || trimmed.length > 50 || trimmed.includes(",")) {
        toast.error("Camera ID cannot be empty", { description: "Please provide a valid camera name." })
        setEditingCameraId(null)
        return
      }

      if (trimmed === editingCameraId) {
        // No change
        setEditingCameraId(null)
        return
      }

      const otherIds = activeCameraIds.filter(id => id !== editingCameraId)
      if (otherIds.includes(trimmed)) {
        toast.error("Camera ID already exists", { description: "Cannot have duplicate camera IDs." })
        setEditingCameraId(null)
        return
      }

      const newIds = activeCameraIds.map(id => id === editingCameraId ? trimmed : id)
      setLocalConfig({ ...localConfig, cameraIds: newIds.join(", ") })
      setEditingCameraId(null)
    }
  }

  const handleSave = async () => {
    if (disabled || configFlight.current) return
    configFlight.current = true
    setSaving(true)
    try {
      const saved = await updateConfig(localConfig)
      setLocalConfig(saved)
      toast.success("Settings saved successfully", { description: saved.applicationError ?? "Applied to subsequent operations" })
    } catch (error) {
      toast.error("Settings could not be saved", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      configFlight.current = false
      setSaving(false)
    }
  }

  const handleUndo = () => {
    setLocalConfig(config)
    toast.info("Changes discarded")
  }

  const handleReset = () => {
    setLocalConfig({ ...config, cameraIds: (config.cameraDeviceIds ?? [0, 1]).map((_, index) => `CAM-${String(index + 1).padStart(3, "0")}`).join(", "), confidenceThreshold: 85, dataRetentionEnabled: true })
    toast.info("Settings reset to defaults")
  }

  const handleExportData = async () => {
    try {
      await api.config.export()
      toast.success("Scan summaries exported", { description: "CSV download started" })
    } catch {
      toast.error("Export Failed", { description: "Could not export scan summaries" })
    }
  }

  const toggleDataRetention = async () => {
    if (disabled || configFlight.current) return
    configFlight.current = true
    const newState = !localConfig.dataRetentionEnabled
    const draft = localConfig
    setSaving(true)
    try {
      const saved = await updateConfig({ dataRetentionEnabled: newState })
      // Retention saves independently; keep unsaved camera/threshold edits.
      setLocalConfig({ ...draft, dataRetentionEnabled: saved.dataRetentionEnabled })
      toast.success(
        saved.dataRetentionEnabled ? "Data Retention Enabled" : "Data Retention Disabled",
        { description: saved.dataRetentionEnabled ? `Unreferenced captures older than ${config.retentionDays} days will be cleaned; scan history is retained` : "Automatic orphan capture cleanup is disabled" }
      )
    } catch (error) {
      toast.error("Data retention could not be updated", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      configFlight.current = false
      setSaving(false)
    }
  }

  const handlePower = async (action: "restart" | "shutdown") => {
    if (powerFlight.current || disabled) return
    powerFlight.current = true; setPowerPending(true)
    powerId.current ??= crypto.randomUUID()
    try {
      const result = await api.config[action](powerId.current)
      setPowerMessage(result.message ?? `Power request ${result.status}`)
      if (result.status === "accepted" || result.status === "unknown" || result.status === "dispatching") {
        setPowerAccepted(true)
        setShowRestartDialog(false); setShowShutdownDialog(false)
      } else { toast.error(result.message ?? "Power request failed"); powerId.current = null }
    } catch (error) {
      setPowerMessage(error instanceof Error ? error.message : "Power outcome unavailable. Check operation status before retrying.")
    } finally { powerFlight.current = false; setPowerPending(false) }
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="mb-2">
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          <Settings className="w-6 h-6 sm:w-7 sm:h-7" /> System Configuration
        </h1>
        <p className="text-muted-foreground text-xs sm:text-sm mt-1">Manage global BananaVision settings</p>
      </div>

      {(!configReady || configError || configConflict) && <Alert>
        <AlertTitle>{configConflict ? "Configuration changed elsewhere" : configError ?? "Loading configuration…"}</AlertTitle>
        <AlertDescription>Your draft is preserved. Reload saved settings before making changes.</AlertDescription>
        <Button variant="outline" disabled={saving} onClick={() => void reloadConfig()}>{configConflict ? "Reload saved settings" : "Retry configuration"}</Button>
      </Alert>}
      {configReady && <p className="text-xs text-muted-foreground">Saved revision {config.revision} · Cameras {config.applicationStatus}. {config.applicationError} Threshold applies to the next scan. Deployment model changes require a backend restart.</p>}
      {configReady && config.applicationStatus !== "applied" && <Button variant="outline" disabled={disabled || saving} onClick={async () => {
        setSaving(true)
        try { acceptConfig(await api.config.applyCameras(crypto.randomUUID())) }
        catch (error) { toast.error(error instanceof Error ? error.message : "Camera application failed") }
        finally { setSaving(false) }
      }}>Retry Applying Cameras</Button>}
      {hasChanges && (
        <div className="fixed bottom-4 sm:bottom-6 left-0 right-0 flex justify-center px-4 z-50 pointer-events-none">
          <Alert className="bg-amber-500/10 text-amber-600 border-amber-500/30 w-full max-w-xl animate-in slide-in-from-bottom-5 fade-in duration-300 py-3 sm:py-4 px-4 sm:px-5 shadow-xl shadow-amber-500/10 backdrop-blur-md pointer-events-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 !pr-4 sm:!pr-5">
            <div className="flex items-start gap-3 w-full sm:w-auto">
              <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
              <div className="flex flex-col gap-1">
                <AlertTitle className="text-sm font-bold mb-0 leading-none">Unsaved Changes</AlertTitle>
                <AlertDescription className="text-amber-600/90 text-xs font-medium leading-tight">
                  You have pending configuration changes.
                </AlertDescription>
              </div>
            </div>
            <div className="flex gap-2 items-center shrink-0 w-full sm:w-auto mt-1 sm:mt-0">
              <Button size="sm" variant="outline" onClick={handleUndo} disabled={saving || disabled} className="flex-1 sm:flex-none h-8 px-4 text-xs font-semibold bg-background/50 border-amber-500/40 hover:bg-amber-500/20 hover:text-amber-700 text-amber-700">
                Discard
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving || disabled} className="flex-1 sm:flex-none h-8 px-4 text-xs font-semibold shadow-sm text-amber-50 bg-amber-600 hover:bg-amber-700 border-none">
                {saving ? "Saving..." : "Save Now"}
              </Button>
            </div>
          </Alert>
        </div>
      )}

      <Tabs defaultValue="scanner" orientation="vertical" className="flex flex-col md:flex-row gap-4 sm:gap-6 w-full">
        <TabsList className="flex !flex-row md:!flex-col h-auto justify-start items-stretch rounded-xl sm:rounded-2xl bg-muted/50 p-1.5 sm:p-2 shrink-0 !w-full md:!w-60 overflow-x-auto overflow-y-hidden snap-x gap-1 sm:gap-1.5 border border-muted/50 no-scrollbar">
          <TabsTrigger value="scanner" className="justify-start px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm whitespace-nowrap snap-start shrink-0 !w-auto md:!w-full">
            <Camera className="w-4 h-4 mr-2 shrink-0" /> Scanner Config
          </TabsTrigger>
          <TabsTrigger value="ai" className="justify-start px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm whitespace-nowrap snap-start shrink-0 !w-auto md:!w-full">
            <Cpu className="w-4 h-4 mr-2 shrink-0" /> AI Settings
          </TabsTrigger>
          <TabsTrigger value="data" className="justify-start px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm whitespace-nowrap snap-start shrink-0 !w-auto md:!w-full">
            <Database className="w-4 h-4 mr-2 shrink-0" /> Data Storage
          </TabsTrigger>
          <TabsTrigger value="power" className="justify-start px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm whitespace-nowrap snap-start shrink-0 !w-auto md:!w-full">
            <Power className="w-4 h-4 mr-2 shrink-0" /> System Power
          </TabsTrigger>
        </TabsList>

        <div className="flex-1 w-full min-w-0">

        <TabsContent value="scanner" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Hardware Integration</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Configure camera devices for banana scanning.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 px-4 sm:px-6">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-sm">Active Camera IDs</Label>
                  <div className="flex flex-wrap gap-2 mb-2 p-3 min-h-12 border rounded-xl bg-muted/20">
                    {activeCameraIds.length === 0 && (
                      <span className="text-sm text-muted-foreground italic flex items-center">No cameras configured</span>
                    )}
                    {activeCameraIds.map(id => (
                      <Badge key={id} variant="secondary" className="px-2.5 py-1 text-xs sm:text-sm rounded-lg flex items-center gap-1.5 font-medium border bg-background group">
                        {editingCameraId === id ? (
                          <input 
                            value={editCameraValue} 
                            onChange={e => setEditCameraValue(e.target.value)} 
                            onBlur={saveEditedCameraId}
                            onKeyDown={e => e.key === "Enter" && saveEditedCameraId()}
                            autoFocus
                            className="bg-transparent border-b border-primary/50 outline-none w-20 px-1 text-center"
                          />
                        ) : (
                          <>
                            <span 
                              onClick={() => startEditingCameraId(id)} 
                              className="cursor-pointer hover:text-primary transition-colors"
                              title="Click to edit"
                            >
                              {id}
                            </span>
                            <div className="flex items-center">
                              <button 
                                onClick={() => startEditingCameraId(id)}
                                className="hover:bg-muted/80 rounded-full p-0.5 text-muted-foreground hover:text-foreground transition-colors mr-0.5"
                                title="Edit"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </>
                        )}
                      </Badge>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">These cameras capture in parallel, with sequential fallback when needed.</p>
                <div className="pt-2">
                  <CameraCalibrationModal disabled={saving || disabled} />
                </div>
              </div>
            </CardContent>
            <CardFooter className="bg-muted/30 border-t px-4 sm:px-6 py-3 sm:py-4 flex flex-col sm:flex-row justify-between gap-3 sm:gap-0 rounded-b-xl sm:rounded-b-2xl">
              <Button variant="ghost" disabled={saving || disabled} onClick={handleReset} className="w-full sm:w-auto">
                <RefreshCw className="w-4 h-4 mr-2" /> Reset Defaults
              </Button>
              <div className="flex flex-col sm:flex-row gap-2 sm:gap-3 w-full sm:w-auto">
                {hasChanges && (
                  <Button variant="outline" onClick={handleUndo} disabled={saving || disabled} className="w-full sm:w-auto text-muted-foreground hover:text-foreground">
                    <Undo2 className="w-4 h-4 mr-2" /> Undo Changes
                  </Button>
                )}
                <Button onClick={handleSave} disabled={saving || disabled || !hasChanges} className="w-full sm:w-auto">
                  {saving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Changes</>}
                </Button>
              </div>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="ai" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">YOLO26 Detection Parameters</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Tune the AI model confidence and detection thresholds.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 px-4 sm:px-6">
              <div className="space-y-4">
                <div className="flex justify-between">
                  <Label className="text-sm">Minimum Confidence Threshold</Label>
                  <span className="font-bold text-primary">{localConfig.confidenceThreshold}%</span>
                </div>
                <Slider 
                  value={[localConfig.confidenceThreshold]} 
                  onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}
                  min={1}
                  disabled={saving || disabled}
                  max={100} 
                  step={1} 
                  className="w-full"
                />
                <p className="text-xs text-muted-foreground">
                  Detections below {localConfig.confidenceThreshold}% will be ignored and not recorded. 
                  Higher values reduce false positives.
                </p>
              </div>
            </CardContent>
            <CardFooter className="bg-muted/30 border-t px-4 sm:px-6 py-3 sm:py-4 flex flex-col sm:flex-row justify-between gap-3 sm:gap-0 rounded-b-xl sm:rounded-b-2xl">
              <Button variant="ghost" disabled={saving || disabled} onClick={handleReset} className="w-full sm:w-auto">
                <RefreshCw className="w-4 h-4 mr-2" /> Reset Defaults
              </Button>
              <div className="flex flex-col sm:flex-row gap-2 sm:gap-3 w-full sm:w-auto">
                {hasChanges && (
                  <Button variant="outline" onClick={handleUndo} disabled={saving || disabled} className="w-full sm:w-auto text-muted-foreground hover:text-foreground">
                    <Undo2 className="w-4 h-4 mr-2" /> Undo Changes
                  </Button>
                )}
                <Button onClick={handleSave} disabled={saving || disabled || !hasChanges} className="w-full sm:w-auto">
                  {saving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Changes</>}
                </Button>
              </div>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="data" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Storage Management</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Protect station history and manage unreferenced captures.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Data Retention</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Clean unreferenced captures older than {config.retentionDays ?? "—"} days; retain scan records and referenced evidence</p>
                </div>
                <Button 
                  variant={localConfig.dataRetentionEnabled ? "default" : "outline"} 
                  onClick={toggleDataRetention} 
                  disabled={saving || disabled}
                  className="w-full sm:w-auto"
                >
                  {localConfig.dataRetentionEnabled ? "Enabled" : "Disabled"}
                </Button>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Export Scan Summaries</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Download scan summaries as CSV. Accounts, settings, audit logs and images are excluded; this export cannot restore the database.</p>
                </div>
                <Button variant="outline" onClick={handleExportData} className="w-full sm:w-auto">
                  <Download className="w-4 h-4 mr-2" /> Export CSV
                </Button>
              </div>
              <StationBackupControls disabled={disabled || saving} onBusy={setArchiveBusy} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="power" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Power Management</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Control the mini PC power state.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">System Status</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">{powerMessage || maintenanceError || `Station ${maintenance?.state ?? "status loading"}`}</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-sm font-medium text-emerald-600">{maintenance?.state ?? "Loading"}</span>
                </div>
              </div>
              
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Restart System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Reboot the mini PC. Services resume if host autostart is configured.</p>
                </div>
                <Button variant="outline" className="w-full sm:w-auto gap-2" disabled={disabled || saving} onClick={() => { powerId.current = null; setShowRestartDialog(true) }}>
                  <RefreshCw className="w-4 h-4" />
                  Restart
                </Button>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-destructive/20 bg-destructive/5">
                <div>
                  <h4 className="font-medium text-destructive text-sm sm:text-base">Shutdown System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Power off the mini PC</p>
                </div>
                <Button variant="destructive" disabled={disabled || saving} onClick={() => { powerId.current = null; setShowShutdownDialog(true) }} className="w-full sm:w-auto gap-2">
                  <Power className="w-4 h-4" />
                  Shutdown
                </Button>
              </div>

              {powerId.current && <Button variant="outline" onClick={async () => {
                try { const result = await api.config.operation(powerId.current!); setPowerMessage(result.message ?? result.status); setPowerAccepted(["accepted", "unknown", "dispatching"].includes(result.status)) }
                catch (error) { setPowerMessage(error instanceof Error ? error.message : "Status unavailable") }
              }}>Check Power Status</Button>}
              {(powerAccepted || maintenance?.state === "power-accepted" || maintenance?.state === "recovery-required") && <div className="space-y-3 p-4 rounded-xl border">
                <Label htmlFor="power-password">Recovery administrator password</Label>
                <Input id="power-password" type="password" value={recoveryPassword} onChange={e => setRecoveryPassword(e.target.value)} />
                <Button variant="outline" disabled={!recoveryPassword || powerPending} onClick={async () => {
                  setPowerPending(true)
                  try { await api.config.recoverPower(recoveryPassword); setPowerAccepted(false); setMaintenance(await api.config.maintenance()); setRecoveryPassword("") }
                  catch (error) { setPowerMessage(error instanceof Error ? error.message : "Cancellation unconfirmed; admission remains closed") }
                  finally { setPowerPending(false) }
                }}>Cancel Pending Power Command</Button>
                <Button variant="outline" disabled={!recoveryPassword || powerPending} onClick={async () => {
                  setPowerPending(true)
                  try { setMaintenance(await api.config.recoverRestore(recoveryPassword)); setRecoveryPassword("") }
                  catch (error) { setPowerMessage(error instanceof Error ? error.message : "Recovery failed") }
                  finally { setPowerPending(false) }
                }}>Retry Restore Recovery</Button>
              </div>}
              <div className="mt-4 p-3 rounded-lg bg-muted/50 border">
                <p className="text-xs text-muted-foreground">
                  <strong>Note:</strong> After shutdown, you will need physical access to the mini PC to power it back on. 
                  Make sure all scans are complete before shutting down.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        </div>
      </Tabs>

      {/* Shutdown Confirmation Dialog */}
      <AlertDialog open={showShutdownDialog} onOpenChange={open => { if (!powerPending) setShowShutdownDialog(open) }}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Shutdown System?</AlertDialogTitle>
            <AlertDialogDescription>
              This will power off the mini PC. You will need physical access to restart the system. 
              New scans will be paused while active scans finish.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90" 
              disabled={powerPending} onClick={event => { event.preventDefault(); void handlePower("shutdown") }}
            >
              <Power className="w-4 h-4 mr-2" />
              Shutdown Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Restart Confirmation Dialog */}
      <AlertDialog open={showRestartDialog} onOpenChange={open => { if (!powerPending) setShowRestartDialog(open) }}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Restart System?</AlertDialogTitle>
            <AlertDialogDescription>
              This schedules a reboot of the mini PC. Services resume if host autostart is configured. Active scans will finish before the request is sent.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={powerPending} onClick={event => { event.preventDefault(); void handlePower("restart") }}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Restart Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
