import { useState, useMemo, useEffect, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"

import { api } from "@/lib/api"
import type { AppNotification, NotificationType } from "@/types"
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

const mapApiNotification = (n: any): AppNotification => ({
  id: n.id,
  type: n.type,
  title: n.title,
  message: n.message,
  timestamp: new Date(n.timestamp),
  read: n.read,
  href: n.href,
})

export function AppNotifications() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await api.notifications.list()
      const items = res.items || res as any
      if (Array.isArray(items)) {
        setNotifications(items.map(mapApiNotification))
      }
    } catch {
      console.error("[AppNotifications] Failed to fetch notifications")
    }
    setLoaded(true)
  }, [loaded])

  // Load on mount
  useEffect(() => {
    if (user) fetchNotifications()
  }, [user])

  // Refresh when popover opens
  useEffect(() => {
    if (open && user) fetchNotifications()
  }, [open])

  const filteredNotifications = useMemo(() => {
    const OPERATOR_TYPES: NotificationType[] = ["scan_complete", "scan_flagged"]
    if (user?.role === "Operator") {
      return notifications.filter(n => OPERATOR_TYPES.includes(n.type))
    }
    return notifications
  }, [notifications, user])

  const unreadCount = useMemo(() => filteredNotifications.filter((n) => !n.read).length, [filteredNotifications])

  const markAsRead = (id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))
    api.notifications.markRead(id).catch(() => {})
  }

  const markAllAsRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
    api.notifications.markAllRead().catch(() => {})
  }

  const handleNotificationClick = (notification: AppNotification) => {
    markAsRead(notification.id)
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
            >
              <Check className="w-3 h-3 mr-1" />
              Mark all read
            </Button>
          )}
        </div>

        <Separator />

        {/* Notification List */}
        <div className="max-h-100 overflow-y-auto">
          {notifications.length === 0 ? (
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
