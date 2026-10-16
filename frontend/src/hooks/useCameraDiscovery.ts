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
