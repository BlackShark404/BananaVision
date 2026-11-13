import type { ScanResult } from "@/types"
import { liveShelfLife, shelfLifeWindowLabel } from "@/lib/shelfLifeWindow"
import { formatSpoilageDays } from "@/lib/spoilageDisplay"

type ShelfLifeRisk = Pick<ScanResult, "remainingDays" | "riskAsOf">

/** Age the server's remaining-life value by elapsed time, never parse a prediction locally. */
export function remainingStockDays(scan: ShelfLifeRisk, now: number): number | null {
  const asOf = Date.parse(scan.riskAsOf ?? "")
  if (scan.remainingDays == null || !Number.isFinite(scan.remainingDays) || !Number.isFinite(asOf)) return null
  return scan.remainingDays - Math.max(0, now - asOf) / 86_400_000
}

export function shelfLifeLabel(days: number | null): string {
  if (days === null || !Number.isFinite(days)) return "Unknown"
  if (days < 0) return "Overdue"
  return `${formatSpoilageDays(days)} left`
}

/**
 * Countdown text for one record, or null when the server sent nothing to count from.
 * The calendar-day window is used whenever it is present. Responses saved before the
 * window existed (old list snapshots, replayed writes) fall back to the aged number.
 */
export function liveShelfLifeLabel(scan: ShelfLifeRisk & Pick<ScanResult, "shelfLifeWindow">, now: number): string | null {
  const live = liveShelfLife(scan.shelfLifeWindow, now)
  if (live) return shelfLifeWindowLabel(live)
  const remaining = remainingStockDays(scan, now)
  return remaining === null ? null : shelfLifeLabel(remaining)
}
