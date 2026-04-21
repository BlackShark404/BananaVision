import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import { Menu } from "lucide-react"
import { useNavigate } from "react-router-dom"
import AppSidebar from "./AppSidebar"

interface AppSidebarHeaderProps {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
}

export default function AppSidebarHeader({ mobileOpen, setMobileOpen }: AppSidebarHeaderProps) {
  const navigate = useNavigate()

  return (
    <>
      {/* Mobile Header */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <div className="lg:hidden fixed top-0 left-0 right-0 z-30 flex items-center gap-3 px-4 py-3 bg-background/80 backdrop-blur-md border-b">
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="h-9 w-9">
              <Menu className="w-5 h-5" />
            </Button>
          </SheetTrigger>
          <div 
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => navigate("/dashboard")}
          >
            <div className="flex items-center justify-center">
              <img src="/bananavision-logo.svg" alt="Logo" className="w-9 h-9 object-contain" />
            </div>
            <span className="font-bold text-sm">BananaVision</span>
          </div>
        </div>
        <SheetContent side="left" className="p-0 w-65" aria-describedby={undefined}>
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <AppSidebar onLinkClick={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>
    </>
  )
}
