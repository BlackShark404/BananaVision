import { format } from "date-fns"
import { CalendarIcon } from "lucide-react"
import { useState } from "react"
import type { Matcher } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { formatIsoDay, parseIsoDay } from "@/lib/isoDay"
import { manilaToday } from "@/lib/manilaTime"

export interface AppDateFilterProps {
  /** Selected calendar day as a YYYY-MM-DD string, or empty/undefined when unset. */
  value?: string
  onChange?: (value: string) => void
  /** Accessible trigger name; also the visible placeholder when nothing is selected. */
  label?: string
  /** Visible text when nothing is selected, if it differs from the label (e.g. "All dates"). */
  emptyText?: string
  title?: string
  className?: string
  /** Disallow picking future dates (after today in Manila). Defaults to false. */
  disableFuture?: boolean
  /** Earliest selectable date as YYYY-MM-DD string or Date. Dates before this will be disabled. */
  minDate?: string | Date
  /** Latest selectable date as YYYY-MM-DD string or Date. Dates after this will be disabled. */
  maxDate?: string | Date
  /** Custom disabled matcher for DayPicker */
  disabled?: React.ComponentProps<typeof Calendar>["disabled"]
}

/**
 * Popover calendar picker that replaces the native browser date input.
 * The grid shows calendar days and the value stays a plain YYYY-MM-DD string, so URL
 * params survive any device time zone. "Today" is the Asia/Manila calendar day.
 */
export function AppDateFilter({
  value = "",
  onChange,
  label = "Date",
  emptyText,
  title,
  className,
  disableFuture = false,
  minDate,
  maxDate,
  disabled,
}: AppDateFilterProps) {
  const [open, setOpen] = useState(false)
  const selected = parseIsoDay(value)
  const display = selected ? format(selected, "MMM d, yyyy") : emptyText ?? label

  const matchers: Matcher[] = []
  if (disabled) {
    if (Array.isArray(disabled)) {
      matchers.push(...disabled)
    } else {
      matchers.push(disabled)
    }
  }
  if (disableFuture) {
    matchers.push({ after: manilaToday() })
  }
  if (minDate) {
    const min = typeof minDate === "string" ? parseIsoDay(minDate) : minDate
    if (min) matchers.push({ before: min })
  }
  if (maxDate) {
    const max = typeof maxDate === "string" ? parseIsoDay(maxDate) : maxDate
    if (max) matchers.push({ after: max })
  }
  const disabledMatcher = matchers.length > 0 ? matchers : undefined

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          title={title}
          aria-label={selected ? `${label}: ${display}` : label}
          className={cn("h-10 justify-start gap-1.5 font-normal", selected ? "text-foreground" : "text-muted-foreground", className)}
        >
          <CalendarIcon className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate">{display}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          mode="single"
          selected={selected}
          // "Today" and the opening month follow Asia/Manila, not the device clock.
          today={manilaToday()}
          defaultMonth={selected ?? manilaToday()}
          disabled={disabledMatcher}
          onSelect={date => {
            if (date) onChange?.(formatIsoDay(date))
            setOpen(false)
          }}
        />
      </PopoverContent>
    </Popover>
  )
}
