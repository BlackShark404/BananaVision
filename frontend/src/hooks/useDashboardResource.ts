import { useCallback, useEffect, useRef, useState } from "react"

interface ResourceState<T> {
  data: T | null
  receivedAt: number | null
  error: string | null
  loading: boolean
}

/** Retain successful snapshots on errors; failed initial loads never become zero activity. */
export function useDashboardResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<ResourceState<T>>({ data: null, receivedAt: null, error: null, loading: true })
  const mounted = useRef(false)
  const sequence = useRef(0)
  const request = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    if (!mounted.current) return
    const current = ++sequence.current
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 15_000)
    setState(previous => ({ ...previous, loading: true }))
    try {
      const data = await load(controller.signal)
      if (controller.signal.aborted) throw new Error("Request timed out")
      if (mounted.current && current === sequence.current) {
        setState({ data, receivedAt: Date.now(), error: null, loading: false })
      }
    } catch (error) {
      if (mounted.current && current === sequence.current) {
        setState(previous => ({ ...previous, loading: false,
          error: controller.signal.aborted ? "Request timed out. Try refreshing." : error instanceof Error ? error.message : "Unable to load data.",
        }))
      }
    } finally {
      window.clearTimeout(timeout)
      if (current === sequence.current) request.current = null
    }
  }, [load])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const interval = window.setInterval(() => void refresh(), 30_000)
    const onResume = () => { if (!document.hidden) void refresh() }
    window.addEventListener("focus", onResume)
    window.addEventListener("online", onResume)
    document.addEventListener("visibilitychange", onResume)
    return () => {
      mounted.current = false
      ++sequence.current
      request.current?.abort()
      window.clearInterval(interval)
      window.removeEventListener("focus", onResume)
      window.removeEventListener("online", onResume)
      document.removeEventListener("visibilitychange", onResume)
    }
  }, [refresh])
  return { ...state, refresh }
}
