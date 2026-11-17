import { useState, useMemo, useRef } from "react"
import { useAdmin } from "@/context/AdminContext"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { ExportDropdown } from "@/components/ExportDropdown"
import { downloadCsv, downloadXlsx } from "@/lib/exportUtils"
import { ScrollText, Filter, Activity, UserCheck, AlertCircle } from "lucide-react"
import { toast } from "sonner"
import { manilaDayKey } from "@/lib/manilaTime"
import { activityBadgeClass, activityLabel, isCriticalActivity } from "@/lib/activityActions"
import type { ActivityLog as ActivityEntry } from "@/types"

const PAGE_SIZE = 15

export default function ActivityLog() {
  const { activityLogs, activityLoading, activityReady, activityError } = useAdmin()
  const initialLoading = activityLoading && !activityReady
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [userFilter, setUserFilter] = useState<string>("all")

  const users = useMemo(() => Array.from(new Set(activityLogs.map(log => log.user))).sort(), [activityLogs])
  const actionTypes = useMemo(() => Array.from(new Set(activityLogs.map(log => log.action)))
    .sort((a, b) => activityLabel(a).localeCompare(activityLabel(b))), [activityLogs])

  const filtered = useMemo(() => {
    return activityLogs.filter((log) => {
      if (actionFilter !== "all" && log.action !== actionFilter) return false
      if (userFilter !== "all" && log.user !== userFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return log.user.toLowerCase().includes(q) || 
               log.action.toLowerCase().includes(q) || 
               activityLabel(log.action).toLowerCase().includes(q) ||
               log.details.toLowerCase().includes(q)
      }
      return true
    })
  }, [activityLogs, search, actionFilter, userFilter])

  const stats = useMemo(() => {
    const last24h = activityLogs.filter(log => {
      const logTime = new Date(log.timestamp).getTime()
      const now = Date.now()
      return now - logTime < 24 * 60 * 60 * 1000
    }).length

    const uniqueUsers = new Set(activityLogs.map(log => log.user)).size
    const criticalActions = activityLogs.filter(log => isCriticalActivity(log.action)).length

    return { last24h, uniqueUsers, criticalActions }
  }, [activityLogs])

  const sortedLogsRef = useRef(filtered)
  const [exporting, setExporting] = useState(false)

  const handleExportCsv = () => {
    if (activityLoading || !!activityError || !activityReady) return
    const logs = sortedLogsRef.current
    const filename = `activity-log-${manilaDayKey(Date.now())}.csv`
    const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
    const rows = logs.map(log => [
      log.timestamp,
      log.user,
      log.action,
      log.details,
      log.ipAddress || ""
    ])
    downloadCsv(filename, headers, rows)
    toast.success("Export successful", { description: `${logs.length} activities exported to CSV` })
  }

  const handleExportXlsx = async () => {
    if (activityLoading || !!activityError || !activityReady) return
    setExporting(true)
    try {
      const logs = sortedLogsRef.current
      const filename = `activity-log-${manilaDayKey(Date.now())}.xlsx`
      const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
      const rows = logs.map(log => [
        log.timestamp,
        log.user,
        log.action,
        log.details,
        log.ipAddress || ""
      ])
      await downloadXlsx(filename, "Activity Log", headers, rows)
      toast.success("Export successful", { description: `${logs.length} activities exported to Excel` })
    } catch (e) {
      toast.error("Export failed", { description: e instanceof Error ? e.message : "Please try again" })
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnDef<ActivityEntry>[] = [
    {
      header: "Timestamp",
      sortable: true,
      sortKey: "timestamp",
      cell: (log) => (
        <div className="text-sm">
          {new Date(log.timestamp).toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })}
          <br />
          <span className="text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleTimeString(undefined, { timeZone: "Asia/Manila" })}</span>
        </div>
      ),
    },
    {
      header: "User",
      sortable: true,
      sortKey: "user",
      cell: (log) => (
        <div className="flex items-center gap-2">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
              {log.user.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium">{log.user}</span>
        </div>
      ),
    },
    {
      header: "Action",
      sortable: true,
      sortKey: (log) => activityLabel(log.action),
      cell: (log) => (
        <Badge variant="outline" className={`text-xs font-medium rounded-md ${activityBadgeClass(log.action)}`}>
          {activityLabel(log.action)}
        </Badge>
      ),
    },
    {
      header: "Details",
      className: "text-sm max-w-md truncate",
      // The full text stays reachable: rejection rows end with the per-view scores.
      cell: (log) => <span title={log.details}>{log.details}</span>,
    },
    {
      header: "IP Address",
      className: "text-sm text-muted-foreground font-mono",
      cell: (log) => log.ipAddress || "—",
    },
  ]

  return (
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Activity Log"
        description="System activity and audit trail"
        icon={ScrollText}
        action={
          <ExportDropdown
            onExportCsv={handleExportCsv}
            onExportXlsx={handleExportXlsx}
            disabled={activityLoading || !!activityError || !activityReady}
            exporting={exporting}
          />
        }
      />

      {(activityLoading || activityError) && (
        <p role={activityError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {activityError || (activityReady ? "Refreshing activity…" : "Loading activity…")}
        </p>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Last 24 Hours"
          value={stats.last24h}
          icon={Activity}
          delay={50}
          description="Recent activity"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Active Users"
          value={stats.uniqueUsers}
          icon={UserCheck}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={100}
          description="Unique operators"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Critical Actions"
          value={stats.criticalActions}
          icon={AlertCircle}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={150}
          description="Security, access & system changes"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search activities..."
        hasActiveFilters={search !== "" || actionFilter !== "all" || userFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setActionFilter("all")
          setUserFilter("all")
        }}
      >
        <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Actions</SelectItem>
            {actionTypes.map((action) => (
              <SelectItem key={action} value={action}>{activityLabel(action)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={userFilter} onValueChange={(v) => { setUserFilter(v) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="User" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Users</SelectItem>
            {users.map((user) => (
              <SelectItem key={user} value={user}>{user}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <AppDataTable
        loading={initialLoading}
        data={filtered}
        columns={columns}
        rowKey={(log) => log.id}
        pagination={{ pageSize: PAGE_SIZE }}
        onSortedData={(rows) => { sortedLogsRef.current = rows }}
        emptyState={{
          icon: Activity,
          title: activityError && !activityReady ? "Data unavailable" : "No activities found",
          description: activityError && !activityReady ? "Reload to try again." : "Try adjusting your filters or search query"
        }}
      />
    </div>
  )
}
