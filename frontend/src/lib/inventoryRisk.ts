import type { ScanResult } from "@/types"
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
