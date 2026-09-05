import { useState, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useScans } from "@/context/ScanContext"
import { useInventory } from "@/context/InventoryContext"
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
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { AppStatsCard } from "@/components/AppStatsCard"
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
  const { scans } = useScans()
  const { intakes, bulkUpdateIntakeInventory } = useInventory()
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("Active")
  const [confirmAction, setConfirmAction] = useState<{ intakeId: string; status: InventoryStatus; scanCount: number } | null>(null)
  const [sourceFilter, setSourceFilter] = useState<string>("all")

  const activeSources = useMemo(() => Array.from(new Set(intakes.map(i => i.source).filter(Boolean))).sort(), [intakes])

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
        return (intake.source?.toLowerCase() || "").includes(q) || 
               intake.id.toLowerCase().includes(q)
      }
      return true
    }).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
  }, [intakesWithScanCount, search, statusFilter, sourceFilter])

  const stats = useMemo(() => {
    const activeIntakes = intakes.filter(i => i.status === "Active").length
    const depletedIntakes = intakes.filter(i => i.status === "Depleted").length
    
    return { activeIntakes, depletedIntakes }
  }, [intakes])

  const exportToCSV = () => {
    const headers = ["Intake ID", "Source", "Date", "Total Scans", "Status"]
    const rows = filtered.map(intake => [
      intake.id,
      intake.source || "Unknown",
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

  const columns: ColumnDef<any>[] = [
    {
      header: "Intake ID",
      headerClassName: "",
      className: "font-medium font-mono text-sm",
      cell: (intake) => intake.id.substring(0, 8),
    },
    {
      header: "Date",
      cell: (intake) => new Date(intake.date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
    },
    {
      header: "Supplier",
      headerClassName: "",
      className: "font-medium",
      cell: (intake) => intake.supplierName || "Unknown",
    },
    {
      header: "Batch / PO",
      headerClassName: "",
      className: "text-muted-foreground",
      cell: (intake) => intake.batchNumber || "—",
    },
    {
      header: "Items Scanned",
      cell: (intake) => `${intake.scanCount || 0} bananas`,
    },
    {
      header: "Status",
      cell: (intake) => intake.status === "Active" ? (
        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
          <CheckCircle className="w-3 h-3 mr-1" />
          Active
        </Badge>
      ) : (
        <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200">
          <ArchiveRestore className="w-3 h-3 mr-1" />
          Depleted
        </Badge>
      ),
    },
    {
      header: "Inventory Status",
      cell: (intake) => {
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
      },
    },
    {
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (intake) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <span className="sr-only">Open menu</span>
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            {intake.qrCode && (
              <>
                <DropdownMenuItem 
                  onClick={() => {
                    const win = window.open("", "_blank");
                    if (win) {
                      win.document.write(`
                        <html>
                          <head><title>Batch QR Code: ${intake.batchNumber}</title></head>
                          <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;">
                            <h2>Batch: ${intake.batchNumber || intake.id}</h2>
                            <p>Supplier: ${intake.supplierName}</p>
                            <img src="${intake.qrCode}" width="300" height="300" />
                            <button onclick="window.print()" style="margin-top:20px;padding:10px 20px;font-size:16px;">Print Label</button>
                          </body>
                        </html>
                      `);
                      win.document.close();
                    }
                  }}
                >
                  <Package className="mr-2 h-4 w-4 text-primary" />
                  <span>Print Batch QR Label</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
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
      ),
    },
  ]

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
        <AppStatsCard
          title="Active Intakes"
          value={stats.activeIntakes}
          icon={Activity}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={50}
          description="Awaiting processing"
        />
        <AppStatsCard
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
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search by source or intake ID..."
        hasActiveFilters={search !== "" || statusFilter !== "all" || sourceFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setStatusFilter("all")
          setSourceFilter("all")
        }}
      >
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v) }}>
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
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            {activeSources.map((source) => (
              <SelectItem key={source} value={source as string}>{source}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <AppDataTable
        data={filtered}
        columns={columns}
        rowKey={(intake) => intake.id}
        onRowClick={(intake) => navigate(`/logs?intake=${intake.id}`)}
        pagination={{ pageSize: PAGE_SIZE }}
        emptyState={{
          icon: Package,
          title: "No intakes found",
          description: "Try adjusting your filters or wait for operators to scan new deliveries."
        }}
      />
    </div>
  )
}
