import { useEffect, useRef, useState } from "react"
import QRCode from "qrcode"
import { api } from "@/lib/api"
import { mapApiScan } from "@/lib/scanData"
import { getImageUrl } from "@/lib/utils"
import type { ScanResult } from "@/types"

const idle = {
  isScanning: false, scanStep: 0, scanProgress: 0, lastResult: null as ScanResult | null,
  owner: "", error: "", pendingScanId: null as string | null,
}

/** Local demo state is never accepted into ScanContext or delivery inventory. */
export function useKioskDemo(sessionKey: string) {
  const [state, setState] = useState(idle)
  const pending = useRef<{ scanId: string; requestId: string; owner: string } | null>(null)
  const busy = useRef<string | null>(null)
  const activeOwner = useRef(sessionKey)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => { activeOwner.current = sessionKey }, [sessionKey])

  const run = async (scanId: string) => {
    if (busy.current === sessionKey) return
    busy.current = sessionKey
    if (pending.current?.owner !== sessionKey) pending.current = null
    setState({ ...idle, owner: sessionKey, isScanning: true, scanStep: 1, scanProgress: 20 })
    try {
      // Demonstration progress uses saved data; no capture/inference endpoint is called.
      for (const step of [2, 3]) {
        await new Promise(resolve => setTimeout(resolve, 350))
        if (!mounted.current || activeOwner.current !== sessionKey) return
        setState(previous => ({ ...previous, scanStep: step, scanProgress: step === 2 ? 60 : 80 }))
      }
      pending.current ??= { scanId, requestId: crypto.randomUUID(), owner: sessionKey }
      const request = pending.current
      setState(previous => ({ ...previous, pendingScanId: request.scanId }))
      const response = await api.scans.kioskDemo(request.scanId, request.requestId)
      const result = { ...mapApiScan(response.scan, getImageUrl), printJob: response.print_job }
      // Printing is already queued by the explicit POST; QR preview failures cannot resubmit it.
      try {
        result.qrCode = await QRCode.toDataURL(response.label.payload, { margin: 4, errorCorrectionLevel: "M" })
      } catch { /* The committed print receipt remains usable without its preview. */ }
      if (mounted.current && activeOwner.current === sessionKey) {
        pending.current = null
        setState({ ...idle, owner: sessionKey, lastResult: result })
      }
    } catch (err) {
      if (mounted.current && activeOwner.current === sessionKey) {
        setState({ ...idle, owner: sessionKey, pendingScanId: pending.current?.scanId ?? null,
          error: err instanceof Error ? err.message : "Demo request failed" })
      }
    } finally {
      if (busy.current === sessionKey) busy.current = null
    }
  }

  const visible = state.owner === sessionKey ? state : idle
  return { state: visible, error: visible.error, pendingScanId: visible.pendingScanId, run }
}
