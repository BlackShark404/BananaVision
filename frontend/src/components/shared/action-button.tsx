import * as React from "react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { LucideIcon } from "lucide-react"

export interface ActionButtonProps extends React.ComponentProps<typeof Button> {
  tooltip: string
  icon: LucideIcon
  iconClassName?: string
}

export function ActionButton({ tooltip, icon: Icon, iconClassName, className, ...props }: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button 
          variant="ghost" 
          size="icon" 
          className={`h-8 w-8 text-muted-foreground ${className || ""}`} 
          {...props}
        >
          <Icon className={`w-4 h-4 ${iconClassName || ""}`} />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{tooltip}</TooltipContent>
    </Tooltip>
  )
}
