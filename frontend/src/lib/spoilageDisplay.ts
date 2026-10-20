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

/** Keep existing separately styled unit spans without duplicating formatting rules. */
export function spoilageDayUnit(value: unknown): string {
  const label = formatSpoilageDays(value, false)
  return label === "Unknown" ? "" : label === "1" ? "day" : "days"
}
