import type { ScanResult } from "@/types"

export interface SupplierVarietyCount {
  cultivar: string
  count: number
}

export interface SupplierReceipt {
  supplier: string
  total: number
  varieties: SupplierVarietyCount[]
}

const UNKNOWN_SUPPLIER = "Unknown Supplier"
const VARIETY_ORDER = ["Lakatan", "Latundan", "Cardaba"]

function varietyRank(cultivar: string) {
  const index = VARIETY_ORDER.indexOf(cultivar)
  return index === -1 ? VARIETY_ORDER.length : index
}

function textOrder(left: string, right: string) {
  return left < right ? -1 : left > right ? 1 : 0
}

/** Every recorded scan counts as one received bunch, whatever its current stock status. */
export function receivedBySupplier(scans: Pick<ScanResult, "source" | "cultivar">[]): SupplierReceipt[] {
  const bySupplier = new Map<string, Map<string, number>>()
  for (const scan of scans) {
    const supplier = scan.source?.trim() || UNKNOWN_SUPPLIER
    const cultivar = scan.cultivar?.trim() || "Unknown"
    const varieties = bySupplier.get(supplier) ?? new Map<string, number>()
    varieties.set(cultivar, (varieties.get(cultivar) ?? 0) + 1)
    bySupplier.set(supplier, varieties)
  }
  return [...bySupplier.entries()]
    .map(([supplier, varieties]) => ({
      supplier,
      total: [...varieties.values()].reduce((sum, count) => sum + count, 0),
      varieties: [...varieties.entries()]
        .sort(([left], [right]) => varietyRank(left) - varietyRank(right) || textOrder(left, right))
        .map(([cultivar, count]) => ({ cultivar, count })),
    }))
    .sort((left, right) => right.total - left.total || textOrder(left.supplier, right.supplier))
}

export function bunchCountText(count: number) {
  return `${count} ${count === 1 ? "bunch" : "bunches"}`
}
