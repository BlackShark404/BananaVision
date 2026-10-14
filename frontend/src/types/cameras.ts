export interface CameraDevice {
  device_id: number
  name: string
  device_uid: string | null
  configured_camera_id: string | null
  online: boolean
}

export interface CameraDiscovery {
  backend: string
  devices: CameraDevice[]
  error: string | null
}
