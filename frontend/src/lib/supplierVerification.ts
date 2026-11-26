import type { Cultivar, DailyIntake, ExpectedStockLine, ScanResult } from "@/types"

export type ScanVerificationStatus =
  | "Complete"
  | "Partial"
  | "Incomplete"
  | "Discrepancy"
  | "Not recorded"

export interface VarietyVerification {
  cultivar: Cultivar | "Unknown"
  expected: number
  scanned: number
}

export interface IntakeVerification {
  id: string
  batchNumber?: string
  date: string
  status: DailyIntake["status"]
  expected: ExpectedStockLine[]
  expectedTotal: number
  scannedTotal: number
  varieties: VarietyVerification[]
  verdict: ScanVerificationStatus
}

export interface SupplierVerification {
  supplier: string
  expectedTotal: number
  scannedTotal: number
  varieties: VarietyVerification[]
  unlinkedScans: number
  unlinkedVarieties: VarietyVerification[]
  intakes: IntakeVerification[]
  verdict: ScanVerificationStatus
}

type VerifyScan = Pick<ScanResult, "source" | "cultivar" | "intakeId">
type VerifyIntake = Pick<DailyIntake, "id" | "supplierName" | "batchNumber" | "date" | "status" | "expectedStock">

const VARIETY_ORDER = ["Lakatan", "Latundan", "Cardaba", "Unknown"]

export function bunchCountText(count: number) {
  return `${count} ${count === 1 ? "bunch" : "bunches"}`
}

function varietyRank(cultivar: string) {
  const index = VARIETY_ORDER.indexOf(cultivar)
  return index === -1 ? VARIETY_ORDER.length : index
}

function normalizedExpected(intake: VerifyIntake): ExpectedStockLine[] {
  const totals = new Map<Cultivar, number>()
  for (const line of intake.expectedStock ?? []) {
    if (!Number.isInteger(line.expectedBunches) || line.expectedBunches <= 0) continue
    totals.set(line.cultivar, (totals.get(line.cultivar) ?? 0) + line.expectedBunches)
  }
  return [...totals.entries()]
    .sort(([left], [right]) => varietyRank(left) - varietyRank(right))
    .map(([cultivar, expectedBunches]) => ({ cultivar, expectedBunches }))
}

function varietiesOf(expected: ExpectedStockLine[], scans: VerifyScan[]): VarietyVerification[] {
  const rows = new Map<string, VarietyVerification>()
  const row = (cultivar: string) => {
    const existing = rows.get(cultivar)
    if (existing) return existing
    const created = { cultivar: cultivar as VarietyVerification["cultivar"], expected: 0, scanned: 0 }
    rows.set(cultivar, created)
    return created
  }
  for (const line of expected) row(line.cultivar).expected += line.expectedBunches
  for (const scan of scans) row(scan.cultivar || "Unknown").scanned += 1
  return [...rows.values()].sort((left, right) =>
    varietyRank(left.cultivar) - varietyRank(right.cultivar)
    || (left.cultivar < right.cultivar ? -1 : left.cultivar > right.cultivar ? 1 : 0))
}

/** Complete, partial, incomplete, discrepancy, or unrecorded expected stock. */
export function verificationVerdict(
  expectedTotal: number,
  scannedTotal: number,
  varieties: VarietyVerification[],
): ScanVerificationStatus {
  if (expectedTotal === 0) return "Not recorded"
  if (scannedTotal === 0) return "Incomplete"
  const unexpected = varieties.some(row => row.scanned > 0 && row.expected === 0)
  const overExpected = varieties.some(row => row.scanned > row.expected)
  if (unexpected || overExpected || scannedTotal > expectedTotal) return "Discrepancy"
  if (scannedTotal < expectedTotal) return "Partial"
  return "Complete"
}

/**
 * Verify one supplier without leaving Inventory. Scans linked to an intake are
 * matched there; scans that only carry the supplier name stay visible as unlinked
 * and still count toward the supplier-level total.
 */
export function verifySupplier(
  supplier: string,
  intakes: VerifyIntake[],
  scans: VerifyScan[],
): SupplierVerification {
  const name = supplier.trim()
  const supplierIntakes = intakes.filter(intake => (intake.supplierName ?? "").trim() === name)
  const intakeIds = new Set(supplierIntakes.map(intake => intake.id))
  const supplierScans = scans.filter(scan =>
    ((scan.source ?? "").trim() || "Unknown Supplier") === name
    || (scan.intakeId !== undefined && intakeIds.has(scan.intakeId)))
  const intakeScans = new Map<string, VerifyScan[]>(supplierIntakes.map(intake => [intake.id, []]))
  const unlinked: VerifyScan[] = []
  for (const scan of supplierScans) {
    const linked = scan.intakeId !== undefined ? intakeScans.get(scan.intakeId) : undefined
    if (linked) linked.push(scan)
    else unlinked.push(scan)
  }

  const rows: IntakeVerification[] = supplierIntakes.map(intake => {
    const expected = normalizedExpected(intake)
    const matched = intakeScans.get(intake.id) ?? []
    const expectedTotal = expected.reduce((sum, line) => sum + line.expectedBunches, 0)
    const varieties = varietiesOf(expected, matched)
    return {
      id: intake.id,
      batchNumber: intake.batchNumber,
      date: intake.date,
      status: intake.status,
      expected,
      expectedTotal,
      scannedTotal: matched.length,
      varieties,
      verdict: verificationVerdict(expectedTotal, matched.length, varieties),
    }
  })

  const expected: ExpectedStockLine[] = rows.flatMap(row => row.expected)
  const expectedTotal = expected.reduce((sum, line) => sum + line.expectedBunches, 0)
  const varieties = varietiesOf(expected, supplierScans)
  const aggregate = verificationVerdict(expectedTotal, supplierScans.length, varieties)
  return {
    supplier: name,
    expectedTotal,
    scannedTotal: supplierScans.length,
    varieties,
    unlinkedScans: unlinked.length,
    unlinkedVarieties: varietiesOf([], unlinked),
    intakes: rows.sort((left, right) =>
      right.date.localeCompare(left.date) || (left.batchNumber ?? "").localeCompare(right.batchNumber ?? "")),
    // Any delivery-level mismatch must stay visible even when totals cancel out.
    verdict: rows.some(row => row.verdict === "Discrepancy") ? "Discrepancy" : aggregate,
  }
}