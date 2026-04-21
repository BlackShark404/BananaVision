import { NavLink, useNavigate } from "react-router-dom"
import { useApp } from "@/context/AppContext"
import AppSidebarFooter from "@/components/AppSidebarFooter"
import { Separator } from "@/components/ui/separator"

import {
  LayoutDashboard,
  ScrollText,
  BarChart3,
  Monitor,
  Users,
  Settings,
  ShieldCheck,
  Package,
  PackageOpen,
  Building2,
} from "lucide-react"

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/logs", icon: ScrollText, label: "Logs" },
  { to: "/analytics", icon: BarChart3, label: "Analytics" },
  { to: "/inventory", icon: PackageOpen, label: "Inventory" },
  { to: "/devices", icon: Monitor, label: "Device Status" },
]

const adminItems = [
  { to: "/admin/users", icon: Users, label: "User Management" },
  { to: "/admin/intakes", icon: Package, label: "Delivery Intakes" },
  { to: "/admin/suppliers", icon: Building2, label: "Supplier Management" },
  { to: "/admin/quality", icon: ShieldCheck, label: "Quality Control" },
  { to: "/admin/activity", icon: ScrollText, label: "Activity Log" },
  { to: "/admin/config", icon: Settings, label: "System Config" },
]

export default function AppSidebar({ onLinkClick }: { onLinkClick?: () => void } = {}) {
  const { user } = useApp()
  const isAdmin = user?.role === "Admin"
  const navigate = useNavigate()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[14px] font-medium transition-all duration-200 group ${
      isActive
        ? "bg-primary text-primary-foreground shadow-md"
        : "text-muted-foreground hover:bg-accent hover:text-foreground"
    }`

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Logo */}
      <div 
        className="flex items-center gap-3 px-4 py-5 shrink-0 cursor-pointer hover:opacity-80 transition-opacity"
        onClick={() => {
          navigate("/dashboard")
          if (onLinkClick) onLinkClick()
        }}
      >
        <div className="flex items-center justify-center">
          <img src="/bananavision-logo.svg" alt="Logo" className="w-12 h-12 object-contain" />
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight">BananaVision</h1>
          <p className="text-[11px] text-muted-foreground -mt-0.5">AI Scanner</p>
        </div>
      </div>

      <Separator className="mb-2 shrink-0" />

      {/* Navigation */}
      <nav className="flex-1 px-3 pb-4 space-y-1 overflow-y-auto overflow-x-hidden">
        <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-3">
          Menu
        </p>
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass} end={item.to === "/dashboard"} onClick={onLinkClick}>
            <item.icon className="w-5 h-5 shrink-0" />
            <span>{item.label}</span>
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <Separator className="my-3" />
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-3">
              Admin
            </p>
            {adminItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={linkClass} onClick={onLinkClick}>
                <item.icon className="w-5 h-5 shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>

      <AppSidebarFooter />
    </div>
  )
}
