import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import type { LucideProps } from "lucide-react"
import type { ForwardRefExoticComponent, RefAttributes } from "react"

type LucideIcon = ForwardRefExoticComponent<Omit<LucideProps, "ref"> & RefAttributes<SVGSVGElement>>

interface AppStatsCardProps {
  title: string
  value: string | number
  icon: LucideIcon
  iconColor?: string
  iconBgColor?: string
  className?: string
  delay?: number
  description?: string
  helpText?: string
  onClick?: () => void
  active?: boolean
  disabled?: boolean
  loading?: boolean
}

export function AppStatsCard({
  title,
  value,
  icon: Icon,
  iconColor = "text-primary",
  iconBgColor = "bg-primary/10",
  className,
  delay = 0,
  description,
  helpText,
  onClick,
  active,
  disabled = false,
  loading = false,
}: AppStatsCardProps) {
  disabled = disabled || loading
  return (
    <Card 
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border/40 bg-card shadow-sm hover:shadow-md transition-all duration-300 ease-out group animate-fade-in",
        onClick && !disabled && "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        active && "ring-2 ring-primary/40 border-primary/30 shadow-md",
        className
      )}
      style={{ animationDelay: `${delay}ms` }}
      title={helpText}
      aria-description={helpText}
      aria-busy={loading || undefined}
      role={onClick ? "button" : undefined}
      tabIndex={onClick && !disabled ? 0 : undefined}
      aria-disabled={onClick ? disabled : undefined}
      onClick={disabled ? undefined : onClick}
      onKeyDown={onClick ? (event) => {
        if (!disabled && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault()
          onClick()
        }
      } : undefined}
    >
      {/* Accent gradient bar */}
      <div className={cn(
        "absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl opacity-60 group-hover:opacity-100 transition-opacity duration-300",
        iconBgColor
      )} />

      {/* Hover shimmer */}
      <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-in-out bg-gradient-to-r from-transparent via-white/[0.06] to-transparent pointer-events-none" />

      <CardContent className="p-5 sm:p-6 pl-6 sm:pl-7 relative z-10 flex flex-col gap-3">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium tracking-wide text-muted-foreground/70 uppercase">{title}</p>
          <div className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-105",
            iconBgColor
          )}>
            <Icon className={cn("w-[18px] h-[18px]", iconColor)} />
          </div>
        </div>
        
        {/* Value + description */}
        <div className="flex flex-col gap-0.5">
          <h3 className="text-3xl sm:text-[2.25rem] font-extrabold tracking-tight text-foreground leading-none">{loading ? <><span className="sr-only">Loading {title}</span><Skeleton aria-hidden="true" className="h-[1em] w-24" /></> : value}</h3>
          {description && (
            <p className="text-xs text-muted-foreground/60 font-medium mt-1">{loading ? <Skeleton aria-hidden="true" className="h-4 w-3/4" /> : description}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
