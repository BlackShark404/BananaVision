import { useCallback, useEffect, useRef, useState } from "react"

interface ResourceOptions {
  keepPreviousData?: boolean
}

interface ResourceState<T> {
  source: (signal: AbortSignal) => Promise<T>
  data: T | null
  receivedAt: number | null
  error: string | null
  loading: boolean
  isPreviousData: boolean
}

/** Retain successful snapshots on errors; failed initial loads never become zero activity. */
export function useDashboardResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  options?: ResourceOptions,
) {
  const keepPreviousData = options?.keepPreviousData ?? false
  const [state, setState] = useState<ResourceState<T>>({
    source: load,
    data: null,
    receivedAt: null,
    error: null,
    loading: true,
    isPreviousData: false,
  })
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
    setState(previous =>
      previous.source === load
        ? { ...previous, loading: true }
        : {
            source: load,
            data: keepPreviousData ? previous.data : null,
            receivedAt: keepPreviousData ? previous.receivedAt : null,
            error: null,
            loading: true,
            isPreviousData: keepPreviousData && previous.data !== null,
          },
    )
    try {
      const data = await load(controller.signal)
      if (controller.signal.aborted) throw new Error("Request timed out")
      if (mounted.current && current === sequence.current) {
        setState({ source: load, data, receivedAt: Date.now(), error: null, loading: false, isPreviousData: false })
      }
    } catch (error) {
      if (mounted.current && current === sequence.current) {
        setState(previous => ({
          ...previous,
          loading: false,
          error: controller.signal.aborted
            ? "Request timed out. Try refreshing."
            : error instanceof Error
              ? error.message
              : "Unable to load data.",
        }))
      }
    } finally {
      window.clearTimeout(timeout)
      if (current === sequence.current) request.current = null
    }
  }, [load, keepPreviousData])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const interval = window.setInterval(() => void refresh(), 30_000)
    let lastResumeAt = 0
    const onResume = () => {
      if (document.hidden) return
      // Focus and visibilitychange usually fire together; keep the first refresh
      // immediate and skip only the near-simultaneous duplicate.
      const now = Date.now()
      if (now - lastResumeAt < 150) return
      lastResumeAt = now
      void refresh()
    }
    window.addEventListener("focus", onResume)
    window.addEventListener("online", onResume)
    document.addEventListener("visibilitychange", onResume)
    return () => {
      mounted.current = false
      // A future request increments the sequence; mounted also guards unmounts.
      request.current?.abort()
      window.clearInterval(interval)
      window.removeEventListener("focus", onResume)
      window.removeEventListener("online", onResume)
      document.removeEventListener("visibilitychange", onResume)
    }
  }, [refresh])

  if (state.source === load) {
    return { ...state, refresh }
  }

  return {
    source: load,
    data: keepPreviousData ? state.data : null,
    receivedAt: keepPreviousData ? state.receivedAt : null,
    error: null,
    loading: true,
    isPreviousData: keepPreviousData && state.data !== null,
    refresh,
  }
}
