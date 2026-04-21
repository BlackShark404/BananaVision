import { useState, useMemo } from "react"
import { useApp } from "@/context/AppContext"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ActionButton } from "@/components/shared/action-button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
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
import { StatsCard } from "@/components/shared/stats-card"
import { AppPageHeader } from "@/components/AppPageHeader"
import { AppTableFilters } from "@/components/AppTableFilters"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Package, Plus, Building2, Phone, User, CheckCircle2, XCircle, Filter, Pencil } from "lucide-react"
import { TooltipProvider } from "@/components/ui/tooltip"
import { toast } from "sonner"
import type { Supplier } from "@/types"

export default function SupplierManagement() {
  const { suppliers, addSupplier, updateSupplier, updateSupplierStatus } = useApp()
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [deactivateTarget, setDeactivateTarget] = useState<Supplier | null>(null)
  const [newSupplier, setNewSupplier] = useState<Partial<Supplier>>({ status: "Active" })
  const [editTarget, setEditTarget] = useState<Supplier | null>(null)
  const [editForm, setEditForm] = useState<Partial<Supplier>>({})

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

  const handleAdd = () => {
    if (!newSupplier.name?.trim()) {
      toast.error("Supplier name is required")
      return
    }
    
    // Check for duplicates
    if (suppliers.some(s => s.name.toLowerCase() === newSupplier.name?.trim().toLowerCase())) {
      toast.error("A supplier with this exact name already exists")
      return
    }

    addSupplier({
      name: newSupplier.name.trim(),
      contactPerson: newSupplier.contactPerson?.trim() || undefined,
      contactPhone: newSupplier.contactPhone?.trim() || undefined,
      status: "Active"
    })
    
    toast.success("Supplier added successfully")
    setIsAddOpen(false)
    setNewSupplier({ status: "Active" })
  }

  const handleToggleStatus = (supplier: Supplier) => {
    if (supplier.status === "Active") {
      setDeactivateTarget(supplier)
    } else {
      updateSupplierStatus(supplier.id, "Active")
      toast.success(`${supplier.name} has been activated`)
    }
  }

  const confirmDeactivate = () => {
    if (!deactivateTarget) return
    updateSupplierStatus(deactivateTarget.id, "Inactive")
    toast.success(`${deactivateTarget.name} has been deactivated`)
    setDeactivateTarget(null)
  }

  const openEditDialog = (supplier: Supplier) => {
    setEditForm({ name: supplier.name, contactPerson: supplier.contactPerson || "", contactPhone: supplier.contactPhone || "" })
    setEditTarget(supplier)
  }

  const handleSaveEdit = () => {
    if (!editTarget) return
    if (!editForm.name?.trim()) {
      toast.error("Supplier name is required")
      return
    }
    if (suppliers.some(s => s.id !== editTarget.id && s.name.toLowerCase() === editForm.name?.trim().toLowerCase())) {
      toast.error("A supplier with this exact name already exists")
      return
    }
    updateSupplier(editTarget.id, {
      name: editForm.name.trim(),
      contactPerson: editForm.contactPerson?.trim() || undefined,
      contactPhone: editForm.contactPhone?.trim() || undefined,
    })
    toast.success("Supplier updated successfully")
    setEditTarget(null)
  }

  return (
    <TooltipProvider>
    <div className="space-y-4 sm:space-y-6">
      {/* Deactivation Confirmation Dialog */}
      <AlertDialog open={!!deactivateTarget} onOpenChange={(open) => !open && setDeactivateTarget(null)}>
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
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeactivate}
              className="bg-red-600 hover:bg-red-700"
            >
              Deactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit Supplier Dialog */}
      <Dialog open={!!editTarget} onOpenChange={(open) => { if (!open) setEditTarget(null) }}>
        <DialogContent className="sm:max-w-106.25">
          <DialogHeader>
            <DialogTitle>Edit Supplier</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Business / Source Name *</Label>
              <Input 
                id="edit-name" 
                placeholder="e.g. Farmer Joe"
                value={editForm.name || ""}
                onChange={e => setEditForm(prev => ({ ...prev, name: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-contact">Contact Person (Optional)</Label>
              <Input 
                id="edit-contact" 
                placeholder="e.g. John Doe"
                value={editForm.contactPerson || ""}
                onChange={e => setEditForm(prev => ({ ...prev, contactPerson: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-phone">Phone Number (Optional)</Label>
              <Input 
                id="edit-phone" 
                placeholder="e.g. 09123456789"
                value={editForm.contactPhone || ""}
                onChange={e => setEditForm(prev => ({ ...prev, contactPhone: e.target.value }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>Cancel</Button>
            <Button onClick={handleSaveEdit}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AppPageHeader
        title="Supplier Management"
        description="Manage your inventory sources and supplier contacts"
        icon={Package}
        action={
          <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
            <DialogTrigger asChild>
              <Button className="w-full sm:w-auto gap-2">
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
                    placeholder="e.g. Farmer Joe"
                    value={newSupplier.name || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="contact">Contact Person (Optional)</Label>
                  <Input 
                    id="contact" 
                    placeholder="e.g. John Doe"
                    value={newSupplier.contactPerson || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, contactPerson: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number (Optional)</Label>
                  <Input 
                    id="phone" 
                    placeholder="e.g. 09123456789"
                    value={newSupplier.contactPhone || ""}
                    onChange={e => setNewSupplier(prev => ({ ...prev, contactPhone: e.target.value }))}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsAddOpen(false)}>Cancel</Button>
                <Button onClick={handleAdd}>Save Supplier</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <StatsCard
          title="Active Suppliers"
          value={stats.active}
          icon={CheckCircle2}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={50}
          description="Available on Kiosk"
        />
        <StatsCard
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
      <Card className="rounded-xl sm:rounded-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="font-semibold">Supplier Details</TableHead>
              <TableHead className="font-semibold hidden sm:table-cell">Contact Info</TableHead>
              <TableHead className="font-semibold">Date Added</TableHead>
              <TableHead className="font-semibold">Status</TableHead>
              <TableHead className="font-semibold text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredSuppliers.length === 0 ? (
               <TableRow>
                <TableCell colSpan={5} className="h-64">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <Building2 className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No suppliers found</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        {search ? "Try adjusting your search terms." : "Add a supplier to start receiving items."}
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            ) : (
              filteredSuppliers.map((supplier) => (
                <TableRow key={supplier.id}>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium text-base">{supplier.name}</span>
                      <span className="text-xs text-muted-foreground font-mono mt-0.5">{supplier.id}</span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
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
                  </TableCell>
                  <TableCell className="text-sm">
                    {new Date(supplier.dateAdded).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    {supplier.status === "Active" ? (
                      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200">
                        <XCircle className="w-3 h-3 mr-1" />
                        Inactive
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <ActionButton
                        tooltip="Edit supplier"
                        icon={Pencil}
                        onClick={() => openEditDialog(supplier)}
                      />
                      <ActionButton
                        tooltip={supplier.status === "Active" ? "Deactivate supplier" : "Activate supplier"}
                        icon={supplier.status === "Active" ? XCircle : CheckCircle2}
                        iconClassName={supplier.status === "Active" ? "text-red-500" : "text-emerald-500"}
                        onClick={() => handleToggleStatus(supplier)}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
    </TooltipProvider>
  )
}
