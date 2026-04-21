import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown } from "lucide-react"
import type { LucideProps } from "lucide-react"
import type { ForwardRefExoticComponent, RefAttributes } from "react"

type LucideIcon = ForwardRefExoticComponent<Omit<LucideProps, "ref"> & RefAttributes<SVGSVGElement>>

interface StatsCardProps {
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

export function StatsCard({
  title,
  value,
  icon: Icon,
  iconColor = "text-primary",
  iconBgColor = "bg-primary/10",
  className,
  delay = 0,
  description,
  trend,
}: StatsCardProps) {
  return (
    <Card 
      className={cn("rounded-xl sm:rounded-2xl animate-fade-in", className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-center gap-3 sm:gap-4">
          <div className={cn(
            "w-11 h-11 sm:w-12 sm:h-12 rounded-lg flex items-center justify-center shrink-0",
            iconBgColor
          )}>
            <Icon className={cn("w-5 h-5 sm:w-6 sm:h-6", iconColor)} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs sm:text-sm text-muted-foreground font-medium">{title}</p>
            <div className="flex items-baseline gap-2">
              <p className="text-2xl sm:text-3xl font-bold truncate">{value}</p>
              {trend && (
                <div className={cn(
                  "flex items-center gap-0.5 text-xs font-medium",
                  trend.isPositive ? "text-emerald-600" : "text-red-600"
                )}>
                  {trend.isPositive ? (
                    <TrendingUp className="w-3 h-3" />
                  ) : (
                    <TrendingDown className="w-3 h-3" />
                  )}
                  <span>{Math.abs(trend.value)}%</span>
                </div>
              )}
            </div>
            {description && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{description}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
