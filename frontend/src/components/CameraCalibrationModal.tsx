import { useState, useEffect } from "react"
import { BASE_URL } from "@/lib/api"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { toast } from "sonner"
import { Camera, RefreshCw } from "lucide-react"

export function CameraCalibrationModal() {
  const [open, setOpen] = useState(false)
  const [cameras, setCameras] = useState<any[]>([])
  const [labels, setLabels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  // Mapping of label -> device_id
  const [mapping, setMapping] = useState<Record<string, number>>({})

  const fetchCameras = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/cameras`)
      const data = await res.json()
      setCameras(data)
      
      const dynamicLabels = data.map((cam: any) => cam.label)
      setLabels(dynamicLabels)
      
      const newMapping: Record<string, number> = {}
      data.forEach((cam: any) => {
        if (cam.label) newMapping[cam.label] = cam.device_id
      })
      setMapping(newMapping)
    } catch (e) {
      toast.error("Failed to fetch cameras")
    }
  }

  useEffect(() => {
    if (open) {
      fetchCameras()
    }
  }, [open])

  const handleSave = async () => {
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

    setLoading(true)
    try {
      const res = await fetch(`${BASE_URL}/api/v1/cameras/mapping`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_ids })
      })
      if (!res.ok) throw new Error("Failed to update mapping")
      toast.success("Camera mapping saved! Restarting camera manager...")
      setOpen(false)
    } catch (e) {
      toast.error("Failed to save camera mapping")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full sm:w-auto gap-2">
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

        {cameras.length === 0 ? (
          <div className="py-8 flex justify-center"><RefreshCw className="animate-spin w-8 h-8 text-primary" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cameras.map((cam, index) => (
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
          <Button onClick={handleSave} disabled={loading}>
            {loading && <RefreshCw className="w-4 h-4 mr-2 animate-spin" />}
            Save Mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
