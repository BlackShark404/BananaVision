import { useState, useEffect } from "react"
import { useApp } from "@/context/AppContext"
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
import { Settings, Save, RefreshCw, Cpu, Database, Camera, Power, Download } from "lucide-react"
import { toast } from "sonner"

export default function SystemConfig() {
  const { config, updateConfig } = useApp()
  const [localConfig, setLocalConfig] = useState(config)
  const [saving, setSaving] = useState(false)
  const [showShutdownDialog, setShowShutdownDialog] = useState(false)
  const [showRestartDialog, setShowRestartDialog] = useState(false)
  const [dataRetentionEnabled, setDataRetentionEnabled] = useState(true)

  useEffect(() => {
    setLocalConfig(config)
  }, [config])

  const handleSave = () => {
    setSaving(true)
    setTimeout(() => {
      updateConfig(localConfig)
      setSaving(false)
      toast.success("Settings saved successfully")
    }, 800)
  }

  const handleReset = () => {
    setLocalConfig({ cameraIds: "CAM-001, CAM-002", confidenceThreshold: 85 })
    toast.info("Settings reset to defaults")
  }

  const handleExportData = () => {
    toast.success("Database Exported", { description: "bananavision_inventory_export.csv saved to downloads" })
  }

  const toggleDataRetention = () => {
    const newState = !dataRetentionEnabled
    setDataRetentionEnabled(newState)
    toast.success(
      newState ? "Data Retention Enabled" : "Data Retention Disabled",
      { description: newState ? "Logs older than 30 days will be deleted automatically" : "All logs will be kept indefinitely" }
    )
  }

  const handleShutdown = () => {
    // In production: API call to shutdown the mini PC
    // fetch('/api/system/shutdown', { method: 'POST' })
    toast.success("Shutdown initiated", { description: "System will power off in 10 seconds..." })
    setShowShutdownDialog(false)
    
    // Simulate countdown
    setTimeout(() => {
      toast.info("System shutting down...", { description: "Please wait while the system powers off" })
    }, 3000)
  }

  const handleRestart = () => {
    // In production: API call to restart the mini PC
    toast.success("Restart initiated", { description: "System will reboot in 10 seconds..." })
    setShowRestartDialog(false)
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
              <div className="space-y-2">
                <Label htmlFor="cameraIds" className="text-sm">Active Camera IDs (comma separated)</Label>
                <Input 
                  id="cameraIds" 
                  value={localConfig.cameraIds} 
                  onChange={e => setLocalConfig({...localConfig, cameraIds: e.target.value})} 
                  placeholder="e.g. CAM-001, CAM-002" 
                  className="rounded-xl h-10 sm:h-11"
                />
                <p className="text-xs text-muted-foreground">These cameras will be used for round-robin scanning.</p>
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
                  variant={dataRetentionEnabled ? "default" : "outline"} 
                  onClick={toggleDataRetention} 
                  className="w-full sm:w-auto"
                >
                  {dataRetentionEnabled ? "Enabled" : "Disabled"}
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
