import type { AnalyticsRange } from "@/types/analytics"

/** The Analytics date choice: a backend preset, or "custom" while Date From/To are set (UI only). */
export type AnalyticsRangeChoice = AnalyticsRange | "custom"

/** A period on the Analytics page or one chart. Dates are inclusive Asia/Manila days (YYYY-MM-DD). */
export interface AnalyticsPeriod {
  range: AnalyticsRangeChoice
  from: string
  to: string
}

export const ANALYTICS_RANGE_LABELS: Record<AnalyticsRange, string> = {
  today: "Today",
  week: "Last 7 Days",
  month: "Last 30 Days",
  all: "All Time",
}

const DEFAULT_RANGE: AnalyticsRange = "week"
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function hasCustomDates(period: AnalyticsPeriod): boolean {
  return period.from !== "" || period.to !== ""
}

function preset(range: AnalyticsRangeChoice): AnalyticsRange {
  return range === "custom" ? DEFAULT_RANGE : range
}

/**
 * Query parameters for /analytics/summary and /analytics/operator-performance.
 * Dates replace the preset; "custom" is never sent, so the request matches the backend contract.
 */
export function analyticsPeriodParams(period: AnalyticsPeriod): { range?: AnalyticsRange; date_from?: string; date_to?: string } {
  if (!hasCustomDates(period)) return { range: preset(period.range) }
  return {
    ...(period.from ? { date_from: period.from } : {}),
    ...(period.to ? { date_to: period.to } : {}),
  }
}

/** "Nov 20, 2026" from "2026-11-20", without time-zone conversion (the value is already a Manila day). */
function dayLabel(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return value
  const month = MONTHS[Number(match[2]) - 1]
  return month ? `${month} ${Number(match[3])}, ${match[1]}` : value
}

/** The period in words, shown on the page and on every chart. */
export function analyticsPeriodLabel(period: AnalyticsPeriod): string {
  const { from, to } = period
  if (from && to) return from === to ? dayLabel(from) : `${dayLabel(from)} – ${dayLabel(to)}`
  if (from) return `From ${dayLabel(from)}`
  if (to) return `Up to ${dayLabel(to)}`
  return ANALYTICS_RANGE_LABELS[preset(period.range)]
}
