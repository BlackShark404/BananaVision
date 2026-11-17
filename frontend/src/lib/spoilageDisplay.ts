/** Display only: never use this label for persistence, sorting or stock risk. */
export function formatSpoilageDays(value: unknown, withUnit = true): string {
  if (typeof value !== "string" && typeof value !== "number") return "Unknown"
  const match = typeof value === "string" ? value.trim().match(/^(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?$/) : null
  if (typeof value === "string" && !match) return "Unknown"
  const low = typeof value === "number" ? value : Number(match![1])
  const high = typeof value === "number" ? value : match![2] === undefined ? low : Number(match![2])
  if (!Number.isFinite(low) || !Number.isFinite(high) || low < 0 || high < low || high > Number.MAX_SAFE_INTEGER) return "Unknown"
  // Whole-day bounds are a readability convention, not a model confidence interval.
  // Keep a known zero; positive estimates below one day display as one day.
  const start = low === 0 ? 0 : Math.max(1, Math.floor(low))
  const end = Math.ceil(high)
  const label = start === end ? String(start) : `${start}–${end}`
  return withUnit ? `${label} ${label === "1" ? "day" : "days"}` : label
}

const CLOSED_STOCK_OUTCOMES: Readonly<Record<string, string>> = {
  Sold: "Sold",
  Spoiled: "Spoiled",
  "For Processing": "For processing",
}

/**
 * Stock that left inventory has no live countdown. Name the outcome on the line where an
 * in-stock row shows its countdown, so every row keeps the same two-line shape.
 */
export function closedStockSpoilageLabel(status: unknown): string | null {
  const outcome = typeof status === "string" && Object.hasOwn(CLOSED_STOCK_OUTCOMES, status) ? CLOSED_STOCK_OUTCOMES[status] : undefined
  return outcome === undefined ? null : `${outcome} · no countdown`
}

/** Keep existing separately styled unit spans without duplicating formatting rules. */
export function spoilageDayUnit(value: unknown): string {
  const label = formatSpoilageDays(value, false)
  return label === "Unknown" ? "" : label === "1" ? "day" : "days"
}
