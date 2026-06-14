import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown } from "lucide-react"
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
  trend?: {
    value: number
    isPositive?: boolean
  }
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
  trend,
}: AppStatsCardProps) {
  return (
    <Card 
      className={cn(
        "relative overflow-hidden rounded-xl sm:rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl shadow-[0_2px_10px_-3px_rgba(6,81,237,0.05)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] hover:-translate-y-1 transition-all duration-300 group animate-fade-in",
        className
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Subtle glare effect */}
      <div className="absolute inset-0 bg-linear-to-br from-white/40 to-transparent dark:from-white/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
      
      <CardContent className="p-5 sm:p-6 relative z-10 flex flex-col gap-4">
        {/* Header: Title and Icon */}
        <div className="flex flex-row-reverse items-center justify-between">
          <div className={cn(
            "w-12 h-12 rounded-[1rem] flex items-center justify-center shrink-0 shadow-sm border border-black/5 dark:border-white/5 transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3",
            iconBgColor
          )}>
            <Icon className={cn("w-6 h-6", iconColor)} />
          </div>
          <p className="text-sm font-semibold text-muted-foreground tracking-tight uppercase">{title}</p>
        </div>
        
        {/* Body: Value and Trend */}
        <div className="flex flex-col gap-2">
          <div className="flex items-end gap-3 flex-wrap">
            <h3 className="text-3xl sm:text-4xl font-black tracking-tight text-foreground drop-shadow-sm leading-none">{value}</h3>
            {trend && (
              <div className={cn(
                "flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-md mb-0.5",
                trend.isPositive ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" : "bg-red-500/15 text-red-700 dark:text-red-400"
              )}>
                {trend.isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                <span>{Math.abs(trend.value)}%</span>
              </div>
            )}
          </div>
          {description && (
            <p className="text-sm font-medium text-muted-foreground/80 leading-relaxed">{description}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
