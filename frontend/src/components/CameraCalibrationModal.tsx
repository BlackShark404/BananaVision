import { useState, useEffect, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import type { ApiConfig } from "@/types/api"
import { api, BASE_URL } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { toast } from "sonner"
import { Camera, RefreshCw } from "lucide-react"

interface CameraSlot { device_id: number; camera_id: string; label: string; online: boolean }

export function CameraCalibrationModal({ disabled = false }: { disabled?: boolean }) {
  const { acceptConfig } = useAdmin()
  const [loadedConfig, setLoadedConfig] = useState<ApiConfig | null>(null)
  const [error, setError] = useState("")
  const pending = useRef(false)
  const operationId = useRef<string | null>(null)
  const [open, setOpen] = useState(false)
  const [cameras, setCameras] = useState<CameraSlot[]>([])
  const [labels, setLabels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  // Mapping of label -> device_id
  const [mapping, setMapping] = useState<Record<string, number>>({})

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    const load = async () => {
      setLoadedConfig(null); setError(""); operationId.current = null
      try {
        const token = getToken()
        const [res, saved] = await Promise.all([
          fetch(`${BASE_URL}/api/v1/cameras`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal }),
          api.config.get(controller.signal),
        ])
        if (!res.ok) throw new Error("Camera list could not be loaded")
        const data: CameraSlot[] = await res.json()
        if (controller.signal.aborted) return
        setCameras(data); setLabels(data.map(cam => cam.camera_id))
        setMapping(Object.fromEntries(data.map(cam => [cam.camera_id, cam.device_id])))
        setLoadedConfig(saved)
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Camera configuration unavailable")
      }
    }
    void load()
    return () => controller.abort()
  }, [open])

  const handleSave = async () => {
    if (!loadedConfig || pending.current) return
    // Reconstruct the array of device_ids in the exact order of labels
    const device_ids = labels.map(label => mapping[label])
    
    // Check if we have a valid ID for every label
    if (device_ids.some(id => id === undefined)) {
      toast.error("Please assign a camera to every position")
      return
    }
    
    // Check for duplicates
    if (new Set(device_ids).size !== device_ids.length) {
      toast.error("A camera cannot be assigned to multiple positions")
      return
    }

    pending.current = true
    operationId.current ??= crypto.randomUUID()
    setLoading(true)
    try {
      const token = getToken()
      const res = await fetch(`${BASE_URL}/api/v1/cameras/mapping`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ device_ids, expected_revision: loadedConfig.revision, operation_id: operationId.current })
      })
      if (!res.ok) {
        const error = await res.json().catch(() => null)
        throw new Error(typeof error?.detail === "string" ? error.detail : "Failed to update mapping")
      }
      const saved: ApiConfig = await res.json()
      acceptConfig(saved)
      setLoadedConfig(saved)
      if (saved.application_status === "applied") { toast.success("Camera mapping saved and applied"); setOpen(false) }
      else { setError(saved.application_error ?? "Mapping saved; some cameras could not initialize"); toast.warning("Camera mapping saved; physical configuration is incomplete") }
    } catch (error) {
      toast.error("Failed to save camera mapping", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={value => { if (!loading) setOpen(value) }}>
      <DialogTrigger asChild>
        <Button variant="outline" disabled={disabled} className="w-full sm:w-auto gap-2">
          <Camera className="w-4 h-4" />
          Calibrate Camera Positions
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Camera Calibration</DialogTitle>
          <DialogDescription>
            View live feeds and assign them to the correct physical positions. 
            This resolves issues where the OS changes camera IDs on reboot.
          </DialogDescription>
        </DialogHeader>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!loadedConfig && !error ? (
          <div className="py-8 flex justify-center"><RefreshCw className="animate-spin w-8 h-8 text-primary" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cameras.map((cam) => (
              <div key={cam.device_id} className="border rounded-xl p-2 bg-muted/10 space-y-2">
                <div className="aspect-video bg-black rounded-lg overflow-hidden relative">
                  {cam.online ? (
                    <img 
                      src={`${BASE_URL}/api/v1/cameras/preview/${cam.device_id}`} 
                      className="w-full h-full object-cover" 
                      alt={`Camera ${cam.device_id}`}
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 800 600"><rect fill="%23000" width="800" height="600"/><text fill="%23fff" x="50%" y="50%" font-family="sans-serif" font-size="30" text-anchor="middle">Feed Offline</text></svg>'
                      }}
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-white/50 text-sm">
                      Offline
                    </div>
                  )}
                  <div className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
                    {cam.camera_id}
                  </div>
                </div>
                
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">Position:</span>
                  <Select 
                    value={Object.keys(mapping).find(key => mapping[key] === cam.device_id) || ""} 
                    onValueChange={(val) => {
                      setMapping(prev => ({ ...prev, [val]: cam.device_id }))
                    }}
                  >
                    <SelectTrigger className="w-[140px]">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      {labels.map(label => (
                        <SelectItem key={label} value={label}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={loading || !loadedConfig}>
            {loading && <RefreshCw className="w-4 h-4 mr-2 animate-spin" />}
            Save Mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
