import { Skeleton } from "@/components/ui/skeleton"
import { useState, useEffect, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import { StationBackupControls } from "@/components/StationBackupControls"
import { Input } from "@/components/ui/input"
import { NumberField } from "@/components/ui/number-field"
import type { MaintenanceStatus } from "@/types/api"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Loader2, Settings, Save, RefreshCw, Cpu, Database, Camera, Power, Edit2, AlertTriangle } from "lucide-react"
import { ExportDropdown } from "@/components/ExportDropdown"
import { toast } from "sonner"
import {
  Alert,
  AlertTitle,
  AlertDescription
} from "@/components/ui/alert"
import { CameraCalibrationModal } from "@/components/CameraCalibrationModal"
import { CameraDevicePicker } from "@/components/CameraDevicePicker"
import { useCameraDiscovery } from "@/hooks/useCameraDiscovery"

export default function SystemConfig() {
  const { config, updateConfig, configReady, configError, configConflict, reloadConfig, acceptConfig } = useAdmin()
  const cameraDiscovery = useCameraDiscovery()
  const [localConfig, setLocalConfig] = useState(config)
  const previousConfig = useRef(config)
  const [maintenance, setMaintenance] = useState<MaintenanceStatus | null>(null)
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const exportFlight = useRef(false)
  const [reloading, setReloading] = useState(false)
  const reloadFlight = useRef(false)
  const [checkingPower, setCheckingPower] = useState(false)
  const checkFlight = useRef(false)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [powerPending, setPowerPending] = useState(false)
  const [powerAccepted, setPowerAccepted] = useState(false)
  const [powerMessage, setPowerMessage] = useState("")
  const [recoveryPassword, setRecoveryPassword] = useState("")
  const powerId = useRef<string | null>(null)
  const powerFlight = useRef(false)
  const configFlight = useRef(false)
  const maintenanceSequence = useRef(0)
  const acceptMaintenance = (result: MaintenanceStatus) => {
    ++maintenanceSequence.current
    setMaintenance(result)
    setMaintenanceError(null)
  }
  const disabled = !configReady || configConflict || archiveBusy || powerPending || powerAccepted || Boolean(maintenance && maintenance.state !== "ready")
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      if (!live) return
      const mySeq = ++maintenanceSequence.current
      try {
        const result = await api.config.maintenance()
        if (live && mySeq === maintenanceSequence.current) { setMaintenance(result); setMaintenanceError(null) }
      } catch {
        if (live && mySeq === maintenanceSequence.current) setMaintenanceError("Maintenance status unavailable")
      }
      if (live) timer = setTimeout(refresh, 5000)
    }
    void refresh()
    return () => { live = false; clearTimeout(timer) }
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
      cameraDeviceIds: JSON.stringify(draft.cameraDeviceIds) === JSON.stringify(previous.cameraDeviceIds) ? config.cameraDeviceIds : draft.cameraDeviceIds,
      confidenceThreshold: draft.confidenceThreshold === previous.confidenceThreshold ? config.confidenceThreshold : draft.confidenceThreshold,
      dataRetentionEnabled: draft.dataRetentionEnabled === previous.dataRetentionEnabled ? config.dataRetentionEnabled : draft.dataRetentionEnabled,
    }))
  }, [config])

  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || JSON.stringify(localConfig.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds) || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)

  const activeCameraIds = localConfig.cameraIds.split(",").map(s => s.trim()).filter(Boolean)

  const addCamera = () => {
    if (disabled || saving || activeCameraIds.length >= 4) return
    const devices = localConfig.cameraDeviceIds ?? []
    let deviceId = 0
    while (devices.includes(deviceId)) deviceId++
    let suffix = activeCameraIds.length + 1
    while (activeCameraIds.includes(`CAM-${String(suffix).padStart(3, "0")}`)) suffix++
    setLocalConfig({ ...localConfig,
      cameraIds: [...activeCameraIds, `CAM-${String(suffix).padStart(3, "0")}`].join(", "),
      cameraDeviceIds: [...devices, deviceId],
    })
  }

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
    const deviceIds = localConfig.cameraDeviceIds ?? []
    if (deviceIds.length !== activeCameraIds.length || new Set(deviceIds).size !== deviceIds.length || deviceIds.some(id => !Number.isSafeInteger(id) || id < 0)) {
      toast.error("Assign a distinct nonnegative device index to every camera")
      return
    }
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

  const handleExportData = async (format: "csv" | "xlsx") => {
    if (exportFlight.current) return
    exportFlight.current = true; setExporting(true)
    try {
      await api.config.export(format)
      toast.success("Scan summaries exported", { description: `${format.toUpperCase()} download started` })
    } catch {
      toast.error("Export Failed", { description: "Could not export scan summaries" })
    } finally { exportFlight.current = false; setExporting(false) }
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
    <div className="space-y-4 sm:space-y-6 max-w-5xl mx-auto w-full min-w-0">
      <div className="mb-2">
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          <Settings className="w-6 h-6 sm:w-7 sm:h-7" /> System Configuration
        </h1>
        <p className="text-muted-foreground text-xs sm:text-sm mt-1">Manage global BananaVision settings</p>
      </div>

      {(configError || configConflict) && <Alert>
        <AlertTitle>{configConflict ? "Configuration changed elsewhere" : configError ?? "Loading configuration…"}</AlertTitle>
        <AlertDescription>Your draft is preserved. Reload saved settings before making changes.</AlertDescription>
        <Button variant="outline" disabled={saving || reloading} onClick={async () => { if (reloadFlight.current) return; reloadFlight.current = true; setReloading(true); try { await reloadConfig() } finally { reloadFlight.current = false; setReloading(false) } }}>{reloading && <Loader2 className="w-4 h-4 animate-spin" />}{configConflict ? "Reload saved settings" : "Retry configuration"}</Button>
      </Alert>}
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Configuration details</summary>
        <div className="mt-3 space-y-3">
          {configReady && <p>Saved revision {config.revision} · Cameras {config.applicationStatus}. Threshold applies to the next scan. Deployment model changes require a backend restart.</p>}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <p>Reset camera names, review threshold (85%), and automatic cleanup (enabled). Device assignments stay at their saved values. Review and save to apply.</p>
            <Button variant="outline" size="sm" disabled={saving || disabled} onClick={handleReset} className="shrink-0 self-start">
              <RefreshCw className="w-4 h-4 mr-2" /> Reset All Settings
            </Button>
          </div>
        </div>
      </details>
      {configReady && config.applicationStatus !== "applied" && config.applicationError && (
        <Alert variant="destructive" role="alert">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Camera application {config.applicationStatus}</AlertTitle>
          <AlertDescription>{config.applicationError}</AlertDescription>
        </Alert>
      )}
      {configReady && config.applicationStatus !== "applied" && <Button variant="outline" disabled={disabled || saving} onClick={async () => {
        if (configFlight.current) return
        configFlight.current = true; setSaving(true)
        try { acceptConfig(await api.config.applyCameras(crypto.randomUUID())) }
        catch (error) { toast.error(error instanceof Error ? error.message : "Camera application failed") }
        finally { configFlight.current = false; setSaving(false) }
      }}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}Retry Applying Cameras</Button>}
      {!configReady && !configError ? <div role="status" aria-label="Loading configuration" className="space-y-4"><Skeleton className="h-12 w-full" /><Skeleton className="h-72 w-full" /></div> : <Tabs defaultValue="scanner" className="w-full min-w-0 gap-4 sm:gap-6">
        <div className="overflow-x-auto pb-1">
          <TabsList aria-label="Configuration sections" className="w-full min-w-max !h-auto gap-1 p-1 rounded-xl">
            <TabsTrigger value="scanner" className="px-3 sm:px-5 py-2.5 text-xs sm:text-sm rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm data-[state=active]:text-foreground"><Camera className="w-4 h-4" /> Cameras</TabsTrigger>
            <TabsTrigger value="ai" className="px-3 sm:px-5 py-2.5 text-xs sm:text-sm rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm data-[state=active]:text-foreground"><Cpu className="w-4 h-4" /> Detection</TabsTrigger>
            <TabsTrigger value="data" className="px-3 sm:px-5 py-2.5 text-xs sm:text-sm rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm data-[state=active]:text-foreground"><Database className="w-4 h-4" /> Data &amp; Backups</TabsTrigger>
            <TabsTrigger value="power" className="px-3 sm:px-5 py-2.5 text-xs sm:text-sm rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm data-[state=active]:text-foreground"><Power className="w-4 h-4" /> Power</TabsTrigger>
          </TabsList>
        </div>
        <div className="w-full min-w-0">

        <TabsContent value="scanner" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Scanner Cameras</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Assign a device to each camera, then save and verify its feed in calibration.</CardDescription>
            </CardHeader>
            <CardContent className="px-4 sm:px-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">{activeCameraIds.length}/4 camera slots configured</p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" disabled={disabled || saving || cameraDiscovery.loading} onClick={cameraDiscovery.refresh}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${cameraDiscovery.loading ? "animate-spin" : ""}`} />{cameraDiscovery.loading ? "Listing Devices..." : "Refresh Device List"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={addCamera} disabled={disabled || saving || activeCameraIds.length >= 4}>Add Camera</Button>
                </div>
              </div>
              {cameraDiscovery.error && <p role="alert" className="text-sm text-destructive">{cameraDiscovery.error} You can still enter device indices in Advanced device settings.</p>}
              {activeCameraIds.length === 0 && <p className="text-sm text-muted-foreground">No cameras configured. Add a camera to get started.</p>}
              <div className="divide-y">
                {activeCameraIds.map((id, index) => {
                  const deviceId = localConfig.cameraDeviceIds?.[index]
                  const device = cameraDiscovery.discovery?.devices.find(item => item.device_id === deviceId)
                  const savedIds = config.cameraIds.split(",").map(value => value.trim())
                  const changed = id !== savedIds[index] || deviceId !== config.cameraDeviceIds?.[index]
                  const status = changed ? "Pending save" : cameraDiscovery.loading ? "Checking devices" : cameraDiscovery.error || !cameraDiscovery.discovery ? "Status unavailable" : !device ? "Not detected" : device.configured_camera_id === id ? device.online ? "Online" : "Offline" : "Detected"
                  return <div key={index} className="py-4 first:pt-0 last:pb-0 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <Camera className="w-4 h-4 text-muted-foreground shrink-0" />
                        {editingCameraId === id ? <Input
                          aria-label={`Camera ${index + 1} name`} value={editCameraValue} disabled={disabled || saving}
                          onChange={event => setEditCameraValue(event.target.value)} onBlur={saveEditedCameraId}
                          onKeyDown={event => { if (event.key === "Enter") saveEditedCameraId(); if (event.key === "Escape") setEditingCameraId(null) }}
                          autoFocus maxLength={50} className="w-40"
                        /> : <button type="button" aria-label={`Rename camera ${index + 1}: ${id}`} disabled={disabled || saving}
                          onClick={() => startEditingCameraId(id)} className="flex items-center gap-2 text-sm font-medium min-w-0 text-left rounded focus-visible:outline-ring disabled:opacity-50">
                          <span className="truncate">{id}</span><Edit2 className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                        </button>}
                        <Badge variant="secondary" className={`shrink-0 text-xs ${status === "Online" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : ""}`}>{status}</Badge>
                      </div>
                      <div className="min-w-0 w-full sm:w-80 shrink-0">
                        <CameraDevicePicker compact discovery={cameraDiscovery.discovery} value={deviceId} slot={index + 1}
                          disabled={disabled || saving || cameraDiscovery.loading}
                          onChange={value => {
                            const devices = [...(localConfig.cameraDeviceIds ?? [])]
                            devices[index] = value
                            setLocalConfig({ ...localConfig, cameraDeviceIds: devices })
                          }} />
                        {!cameraDiscovery.discovery?.devices.length && <p className="text-xs text-muted-foreground">{cameraDiscovery.loading ? "Loading device list…" : `Device index ${Number.isSafeInteger(deviceId) ? deviceId : "not set"} · Manual assignment below`}</p>}
                      </div>
                    </div>
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Advanced device settings for camera {index + 1}</summary>
                      <div className="mt-3 flex flex-wrap items-center gap-3">
                        <Label htmlFor={`camera-device-${index}`} className="text-xs">Manual device index</Label>
                        <NumberField id={`camera-device-${index}`} aria-label={`Device index for camera ${index + 1}`} min={0} step={1}
                          className="w-28" disabled={disabled || saving}
                          value={Number.isNaN(deviceId) ? "" : deviceId ?? ""}
                          onChange={value => {
                            const devices = [...(localConfig.cameraDeviceIds ?? [])]
                            devices[index] = value === "" ? Number.NaN : Number(value)
                            setLocalConfig({ ...localConfig, cameraDeviceIds: devices })
                          }} />
                        {device?.device_uid && <p className="w-full break-all">Device ID: {device.device_uid}</p>}
                      </div>
                    </details>
                  </div>
                })}
              </div>
              <details className="border-t pt-4 text-xs text-muted-foreground">
                <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Device discovery details</summary>
                <div className="mt-3 space-y-2 break-words">
                  <p>Assign a distinct index to each camera. The laptop webcam may occupy one index. Detection confirms presence; calibration confirms a usable feed.</p>
                  {cameraDiscovery.discovery && <>
                    <p>Discovery backend: {cameraDiscovery.discovery.backend.toUpperCase()}</p>
                    {cameraDiscovery.discovery.devices.length === 0 && <p>No camera devices detected. Check the connections and refresh.</p>}
                    {cameraDiscovery.discovery.devices.map(device => <p key={device.device_id} className="break-all">Index {device.device_id} — {device.name}{device.device_uid ? ` · ${device.device_uid}` : ""}{device.configured_camera_id ? ` · ${device.configured_camera_id}: ${device.online ? "Online" : "Offline"}` : " · Not assigned"}</p>)}
                  </>}
                </div>
              </details>
              <div className="border-t pt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">{hasChanges ? "Save changes before opening calibration." : "All configured online cameras participate in each scan."}</p>
                <CameraCalibrationModal disabled={saving || disabled || hasChanges} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ai" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Detection Review</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Choose when scan results need a closer look.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 px-4 sm:px-6">
              <div className="space-y-4">
                <div className="flex justify-between">
                  <Label id="review-confidence-label" className="text-sm">Review Confidence Threshold</Label>
                  <span className="font-bold text-primary">{localConfig.confidenceThreshold}%</span>
                </div>
                <Slider aria-labelledby="review-confidence-label"
                  value={[localConfig.confidenceThreshold]} 
                  onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}
                  min={1}
                  disabled={saving || disabled}
                  max={100} 
                  step={1} 
                  className="w-full"
                />
                <p className="text-xs text-muted-foreground">
                  Results below {localConfig.confidenceThreshold}% are flagged for review.
                  <span className="block mt-1">Applies to the next scan after saving.</span>
                </p>
              </div>
              <details className="border-t pt-4 text-xs text-muted-foreground">
                <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Model information</summary>
                <div className="mt-3 space-y-2">
                  <p>YOLO26 detections keep their original confidence scores. The current detection cutoff below reflects the saved configuration.</p>
                  {config.detectionConfidenceThreshold !== undefined && <p>Current YOLO detection cutoff: {config.detectionConfidenceThreshold}%</p>}
                  <p>Deployment model changes require a backend restart.</p>
                </div>
              </details>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="data" forceMount className="m-0 border-0 outline-none data-[state=inactive]:hidden">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Data &amp; Backups</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Manage capture cleanup, reports, and station recovery.</CardDescription>
            </CardHeader>
            <CardContent className="divide-y px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Automatic Capture Cleanup</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Clean unreferenced captures older than {config.retentionDays ?? "—"} days. Scan records and referenced evidence are retained.</p>
                  <p className="text-xs text-muted-foreground mt-1">Saves immediately · Applies on the next cleanup cycle.</p>
                </div>
                <Button 
                  role="switch" aria-label="Automatic capture cleanup" aria-checked={localConfig.dataRetentionEnabled}
                  variant={localConfig.dataRetentionEnabled ? "default" : "outline"} 
                  onClick={toggleDataRetention} 
                  disabled={saving || disabled}
                  className="w-full sm:w-auto shrink-0"
                >
                  {localConfig.dataRetentionEnabled ? "Enabled" : "Disabled"}
                </Button>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Export Scan Summaries</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Download a CSV or XLSX report of scan summaries. This export cannot restore station data.</p>
                </div>
                <ExportDropdown
                  onExportCsv={() => void handleExportData("csv")}
                  onExportXlsx={() => void handleExportData("xlsx")}
                  disabled={exporting}
                  exporting={exporting}
                />
              </div>
              <StationBackupControls disabled={disabled || saving} onBusy={setArchiveBusy} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="power" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Station Power</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Control the mini PC power state.</CardDescription>
            </CardHeader>
            <CardContent className="divide-y px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">System Status</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">{powerMessage || maintenanceError || `Station ${maintenance?.state ?? "status loading"}`}</p>
                </div>
                <Badge variant="secondary" role="status" className={maintenanceError ? "" : maintenance?.state === "ready" && !powerPending && !powerAccepted ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-amber-500/10 text-amber-700 dark:text-amber-400"}>
                  {maintenanceError ? "Status unavailable" : powerPending ? "Request pending" : powerAccepted ? "Power pending" : maintenance?.state?.replaceAll("-", " ") ?? "Loading"}
                </Badge>
              </div>
              
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Restart System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Reboot the mini PC. Services resume if host autostart is configured.</p>
                </div>
                <Button variant="outline" className="w-full sm:w-auto gap-2" disabled={disabled || saving} onClick={() => { powerId.current = null; setShowRestartDialog(true) }}>
                  <RefreshCw className="w-4 h-4" />
                  Restart
                </Button>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5">
                <div>
                  <h4 className="font-medium text-destructive text-sm sm:text-base">Shutdown System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Power off the mini PC</p>
                </div>
                <Button variant="destructive" disabled={disabled || saving} onClick={() => { powerId.current = null; setShowShutdownDialog(true) }} className="w-full sm:w-auto gap-2">
                  <Power className="w-4 h-4" />
                  Shutdown
                </Button>
              </div>

              {powerId.current && <Button variant="outline" disabled={checkingPower} onClick={async () => {
                if (checkFlight.current) return
                checkFlight.current = true; setCheckingPower(true)
                try { const result = await api.config.operation(powerId.current!); setPowerMessage(result.message ?? result.status); setPowerAccepted(["accepted", "unknown", "dispatching"].includes(result.status)) }
                catch (error) { setPowerMessage(error instanceof Error ? error.message : "Status unavailable") }
                finally { checkFlight.current = false; setCheckingPower(false) }
              }}>{checkingPower && <Loader2 className="w-4 h-4 animate-spin" />}Check Power Status</Button>}
              {(powerAccepted || maintenance?.state === "power-accepted" || maintenance?.state === "recovery-required") && <div className="space-y-3 p-4 rounded-xl border">
                <Label htmlFor="power-password">Recovery administrator password</Label>
                <Input id="power-password" type="password" value={recoveryPassword} onChange={e => setRecoveryPassword(e.target.value)} />
                <Button variant="outline" disabled={!recoveryPassword || powerPending} onClick={async () => {
                  if (powerFlight.current) return
                  powerFlight.current = true; setPowerPending(true)
                  try { await api.config.recoverPower(recoveryPassword); setPowerAccepted(false); acceptMaintenance(await api.config.maintenance()); setRecoveryPassword("") }
                  catch (error) { setPowerMessage(error instanceof Error ? error.message : "Cancellation unconfirmed; admission remains closed") }
                  finally { powerFlight.current = false; setPowerPending(false) }
                }}>{powerPending && <Loader2 className="w-4 h-4 animate-spin" />}Cancel Pending Power Command</Button>
                <Button variant="outline" disabled={!recoveryPassword || powerPending} onClick={async () => {
                  if (powerFlight.current) return
                  powerFlight.current = true; setPowerPending(true)
                  try { acceptMaintenance(await api.config.recoverRestore(recoveryPassword)); setRecoveryPassword("") }
                  catch (error) { setPowerMessage(error instanceof Error ? error.message : "Recovery failed") }
                  finally { powerFlight.current = false; setPowerPending(false) }
                }}>{powerPending && <Loader2 className="w-4 h-4 animate-spin" />}Retry Restore Recovery</Button>
              </div>}
              <div className="pt-4">
                <p className="text-xs text-muted-foreground">
                  <strong>Note:</strong> After shutdown, you will need physical access to the mini PC to power it back on. 
                  Make sure all scans are complete before shutting down.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        </div>
      </Tabs>}
      {hasChanges && (
        <div role="region" aria-label="Unsaved configuration changes" className="sticky bottom-0 z-20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border rounded-xl bg-background p-4 shadow-lg">
          <div>
            <p className="text-sm font-medium">Unsaved changes</p>
            <p className="text-xs text-muted-foreground">Save applies pending edits across all settings tabs.</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button variant="outline" onClick={handleUndo} disabled={saving || disabled} className="flex-1 sm:flex-none">Discard</Button>
            <Button onClick={handleSave} disabled={saving || disabled} className="flex-1 sm:flex-none">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      )}

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
            <AlertDialogCancel disabled={powerPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90" 
              disabled={powerPending} onClick={event => { event.preventDefault(); void handlePower("shutdown") }}
            >
              <Power className="w-4 h-4 mr-2" />
              {powerPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
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
              {powerPending && <span className="block text-xs font-medium text-muted-foreground mt-2">Waiting for active work to finish…</span>}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={powerPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={powerPending} onClick={event => { event.preventDefault(); void handlePower("restart") }}>
              <RefreshCw className="w-4 h-4 mr-2" />
              {powerPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Restart Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
