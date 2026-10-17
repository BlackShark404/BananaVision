import { Suspense, useState } from "react"
import { ContentSkeleton } from "@/components/LoadingState"
import { Outlet } from "react-router-dom"
import AppHeader from "@/components/AppHeader"
import AppSidebar from "@/components/AppSidebar"
import AppSidebarHeader from "@/components/AppSidebarHeader"


export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col border-r border-sidebar-border bg-sidebar w-65">
        <AppSidebar />
      </aside>

      {/* Mobile header with sidebar */}
      <AppSidebarHeader mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <AppHeader />
        <div className="lg:hidden h-15" />
        <div className="p-4 lg:p-6 xl:p-8 max-w-7xl mx-auto">
          <Suspense fallback={<ContentSkeleton label="Loading page…" />}><Outlet /></Suspense>
        </div>
      </main>
    </div>
  )
}
