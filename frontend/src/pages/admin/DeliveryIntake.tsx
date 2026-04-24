import { useState, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useApp } from "@/context/AppContext"
import { Card } from "@/components/ui/card"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
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
import type { InventoryStatus } from "@/types"
import { 
  Package, 
  Filter, 
  Download, 
  Activity, 
  ArchiveRestore, 
  ChevronsLeft, 
  ChevronsRight, 
  CheckCircle, 
  MoreVertical, 
  Box, 
  DollarSign, 
  Settings, 
  AlertTriangle,
  Cog
} from "lucide-react"
import { toast } from "sonner"

// Valid transitions: key = current status, value = allowed target statuses
const VALID_TRANSITIONS: Record<string, InventoryStatus[]> = {
  "In Stock": ["Sold", "For Processing", "Spoiled"],
  "For Processing": ["Sold", "Spoiled"],
  "Sold": [],
  "Spoiled": [],
}

// Terminal statuses that require confirmation
const TERMINAL_STATUSES: InventoryStatus[] = ["Sold", "Spoiled"]

const PAGE_SIZE = 15

export default function DeliveryIntake() {
  const navigate = useNavigate()
  const { intakes, scans, bulkUpdateIntakeInventory } = useApp()
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("Active")
  const [confirmAction, setConfirmAction] = useState<{ intakeId: string; status: InventoryStatus; scanCount: number } | null>(null)
  const [sourceFilter, setSourceFilter] = useState<string>("all")
  const [page, setPage] = useState(1)

  const activeSources = useMemo(() => Array.from(new Set(intakes.map(i => i.source))).sort(), [intakes])

  const intakesWithScanCount = useMemo(() => {
    return intakes.map(intake => {
      const intakeScans = scans.filter(s => s.intakeId === intake.id)
      // Determine dominant inventory status
      const statusCounts = intakeScans.reduce((acc, s) => {
        const st = s.inventoryStatus || "In Stock"
        acc[st] = (acc[st] || 0) + 1
        return acc
      }, {} as Record<string, number>)
      const inventoryStatus = Object.entries(statusCounts).sort((a, b) => b[1] - a[1])[0]?.[0] as InventoryStatus | undefined

      return {
        ...intake,
        scanCount: intakeScans.length,
        inventoryStatus: inventoryStatus || "In Stock" as InventoryStatus
      }
    })
  }, [intakes, scans])

  const filtered = useMemo(() => {
    return intakesWithScanCount.filter((intake) => {
      if (statusFilter !== "all" && intake.status !== statusFilter) return false
      if (sourceFilter !== "all" && intake.source !== sourceFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return intake.source.toLowerCase().includes(q) || 
               intake.id.toLowerCase().includes(q)
      }
      return true
    }).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
  }, [intakesWithScanCount, search, statusFilter, sourceFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const stats = useMemo(() => {
    const activeIntakes = intakes.filter(i => i.status === "Active").length
    const depletedIntakes = intakes.filter(i => i.status === "Depleted").length
    
    return { activeIntakes, depletedIntakes }
  }, [intakes])

  const exportToCSV = () => {
    const headers = ["Intake ID", "Source", "Date", "Total Scans", "Status"]
    const rows = filtered.map(intake => [
      intake.id,
      intake.source,
      intake.date,
      intake.scanCount.toString(),
      intake.status
    ])

    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(","))
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const link = document.createElement("a")
    const url = URL.createObjectURL(blob)
    link.setAttribute("href", url)
    link.setAttribute("download", `intakes-${new Date().toISOString().split('T')[0]}.csv`)
    link.style.visibility = "hidden"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    toast.success("Export successful", { description: `${filtered.length} intakes exported to CSV` })
  }

  const handleBulkUpdate = (intake: { id: string; inventoryStatus: InventoryStatus; scanCount: number }, status: InventoryStatus) => {
    if (TERMINAL_STATUSES.includes(status)) {
      setConfirmAction({ intakeId: intake.id, status, scanCount: intake.scanCount })
      return
    }
    bulkUpdateIntakeInventory(intake.id, status)
    toast.success(`Intake and scans marked as ${status}`)
  }

  const confirmBulkUpdate = () => {
    if (!confirmAction) return
    bulkUpdateIntakeInventory(confirmAction.intakeId, confirmAction.status)
    toast.success(`Intake and scans marked as ${confirmAction.status}`)
    setConfirmAction(null)
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Confirmation Dialog for terminal statuses */}
      <AlertDialog open={!!confirmAction} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              {confirmAction?.status === "Spoiled" ? (
                <AlertTriangle className="w-5 h-5 text-red-500" />
              ) : (
                <DollarSign className="w-5 h-5 text-emerald-500" />
              )}
              Mark all as {confirmAction?.status}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will mark all <strong>{confirmAction?.scanCount}</strong> scans in this intake as <strong>{confirmAction?.status}</strong>. This is a terminal status and cannot be easily undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmBulkUpdate}
              className={confirmAction?.status === "Spoiled" ? "bg-red-600 hover:bg-red-700" : "bg-emerald-600 hover:bg-emerald-700"}
            >
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AppPageHeader
        title="Delivery Intakes"
        description="Monitor automated, scan-driven implicit delivery intakes"
        icon={Package}
        action={
          <Button variant="outline" className="gap-2 w-full sm:w-auto" onClick={exportToCSV}>
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Export CSV</span>
          </Button>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <StatsCard
          title="Active Intakes"
          value={stats.activeIntakes}
          icon={Activity}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={50}
          description="Awaiting processing"
        />
        <StatsCard
          title="Depleted Intakes"
          value={stats.depletedIntakes}
          icon={ArchiveRestore}
          iconColor="text-gray-600"
          iconBgColor="bg-gray-500/10"
          delay={100}
          description="Processed and sold"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value); setPage(1) }}
        searchPlaceholder="Search by source or intake ID..."
        hasActiveFilters={search !== "" || statusFilter !== "all" || sourceFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setStatusFilter("all")
          setSourceFilter("all")
          setPage(1)
        }}
      >
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-37.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="Active">Active</SelectItem>
            <SelectItem value="Depleted">Depleted</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {activeSources.map((source) => (
              <SelectItem key={source} value={source}>{source}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <Card className="rounded-xl sm:rounded-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="font-semibold">Intake ID</TableHead>
              <TableHead className="font-semibold">Date</TableHead>
              <TableHead className="font-semibold">Source</TableHead>
              <TableHead className="font-semibold">Items Scanned</TableHead>
              <TableHead className="font-semibold">Status</TableHead>
              <TableHead className="font-semibold">Inventory Status</TableHead>
              <TableHead className="font-semibold text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginated.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-64">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <Package className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No intakes found</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        Try adjusting your filters or wait for operators to scan new deliveries.
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            ) : (
              paginated.map((intake, i) => (
                <TableRow 
                  key={intake.id} 
                  className="animate-fade-in-row cursor-pointer hover:bg-muted/50 transition-colors" 
                  style={{ animationDelay: `${i * 30}ms` }}
                  onClick={() => navigate(`/logs?intake=${intake.id}`)}
                >
                  <TableCell className="font-medium font-mono text-sm">{intake.id}</TableCell>
                  <TableCell>
                    {new Date(intake.date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </TableCell>
                  <TableCell className="font-medium">{intake.source}</TableCell>
                  <TableCell>
                    {intake.scanCount} bananas
                  </TableCell>
                  <TableCell>
                    {intake.status === "Active" ? (
                      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200">
                        <ArchiveRestore className="w-3 h-3 mr-1" />
                        Depleted
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {(() => {
                      const st = intake.inventoryStatus
                      const styles: Record<string, { cls: string; icon: typeof Box }> = {
                        "In Stock": { cls: "bg-blue-50 text-blue-700 border-blue-200", icon: Box },
                        "Sold": { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: DollarSign },
                        "For Processing": { cls: "bg-purple-50 text-purple-700 border-purple-200", icon: Cog },
                        "Spoiled": { cls: "bg-red-50 text-red-700 border-red-200", icon: AlertTriangle },
                      }
                      const { cls, icon: Icon } = styles[st] || styles["In Stock"]
                      return (
                        <Badge variant="outline" className={cls}>
                          <Icon className="w-3 h-3 mr-1" />
                          {st}
                        </Badge>
                      )
                    })()}
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                          <span className="sr-only">Open menu</span>
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-56">
                        <DropdownMenuLabel>Bulk Update Status</DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        {([
                          { status: "In Stock" as InventoryStatus, icon: Box, color: "text-blue-500" },
                          { status: "For Processing" as InventoryStatus, icon: Settings, color: "text-purple-500" },
                          { status: "Sold" as InventoryStatus, icon: DollarSign, color: "text-emerald-500" },
                          { status: "Spoiled" as InventoryStatus, icon: AlertTriangle, color: "text-red-500" },
                        ] as const).map(({ status, icon: ItemIcon, color }) => {
                          const allowed = VALID_TRANSITIONS[intake.inventoryStatus] || []
                          const isDisabled = !allowed.includes(status) || intake.inventoryStatus === status
                          return (
                            <DropdownMenuItem
                              key={status}
                              onClick={() => !isDisabled && handleBulkUpdate(intake, status)}
                              disabled={isDisabled}
                              className={isDisabled ? "opacity-40 cursor-not-allowed" : ""}
                            >
                              <ItemIcon className={`mr-2 h-4 w-4 ${isDisabled ? "text-muted-foreground" : color}`} />
                              <span>Mark all {status}</span>
                            </DropdownMenuItem>
                          )
                        })}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
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
