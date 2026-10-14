import type { CameraDiscovery } from "@/types/cameras"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export function CameraDevicePicker({ discovery, value, onChange, disabled, slot }: {
  discovery: CameraDiscovery | null
  value: number | undefined
  onChange: (value: number) => void
  disabled: boolean
  slot: number
}) {
  const cameras = discovery?.devices ?? []
  if (!cameras.length) return null
  const known = cameras.some(camera => camera.device_id === value)
  const selected = value !== undefined && Number.isSafeInteger(value) ? String(value) : ""
  return <Select value={selected} onValueChange={index => onChange(Number(index))} disabled={disabled}>
    <SelectTrigger aria-label={`Detected device for camera ${slot}`} className="w-full sm:w-80">
      <SelectValue placeholder="Choose a detected camera" />
    </SelectTrigger>
    <SelectContent>
      {!known && selected && <SelectItem value={selected}>Index {selected} — not detected</SelectItem>}
      {cameras.map(camera => <SelectItem key={camera.device_id} value={String(camera.device_id)}>
        Index {camera.device_id} — {camera.name}{camera.device_uid ? ` · ${camera.device_uid}` : ""}
      </SelectItem>)}
    </SelectContent>
  </Select>
}
