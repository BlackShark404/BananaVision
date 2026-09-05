import { useState } from "react"
import { NavLink, useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
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
import { LogOut, ShieldCheck, ShieldAlert, User } from "lucide-react"

export default function AppSidebarFooter() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [showLogoutDialog, setShowLogoutDialog] = useState(false)

  const handleLogout = () => {
    logout()
    navigate("/")
  }

  const [popoverOpen, setPopoverOpen] = useState(false)

  return (
    <div className="px-3 pb-4 shrink-0">
      <Separator className="mb-3" />

      <div className="flex items-center gap-3 px-2">
        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <button className="flex items-center gap-3 hover:bg-accent rounded-lg p-2 transition-colors w-full">
              <Avatar className="h-9 w-9 border-2 border-primary/20">
                <AvatarImage src={user?.avatar || undefined} className="object-cover" />
                <AvatarFallback className="bg-primary/10 text-primary text-xs font-bold">
                  {user?.fullName?.split(" ").map((n) => n[0]).join("")?.toUpperCase() || "?"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-sm font-semibold truncate">{user?.fullName}</p>
                <Badge variant="outline" className={`text-[10px] h-5 px-1.5 gap-1 ${user?.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : ""}`}>
                  {user?.role === "Admin" ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
                  {user?.role}
                </Badge>
              </div>
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-56 p-2 rounded-xl" align="start" side="top" sideOffset={8}>
            <div className="space-y-1">
              <NavLink to="/profile" onClick={() => setPopoverOpen(false)} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm font-medium transition-colors">
                <User className="w-4 h-4" />
                My Profile
              </NavLink>
              <Separator className="my-1" />
              <button
                onClick={() => { setPopoverOpen(false); setShowLogoutDialog(true) }}
                className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 hover:text-destructive text-sm font-medium transition-colors w-full text-left"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Logout Confirmation Dialog */}
      <AlertDialog open={showLogoutDialog} onOpenChange={setShowLogoutDialog}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Logout</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to log out? You will need to sign in again to access your account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={handleLogout}>
              Logout
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
