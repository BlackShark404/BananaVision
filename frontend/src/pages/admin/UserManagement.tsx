import { useState, useMemo } from "react"
import { useApp } from "@/context/AppContext"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { StatsCard } from "@/components/shared/stats-card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
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
import { TooltipProvider } from "@/components/ui/tooltip"
import { ActionButton } from "@/components/shared/action-button"
import { AppTableFilters } from "@/components/AppTableFilters"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Users, Plus, Pencil, ShieldAlert, ShieldCheck, UserCheck, Filter, ChevronsLeft, ChevronsRight, KeyRound, Key } from "lucide-react"
import { toast } from "sonner"
import type { Role } from "@/types"

const PAGE_SIZE = 10

export default function UserManagement() {
  const { users, addUser, updateUser } = useApp()
  const [search, setSearch] = useState("")
  const [roleFilter, setRoleFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [page, setPage] = useState(1)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  
  const [resetConfirmUser, setResetConfirmUser] = useState<{id: string, fullName: string} | null>(null)
  const [resetConfirmPin, setResetConfirmPin] = useState<{id: string, fullName: string} | null>(null)
  
  const [formData, setFormData] = useState({
    username: "",
    fullName: "",
    role: "Operator" as Role,
    status: "Active" as "Active" | "Inactive",
  })

  const filteredUsers = useMemo(() =>
    users.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false
      if (statusFilter !== "all" && u.status !== statusFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return u.fullName.toLowerCase().includes(q) || u.username.toLowerCase().includes(q)
      }
      return true
    }), [users, search, roleFilter, statusFilter]
  )

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE))
  const paginatedUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleOpenDialog = (id?: string) => {
    if (id) {
      const u = users.find(x => x.id === id)
      if (u) {
        setFormData({ username: u.username, fullName: u.fullName, role: u.role, status: u.status })
        setEditingId(id)
      }
    } else {
      setFormData({ username: "", fullName: "", role: "Operator", status: "Active" })
      setEditingId(null)
    }
    setIsDialogOpen(true)
  }

  const handleSubmit = (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (editingId) {
      updateUser(editingId, formData)
      toast.success("User updated")
    } else {
      const isOperator = formData.role === "Operator"
      addUser({
        ...formData,
        lastActive: "Never",
        password: "banana123",
        requiresPasswordChange: true,
        passwordSetupReason: "new_account",
        ...(isOperator ? { pin: "1234", requiresPinChange: true, pinSetupReason: "new_account" as const } : {}),
      })
      toast.success(
        isOperator
          ? "User created with temporary credentials: password 'banana123' and PIN '1234'"
          : "User created with temporary password 'banana123'"
      )
    }
    setIsDialogOpen(false)
  }

  const confirmResetPassword = () => {
    if (resetConfirmUser) {
      updateUser(resetConfirmUser.id, {
        requiresPasswordChange: true,
        password: "banana123",
        passwordSetupReason: "password_reset",
      })
      toast.success(`Password for ${resetConfirmUser.fullName} reset to 'banana123'`)
      setResetConfirmUser(null)
    }
  }

  const confirmResetPin = () => {
    if (resetConfirmPin) {
      updateUser(resetConfirmPin.id, { requiresPinChange: true, pin: "1234", pinSetupReason: "pin_reset" })
      toast.success(`Kiosk PIN for ${resetConfirmPin.fullName} reset to '1234'`)
      setResetConfirmPin(null)
    }
  }

  return (
    <TooltipProvider>
      <div className="space-y-6">
        <AppPageHeader
          title="User Management"
          description="Manage operators and system administrators"
          icon={Users}
          action={
            <Button onClick={() => handleOpenDialog()} className="shadow-md gap-2 w-full sm:w-auto">
              <Plus className="w-4 h-4" /> Add User
            </Button>
          }
        />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatsCard
          title="Total Users"
          value={users.length}
          icon={Users}
          delay={50}
          description="System accounts"
        />
        <StatsCard
          title="Active Users"
          value={users.filter(u => u.status === "Active").length}
          icon={UserCheck}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Currently enabled"
          trend={{ value: 5, isPositive: true }}
        />
        <StatsCard
          title="Admins"
          value={users.filter(u => u.role === "Admin").length}
          icon={ShieldAlert}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={150}
          description="Privileged accounts"
        />
      </div>

      {/* Filters */}
      <AppTableFilters
        searchQuery={search}
        onSearchChange={(value) => { setSearch(value); setPage(1) }}
        searchPlaceholder="Search users..."
        hasActiveFilters={search !== "" || roleFilter !== "all" || statusFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setRoleFilter("all")
          setStatusFilter("all")
          setPage(1)
        }}
      >
        <Select value={roleFilter} onValueChange={(v) => { setRoleFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-40 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Roles" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Roles</SelectItem>
            <SelectItem value="Admin">Admin</SelectItem>
            <SelectItem value="Operator">Operator</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-40 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="Active">Active</SelectItem>
            <SelectItem value="Inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </AppTableFilters>

      <Card className="rounded-2xl">
        <CardContent className="p-4">
          <div className="rounded-xl border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Active</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedUsers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="h-64">
                      <Empty>
                        <EmptyHeader>
                          <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                            <Users className="w-4 h-4" />
                          </EmptyMedia>
                          <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No users found</EmptyTitle>
                          <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                            Try adjusting your search query
                          </EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedUsers.map((user, i) => (
                    <TableRow key={user.id} className="animate-fade-in-row" style={{ animationDelay: `${i * 40}ms` }}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Avatar className="w-9 h-9">
                          <AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">
                            {user.fullName.split(' ').map(n => n[0]).join('').toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <div className="font-medium">{user.fullName}</div>
                          <div className="text-xs text-muted-foreground">@{user.username}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`gap-1 ${user.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : ""}`}>
                        {user.role === "Admin" ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
                        {user.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={user.status === "Active" ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-100" : "bg-muted text-muted-foreground"}>
                        {user.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {user.lastActive === "Never" ? "Never" : new Date(user.lastActive).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <ActionButton 
                          tooltip="Edit User" 
                          icon={Pencil} 
                          onClick={() => handleOpenDialog(user.id)} 
                          className="hover:text-primary" 
                        />
                        
                        <ActionButton 
                          tooltip="Reset Password" 
                          icon={KeyRound} 
                          onClick={() => setResetConfirmUser({ id: user.id, fullName: user.fullName })} 
                          className="hover:text-amber-600" 
                        />
                        {user.role === "Operator" && (
                          <ActionButton 
                            tooltip="Reset Kiosk PIN" 
                            icon={Key} 
                            onClick={() => setResetConfirmPin({ id: user.id, fullName: user.fullName })} 
                            className="hover:text-indigo-600" 
                          />
                        )}
                        
                      </div>
                    </TableCell>
                  </TableRow>
                ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {filteredUsers.length > PAGE_SIZE && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-muted-foreground">
                Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filteredUsers.length)} of {filteredUsers.length}
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
          )}
        </CardContent>
      </Card>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle>{editingId ? "Edit User" : "Add New User"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="fullName">Full Name</Label>
              <Input id="fullName" value={formData.fullName} onChange={e => setFormData({ ...formData, fullName: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={formData.role} onValueChange={(v: Role) => setFormData({ ...formData, role: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Operator">Operator</SelectItem>
                    <SelectItem value="Admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={formData.status} onValueChange={(v: "Active" | "Inactive") => setFormData({ ...formData, status: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Active">Active</SelectItem>
                    <SelectItem value="Inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {!editingId && (
              <div className="bg-muted/50 border text-muted-foreground p-4 rounded-xl text-sm leading-relaxed mt-2">
                <p>New users are created with a default password of <span className="font-mono font-medium text-foreground bg-background px-1.5 py-0.5 rounded border">banana123</span>.</p>
                {formData.role === "Operator" && <p className="mt-2">Operators also receive a default PIN of <span className="font-mono font-medium text-foreground bg-background px-1.5 py-0.5 rounded border">1234</span>.</p>}
                <p className="mt-2">They will be required to change their credentials upon first login.</p>
              </div>
            )}
            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>Cancel</Button>
              <Button type="submit">{editingId ? "Save Changes" : "Create User"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!resetConfirmUser} onOpenChange={(open) => !open && setResetConfirmUser(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Password</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the password for <span className="font-semibold text-foreground">{resetConfirmUser?.fullName}</span>?
              <br /><br />
              Their new temporary password will be set to: <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-foreground">banana123</span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={confirmResetPassword}>
              Reset Password
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!resetConfirmPin} onOpenChange={(open) => !open && setResetConfirmPin(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Kiosk PIN</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the Kiosk PIN for <span className="font-semibold text-foreground">{resetConfirmPin?.fullName}</span>?
              <br /><br />
              Their new temporary PIN will be set to: <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-foreground">1234</span>. They will be required to change it on their next Kiosk login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={confirmResetPin}>
              Reset PIN
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>


    </div>
    </TooltipProvider>
  )
}
