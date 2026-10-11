import type { ScanResult } from "@/types"

/** Age the server's remaining-life value by elapsed time, never parse a prediction locally. */
export function remainingStockDays(scan: ScanResult, now: number): number | null {
  const asOf = Date.parse(scan.riskAsOf ?? "")
  if (scan.remainingDays == null || !Number.isFinite(scan.remainingDays) || !Number.isFinite(asOf)) return null
  return scan.remainingDays - Math.max(0, now - asOf) / 86_400_000
}

export function shelfLifeLabel(days: number | null): string {
  if (days === null) return "Unknown"
  if (days < 0) return "Overdue"
  return `${days.toFixed(1)}d left`
}
