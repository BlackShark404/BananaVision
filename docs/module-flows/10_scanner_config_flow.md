# `10_scanner_config_flow.md` — Module 10: Scanner Config (Camera Slots, Hardware Discovery, Device Index Mapping & Live MJPEG Calibration) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 10 (Scanner Config) |
| :--- | :--- |
| `frontend/src/pages/admin/SystemConfig.tsx` | **Scanner Cameras Tab UI (`<TabsContent value="scanner">`):** Renders configured camera slots (`1–4` slots), `"Refresh Device List"`, `"Add Camera"`, inline camera ID renaming (`startEditingCameraId` / `saveEditedCameraId`), status badges (`Online`, `Offline`, `Detected`, `Not detected`, `Pending save`), `<CameraDevicePicker>`, manual `<NumberField>` device index input, and `<CameraCalibrationModal>`. |
| `frontend/src/hooks/useCameraDiscovery.ts` | **Hardware Discovery Hook (`useCameraDiscovery`):** Calls `api.cameras.discover(controller.signal)` (`GET /api/v1/cameras/discovery`) and exposes `{ discovery, error, loading, refresh }`. |
| `frontend/src/components/CameraDevicePicker.tsx` | **Detected Camera Dropdown:** Renders a `<Select>` listing all USB/DirectShow cameras enumerated by the backend (`Index {device_id} — {name} · {device_uid}`). |
| `frontend/src/components/CameraCalibrationModal.tsx` | **Live MJPEG Calibration & Position Swap Modal:** Fetches `GET /api/v1/cameras` and `GET /api/v1/config`, streams live MJPEG feeds via `<img src={withMediaToken("${BASE_URL}/api/v1/cameras/preview/${cam.device_id}")} />`, swaps physical device indices across logical positions (`Top`, `Left`, `Right`, `Rear`), and saves via `POST /api/v1/cameras/mapping`. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client & Media Token Helper:** Provides `withMediaToken()` (appends `?token=<JWT>` for `<img>` MJPEG streams that cannot send `Authorization` headers) and `api.cameras.discover`, `api.cameras.list`, and `api.cameras.map`. |
| `backend/app/api/v1/cameras.py` | **Cameras Controller:** Defines `GET /api/v1/cameras/discovery`, `GET /api/v1/cameras`, `GET /api/v1/cameras/preview/{camera_index}` (15 FPS `multipart/x-mixed-replace; boundary=frame` MJPEG stream authenticated via `MediaUser`), and `POST /api/v1/cameras/mapping`. |
| `backend/app/services/camera_discovery.py` | **Native USB Camera Enumerator (`discover_camera_devices`):** Uses `cv2_enumerate_cameras` with DirectShow (`cv2.CAP_DSHOW` on Windows) to read USB hardware names and a 12-char SHA-256 `device_uid` from `camera.path` without opening or disrupting active `VideoCapture` streams. |
| `backend/app/services/configuration.py` | **Slot Persistence & Post-Commit Hardware Application:** Validates 1–4 unique camera IDs and nonnegative device indices (`_validate_camera_slots`), rewrites `Device` slot rows in place (`_replace_camera_slots`), applies the configuration to `camera_manager.configure` (`apply_camera_config`), and updates `Device.status` / `resolution` / `last_seen` (`sync_devices`). |
| `backend/app/services/camera_manager.py` | **OpenCV Multi-Camera Hardware Manager (`CameraManager`):** Opens and keeps `cv2.VideoCapture` handles alive across the station lifecycle, negotiates resolution modes (`2560x1440` → `1920x1080` → `1280x720` → `640x480`), validates non-black frames (`_MEAN_THRESHOLD = 15.0`, `_STDDEV_THRESHOLD = 8.0`), and captures single or parallel frames. |
| `backend/app/models/device.py` | **SQLAlchemy ORM Model (`device`):** Stores `camera_id` (unique), `slot_index` (`0..3`, unique), `device_index` (`>= 0`, unique), `label` (`Top`, `Left`, `Right`, `Rear`), `status` (`Online`/`Offline`), `resolution`, and `last_seen`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Hardware Discovery, Camera Slot Editing & Device Index Assignment

#### Step A1: Enumerating Hardware Cameras (`useCameraDiscovery.ts` → `GET /api/v1/cameras/discovery` → `camera_discovery.py`)
* **Step Title & Trigger:** When `SystemConfig.tsx` mounts (or when the admin clicks `"Refresh Device List"`), `useCameraDiscovery()` calls `GET /api/v1/cameras/discovery`.
* **Exact File Path & Line Numbers:**
  * `frontend/src/hooks/useCameraDiscovery.ts` (Lines 1–33)
  * `frontend/src/components/CameraDevicePicker.tsx` (Lines 1–27)
  * `backend/app/api/v1/cameras.py` (Lines 32–48)
  * `backend/app/services/camera_discovery.py` (Lines 1–53)
* **Complete Uncut Code Block (`frontend/src/hooks/useCameraDiscovery.ts`, Lines 1–33):**
```ts
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import type { CameraDiscovery } from "@/types/cameras"

export function useCameraDiscovery(enabled = true) {
  const [discovery, setDiscovery] = useState<CameraDiscovery | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [request, setRequest] = useState(0)

  useEffect(() => {
    if (!enabled) { setLoading(false); return }
    const controller = new AbortController()
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.cameras.discover(controller.signal)
        if (!controller.signal.aborted) { setDiscovery(result); setError(result.error) }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Camera device list unavailable")
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [enabled, request])

  return { discovery, error, loading, refresh: () => setRequest(value => value + 1) }
}
```
* **Complete Uncut Code Block (`frontend/src/components/CameraDevicePicker.tsx`, Lines 1–27):**
```tsx
import type { CameraDiscovery } from "@/types/cameras"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export function CameraDevicePicker({ discovery, value, onChange, disabled, slot, compact = false }: {
  discovery: CameraDiscovery | null
  value: number | undefined
  onChange: (value: number) => void
  disabled: boolean
  compact?: boolean
  slot: number
}) {
  const cameras = discovery?.devices ?? []
  if (!cameras.length) return null
  const known = cameras.some(camera => camera.device_id === value)
  const selected = value !== undefined && Number.isSafeInteger(value) ? String(value) : ""
  return <Select value={selected} onValueChange={index => onChange(Number(index))} disabled={disabled}>
    <SelectTrigger aria-label={`Detected device for camera ${slot}`} className="w-full sm:w-80 min-w-0 [&>span]:truncate [&>span]:min-w-0 [&>span]:block">
      <SelectValue placeholder="Choose a detected camera" />
    </SelectTrigger>
    <SelectContent>
      {!known && selected && <SelectItem value={selected}>Index {selected} — not detected</SelectItem>}
      {cameras.map(camera => <SelectItem key={camera.device_id} value={String(camera.device_id)}>
        Index {camera.device_id} — {camera.name}{!compact && camera.device_uid ? ` · ${camera.device_uid}` : ""}
      </SelectItem>)}
    </SelectContent>
  </Select>
}
```
* **Complete Uncut Code Block (`backend/app/api/v1/cameras.py`, Lines 32–48):**
```python
@router.get("/discovery", response_model=CameraDiscoveryResponse)
async def discover_cameras(db: DbSession, admin: AdminUser):
    """Enumerate named devices for administrators without acquiring camera handles."""
    config = await configuration.get_config(db)
    async with coordinator.operation():
        discovered = await run_blocking(discover_camera_devices)
    saved = {slot.device_index: slot.camera_id for slot in config.camera_slots}
    applied = dict(zip(camera_manager._device_ids, camera_manager._logical_ids, strict=False))
    online = set(camera_manager.online_cameras)
    for device in discovered['devices']:
        device_id = device['device_id']
        name = saved.get(device_id)
        device['configured_camera_id'] = name
        device['online'] = (
            name is not None and applied.get(device_id) == name and device_id in online
        )
    return discovered
```
* **Complete Uncut Code Block (`backend/app/services/camera_discovery.py`, Lines 1–53):**
```python
"""Read capture-backend device metadata without opening camera streams."""
from __future__ import annotations

import hashlib
import logging
import sys

import cv2

from app.config import get_settings

logger = logging.getLogger(__name__)


def capture_backend(preference: str) -> tuple[str, int]:
    """Keep device enumeration and VideoCapture in the same index namespace."""
    if preference == "auto":
        preference = "dshow" if sys.platform == "win32" else "auto"
    return preference, {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(
        preference, cv2.CAP_ANY,
    )


def _enumerate_backend(api: int):
    # This library queries native device metadata; it does not create VideoCapture.
    from cv2_enumerate_cameras import enumerate_cameras

    return enumerate_cameras(api)


def discover_camera_devices() -> dict:
    backend, api = capture_backend(get_settings().camera_backend)
    if sys.platform != "win32":
        return {"backend": backend, "devices": [], "error":
                "Camera name discovery is available on Windows. Enter device indices manually."}
    try:
        cameras = _enumerate_backend(api)
        devices = []
        for camera in cameras:
            # Do not use friendly names as identity: identical USB cameras share names.
            path = camera.path or ""
            uid = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12] if path else None
            devices.append({"device_id": camera.index, "name": camera.name,
                            "device_uid": uid})
        return {"backend": backend, "devices": devices, "error": None}
    except ImportError:
        return {"backend": backend, "devices": [], "error":
                "Camera name discovery requires cv2-enumerate-cameras. "
                "Install backend requirements and restart the backend."}
    except Exception:
        logger.warning("Camera device metadata could not be enumerated", exc_info=True)
        return {"backend": backend, "devices": [], "error":
                "Camera device names could not be listed. Retry or enter device indices manually."}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`camera_discovery.py` Lines 15–21 (`capture_backend`):** On Windows (`sys.platform == "win32"`), `"auto"` resolves to `"dshow"` (`cv2.CAP_DSHOW`). Using the exact same backend for both `enumerate_cameras(api)` and `cv2.VideoCapture(dev_id, api)` guarantees that `camera.index` (`0, 1, 2, 3`) refers to the exact same physical USB port in both discovery and capture.
  * **`camera_discovery.py` Lines 40–44 (`device_uid`):** Identical USB webcams have the same friendly `camera.name`. BananaVision hashes the OS USB hardware path (`hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]`) to produce a unique 12-character `device_uid` without exposing raw OS paths.

---

#### Step B1: Adding, Renaming & Assigning Camera Slots in `SystemConfig.tsx` (`<TabsContent value="scanner">`)
* **Step Title & Trigger:** Administrator clicks `"Add Camera"`, clicks a camera name to rename it inline (`startEditingCameraId` → `saveEditedCameraId`), or selects a device index in `<CameraDevicePicker>` / `<NumberField>`, then clicks `"Save Changes"`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 103–172 & 284–370)
* **Complete Uncut Code Block:**
```tsx
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
```
```tsx
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 105–116 (`addCamera`):** Enforces a maximum of 4 camera slots (`activeCameraIds.length >= 4`). Picks the lowest unused nonnegative integer `deviceId` (`0, 1, 2...`) and lowest unused `CAM-00X` name, appending them to `localConfig.cameraIds` and `localConfig.cameraDeviceIds`.
  * **Lines 124–151 (`saveEditedCameraId`):** Validates that the renamed camera ID is nonempty, `<= 50` characters, contains no comma, and does not duplicate any other slot's camera ID.
  * **Lines 155–159 (`handleSave` Client Validation):** Rejects saving if `deviceIds.length !== activeCameraIds.length`, if two slots share the same `deviceId` (`new Set(deviceIds).size !== deviceIds.length`), or if any index is negative or `NaN`.

---

### Phase C & D: Live MJPEG Calibration Modal & Atomic Camera Mapping (`CameraCalibrationModal.tsx` & `cameras.py`)

#### Step C1: Live MJPEG Streaming & Position Swapping (`CameraCalibrationModal.tsx` → `backend/app/api/v1/cameras.py`)
* **Step Title & Trigger:** Administrator clicks `"Calibrate Camera Positions"`, views live MJPEG streams from each camera (`GET /api/v1/cameras/preview/{camera_index}`), swaps positions (`Top`, `Left`, `Right`, `Rear`) via the `<Select>` dropdown, and clicks `"Save Mapping"` (`POST /api/v1/cameras/mapping`).
* **Exact File Path & Line Numbers:** `frontend/src/components/CameraCalibrationModal.tsx` (Lines 1–198) and `backend/app/api/v1/cameras.py` (Lines 50–194)
* **Complete Uncut Code Block (`frontend/src/components/CameraCalibrationModal.tsx`, Lines 1–198):**
```tsx
import { useState, useEffect, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import type { ApiConfig } from "@/types/api"
import { api, BASE_URL, withMediaToken } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "sonner"
import { Camera, RefreshCw } from "lucide-react"
import { useCameraDiscovery } from "@/hooks/useCameraDiscovery"

interface CameraSlot { device_id: number; camera_id: string; label: string; online: boolean }

export function CameraCalibrationModal({ disabled = false }: { disabled?: boolean }) {
  const { acceptConfig } = useAdmin()
  const [loadedConfig, setLoadedConfig] = useState<ApiConfig | null>(null)
  const [error, setError] = useState("")
  const pending = useRef(false)
  const operationId = useRef<string | null>(null)
  const [open, setOpen] = useState(false)
  const cameraDiscovery = useCameraDiscovery(open)
  const [cameras, setCameras] = useState<CameraSlot[]>([])
  const [labels, setLabels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  // Mapping of label -> device_id
  const [mapping, setMapping] = useState<Record<string, number>>({})
  const detectedDevices = new Map(cameraDiscovery.discovery?.devices.map(device => [device.device_id, device]))

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    const load = async () => {
      setLoadedConfig(null); setError(""); operationId.current = null
      try {
        const [data, saved] = await Promise.all([
          api.cameras.list(controller.signal),
          api.config.get(controller.signal),
        ])
        if (controller.signal.aborted) return
        setCameras(data); setLabels(data.map(cam => cam.label))
        setMapping(Object.fromEntries(data.map(cam => [cam.label, cam.device_id])))
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
      setOpen(false)
      if (saved.application_status === "applied") { toast.success("Camera mapping saved and applied") }
      else { toast.warning("Camera mapping saved", { description: saved.application_error ?? "Some cameras could not initialize — they may be offline or disconnected." }) }
    } catch (error) {
      toast.error("Failed to save camera mapping", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      pending.current = false
      operationId.current = null
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
        {cameraDiscovery.loading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><RefreshCw className="w-4 h-4 animate-spin" />Listing camera devices…</p>}
        {cameraDiscovery.error && <p className="text-sm text-muted-foreground">{cameraDiscovery.error}</p>}
        {!loadedConfig && !error ? (
          <div role="status" aria-label="Loading camera configuration" className="grid grid-cols-1 md:grid-cols-2 gap-4">{[0, 1].map(i => <div key={i} className="border rounded-xl p-2 space-y-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="aspect-video w-full" /><Skeleton className="h-9 w-full" /></div>)}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cameras.map((cam) => (
              <div key={cam.device_id} className="border rounded-xl p-2 bg-muted/10 space-y-2">
                <p className="text-xs text-muted-foreground">
                  Index {cam.device_id} — {detectedDevices.get(cam.device_id)?.name ?? "Device name unavailable"}
                  {detectedDevices.get(cam.device_id)?.device_uid && ` · ${detectedDevices.get(cam.device_id)?.device_uid}`}
                </p>
                <div className="aspect-video bg-black rounded-lg overflow-hidden relative">
                  {cam.online ? (
                    <img 
                      src={withMediaToken(`${BASE_URL}/api/v1/cameras/preview/${cam.device_id}`)}
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
                  <Select disabled={loading}
                    value={Object.keys(mapping).find(key => mapping[key] === cam.device_id) || ""} 
                    onValueChange={(newLabel) => {
                      setMapping(prev => {
                        const next = { ...prev }
                        // Find the label this camera currently holds
                        const oldLabel = Object.keys(next).find(k => next[k] === cam.device_id)
                        // Find the device that currently holds the target label
                        const otherDeviceId = next[newLabel]
                        // Swap: give the other camera our old label
                        if (oldLabel && otherDeviceId !== undefined) {
                          next[oldLabel] = otherDeviceId
                        }
                        // Assign the new label to this camera
                        next[newLabel] = cam.device_id
                        return next
                      })
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
          <Button variant="outline" disabled={loading} onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={loading || !loadedConfig}>
            {loading && <RefreshCw className="w-4 h-4 mr-2 animate-spin" />}
            Save Mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```
* **Complete Uncut Code Block (`backend/app/api/v1/cameras.py`, Lines 50–194):**
```python
@router.get("")
async def list_cameras(db: DbSession):
    """
    List all configured cameras with their device IDs and online status.
    No auth required — used by the kiosk to map cameras to preview streams.
    """
    config = await configuration.get_config(db)
    applied = dict(zip(camera_manager._device_ids, camera_manager._logical_ids))
    return [{"device_id": slot.device_index, "camera_id": slot.camera_id,
             "label": settings.camera_labels[index] if index < len(settings.camera_labels) else f"Scanner {index + 1}",
             "online": slot.device_index in camera_manager.online_cameras
             and applied.get(slot.device_index) == slot.camera_id}
            for index, slot in enumerate(configuration.ordered_camera_slots(config.camera_slots))]

async def generate_frames(camera_index: int, fps: int = 15):
    """
    Generator that captures frames continuously from the specified camera,
    downscales them, and yields them as an MJPEG stream.
    """
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} is not online")

    interval = 1.0 / fps
    loop = asyncio.get_event_loop()

    generation = camera_manager.generation
    while generation == camera_manager.generation:
        coordinator.assert_ready()
        start_time = loop.time()
        try:
            # Capture frame
            async with coordinator.operation():
                capture = await run_blocking(camera_manager._capture_single, camera_index)
            if generation != camera_manager.generation:
                break
            
            # Preserve native geometry and pixels when already within the preview bounds.
            frame = capture.frame
            height, width = frame.shape[:2]
            scale = min(
                1.0, settings.camera_preview_max_width / width,
                settings.camera_preview_max_height / height,
            )
            if scale < 1.0:
                frame = cv2.resize(
                    frame, (max(1, round(width * scale)), max(1, round(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            
            # Encode as JPEG
            success, buffer = cv2.imencode(
                '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, settings.camera_preview_jpeg_quality],
            )
            if not success:
                logger.warning(f"Failed to encode frame from camera {camera_index}")
                await asyncio.sleep(interval)
                continue

            # Yield multipart chunks
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
            )
        except Exception as exc:
            logger.error(f"Error yielding frame from camera {camera_index}: {exc}")
            # If camera disconnects, we should break and let the stream end appropriately
            break

        # Enforce FPS limit
        elapsed = loop.time() - start_time
        sleep_time = interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            # Quick yield buffer even if we are behind
            await asyncio.sleep(0.001)

@router.get("/preview/{camera_index}")
async def video_feed(
    camera_index: int,
    user: MediaUser,
    fps: Annotated[int, Query(ge=1, le=30)] = 15,
):
    """
    Returns an MJPEG stream for a specific camera.
    """
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail="Camera not found or offline.")
        
    return StreamingResponse(
        generate_frames(camera_index, fps),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

class CameraMappingUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    operation_id: uuid.UUID
    device_ids: list[StrictInt] = Field(min_length=1, max_length=4)

    @field_validator("device_ids")
    @classmethod
    def valid_mapping(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Camera indices must be distinct and nonnegative")
        return ids

def _device_ids(config) -> dict:
    """Physical slot indices as plain text, read before the update refreshes the slots."""
    _, device_ids = configuration.camera_slot_values(config.camera_slots)
    return {'camera_device_ids': ', '.join(str(value) for value in device_ids)}


@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate, db: DbSession, admin: AdminUser, request: Request):
    """Persist physical slots atomically, then apply and report actual hardware results."""
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan before remapping cameras")
    async with station_lock:
        previous = await operation_result(db, str(mapping.operation_id))
        if previous:
            if previous.get('actor_id') != str(admin.id) or previous.get('device_ids') != mapping.device_ids or previous.get('kind') != 'calibration':
                raise HTTPException(409, 'Operation ID already used')
            return configuration.config_response(await configuration.get_config(db))
        admin_profile_id = await db.scalar(select(AdminProfile.id).where(AdminProfile.account_id == admin.id))
        before = _device_ids(await configuration.get_config(db))
        config = await configuration.update_config(db, {'camera_device_ids': mapping.device_ids},
            mapping.expected_revision, admin_profile_id)
        described = audit.describe_changes(before, _device_ids(config))
        if described:  # Saving the same mapping is not an event.
            await audit.record(
                db, audit.AuditAction.CONFIG_CHANGED,
                f'Camera mapping revision {mapping.expected_revision} → {config.revision}: '
                f'{described}',
                actor=admin, ip=get_client_ip(request),
            )
        await record_operation(db, str(mapping.operation_id), {'kind': 'calibration', 'actor_id': str(admin.id),
            'device_ids': mapping.device_ids, 'status': 'saved'})
        await db.commit()
        await configuration.apply_camera_config(config)
        await configuration.sync_devices(db)
        response = configuration.config_response(config)
        response['results'] = {device_id: device_id in camera_manager.online_cameras for device_id in mapping.device_ids}
        response['message'] = 'Camera mapping saved; see application status for hardware results'
        return response
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Position Swap Logic (`CameraCalibrationModal.tsx` Lines 156–171):** When the admin assigns `newLabel` (e.g., `"Top"`) to `cam.device_id`, `setMapping` automatically swaps `oldLabel` (the position `cam.device_id` previously held) to `otherDeviceId` (the camera that previously held `"Top"`), preventing duplicate assignments.
  * **Idempotent `operation_id` (`cameras.py` Lines 169–173):** If a network hiccup causes a retry with the same `operation_id`, `operation_result(db, str(mapping.operation_id))` returns the already-saved configuration instead of failing with a revision mismatch.

---

### Phase E: Database Slot Storage (`device` Table) & Two-Phase Unique Constraint Rewrite

#### Step E1: `Device` ORM Model (`device.py`) & `_replace_camera_slots` (`configuration.py`)
* **Step Title & Trigger:** When `camera_ids` or `camera_device_ids` change, `update_config()` calls `_replace_camera_slots()` to update the `device` table without violating unique constraints on `camera_id`, `slot_index`, or `device_index`, then calls `apply_camera_config()` and `sync_devices()`.
* **Exact File Path & Line Numbers:** `backend/app/models/device.py` (Lines 1–58) and `backend/app/services/configuration.py` (Lines 196–240 & 284–302)
* **Complete Uncut Code Block (`backend/app/models/device.py`, Lines 1–58):**
```python
"""
Device (camera) ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import CheckConstraint, Enum as SAEnum, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import DeviceStatusEnum

class Device(Base):
    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("slot_index", name="uq_device_slot_index"),
        UniqueConstraint("device_index", name="uq_device_device_index"),
        CheckConstraint(
            "slot_index IS NULL OR (slot_index >= 0 AND slot_index < 4)",
            name="ck_device_slot_index_range",
        ),
        CheckConstraint(
            "device_index IS NULL OR device_index >= 0",
            name="ck_device_device_index_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # Nullable only for operational rows that were never assigned to a saved slot.
    # The saved camera-slot mapping itself is these two columns, not a repeated
    # CSV/JSON field on system_config.
    slot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DeviceStatusEnum] = mapped_column(SAEnum(DeviceStatusEnum), nullable=False, default=DeviceStatusEnum.OFFLINE
    )
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True, default="1920x1080")
    last_seen: Mapped[datetime | None] = mapped_column(ManilaDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )

    # Relationships — reverse links to per-camera scan data
    detections = relationship("ScanDetection", back_populates="device", lazy="raise")
    images = relationship("ScanImage", back_populates="device", lazy="raise")
```
* **Complete Uncut Code Block (`backend/app/services/configuration.py`, Lines 196–240 & 284–302):**
```python
async def _replace_camera_slots(db, current_slots, camera_ids, device_ids):
    """Rewrite slot rows in place, preserving each existing slot's device UUID.

    Unassigned rows are retained unless a reused slot needs the same camera name.
    """
    names = [part.strip() for part in camera_ids.split(',')]
    devices = (await db.execute(select(Device))).scalars().all()
    slot_rows = {device.slot_index: device for device in
                 ordered_camera_slots(current_slots) if device.slot_index is not None}
    unassigned = {device.camera_id: device for device in devices if device.slot_index is None}

    # Release every unique name/index before assigning the new arrangement.
    for device in slot_rows.values():
        device.camera_id = f'pending-{device.id}'
        device.slot_index = None
        device.device_index = None
    # An unassigned duplicate cannot keep a name that a reused slot now owns.
    for index, name in enumerate(names):
        device = unassigned.get(name)
        if device is not None and index in slot_rows:
            await db.delete(device)
    await db.flush()

    for index, (name, device_index) in enumerate(zip(names, device_ids, strict=True)):
        device = slot_rows.get(index)
        if device is None:
            device = unassigned.get(name)
        if device is None:
            device = Device(
                camera_id=name, label=f'Scanner {index + 1}',
                status='Offline', resolution=None,
            )
            db.add(device)
        device.camera_id = name
        device.slot_index = index
        device.device_index = device_index

    for index, device in slot_rows.items():
        if index >= len(names):
            await db.delete(device)

    await db.execute(update(Device).where(Device.slot_index.is_not(None)).values(
        status='Offline', resolution=None,
    ))
```
```python
async def apply_camera_config(config) -> None:
    """Call only after saved configuration and its audit have committed."""
    from app.services.runtime_operations import run_blocking
    names, device_ids = camera_slot_values(config.camera_slots)
    await run_blocking(camera_manager.configure, names.split(', '), device_ids)


async def sync_devices(db):
    """Publish only frame-verified current mappings after physical application."""
    mapping = dict(zip(camera_manager._logical_ids, camera_manager._device_ids))
    online = set(camera_manager.online_cameras)
    for device in (await db.execute(select(Device))).scalars():
        ok = mapping.get(device.camera_id) in online
        device.status = 'Online' if ok else 'Offline'
        measured = camera_manager.get_resolution(mapping[device.camera_id]) if ok else None
        device.resolution = f'{measured[0]}x{measured[1]}' if measured else None
        if ok:
            device.last_seen = now_manila()
    await db.commit()
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Normalized Storage in `device` (`device.py` Lines 23–34):** Rather than storing a CSV string of camera IDs on `system_config`, each configured camera slot is a row in the `device` table with `slot_index` (`0..3`) and `device_index` (`>= 0`), enforced by `uq_device_slot_index`, `uq_device_device_index`, `ck_device_slot_index_range`, and `ck_device_device_index_nonnegative`.
  * **Two-Phase Flush to Avoid Unique Collisions on Swaps (`configuration.py` Lines 208–217):** If an admin swaps `device_index` `0` and `1` between `CAM-001` and `CAM-002`, updating them directly would violate `uq_device_device_index`. `_replace_camera_slots` first sets `camera_id = f'pending-{device.id}'`, `slot_index = None`, and `device_index = None` on all slot rows and runs `await db.flush()`, then assigns the new `(name, index, device_index)` pairs while preserving each slot row's `Device.id` UUID.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Camera Discovery Endpoint** | `GET /api/v1/cameras/discovery` → `discover_cameras()` (`backend/app/api/v1/cameras.py` Lines 32–48) |
| **MJPEG Preview Endpoint** | `GET /api/v1/cameras/preview/{camera_index}` → `video_feed()` (`cameras.py` Lines 127–142), authenticated via `MediaUser` (`?token=<JWT>`) |
| **Camera Mapping Endpoint** | `POST /api/v1/cameras/mapping` → `update_camera_mapping()` (`cameras.py` Lines 163–194) |
| **Retry Hardware Apply Endpoint** | `POST /api/v1/config/maintenance/apply` → `apply_cameras()` (`backend/app/api/v1/maintenance.py` Lines 247–283) |
| **Slot Limits & DB Constraints** | `1–4` slots (`0 <= slot_index < 4`), `device_index >= 0`, distinct `camera_id`, `slot_index`, and `device_index` on `device` table |
| **Frame Validation Thresholds** | `_MEAN_THRESHOLD = 15.0`, `_STDDEV_THRESHOLD = 8.0`, `_VALIDATION_FRAMES = 3`, `> 1%` pixels brighter than `30/255` (`camera_manager.py` Lines 96–133) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Add a `"Remove Camera"` Button Next to Each Camera Slot (When More Than 1 Camera Is Configured)
* **Examiner Prompt:** *"In `SystemConfig.tsx` shows an `'Add Camera'` button (up to 4 slots), but no button to remove a camera slot. Add a `'Remove'` button on each camera row that is enabled whenever `activeCameraIds.length > 1`."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 116 & 322–324)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Line 322):**
```tsx
                        <Badge variant="secondary" className={`shrink-0 text-xs ${status === "Online" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : ""}`}>{status}</Badge>
                      </div>
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 322–335):**
```tsx
                        <Badge variant="secondary" className={`shrink-0 text-xs ${status === "Online" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : ""}`}>{status}</Badge>
                        {activeCameraIds.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={disabled || saving}
                            className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                            onClick={() => {
                              const nextIds = activeCameraIds.filter((_, i) => i !== index)
                              const nextDevices = (localConfig.cameraDeviceIds ?? []).filter((_, i) => i !== index)
                              setLocalConfig({ ...localConfig, cameraIds: nextIds.join(", "), cameraDeviceIds: nextDevices })
                            }}
                          >
                            Remove
                          </Button>
                        )}
                      </div>
```

---

#### Drill Scenario 2: Display the Camera Position Label (`Top`, `Left`, `Right`, `Rear`) Next to Each Camera Slot in `SystemConfig.tsx`
* **Examiner Prompt:** *"In the Scanner Cameras list in `SystemConfig.tsx`, display the physical view label (`Top`, `Left`, `Right`, `Rear`) badge next to each camera slot name so administrators know which angle Slot 1..4 corresponds to."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 303–324)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 311–313):**
```tsx
                      <div className="flex items-center gap-3 min-w-0">
                        <Camera className="w-4 h-4 text-muted-foreground shrink-0" />
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 311–316):**
```tsx
                      <div className="flex items-center gap-3 min-w-0">
                        <Camera className="w-4 h-4 text-muted-foreground shrink-0" />
                        <Badge variant="outline" className="shrink-0 text-xs font-semibold">
                          {["Top", "Left", "Right", "Rear"][index] ?? `Slot ${index + 1}`}
                        </Badge>
```

---

#### Drill Scenario 3: Adjust the MJPEG Live Preview Frame Rate from 15 FPS to 24 FPS
* **Examiner Prompt:** *"Increase the default MJPEG calibration preview stream frame rate from 15 FPS to 24 FPS in `backend/app/api/v1/cameras.py`."*
* **File to Edit:** `backend/app/api/v1/cameras.py` (Lines 64 & 131)
* **Before (`backend/app/api/v1/cameras.py`, Lines 64 & 131):**
```python
async def generate_frames(camera_index: int, fps: int = 15):
```
```python
@router.get("/preview/{camera_index}")
async def video_feed(
    camera_index: int,
    user: MediaUser,
    fps: Annotated[int, Query(ge=1, le=30)] = 15,
):
```
* **After (`backend/app/api/v1/cameras.py`, Lines 64 & 131):**
```python
async def generate_frames(camera_index: int, fps: int = 24):
```
```python
@router.get("/preview/{camera_index}")
async def video_feed(
    camera_index: int,
    user: MediaUser,
    fps: Annotated[int, Query(ge=1, le=30)] = 24,
):
```
