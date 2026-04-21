import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"

export interface AppPageHeaderProps {
  title: string
  description?: string
  icon?: LucideIcon
  action?: ReactNode
}

export function AppPageHeader({ title, description, icon: Icon, action }: AppPageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
      <div>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          {Icon && <Icon className="w-6 h-6 sm:w-7 sm:h-7" />}
          {title}
        </h1>
        {description && (
          <p className="text-muted-foreground text-xs sm:text-sm mt-1">
            {description}
          </p>
        )}
      </div>
      {action && (
        <div className="w-full sm:w-auto">
          {action}
        </div>
      )}
    </div>
  )
}
