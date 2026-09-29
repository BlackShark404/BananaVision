import { useState, useEffect } from "react"
import { useAdmin } from "@/context/AdminContext"
import { api } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
import { Settings, Save, RefreshCw, Cpu, Database, Camera, Power, Download, Edit2, Plus } from "lucide-react"
import { toast } from "sonner"
import { CameraCalibrationModal } from "@/components/CameraCalibrationModal"

export default function SystemConfig() {
  const { config, updateConfig } = useAdmin()
  const [localConfig, setLocalConfig] = useState(config)
  const [saving, setSaving] = useState(false)
  const [showShutdownDialog, setShowShutdownDialog] = useState(false)
  const [showRestartDialog, setShowRestartDialog] = useState(false)
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null)
  const [editCameraValue, setEditCameraValue] = useState("")

  useEffect(() => {
    setLocalConfig(config)
  }, [config])

  const activeCameraIds = localConfig.cameraIds.split(",").map(s => s.trim()).filter(Boolean)

  const startEditingCameraId = (idToEdit: string) => {
    setEditingCameraId(idToEdit)
    setEditCameraValue(idToEdit)
  }

  const saveEditedCameraId = () => {
    if (editingCameraId) {
      const trimmed = editCameraValue.trim()
      
      if (!trimmed) {
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

  const handleSave = () => {
    setSaving(true)
    setTimeout(() => {
      updateConfig(localConfig)
      setSaving(false)
      toast.success("Settings saved successfully")
    }, 800)
  }

  const handleReset = () => {
    setLocalConfig({ cameraIds: "CAM-001, CAM-002, CAM-003, CAM-004", confidenceThreshold: 85, dataRetentionEnabled: true })
    toast.info("Settings reset to defaults")
  }

  const handleExportData = async () => {
    try {
      await api.config.export()
      toast.success("Database Exported", { description: "bananavision_inventory_export.csv saved to downloads" })
    } catch {
      toast.error("Export Failed", { description: "Could not export database" })
    }
  }

  const toggleDataRetention = () => {
    const newState = !localConfig.dataRetentionEnabled
    setLocalConfig({...localConfig, dataRetentionEnabled: newState})
    updateConfig({ dataRetentionEnabled: newState })
    toast.success(
      newState ? "Data Retention Enabled" : "Data Retention Disabled",
      { description: newState ? "Logs older than 30 days will be deleted automatically" : "All logs will be kept indefinitely" }
    )
  }

  const handleShutdown = async () => {
    try {
      await api.config.shutdown()
      toast.success("Shutdown initiated", { description: "System will power off in 10 seconds..." })
      setShowShutdownDialog(false)
      
      // Simulate countdown
      setTimeout(() => {
        toast.info("System shutting down...", { description: "Please wait while the system powers off" })
      }, 3000)
    } catch {
      toast.error("Shutdown Failed", { description: "Could not initiate shutdown" })
    }
  }

  const handleRestart = async () => {
    try {
      await api.config.restart()
      toast.success("Restart initiated", { description: "System will reboot in 10 seconds..." })
      setShowRestartDialog(false)
    } catch {
      toast.error("Restart Failed", { description: "Could not initiate restart" })
    }
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          <Settings className="w-6 h-6 sm:w-7 sm:h-7" /> System Configuration
        </h1>
        <p className="text-muted-foreground text-xs sm:text-sm mt-1">Manage global BananaVision settings</p>
      </div>

      <Tabs defaultValue="scanner" orientation="vertical" className="flex flex-col md:flex-row gap-4 sm:gap-6 w-full">
        <TabsList className="flex flex-col h-auto justify-start items-stretch rounded-xl sm:rounded-2xl bg-muted/50 p-2 shrink-0 md:w-60">
          <TabsTrigger value="scanner" className="justify-start w-full px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm">
            <Camera className="w-4 h-4 mr-2" /> Scanner Config
          </TabsTrigger>
          <TabsTrigger value="ai" className="justify-start w-full px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm mt-1">
            <Cpu className="w-4 h-4 mr-2" /> AI Settings
          </TabsTrigger>
          <TabsTrigger value="data" className="justify-start w-full px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm mt-1">
            <Database className="w-4 h-4 mr-2" /> Data Storage
          </TabsTrigger>
          <TabsTrigger value="power" className="justify-start w-full px-4 py-2.5 sm:py-3 text-left rounded-lg sm:rounded-xl data-[state=active]:bg-background data-[state=active]:shadow-sm text-xs sm:text-sm mt-1">
            <Power className="w-4 h-4 mr-2" /> System Power
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
                <p className="text-xs text-muted-foreground">These cameras will be used for round-robin scanning.</p>
                <div className="pt-2">
                  <CameraCalibrationModal />
                </div>
              </div>
            </CardContent>
            <CardFooter className="bg-muted/30 border-t px-4 sm:px-6 py-3 sm:py-4 flex flex-col sm:flex-row justify-between gap-2 sm:gap-0 rounded-b-xl sm:rounded-b-2xl">
              <Button variant="ghost" onClick={handleReset} className="w-full sm:w-auto">
                <RefreshCw className="w-4 h-4 mr-2" /> Reset Defaults
              </Button>
              <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto">
                {saving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Changes</>}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="ai" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">YOLOv8 Detection Parameters</CardTitle>
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
            <CardFooter className="bg-muted/30 border-t px-4 sm:px-6 py-3 sm:py-4 flex flex-col sm:flex-row justify-between gap-2 sm:gap-0 rounded-b-xl sm:rounded-b-2xl">
              <Button variant="ghost" onClick={handleReset} className="w-full sm:w-auto">
                <RefreshCw className="w-4 h-4 mr-2" /> Reset Defaults
              </Button>
              <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto">
                {saving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Changes</>}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="data" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Storage Management</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Manage how long scan logs and images are retained.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Data Retention</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Delete logs older than 30 days automatically</p>
                </div>
                <Button 
                  variant={localConfig.dataRetentionEnabled ? "default" : "outline"} 
                  onClick={toggleDataRetention} 
                  className="w-full sm:w-auto"
                >
                  {localConfig.dataRetentionEnabled ? "Enabled" : "Disabled"}
                </Button>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Export Database Backup</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Download all logs and inventory data as CSV</p>
                </div>
                <Button variant="outline" onClick={handleExportData} className="w-full sm:w-auto">
                  <Download className="w-4 h-4 mr-2" /> Export CSV
                </Button>
              </div>
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
                  <p className="text-xs sm:text-sm text-muted-foreground">System is currently running</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-sm font-medium text-emerald-600">Online</span>
                </div>
              </div>
              
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Restart System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Reboot the mini PC and restart all services</p>
                </div>
                <Button variant="outline" className="w-full sm:w-auto gap-2" onClick={() => setShowRestartDialog(true)}>
                  <RefreshCw className="w-4 h-4" />
                  Restart
                </Button>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-destructive/20 bg-destructive/5">
                <div>
                  <h4 className="font-medium text-destructive text-sm sm:text-base">Shutdown System</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Power off the mini PC</p>
                </div>
                <Button variant="destructive" onClick={() => setShowShutdownDialog(true)} className="w-full sm:w-auto gap-2">
                  <Power className="w-4 h-4" />
                  Shutdown
                </Button>
              </div>

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
      <AlertDialog open={showShutdownDialog} onOpenChange={setShowShutdownDialog}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Shutdown System?</AlertDialogTitle>
            <AlertDialogDescription>
              This will power off the mini PC. You will need physical access to restart the system. 
              Make sure all scans are complete before proceeding.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90" 
              onClick={handleShutdown}
            >
              <Power className="w-4 h-4 mr-2" />
              Shutdown Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Restart Confirmation Dialog */}
      <AlertDialog open={showRestartDialog} onOpenChange={setShowRestartDialog}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Restart System?</AlertDialogTitle>
            <AlertDialogDescription>
              This will reboot the mini PC and restart all services. Any active scans will be interrupted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleRestart}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Restart Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
