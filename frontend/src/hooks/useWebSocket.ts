/**
 * WebSocket hook with auto-reconnect and event dispatch.
 *
 * Usage:
 *   const { status, lastEvent } = useWebSocket({
 *     rooms: ["kiosk", "dashboard"],
 *     onEvent: (event, data) => { ... },
 *   })
 */

import { useEffect, useRef, useState, useCallback } from "react"
import { getToken } from "@/lib/auth"

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000"

export type ConnectionStatus = "connecting" | "connected" | "disconnected"

export interface WsEvent {
  event: string
  data: any
  timestamp: string
}

interface UseWebSocketOptions {
  /** Room names to subscribe to */
  rooms?: string[]
  /** Callback for each received event */
  onEvent?: (event: string, data: any) => void
  /** Whether to enable the connection (defaults to true) */
  enabled?: boolean
}

export function useWebSocket({ rooms = [], onEvent, enabled = true }: UseWebSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected")
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)

  // Keep callback ref up to date without re-triggering effect
  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  const connect = useCallback(() => {
    const token = getToken()
    if (!token || !enabled) return

    // Build URL
    const roomsParam = rooms.length > 0 ? `&rooms=${rooms.join(",")}` : ""
    const url = `${WS_BASE}/api/v1/ws?token=${token}${roomsParam}`

    setStatus("connecting")
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus("connected")
      reconnectAttempt.current = 0
      console.log("[WS] Connected", rooms)
    }

    ws.onmessage = (e) => {
      try {
        const msg: WsEvent = JSON.parse(e.data)
        setLastEvent(msg)
        onEventRef.current?.(msg.event, msg.data)
      } catch {
        console.warn("[WS] Invalid message:", e.data)
      }
    }

    ws.onclose = (e) => {
      setStatus("disconnected")
      wsRef.current = null

      // Don't reconnect if closed cleanly (code 1000) or disabled
      if (e.code === 1000 || !enabled) return

      // Exponential backoff: 1s → 2s → 4s → 8s → max 30s
      const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 30000)
      reconnectAttempt.current += 1
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempt.current})`)
      reconnectTimer.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      // onclose will fire after this, triggering reconnect
    }
  }, [enabled, rooms.join(",")])

  // Connect on mount / when deps change
  useEffect(() => {
    connect()

    return () => {
      // Cleanup
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close(1000) // Clean close — no reconnect
      }
    }
  }, [connect])

  return { status, lastEvent }
}
