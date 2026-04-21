import { Badge } from "@/components/ui/badge"
import { Package, Cog, XCircle } from "lucide-react"

interface StatusBadgeProps {
  status: string
  type: "ripeness" | "inventory" | "role" | "device" | "user" | "quality"
  className?: string
  size?: "sm" | "md" | "lg"
}

// Global dictionary for mapping specific statuses to styles
const STYLE_MAP = {
  ripeness: {
    Unripe: { colors: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-400 dark:border-emerald-500/30" },
    Ripe: { colors: "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/20 dark:text-yellow-400 dark:border-yellow-500/30" },
    Overripe: { colors: "bg-red-100 text-red-700 border-red-200 dark:bg-red-500/20 dark:text-red-400 dark:border-red-500/30" },
    Rotten: { colors: "bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-500/20 dark:text-violet-400 dark:border-violet-500/30" },
  },
  inventory: {
    "In Stock": { colors: "bg-blue-50 text-blue-700 border-blue-200", icon: Package },
    Sold: { colors: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: Package },
    "For Processing": { colors: "bg-purple-50 text-purple-700 border-purple-200", icon: Cog },
    Spoiled: { colors: "bg-red-50 text-red-700 border-red-200", icon: XCircle },
  },
  role: {
    Admin: { colors: "bg-primary/10 text-primary border-primary/20" },
    Operator: { colors: "bg-secondary text-secondary-foreground" },
  },
} as const

export function StatusBadge({ status, type, className = "", size = "md" }: StatusBadgeProps) {
  // @ts-expect-error dynamic access
  const config = STYLE_MAP[type]?.[status]
  
  if (!config) {
    return <Badge variant="outline" className={className}>{status}</Badge>
  }

  const { colors, icon: Icon } = config
  const sizeClasses = size === "sm" ? "px-1.5 py-0 text-[10px] h-4" : size === "lg" ? "px-3 py-1.5 text-sm" : "px-2 py-0.5 text-xs"

  return (
    <Badge variant="outline" className={`${colors} ${sizeClasses} gap-1 font-medium ${className}`}>
      {Icon && <Icon className={size === "sm" ? "w-2.5 h-2.5" : "w-3 h-3"} />}
      {status}
    </Badge>
  )
}
