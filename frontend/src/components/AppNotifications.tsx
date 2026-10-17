import { useState, useMemo, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"

import { api } from "@/lib/api"
import { toast } from "sonner"
import type { AppNotification, NotificationType } from "@/types"
import type { ApiNotification } from "@/types/api"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Bell,
  AlertTriangle,
  Package,
  CheckCircle2,
  Info,
  ShieldAlert,
  Check,
  Loader2,
} from "lucide-react"

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeTime(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return "Just now"
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}

const notificationConfig: Record<NotificationType, { icon: typeof Bell; color: string; bg: string }> = {
  scan_complete: {
    icon: CheckCircle2,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
  },
  scan_flagged: {
    icon: AlertTriangle,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
  },
  intake_update: {
    icon: Package,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
  },
  system_alert: {
    icon: Info,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
  },
  quality_warning: {
    icon: ShieldAlert,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
  },
}

const mapApiNotification = (n: ApiNotification): AppNotification => ({
  id: n.id,
  type: n.type,
  title: n.title,
  message: n.message,
  timestamp: new Date(n.timestamp),
  read: n.read,
  href: n.href ?? undefined,
})

export function AppNotifications() {
  const { user } = useAuth()
  return user ? <NotificationList key={`${user.id}:${user.role}`} /> : null
}

function NotificationList() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [markingRead, setMarkingRead] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const pending = useRef(new Set<string>())
  const confirmedRead = useRef(new Set<string>())
  const markAllPending = useRef(false)
  const request = useRef<AbortController | null>(null)
  const mounted = useRef(false)

  const fetchNotifications = useCallback(async () => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError(null)
    try {
      const res = await api.notifications.list(controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      if (!Array.isArray(res.items)) throw new Error("Notifications could not be loaded.")
      setNotifications(res.items.map(item => ({ ...mapApiNotification(item), read: item.read || confirmedRead.current.has(item.id) })))
      setLoaded(true)
    } catch (cause) {
      if (!controller.signal.aborted && mounted.current) setError(cause instanceof Error ? cause.message : "Notifications could not be loaded.")
    } finally {
      if (request.current === controller && mounted.current) setLoading(false)
    }
  }, [])

  // Load on mount
  useEffect(() => {
    mounted.current = true
    void fetchNotifications()
    return () => { mounted.current = false; request.current?.abort() }
  }, [fetchNotifications])

  // Refresh when popover opens
  useEffect(() => {
    if (open) void fetchNotifications()
  }, [open, fetchNotifications])

  const filteredNotifications = useMemo(() => {
    const OPERATOR_TYPES: NotificationType[] = ["scan_complete", "scan_flagged"]
    if (user?.role === "Operator") {
      return notifications.filter(n => OPERATOR_TYPES.includes(n.type))
    }
    return notifications
  }, [notifications, user])

  const unreadCount = useMemo(() => filteredNotifications.filter((n) => !n.read).length, [filteredNotifications])

  const markAsRead = async (id: string) => {
    if (pending.current.has(id) || markAllPending.current) return
    pending.current.add(id)
    setPendingIds(new Set(pending.current))
    try {
      await api.notifications.markRead(id)
      if (!mounted.current) return
      confirmedRead.current.add(id)
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))
    } catch (error) {
      toast.error("Could not mark notification as read", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      pending.current.delete(id)
      if (mounted.current) setPendingIds(new Set(pending.current))
    }
  }

  const markAllAsRead = async () => {
    if (markAllPending.current || pending.current.size) return
    markAllPending.current = true
    setMarkingRead(true)
    const ids = new Set(notifications.map(notification => notification.id))
    try {
      await api.notifications.markAllRead()
      if (!mounted.current) return
      ids.forEach(id => confirmedRead.current.add(id))
      setNotifications((prev) => prev.map((n) => ids.has(n.id) ? { ...n, read: true } : n))
    } catch (error) {
      toast.error("Could not mark notifications as read", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      markAllPending.current = false
      if (mounted.current) setMarkingRead(false)
    }
  }

  const handleNotificationClick = (notification: AppNotification) => {
    if (!notification.read) void markAsRead(notification.id)
    if (notification.href) {
      navigate(notification.href)
      setOpen(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id="notification-trigger"
          aria-label="Notifications"
          variant="ghost"
          size="icon"
          className="relative h-9 w-9 rounded-lg hover:bg-accent"
        >
          <Bell className="w-4.5 h-4.5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-4.5 h-4.5 rounded-full bg-destructive text-white text-[10px] font-bold px-1 shadow-sm animate-in zoom-in-50 duration-200">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        id="notification-popover"
        className="w-95 p-0 rounded-xl shadow-xl"
        align="end"
        sideOffset={8}
      >
        {/* Popover Header */}
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Notifications</h3>
            {unreadCount > 0 && (
              <Badge variant="destructive" className="text-[10px] h-5 px-1.5">
                {unreadCount > 9 ? '9+' : unreadCount} new
              </Badge>
            )}
          </div>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 px-2 text-muted-foreground hover:text-foreground"
              onClick={markAllAsRead}
              disabled={markingRead || pendingIds.size > 0}
            >
              {markingRead ? <Loader2 aria-hidden="true" className="w-3 h-3 mr-1 animate-spin" /> : <Check className="w-3 h-3 mr-1" />}
              Mark all read
            </Button>
          )}
        </div>

        <Separator />

        {/* Notification List */}
        <div className="max-h-100 overflow-y-auto" aria-busy={loading}>
          {error && <div role="alert" className="px-4 py-3 text-sm text-muted-foreground">{loaded ? "Showing previously loaded notifications. " : ""}{error}<Button variant="ghost" size="sm" disabled={loading} onClick={() => void fetchNotifications()}>Retry notifications</Button></div>}
          {loading && loaded && <p role="status" className="px-4 py-2 text-xs text-muted-foreground">Refreshing notifications…</p>}
          {!loaded && loading ? <div role="status" aria-label="Loading notifications" className="space-y-3 p-4"><span className="sr-only">Loading notifications</span>{[0, 1, 2].map(index => <Skeleton key={index} aria-hidden="true" className="h-14 w-full" />)}</div> : !loaded ? null : filteredNotifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Bell className="w-8 h-8 mb-2 opacity-40" />
              <p className="text-sm">No notifications yet</p>
            </div>
          ) : (
            <div className="py-1">
              {filteredNotifications.map((notification) => {
                const cfg = notificationConfig[notification.type]
                const Icon = cfg.icon
                return (
                  <button
                    key={notification.id}
                    disabled={pendingIds.has(notification.id) || markingRead}
                    aria-busy={pendingIds.has(notification.id)}
                    className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/60 ${!notification.read ? "bg-accent/30" : ""
                      }`}
                    onClick={() => handleNotificationClick(notification)}
                  >
                    <div className={`shrink-0 mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center ${cfg.bg}`}>
                      <Icon className={`w-4 h-4 ${cfg.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={`text-sm font-medium truncate ${!notification.read ? "text-foreground" : "text-muted-foreground"}`}>
                          {notification.title}
                        </p>
                        {!notification.read && (
                          <span className="shrink-0 w-2 h-2 rounded-full bg-primary" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
                        {notification.message}
                      </p>
                      <p className="text-[11px] text-muted-foreground/70 mt-1">
                        {relativeTime(notification.timestamp)}
                      </p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        <Separator />

        {/* Popover Footer */}
        {user?.role !== "Operator" && (
          <div className="p-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs h-8 text-muted-foreground hover:text-foreground"
              onClick={() => {
                setOpen(false)
                navigate("/admin/activity")
              }}
            >
              View all activity
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
