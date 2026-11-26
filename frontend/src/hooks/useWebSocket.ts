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
const secureContext = window.location.protocol === "https:"
const protocol = secureContext ? "wss:" : "ws:"
// An HTTPS page must use the same origin so a reverse proxy can forward the upgrade.
const WS_BASE = import.meta.env.VITE_WS_URL || (secureContext ? `${protocol}//${window.location.host}` : `${protocol}//${host}:8000`)

const HEARTBEAT_INTERVAL_MS = 25_000

export type ConnectionStatus = "connecting" | "connected" | "disconnected"

export interface WsEvent {
  event: string
  data: unknown
  timestamp: string
}

interface UseWebSocketOptions {
  /** Room names to subscribe to */
  rooms?: string[]
  /** Callback for each received event */
  onEvent?: (event: string, data: unknown) => void
  /** Called after an existing connection reopens, so clients can resync. */
  onReconnect?: () => void
  /** Whether to enable the connection (defaults to true) */
  enabled?: boolean
}

export function useWebSocket({ rooms = [], onEvent, onReconnect, enabled = true }: UseWebSocketOptions) {
  const roomsKey = rooms.join(",")
  const connectionKey = enabled ? roomsKey : null
  const [activeKey, setActiveKey] = useState(connectionKey)
  const [status, setStatus] = useState<ConnectionStatus>(() =>
    connectionKey !== null && getToken() ? "connecting" : "disconnected",
  )
  if (activeKey !== connectionKey) {
    setActiveKey(connectionKey)
    setStatus(connectionKey !== null && getToken() ? "connecting" : "disconnected")
  }
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const onEventRef = useRef(onEvent)
  const onReconnectRef = useRef(onReconnect)
  const openSocketRef = useRef<() => void>(() => {})
  const hasConnected = useRef(false)

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current)
      heartbeatTimer.current = null
    }
  }, [])

  // Keep callback refs up to date without re-triggering the connection effect.
  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  useEffect(() => {
    onReconnectRef.current = onReconnect
  }, [onReconnect])

  const openSocket = useCallback(() => {
    const token = getToken()
    if (!token || !enabled) return

    // Build URL
    const roomsParam = roomsKey.length > 0 ? `&rooms=${roomsKey}` : ""
    const url = `${WS_BASE}/api/v1/ws?token=${token}${roomsParam}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (wsRef.current !== ws) return
      const resumed = hasConnected.current
      hasConnected.current = true
      setStatus("connected")
      reconnectAttempt.current = 0
      stopHeartbeat()
      // Proxies close idle WebSockets; the backend answers this with pong.
      heartbeatTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ event: "ping" }))
      }, HEARTBEAT_INTERVAL_MS)
      console.log("[WS] Connected", roomsKey ? roomsKey.split(",") : [])
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
      stopHeartbeat()
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
      reconnectTimer.current = setTimeout(() => {
        if (enabled && getToken()) setStatus("connecting")
        openSocketRef.current()
      }, delay)
    }

    ws.onerror = () => {
      // onclose will fire after this, triggering reconnect
    }
  }, [enabled, roomsKey, stopHeartbeat])

  useEffect(() => {
    openSocketRef.current = openSocket
  }, [openSocket])

  const reconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    stopHeartbeat()
    reconnectAttempt.current = 0
    if (wsRef.current) {
      const previous = wsRef.current
      wsRef.current = null
      previous.close(1000)
    }
    if (enabled && getToken()) setStatus("connecting")
    openSocket()
  }, [enabled, openSocket, stopHeartbeat])

  // Connect on mount / when deps change
  useEffect(() => {
    openSocket()

    return () => {
      // Cleanup
      hasConnected.current = false
      stopHeartbeat()
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
  }, [openSocket, stopHeartbeat])

  return { status, lastEvent, reconnect }
}
