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
import { getToken, clearAuth } from "@/lib/auth"

const host = window.location.hostname
const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
const WS_BASE = import.meta.env.VITE_WS_URL || `${protocol}//${host}:8000`

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
  /** Called after an existing connection reopens, so clients can resync. */
  onReconnect?: () => void
  /** Whether to enable the connection (defaults to true) */
  enabled?: boolean
}

export function useWebSocket({ rooms = [], onEvent, onReconnect, enabled = true }: UseWebSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected")
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)
  const onReconnectRef = useRef(onReconnect)
  const hasConnected = useRef(false)

  // Keep callback refs up to date without re-triggering the connection effect.
  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  useEffect(() => {
    onReconnectRef.current = onReconnect
  }, [onReconnect])

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
      if (wsRef.current !== ws) return
      const resumed = hasConnected.current
      hasConnected.current = true
      setStatus("connected")
      reconnectAttempt.current = 0
      console.log("[WS] Connected", rooms)
      // The first connection uses initial fetches; only a resume can have
      // missed events while no socket was open.
      if (resumed) onReconnectRef.current?.()
    }

    ws.onmessage = (e) => {
      if (wsRef.current !== ws) return
      try {
        const msg: WsEvent = JSON.parse(e.data)
        setLastEvent(msg)
        onEventRef.current?.(msg.event, msg.data)
      } catch {
        console.warn("[WS] Invalid message:", e.data)
      }
    }

    ws.onclose = (e) => {
      if (wsRef.current !== ws) return
      setStatus("disconnected")
      wsRef.current = null

      if ((e.code === 4001 || e.code === 4003) && getToken() === token) {
        clearAuth()
        window.location.href = "/login"
        return
      }

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

  const reconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    reconnectAttempt.current = 0
    if (wsRef.current) {
      const previous = wsRef.current
      wsRef.current = null
      previous.close(1000)
    }
    connect()
  }, [connect])

  // Connect on mount / when deps change
  useEffect(() => {
    connect()

    return () => {
      // Cleanup
      hasConnected.current = false
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      if (wsRef.current) {
        const previous = wsRef.current
        wsRef.current = null
        previous.close(1000) // Invalidate ownership before asynchronous close callbacks.
      }
    }
  }, [connect])

  return { status, lastEvent, reconnect }
}
