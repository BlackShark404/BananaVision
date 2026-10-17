import * as React from "react"
import { Minus, Plus } from "lucide-react"

import { cn } from "@/lib/utils"

interface NumberFieldProps
  extends Omit<React.ComponentProps<"input">, "type" | "onChange" | "value"> {
  value: number | string
  onChange: (value: number | string) => void
  min?: number
  max?: number
  step?: number
  /** Allow forms with explicit validation to keep the user's invalid draft visible. */
  clampOnBlur?: boolean
}

function NumberField({
  className,
  value,
  onChange,
  min,
  max,
  step = 1,
  clampOnBlur = true,
  disabled,
  id,
  ...props
}: NumberFieldProps) {
  const numericValue =
    typeof value === "string" ? (value === "" ? NaN : Number(value)) : value

  const canDecrement =
    !disabled && (min === undefined || (!Number.isNaN(numericValue) && numericValue > min))
  const canIncrement =
    !disabled && (max === undefined || (!Number.isNaN(numericValue) && numericValue < max))

  function clamp(n: number) {
    let v = n
    if (min !== undefined) v = Math.max(min, v)
    if (max !== undefined) v = Math.min(max, v)
    return v
  }

  function handleIncrement() {
    if (!canIncrement) return
    const base = Number.isNaN(numericValue) ? (min ?? 0) : numericValue
    onChange(clamp(base + step))
  }

  function handleDecrement() {
    if (!canDecrement) return
    const base = Number.isNaN(numericValue) ? (min ?? 0) : numericValue
    onChange(clamp(base - step))
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value
    if (raw === "" || raw === "-") {
      onChange(raw)
      return
    }
    const parsed = Number(raw)
    if (!Number.isNaN(parsed)) {
      onChange(parsed)
    }
  }

  function handleBlur() {
    if (!clampOnBlur) return
    if (typeof value === "string" && value !== "") {
      const parsed = Number(value)
      if (!Number.isNaN(parsed)) {
        onChange(clamp(parsed))
      }
    } else if (typeof value === "number") {
      onChange(clamp(value))
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowUp") {
      e.preventDefault()
      handleIncrement()
    } else if (e.key === "ArrowDown") {
      e.preventDefault()
      handleDecrement()
    }
  }

  return (
    <div
      data-slot="number-field"
      className={cn(
        "inline-flex h-8 items-center rounded-lg border border-input transition-colors has-[:focus-visible]:border-ring has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50 has-[:disabled]:opacity-50",
        className,
      )}
    >
      <button
        type="button"
        tabIndex={-1}
        disabled={disabled || !canDecrement}
        onClick={handleDecrement}
        aria-label="Decrease value"
        className="flex h-full shrink-0 items-center justify-center rounded-l-[calc(var(--radius-lg)-1px)] px-1.5 text-muted-foreground transition-colors select-none hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
      >
        <Minus className="size-3.5" />
      </button>
      <input
        id={id}
        inputMode="numeric"
        value={typeof value === "number" && Number.isNaN(value) ? "" : value}
        onChange={handleInputChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        min={min}
        max={max}
        step={step}
        className="h-full min-w-0 flex-1 border-x border-input bg-transparent px-2 text-center text-sm outline-none [appearance:textfield] placeholder:text-muted-foreground disabled:cursor-not-allowed [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        {...props}
      />
      <button
        type="button"
        tabIndex={-1}
        disabled={disabled || !canIncrement}
        onClick={handleIncrement}
        aria-label="Increase value"
        className="flex h-full shrink-0 items-center justify-center rounded-r-[calc(var(--radius-lg)-1px)] px-1.5 text-muted-foreground transition-colors select-none hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  )
}

export { NumberField }
export type { NumberFieldProps }
