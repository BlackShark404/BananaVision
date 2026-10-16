import { useState, useMemo } from "react"
import { useAdmin } from "@/context/AdminContext"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { AppDataTable, type ColumnDef } from "@/components/AppDataTable"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
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
import { AppActionButton } from "@/components/AppActionButton"
import { AppTableFilters } from "@/components/AppTableFilters"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Loader2, Users, Plus, Pencil, ShieldAlert, ShieldCheck, UserCheck, Filter, KeyRound, Key } from "lucide-react"
import { toast } from "sonner"
import type { Role, User } from "@/types"

const PAGE_SIZE = 10

export default function UserManagement() {
  const { users, usersLoading, usersReady, usersError, addUser, updateUser, resetPassword, resetPin } = useAdmin()
  const [saving, setSaving] = useState(false)
  const initialLoading = usersLoading && !usersReady
  const [search, setSearch] = useState("")
  const [roleFilter, setRoleFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  
  const [resetConfirmUser, setResetConfirmUser] = useState<{id: string, fullName: string} | null>(null)
  const [resetConfirmPin, setResetConfirmPin] = useState<{id: string, fullName: string} | null>(null)
  
  const [handoff, setHandoff] = useState<{ username: string; password?: string; pin?: string } | null>(null)

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

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (saving) return
    setSaving(true)
    try {
      if (editingId) {
        await updateUser(editingId, formData)
        toast.success("User updated")
      } else {
        const result = await addUser({ ...formData, lastActive: "Never" })
        setHandoff({ username: result.user.username, password: result.password, pin: result.pin })
        toast.success("User created")
      }
      setIsDialogOpen(false)
    } catch (error) {
      toast.error("Could not save user", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSaving(false)
    }
  }

  const confirmResetPassword = async () => {
    if (!resetConfirmUser || saving) return
    setSaving(true)
    try {
      const password = await resetPassword(resetConfirmUser.id)
      setHandoff({ username: users.find(u => u.id === resetConfirmUser.id)?.username || resetConfirmUser.fullName, password })
      toast.success("Password reset")
      setResetConfirmUser(null)
    } catch (error) {
      toast.error("Could not reset password", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSaving(false)
    }
  }

  const confirmResetPin = async () => {
    if (!resetConfirmPin || saving) return
    setSaving(true)
    try {
      const pin = await resetPin(resetConfirmPin.id)
      setHandoff({ username: users.find(u => u.id === resetConfirmPin.id)?.username || resetConfirmPin.fullName, pin })
      toast.success("PIN reset")
      setResetConfirmPin(null)
    } catch (error) {
      toast.error("Could not reset PIN", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnDef<User>[] = [
    {
      header: "User",
      sortable: true,
      sortKey: "fullName",
      cell: (user) => (
        <div className="flex items-center gap-3">
          <Avatar className="w-9 h-9">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">
              {user.fullName.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div>
            <div className="font-medium">{user.fullName}</div>
            <div className="text-xs text-muted-foreground">@{user.username}</div>
          </div>
        </div>
      ),
    },
    {
      header: "Role",
      sortable: true,
      sortKey: "role",
      cell: (user) => (
        <Badge variant="outline" className={`gap-1 ${user.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : ""}`}>
          {user.role === "Admin" ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
          {user.role}
        </Badge>
      ),
    },
    {
      header: "Status",
      sortable: true,
      sortKey: "status",
      cell: (user) => (
        <Badge variant="secondary" className={user.status === "Active" ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-100" : "bg-muted text-muted-foreground"}>
          {user.status}
        </Badge>
      ),
    },
    {
      header: "Last Active",
      className: "text-sm text-muted-foreground",
      sortable: true,
      sortKey: "lastActive",
      cell: (user) => user.lastActive === "Never" ? "Never" : new Date(user.lastActive).toLocaleDateString(),
    },
    {
      header: "Actions",
      className: "text-right",
      stopPropagation: true,
      cell: (user) => (
        <div className="flex items-center justify-end gap-1">
          <AppActionButton 
            disabled={saving}
            tooltip="Edit User" 
            icon={Pencil} 
            onClick={() => handleOpenDialog(user.id)} 
            className="hover:text-primary" 
          />
          <AppActionButton 
            disabled={saving}
            tooltip="Reset Password" 
            icon={KeyRound} 
            onClick={() => setResetConfirmUser({ id: user.id, fullName: user.fullName })} 
            className="hover:text-amber-600" 
          />
          {user.role === "Operator" && (
            <AppActionButton 
            disabled={saving}
              tooltip="Reset Kiosk PIN" 
              icon={Key} 
              onClick={() => setResetConfirmPin({ id: user.id, fullName: user.fullName })} 
              className="hover:text-indigo-600" 
            />
          )}
        </div>
      ),
    },
  ]

  return (
    <TooltipProvider>
      <div className="space-y-6">
        <AppPageHeader
          title="User Management"
          description="Manage operators and system administrators"
          icon={Users}
          action={
            <Button disabled={saving} onClick={() => handleOpenDialog()} className="shadow-md gap-2 w-full sm:w-auto">
              <Plus className="w-4 h-4" /> Add User
            </Button>
          }
        />

      {(usersLoading || usersError) && (
        <p role={usersError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {usersError || (usersReady ? "Refreshing users…" : "Loading users…")}
        </p>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={initialLoading}
          title="Total Users"
          value={users.length}
          icon={Users}
          delay={50}
          description="System accounts"
        />
        <AppStatsCard
          loading={initialLoading}
          title="Active Users"
          value={users.filter(u => u.status === "Active").length}
          icon={UserCheck}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description="Currently enabled"
        />
        <AppStatsCard
          loading={initialLoading}
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
        onSearchChange={(value) => { setSearch(value) }}
        searchPlaceholder="Search users..."
        hasActiveFilters={search !== "" || roleFilter !== "all" || statusFilter !== "all"}
        onClearFilters={() => {
          setSearch("")
          setRoleFilter("all")
          setStatusFilter("all")
        }}
      >
        <Select value={roleFilter} onValueChange={(v) => { setRoleFilter(v) }}>
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
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v) }}>
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

      <AppDataTable
        loading={initialLoading}
        data={filteredUsers}
        columns={columns}
        rowKey={(user) => user.id}
        pagination={{ pageSize: PAGE_SIZE }}
        className="rounded-2xl border-none shadow-none"
        emptyState={{
          icon: Users,
          title: usersError && !usersReady ? "Data unavailable" : "No users found",
          description: usersError && !usersReady ? "Reload to try again." : "Try adjusting your search query"
        }}
      />

      <Dialog open={isDialogOpen} onOpenChange={open => !saving && setIsDialogOpen(open)}>
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
              <Input id="username" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} required disabled={!!editingId} className={editingId ? "opacity-60 cursor-not-allowed" : ""} />
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
                <p>A unique temporary password and, for operators, PIN will be displayed once after creation. Share them privately with the account owner.</p>
                <p className="mt-2">They will be required to change their credentials upon first login.</p>
              </div>
            )}
            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" disabled={saving} onClick={() => setIsDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>{saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Saving…" : editingId ? "Save Changes" : "Create User"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!handoff} onOpenChange={open => !open && setHandoff(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Temporary credentials</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Share these privately with the account owner before closing. They are displayed only now and must be replaced on first use.</p>
          <p>Username: <strong>{handoff?.username}</strong></p>
          {handoff?.password && <p>Temporary password: <code className="select-all break-all">{handoff.password}</code></p>}
          {handoff?.pin && <p>Temporary PIN: <code className="select-all">{handoff.pin}</code></p>}
          <DialogFooter><Button onClick={() => setHandoff(null)}>Done</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!resetConfirmUser} onOpenChange={(open) => !saving && !open && setResetConfirmUser(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Password</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the password for <span className="font-semibold text-foreground">{resetConfirmUser?.fullName}</span>?
              <br /><br />
              A unique temporary password will be displayed once after reset. The user must replace it on their next login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={saving} className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={event => { event.preventDefault(); void confirmResetPassword() }}>
              {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Resetting…" : "Reset Password"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!resetConfirmPin} onOpenChange={(open) => !saving && !open && setResetConfirmPin(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Kiosk PIN</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the Kiosk PIN for <span className="font-semibold text-foreground">{resetConfirmPin?.fullName}</span>?
              <br /><br />
              A unique temporary PIN will be displayed once after reset. They will be required to change it on their next Kiosk login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={saving} className="bg-amber-600 focus:ring-amber-600 hover:bg-amber-700" onClick={event => { event.preventDefault(); void confirmResetPin() }}>
              {saving && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin mr-2" />}{saving ? "Resetting…" : "Reset PIN"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>


    </div>
    </TooltipProvider>
  )
}
