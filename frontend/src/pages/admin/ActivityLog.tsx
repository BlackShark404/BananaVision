import { useState, useMemo } from "react"
import { useApp } from "@/context/AppContext"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { StatsCard } from "@/components/shared/stats-card"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { ScrollText, Filter, Download, Activity, UserCheck, AlertCircle, ChevronsLeft, ChevronsRight } from "lucide-react"
import { toast } from "sonner"

const actionTypeColors: Record<string, string> = {
  login: "bg-blue-50 text-blue-700 border-blue-200",
  logout: "bg-gray-50 text-gray-700 border-gray-200",
  scan_created: "bg-emerald-50 text-emerald-700 border-emerald-200",
  scan_edited: "bg-yellow-50 text-yellow-700 border-yellow-200",
  scan_deleted: "bg-red-50 text-red-700 border-red-200",
  user_created: "bg-purple-50 text-purple-700 border-purple-200",
  user_updated: "bg-indigo-50 text-indigo-700 border-indigo-200",
  user_deleted: "bg-red-50 text-red-700 border-red-200",
  config_changed: "bg-orange-50 text-orange-700 border-orange-200",
  scan_flagged: "bg-pink-50 text-pink-700 border-pink-200",
}

const PAGE_SIZE = 15

export default function ActivityLog() {
  const { activityLogs } = useApp()
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [userFilter, setUserFilter] = useState<string>("all")
  const [page, setPage] = useState(1)

  const users = useMemo(() => Array.from(new Set(activityLogs.map(log => log.user))).sort(), [activityLogs])
  const actionTypes = useMemo(() => Array.from(new Set(activityLogs.map(log => log.action))).sort(), [activityLogs])

  const filtered = useMemo(() => {
    return activityLogs.filter((log) => {
      if (actionFilter !== "all" && log.action !== actionFilter) return false
      if (userFilter !== "all" && log.user !== userFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return log.user.toLowerCase().includes(q) || 
               log.action.toLowerCase().includes(q) || 
               log.details.toLowerCase().includes(q)
      }
      return true
    })
  }, [activityLogs, search, actionFilter, userFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const stats = useMemo(() => {
    const last24h = activityLogs.filter(log => {
      const logTime = new Date(log.timestamp).getTime()
      // eslint-disable-next-line react-hooks/purity
      const now = Date.now()
      return now - logTime < 24 * 60 * 60 * 1000
    }).length

    const uniqueUsers = new Set(activityLogs.map(log => log.user)).size
    const criticalActions = activityLogs.filter(log => 
      log.action.includes("deleted") || log.action === "config_changed"
    ).length

    return { last24h, uniqueUsers, criticalActions }
  }, [activityLogs])

  const exportToCSV = () => {
    const headers = ["Timestamp", "User", "Action", "Details", "IP Address"]
    const rows = filtered.map(log => [
      new Date(log.timestamp).toLocaleString(),
      log.user,
      log.action,
      log.details,
      log.ipAddress || "N/A"
    ])

    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(","))
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const link = document.createElement("a")
    const url = URL.createObjectURL(blob)
    link.setAttribute("href", url)
    link.setAttribute("download", `activity-log-${new Date().toISOString().split('T')[0]}.csv`)
    link.style.visibility = "hidden"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    toast.success("Export successful", { description: `${filtered.length} activities exported to CSV` })
  }

  const formatAction = (action: string) => {
    return action.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Activity Log"
        description="System activity and audit trail"
        icon={ScrollText}
        action={
          <Button variant="outline" className="gap-2 w-full sm:w-auto" onClick={exportToCSV}>
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Export CSV</span>
          </Button>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatsCard
          title="Last 24 Hours"
          value={stats.last24h}
          icon={Activity}
          delay={50}
          description="Recent activity"
          trend={{ value: 12, isPositive: true }}
        />
        <StatsCard
          title="Active Users"
          value={stats.uniqueUsers}
          icon={UserCheck}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={100}
          description="Unique operators"
        />
        <StatsCard
          title="Critical Actions"
          value={stats.criticalActions}
          icon={AlertCircle}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={150}
          description="Deletions & config changes"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value); setPage(1) }}
        searchPlaceholder="Search activities..."
        hasActiveFilters={search !== "" || actionFilter !== "all" || userFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setActionFilter("all")
          setUserFilter("all")
          setPage(1)
        }}
      >
        <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Actions</SelectItem>
            {actionTypes.map((action) => (
              <SelectItem key={action} value={action}>{formatAction(action)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={userFilter} onValueChange={(v) => { setUserFilter(v); setPage(1) }}>
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
      <Card className="rounded-xl sm:rounded-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="font-semibold">Timestamp</TableHead>
              <TableHead className="font-semibold">User</TableHead>
              <TableHead className="font-semibold">Action</TableHead>
              <TableHead className="font-semibold">Details</TableHead>
              <TableHead className="font-semibold">IP Address</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginated.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-64">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <Activity className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No activities found</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        Try adjusting your filters or search query
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            ) : (
              paginated.map((log, i) => (
                <TableRow key={log.id} className="animate-fade-in-row" style={{ animationDelay: `${i * 30}ms` }}>
                  <TableCell className="text-sm">
                    {new Date(log.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    <br />
                    <span className="text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Avatar className="w-8 h-8">
                        <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                          {log.user.split(' ').map(n => n[0]).join('').toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-sm font-medium">{log.user}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-xs font-medium rounded-md ${actionTypeColors[log.action] || 'bg-muted'}`}>
                      {formatAction(log.action)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm max-w-md truncate">{log.details}</TableCell>
                  <TableCell className="text-sm text-muted-foreground font-mono">{log.ipAddress || "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>

        {/* Pagination */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t bg-muted/20">
          <p className="text-xs sm:text-sm text-muted-foreground">
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex justify-end">
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(1)}
                    disabled={page <= 1}
                    title="First page"
                  >
                    <ChevronsLeft className="w-4 h-4" />
                  </Button>
                </PaginationItem>
                <PaginationItem>
                  <PaginationPrevious 
                    href="#" 
                    onClick={(e) => { e.preventDefault(); if (page > 1) setPage(page - 1) }}
                    className={page <= 1 ? "pointer-events-none opacity-50" : ""}
                  />
                </PaginationItem>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => {
                  if (totalPages <= 7) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationLink
                          href="#"
                          onClick={(e) => { e.preventDefault(); setPage(p) }}
                          isActive={p === page}
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }
                  if (p === 1 || p === totalPages || (p >= page - 1 && p <= page + 1)) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationLink
                          href="#"
                          onClick={(e) => { e.preventDefault(); setPage(p) }}
                          isActive={p === page}
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }
                  if (p === page - 2 || p === page + 2) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationEllipsis />
                      </PaginationItem>
                    )
                  }
                  return null
                })}
                <PaginationItem>
                  <PaginationNext 
                    href="#" 
                    onClick={(e) => { e.preventDefault(); if (page < totalPages) setPage(page + 1) }}
                    className={page >= totalPages ? "pointer-events-none opacity-50" : ""}
                  />
                </PaginationItem>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(totalPages)}
                    disabled={page >= totalPages}
                    title="Last page"
                  >
                    <ChevronsRight className="w-4 h-4" />
                  </Button>
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        </div>
      </Card>
    </div>
  )
}
