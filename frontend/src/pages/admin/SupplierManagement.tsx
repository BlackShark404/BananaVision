import { useState, useMemo } from "react"
import { useInventory } from "@/context/InventoryContext"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AppActionButton } from "@/components/AppActionButton"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog"
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
import { Label } from "@/components/ui/label"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { Loader2, Package, Plus, Building2, Phone, User, CheckCircle2, XCircle, Filter, Pencil } from "lucide-react"
import { TooltipProvider } from "@/components/ui/tooltip"
import { toast } from "sonner"
import type { Supplier } from "@/types"

export default function SupplierManagement() {
  const { suppliers, suppliersLoading, suppliersReady, suppliersError, addSupplier, updateSupplier, updateSupplierStatus } = useInventory()
  const initialLoading = suppliersLoading && !suppliersReady
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [deactivateTarget, setDeactivateTarget] = useState<Supplier | null>(null)
  const [newSupplier, setNewSupplier] = useState<Partial<Supplier>>({ status: "Active" })
  const [editTarget, setEditTarget] = useState<Supplier | null>(null)
  const [editForm, setEditForm] = useState<Partial<Supplier>>({})
  const [saving, setSaving] = useState(false)

  const stats = useMemo(() => {
    const active = suppliers.filter(s => s.status === "Active").length
    const inactive = suppliers.filter(s => s.status === "Inactive").length
    return { active, inactive }
  }, [suppliers])

  const filteredSuppliers = useMemo(() => {
    return suppliers.filter(s => {
      if (statusFilter !== "all" && s.status !== statusFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return s.name.toLowerCase().includes(q) || 
               s.contactPerson?.toLowerCase().includes(q) || 
               s.id.toLowerCase().includes(q)
      }
      return true
    })
  }, [suppliers, search, statusFilter])

  const handleAdd = async () => {
    if (saving) return
    if (!newSupplier.name?.trim()) {
      toast.error("Supplier name is required")
      return
    }
    
    // Check for duplicates
    if (suppliers.some(s => s.name.toLowerCase() === newSupplier.name?.trim().toLowerCase())) {
      toast.error("A supplier with this exact name already exists")
      return
    }

    setSaving(true)
    try {
      await addSupplier({
        name: newSupplier.name.trim(),
        contactPerson: newSupplier.contactPerson?.trim() || undefined,
        contactPhone: newSupplier.contactPhone?.trim() || undefined,
        status: "Active"
      })
      toast.success("Supplier added successfully")
      setIsAddOpen(false)
      setNewSupplier({ status: "Active" })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to add supplier")
    } finally {
      setSaving(false)
    }
  }

  const handleToggleStatus = async (supplier: Supplier) => {
    if (saving) return
    if (supplier.status === "Active") {
      setDeactivateTarget(supplier)
    } else {
      setSaving(true)
      try {
        await updateSupplierStatus(supplier.id, "Active")
        toast.success(`${supplier.name} has been activated`)
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to activate supplier")
      } finally {
        setSaving(false)
      }
    }
  }

  const confirmDeactivate = async () => {
    if (!deactivateTarget || saving) return
    setSaving(true)
    try {
      await updateSupplierStatus(deactivateTarget.id, "Inactive")
      toast.success(`${deactivateTarget.name} has been deactivated`)
      setDeactivateTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to deactivate supplier")
    } finally {
      setSaving(false)
    }
  }

  const openEditDialog = (supplier: Supplier) => {
    setEditForm({ name: supplier.name, contactPerson: supplier.contactPerson || "", contactPhone: supplier.contactPhone || "" })
    setEditTarget(supplier)
  }

  const handleSaveEdit = async () => {
    if (!editTarget || saving) return
    if (!editForm.name?.trim()) {
      toast.error("Supplier name is required")
      return
    }
    if (suppliers.some(s => s.id !== editTarget.id && s.name.toLowerCase() === editForm.name?.trim().toLowerCase())) {
      toast.error("A supplier with this exact name already exists")
      return
    }
    setSaving(true)
    try {
      await updateSupplier(editTarget.id, {
        name: editForm.name.trim(),
        contactPerson: editForm.contactPerson?.trim() || "",
        contactPhone: editForm.contactPhone?.trim() || "",
      })
      toast.success("Supplier updated successfully")
      setEditTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update supplier")
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnDef<Supplier>[] = [
    {
      header: "Supplier Details",
      sortable: true,
      sortKey: "name",
      cell: (supplier) => (
        <div className="flex flex-col">
          <span className="font-medium text-base">{supplier.name}</span>
          <span className="text-xs text-muted-foreground font-mono mt-0.5">{supplier.id}</span>
        </div>
      )
    },
    {
      header: "Contact Info",
      className: "hidden sm:table-cell",
      headerClassName: "hidden sm:table-cell",
      cell: (supplier) => (
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          {supplier.contactPerson && (
            <div className="flex items-center gap-1.5 text-foreground/80">
              <User className="w-3.5 h-3.5" />
              <span>{supplier.contactPerson}</span>
            </div>
          )}
          {supplier.contactPhone && (
            <div className="flex items-center gap-1.5">
              <Phone className="w-3.5 h-3.5" />
              <span>{supplier.contactPhone}</span>
            </div>
          )}
          {!supplier.contactPerson && !supplier.contactPhone && (
            <span className="italic text-muted-foreground/50">No contact provided</span>
          )}
        </div>
      )
    },
    {
      header: "Date Added",
      sortable: true,
      sortKey: "dateAdded",
      cell: (supplier) => <span className="text-sm">{supplier.dateAdded ? new Date(supplier.dateAdded).toLocaleDateString() : "â€”"}</span>
    },
    {
      header: "Status",
      sortable: true,
      sortKey: "status",
      cell: (supplier) => supplier.status === "Active" ? (
        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Active
        </Badge>
      ) : (
        <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200">
          <XCircle className="w-3 h-3 mr-1" />
          Inactive
        </Badge>
      )
    },
    {
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (supplier) => (
        <div className="flex items-center justify-end gap-1">
          <AppActionButton
            disabled={saving}
            tooltip="Edit supplier"
            icon={Pencil}
            onClick={() => openEditDialog(supplier)}
          />
          <AppActionButton
            disabled={saving}
            tooltip={supplier.status === "Active" ? "Deactivate supplier" : "Activate supplier"}
            icon={supplier.status === "Active" ? XCircle : CheckCircle2}
            iconClassName={supplier.status === "Active" ? "text-red-500" : "text-emerald-500"}
            onClick={() => handleToggleStatus(supplier)}
          />
        </div>
      )
    }
  ]

  return (
    <TooltipProvider>
    <div className="space-y-4 sm:space-y-6">
      {/* Deactivation Confirmation Dialog */}
      <AlertDialog open={!!deactivateTarget} onOpenChange={(open) => !open && !saving && setDeactivateTarget(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              Deactivate {deactivateTarget?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This supplier will be <strong>removed from the Operator Kiosk</strong> and operators will no longer be able to scan new deliveries from them. You can reactivate them at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={saving}
              onClick={(event) => { event.preventDefault(); void confirmDeactivate() }}
              className="bg-red-600 hover:bg-red-700"
            >
              {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}{saving ? "Deactivating…" : "Deactivate"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit Supplier Dialog */}
      <Dialog open={!!editTarget} onOpenChange={(open) => { if (!open && !saving) setEditTarget(null) }}>
        <DialogContent className="sm:max-w-106.25">
          <DialogHeader>
            <DialogTitle>Edit Supplier</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Business / Source Name *</Label>
              <Input 
                id="edit-name" 
                disabled={saving}
                placeholder="e.g. Farmer Joe"
                value={editForm.name || ""}
                onChange={e => setEditForm(prev => ({ ...prev, name: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-contact">Contact Person (Optional)</Label>
              <Input 
                id="edit-contact" 
                disabled={saving}
                placeholder="e.g. John Doe"
                value={editForm.contactPerson || ""}
                onChange={e => setEditForm(prev => ({ ...prev, contactPerson: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-phone">Phone Number (Optional)</Label>
              <Input 
                id="edit-phone" 
                disabled={saving}
                placeholder="e.g. 09123456789"
                value={editForm.contactPhone || ""}
                onChange={e => setEditForm(prev => ({ ...prev, contactPhone: e.target.value }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={saving} onClick={() => setEditTarget(null)}>Cancel</Button>
            <Button disabled={saving} onClick={handleSaveEdit}>{saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}{saving ? "Saving…" : "Save Changes"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AppPageHeader
        title="Supplier Management"
        description="Manage your inventory sources and supplier contacts"
        icon={Package}
        action={
          <Dialog open={isAddOpen} onOpenChange={(open) => { if (!saving) setIsAddOpen(open) }}>
            <DialogTrigger asChild>
              <Button disabled={saving} className="w-full sm:w-auto gap-2">
                <Plus className="w-4 h-4" />
                <span className="hidden sm:inline">Add Supplier</span>
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-106.25">
              <DialogHeader>
                <DialogTitle>Add New Supplier</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Business / Source Name *</Label>
                  <Input 
                    id="name" 
                    disabled={saving}
                    placeholder="e.g. Farmer Joe"
                    value={newSupplier.name || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="contact">Contact Person (Optional)</Label>
                  <Input 
                    id="contact" 
                    disabled={saving}
                    placeholder="e.g. John Doe"
                    value={newSupplier.contactPerson || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, contactPerson: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number (Optional)</Label>
                  <Input 
                    id="phone" 
                    disabled={saving}
                    placeholder="e.g. 09123456789"
                    value={newSupplier.contactPhone || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, contactPhone: e.target.value }))}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button disabled={saving} variant="outline" onClick={() => setIsAddOpen(false)}>Cancel</Button>
                <Button disabled={saving} onClick={handleAdd}>{saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}{saving ? "Saving…" : "Save Supplier"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {(suppliersLoading || suppliersError) && (
        <p role={suppliersError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {suppliersError || (suppliersReady ? "Refreshing suppliers…" : "Loading suppliers…")}
        </p>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Active Suppliers"
          value={stats.active}
          icon={CheckCircle2}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={50}
          description="Available on Kiosk"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Inactive Suppliers"
          value={stats.inactive}
          icon={XCircle}
          iconColor="text-gray-600"
          iconBgColor="bg-gray-500/10"
          delay={100}
          description="Hidden from Kiosk"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search by name, ID, or contact..."
        hasActiveFilters={search !== "" || statusFilter !== "all"}
        onClearFilters={() => { setSearch(""); setStatusFilter("all") }}
      >
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-full sm:w-37.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="Active">Active</SelectItem>
            <SelectItem value="Inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Table */}
      <AppDataTable
        loading={initialLoading}
        data={filteredSuppliers}
        columns={columns}
        rowKey={(supplier) => supplier.id}
        emptyState={{
          icon: Building2,
          title: suppliersError && !suppliersReady ? "Data unavailable" : "No suppliers found",
          description: suppliersError && !suppliersReady ? "Reload to try again." : search ? "Try adjusting your search terms." : "Add a supplier to start receiving items."
        }}
      />
    </div>
    </TooltipProvider>
  )
}
