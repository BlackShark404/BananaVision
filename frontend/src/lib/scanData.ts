import type { ScanResult, ScanNote } from "@/types"
import type { ShelfLifeWindow } from "@/lib/shelfLifeWindow"

/** Stored records never receive a client-generated timestamp. */
export interface ApiScan {
  print_job?: ScanResult["printJob"] | null
  print_error?: string | null
  id: string
  revision: number
  date_time?: string
  scanned_at?: string
  dateTime?: string
  cultivar: ScanResult["cultivar"] | null
  ripeness: ScanResult["ripeness"] | null
  confidence: number | null
  temperature?: number | null
  humidity?: number | null
  vpd?: number | null
  treatment?: ScanResult["treatment"] | null
  spoilage_days: string | null
  finger_count: number
  operator_name?: string
  operator?: string
  source_text?: string | null
  supplier_name?: string | null
  source?: string | null
  thumbnail_url?: string | null
  intake_id?: string | null
  intake_origin_id?: string | null
  intake_provenance?: string
  inventory_eligible?: boolean
  remaining_days?: number | null
  risk_as_of?: string | null
  shelf_life_window?: ShelfLifeWindow | null
  inventory_status?: ScanResult["inventoryStatus"]
  status_updated_at?: string | null
  flagged?: boolean
  is_overridden?: boolean
  original_ai_result?: { cultivar: ScanResult["cultivar"] | null; ripeness: ScanResult["ripeness"] | null; confidence: number | null; finger_count: number; spoilage_days?: string | null } | null
  has_notes?: boolean
  images?: { camera_id: string; file_path: string }[]
  detections?: ScanResult["detections"]
  notes?: ApiScanNote[]
  history?: ScanResult["history"]
}

export interface ApiScanNote {
  id: string
  scan_id: string
  text: string
  author_name: string
  timestamp: string
}

export function storedTimestamp(value: string | undefined | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) throw new Error("A stored scan timestamp is missing or invalid. Please refresh or contact an administrator.")
  return value
}

export function mapApiScan(scan: ApiScan, imageUrl: (path: string) => string = path => path): ScanResult {
  return {
    printJob: scan.print_job ?? undefined,
    printError: scan.print_error ?? undefined,
    id: scan.id,
    revision: scan.revision,
    dateTime: storedTimestamp(scan.date_time ?? scan.scanned_at ?? scan.dateTime),
    cultivar: scan.cultivar ?? "Unknown",
    ripeness: scan.ripeness ?? "Unknown",
    confidence: scan.confidence !== null && Number.isFinite(scan.confidence) && scan.confidence >= 0 && scan.confidence <= 100 ? scan.confidence : null,
    temperature: scan.temperature ?? undefined,
    humidity: scan.humidity ?? undefined,
    vpd: scan.vpd ?? undefined,
    treatment: scan.treatment ?? undefined,
    spoilageDays: scan.spoilage_days ?? "Unknown",
    fingerCount: scan.finger_count,
    operator: scan.operator_name ?? scan.operator ?? "Unknown",
    source: scan.source_text ?? scan.supplier_name ?? scan.source ?? undefined,
    thumbnailUrl: scan.thumbnail_url ? imageUrl(scan.thumbnail_url) : undefined,
    intakeId: scan.intake_id ?? undefined,
    intakeOriginId: scan.intake_origin_id ?? undefined,
    intakeProvenance: scan.intake_provenance ?? "unverified",
    inventoryEligible: scan.inventory_eligible === true,
    remainingDays: scan.remaining_days ?? null,
    riskAsOf: scan.risk_as_of ?? undefined,
    shelfLifeWindow: scan.shelf_life_window ?? null,
    inventoryStatus: scan.inventory_status,
    statusUpdatedAt: scan.status_updated_at ? storedTimestamp(scan.status_updated_at) : undefined,
    flagged: scan.flagged,
    isOverridden: scan.is_overridden,
    originalAiResult: scan.original_ai_result ? {
      cultivar: scan.original_ai_result.cultivar ?? "Unknown",
      ripeness: scan.original_ai_result.ripeness ?? "Unknown",
      confidence: scan.original_ai_result.confidence,
      fingerCount: scan.original_ai_result.finger_count,
      spoilageDays: scan.original_ai_result.spoilage_days ?? undefined,
    } : undefined,
    hasNotes: scan.has_notes ?? false,
    images: (scan.images ?? []).map(image => ({ ...image, file_path: imageUrl(image.file_path) })),
    detections: scan.detections ?? [],
    notes: scan.notes?.map(mapApiScanNote),
    history: scan.history,
  }
}

export function mapApiScanNote(note: ApiScanNote): ScanNote {
  return { id: note.id, scanId: note.scan_id, note: note.text, author: note.author_name, timestamp: storedTimestamp(note.timestamp) }
}

/** Describe conflicting views when the AI candidate lacks a camera majority. */
export function cultivarCameraConflict(
  scan: Pick<ScanResult, "cultivar" | "isOverridden" | "originalAiResult" | "history" | "detections">,
): string | null {
  const originalCultivar = scan.originalAiResult?.cultivar
  const cultivarCorrection = originalCultivar && originalCultivar !== "Unknown"
    && originalCultivar !== scan.cultivar
  const recordedCorrection = scan.history?.some(event =>
    event.new_values.cultivar === scan.cultivar
    && typeof event.previous_values?.cultivar === "string"
    && event.previous_values.cultivar !== scan.cultivar,
  )
  // Editing the count/ripeness also sets isOverridden; only cultivar evidence
  // can resolve cultivar disagreement.
  if (scan.isOverridden && (cultivarCorrection || recordedCorrection)) return null
  const seen = new Set<string>()
  const views = new Map<string, string[]>()
  for (const detection of scan.detections ?? []) {
    if (seen.has(detection.camera_id)) continue
    seen.add(detection.camera_id)
    const { detected_cultivar: cultivar, detected_ripeness: ripeness, confidence } = detection
    if (!cultivar || !ripeness || confidence === null || !Number.isFinite(confidence)
      || confidence <= 0 || confidence > 100) continue
    const labels = views.get(cultivar) ?? []
    labels.push(detection.camera_label || detection.camera_id)
    views.set(cultivar, labels)
  }
  const total = [...views.values()].reduce((sum, labels) => sum + labels.length, 0)
  const supporting = views.get(scan.cultivar)?.length ?? 0
  if (views.size < 2 || supporting * 2 > total) return null
  return [...views].map(([cultivar, labels]) => `${labels.join(" + ")}: ${cultivar}`).join("; ")
}

export interface RecordPage<T> { items: T[]; total: number; page: number; page_size: number; snapshot_id?: string }

/** Publish a complete history only after every page succeeds. */
export async function collectScanPages<T extends { id: string }>(
  fetchPage: (page: number, pageSize: number, signal?: AbortSignal, snapshotId?: string) => Promise<RecordPage<T>>,
  signal?: AbortSignal,
): Promise<T[]> {
  const records = new Map<string, T>()
  const pageSize = 100
  let snapshotId: string | undefined
  for (let page = 1; ; page++) {
    signal?.throwIfAborted()
    const response = await fetchPage(page, pageSize, signal, snapshotId)
    signal?.throwIfAborted()
    if (snapshotId && response.snapshot_id !== snapshotId) throw new Error("Scan snapshot changed. Please retry.")
    snapshotId = response.snapshot_id
    if (!Array.isArray(response.items) || response.page !== page || !Number.isInteger(response.page_size) || response.page_size < 1 || response.items.length > response.page_size || !Number.isInteger(response.total) || response.total < 0) {
      throw new Error("The server returned an invalid scan history page.")
    }
    const previousSize = records.size
    response.items.forEach(record => records.set(record.id, record))
    if (page * response.page_size >= response.total) {
      if (records.size !== response.total) throw new Error("Scan history changed or is incomplete. Please retry.")
      return [...records.values()]
    }
    if (response.items.length === 0 || previousSize === records.size) throw new Error("Scan history is incomplete. Please retry.")
  }
}
