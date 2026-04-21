import { Search, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export interface AppTableFiltersProps {
  searchQuery?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string
  hideSearch?: boolean
  hasActiveFilters?: boolean
  onClearFilters?: () => void
  children?: React.ReactNode // For additional filters (e.g. Select dropdowns)
}

export function AppTableFilters({ 
  searchQuery = "", 
  onSearchChange = () => {}, 
  searchPlaceholder = "Search...", 
  hideSearch = false,
  hasActiveFilters = false,
  onClearFilters,
  children 
}: AppTableFiltersProps) {
  return (
    <Card className="rounded-xl sm:rounded-2xl border bg-card text-card-foreground shadow-sm mb-4">
      <CardContent className="p-3 sm:p-4">
        <div className="flex flex-col gap-3">
          {!hideSearch && (
            <div className="relative group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
              <Input 
                placeholder={searchPlaceholder} 
                className="pl-9 pr-9 h-10 bg-background hover:bg-muted/50 transition-colors border-muted-foreground/20 focus-visible:ring-1 focus-visible:ring-primary focus-visible:border-primary" 
                value={searchQuery} 
                onChange={(e) => onSearchChange(e.target.value)} 
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => onSearchChange("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          )}
          {(children || onClearFilters) && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex flex-wrap items-center gap-2 flex-grow">
                {children}
              </div>
              {onClearFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onClearFilters}
                  disabled={!hasActiveFilters}
                  className={`h-9 px-3 shrink-0 transition-opacity ${
                    hasActiveFilters 
                      ? "text-muted-foreground hover:text-foreground hover:bg-muted" 
                      : "text-muted-foreground opacity-50 pointer-events-none"
                  }`}
                >
                  Reset
                </Button>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
