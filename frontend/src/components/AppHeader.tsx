import { useApp } from "@/context/AppContext"
import { AppNotifications } from "./AppNotifications"

// ─── Component ───────────────────────────────────────────────────────────────

export default function AppHeader() {
  const { user } = useApp()

  return (
    <header className="hidden lg:flex items-center justify-between h-15 px-6 xl:px-8 border-b border-border/60 bg-background/80 backdrop-blur-md sticky top-0 z-20">
      {/* Left: Page title + greeting */}
      <div className="flex items-center gap-4">
        <div>
          {user && (
            <h2 className="text-lg font-semibold tracking-tight leading-tight">
              Welcome back, <span className="text-foreground">{user.fullName.split(" ")[0]}</span>
            </h2>
          )}
        </div>
      </div>

      {/* Right: Notification bell */}
      <div className="flex items-center gap-2">
        <AppNotifications />
      </div>
    </header>
  )
}
