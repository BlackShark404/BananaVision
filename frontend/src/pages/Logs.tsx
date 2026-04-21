import { useState, useMemo } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useApp } from "@/context/AppContext"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AspectRatio } from "@/components/ui/aspect-ratio"
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
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuLabel, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu"
import { ScrollText, Filter, Download, Banana, TrendingUp, Target, ChevronsLeft, ChevronsRight, Package, Users, Clock, MoreVertical, Box, DollarSign, Settings, AlertTriangle, Thermometer, Droplets } from "lucide-react"
import { toast } from "sonner"
import { parseSpoilageAvg } from "@/lib/utils"
import type { Cultivar, Ripeness, InventoryStatus } from "@/types"
import { StatusBadge } from "@/components/shared/status-badge"

const PAGE_SIZE = 10

export default function Logs() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { scans, user, updateScanData } = useApp()
  const [search, setSearch] = useState("")
  const [cultivarFilter, setCultivarFilter] = useState<string>("all")
  const [ripenessFilter, setRipenessFilter] = useState<string>("all")
  const [sourceFilter, setSourceFilter] = useState<string>(searchParams.get("source") || "all")
  const [operatorFilter, setOperatorFilter] = useState<string>("all")
  const [intakeFilter, setIntakeFilter] = useState<string>(searchParams.get("intake") || "all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [page, setPage] = useState(1)

  const roleFilteredScans = useMemo(() => {
    return user?.role === "Operator" ? scans.filter(s => s.operator === user.fullName) : scans
  }, [scans, user])


  const operators = useMemo(() => Array.from(new Set(scans.map(s => s.operator))).sort(), [scans])

  const handleStatusUpdate = (scanId: string, status: InventoryStatus) => {
    updateScanData(scanId, { inventoryStatus: status, statusUpdatedAt: new Date().toISOString() })
    toast.success(`Scan marked as ${status}`)
  }

  const getStatus = (status?: InventoryStatus) => {
    return <StatusBadge status={status || "In Stock"} type="inventory" />
  }

  const filtered = useMemo(() => {
    return roleFilteredScans.filter((s) => {
      if (intakeFilter !== "all" && s.intakeId !== intakeFilter) return false
      if (cultivarFilter !== "all" && s.cultivar !== cultivarFilter) return false
      if (ripenessFilter !== "all" && s.ripeness !== ripenessFilter) return false
      if (sourceFilter !== "all" && s.source !== sourceFilter) return false
      if (operatorFilter !== "all" && s.operator !== operatorFilter) return false
      if (statusFilter !== "all" && (s.inventoryStatus || "In Stock") !== statusFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return s.cultivar.toLowerCase().includes(q) || s.operator.toLowerCase().includes(q) || (s.source?.toLowerCase().includes(q) ?? false) || (s.intakeId?.toLowerCase().includes(q) ?? false)
      }
      return true
    })
  }, [roleFilteredScans, search, cultivarFilter, ripenessFilter, sourceFilter, operatorFilter, statusFilter, intakeFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const stats = useMemo(() => {
    const avgConfidence = filtered.length 
      ? (filtered.reduce((sum, s) => sum + s.confidence, 0) / filtered.length).toFixed(1)
      : 0
    const spoilingSoon = filtered.filter(s => parseSpoilageAvg(s.spoilageDays) <= 2).length
    return { avgConfidence, spoilingSoon }
  }, [filtered])

  const exportToCSV = () => {
    const headers = ["Date/Time", "Cultivar", "Ripeness", "Confidence (%)", "Temperature (°C)", "Humidity (%)", "Spoilage (days)", "Fingers", "Operator"]
    const rows = filtered.map(scan => [
      new Date(scan.dateTime).toLocaleString(),
      scan.cultivar,
      scan.ripeness,
      scan.confidence,
      scan.temperature || "—",
      scan.humidity || "—",
      scan.spoilageDays,
      scan.fingerCount,
      scan.operator
    ])

    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(","))
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const link = document.createElement("a")
    const url = URL.createObjectURL(blob)
    link.setAttribute("href", url)
    link.setAttribute("download", `banana-scans-${new Date().toISOString().split('T')[0]}.csv`)
    link.style.visibility = "hidden"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    toast.success("Export successful", { description: `${filtered.length} scans exported to CSV` })
  }



  return (
    <div className="space-y-6">
      <AppPageHeader
        title={intakeFilter !== "all" ? `Logs for Intake ${intakeFilter}` : "Scan Logs"}
        description={intakeFilter !== "all" ? "Viewing all scans grouped under this delivery" : "View all banana scan results"}
        icon={ScrollText}
        action={
          <div className="flex items-center gap-2 w-full sm:w-auto">
            {intakeFilter !== "all" && (
              <Button variant="ghost" onClick={() => { setIntakeFilter("all"); navigate('/logs', { replace: true }) }}>
                Clear Intake Filter
              </Button>
            )}
            <Button variant="outline" className="gap-2 w-full sm:w-auto" onClick={exportToCSV}>
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">Export CSV</span>
            </Button>
          </div>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatsCard
          title="Total Scans"
          value={filtered.length}
          icon={TrendingUp}
          delay={50}
          description="All time records"
          trend={{ value: 8, isPositive: true }}
        />
        <StatsCard
          title="Avg Confidence"
          value={`${stats.avgConfidence}%`}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Detection accuracy"
          trend={{ value: 3, isPositive: true }}
        />
        <StatsCard
          title="At-Risk Scans"
          value={stats.spoilingSoon}
          icon={Clock}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={150}
          description="Spoiling in ≤2 days"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value); setPage(1) }}
        searchPlaceholder="Search by cultivar, operator, or ID..."
        hasActiveFilters={search !== "" || cultivarFilter !== "all" || ripenessFilter !== "all" || sourceFilter !== "all" || operatorFilter !== "all" || statusFilter !== "all" || intakeFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setCultivarFilter("all")
          setRipenessFilter("all")
          setSourceFilter("all")
          setOperatorFilter("all")
          setStatusFilter("all")
          if (intakeFilter !== "all") {
            setIntakeFilter("all")
            navigate('/logs', { replace: true })
          }
          setPage(1)
        }}
      >
        <Select value={cultivarFilter} onValueChange={(v) => { setCultivarFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-35 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Cultivar" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Cultivars</SelectItem>
            {(["Lakatan", "Latundan", "Saba"] as Cultivar[]).map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={ripenessFilter} onValueChange={(v) => { setRipenessFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-35 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Ripeness" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Ripeness</SelectItem>
            {(["Unripe", "Ripe", "Overripe", "Rotten"] as Ripeness[]).map((r) => (
              <SelectItem key={r} value={r}>{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-47.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {Array.from(new Set(scans.map(s => s.source).filter(Boolean))).map((src) => (
              <SelectItem key={src as string} value={src as string}>{src}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {user?.role === "Admin" && (
          <Select value={operatorFilter} onValueChange={(v) => { setOperatorFilter(v); setPage(1) }}>
            <SelectTrigger className="w-full sm:w-45 h-10!">
              <Users className="w-3.5 h-3.5 mr-1.5" />
              <SelectValue placeholder="Operator" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Operators</SelectItem>
              {operators.map((op) => (
                <SelectItem key={op} value={op}>{op}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-37.5 h-10!">
            <Package className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="In Stock">In Stock</SelectItem>
            <SelectItem value="Sold">Sold</SelectItem>
            <SelectItem value="For Processing">For Processing</SelectItem>
            <SelectItem value="Spoiled">Spoiled</SelectItem>
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <Card className="rounded-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="font-semibold w-20">Image</TableHead>
              <TableHead className="font-semibold">Date/Time</TableHead>
              <TableHead className="font-semibold">Cultivar</TableHead>
              <TableHead className="font-semibold">Ripeness</TableHead>
              <TableHead className="font-semibold">Source</TableHead>
              <TableHead className="font-semibold">Confidence</TableHead>
              <TableHead className="font-semibold">IoT Data</TableHead>
              <TableHead className="font-semibold">Est. Spoilage</TableHead>
              <TableHead className="font-semibold">Est. Fingers</TableHead>
              {user?.role === "Admin" && <TableHead className="font-semibold">Operator</TableHead>}
              <TableHead className="font-semibold">Status</TableHead>
              {user?.role === "Admin" && <TableHead className="font-semibold text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginated.length === 0 ? (
              <TableRow>
                <TableCell colSpan={user?.role === "Admin" ? 11 : 10} className="h-64">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <Banana className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No scans match your filters</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        Try adjusting your search or filter criteria
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            ) : (
              paginated.map((scan, i) => (
                <TableRow key={scan.id} className="animate-fade-in-row cursor-pointer hover:bg-muted/50" style={{ animationDelay: `${i * 30}ms` }} onClick={() => navigate(`/scans/${scan.id}`)}>
                  <TableCell>
                    <div className="w-14">
                      <AspectRatio ratio={1} className="rounded-lg overflow-hidden bg-muted/50 border">
                        {scan.thumbnailUrl ? (
                          <img src={scan.thumbnailUrl} alt={scan.cultivar} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Banana className="w-6 h-6 text-muted-foreground/40" />
                          </div>
                        )}
                      </AspectRatio>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {new Date(scan.dateTime).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    <br />
                    <span className="text-xs text-muted-foreground">{new Date(scan.dateTime).toLocaleTimeString()}</span>
                  </TableCell>
                  <TableCell className="font-medium">{scan.cultivar}</TableCell>
                  <TableCell>
                    <StatusBadge type="ripeness" status={scan.ripeness} size="md" />
                  </TableCell>
                  <TableCell>
                    {scan.source ? (
                      <span className="font-medium text-sm">{scan.source}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${scan.confidence}%` }} />
                      </div>
                      <span className="text-sm">{scan.confidence}%</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1 text-xs">
                      {scan.temperature !== undefined ? (
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Thermometer className="h-3.5 w-3.5" />
                          <span>{scan.temperature.toFixed(1)}°C</span>
                        </div>
                      ) : null}
                      {scan.humidity !== undefined ? (
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Droplets className="h-3.5 w-3.5" />
                          <span>{scan.humidity.toFixed(1)}%</span>
                        </div>
                      ) : null}
                      {scan.temperature === undefined && scan.humidity === undefined && (
                         <span className="text-muted-foreground">—</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {scan.spoilageDays} days
                  </TableCell>
                  <TableCell className="text-sm">{scan.fingerCount}</TableCell>
                  {user?.role === "Admin" && (
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Avatar className="w-8 h-8">
                          <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                            {scan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <span className="text-sm">{scan.operator}</span>
                      </div>
                    </TableCell>
                  )}
                  <TableCell>
                    {getStatus(scan.inventoryStatus)}
                  </TableCell>
                  {user?.role === "Admin" && (
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0">
                            <span className="sr-only">Open menu</span>
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                          <DropdownMenuLabel>Update Status</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          {([
                            { actionStatus: "In Stock" as InventoryStatus, icon: Box, color: "text-blue-500" },
                            { actionStatus: "For Processing" as InventoryStatus, icon: Settings, color: "text-purple-500" },
                            { actionStatus: "Sold" as InventoryStatus, icon: DollarSign, color: "text-emerald-500" },
                            { actionStatus: "Spoiled" as InventoryStatus, icon: AlertTriangle, color: "text-red-500" },
                          ] as const).map(({ actionStatus, icon: ItemIcon, color }) => {
                            const isDisabled = scan.inventoryStatus === actionStatus
                            return (
                              <DropdownMenuItem
                                key={actionStatus}
                                onClick={() => !isDisabled && handleStatusUpdate(scan.id, actionStatus)}
                                disabled={isDisabled}
                                className={isDisabled ? "opacity-40 cursor-not-allowed" : ""}
                              >
                                <ItemIcon className={`mr-2 h-4 w-4 ${isDisabled ? "text-muted-foreground" : color}`} />
                                <span>Mark {actionStatus}</span>
                              </DropdownMenuItem>
                            )
                          })}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/20">
          <p className="text-sm text-muted-foreground">
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
