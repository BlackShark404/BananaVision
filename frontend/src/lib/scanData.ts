import type { ScanResult, ScanNote } from "@/types"

/** Stored records never receive a client-generated timestamp. */
export interface ApiScan {
  id: string
  date_time?: string
  scanned_at?: string
  dateTime?: string
  cultivar: ScanResult["cultivar"]
  ripeness: ScanResult["ripeness"]
  confidence: number
  temperature?: number | null
  humidity?: number | null
  vpd?: number | null
  treatment?: ScanResult["treatment"] | null
  spoilage_days: string
  finger_count: number
  operator_name?: string
  operator?: string
  source_text?: string | null
  supplier_name?: string | null
  source?: string | null
  thumbnail_url?: string | null
  intake_id?: string | null
  inventory_status?: ScanResult["inventoryStatus"]
  status_updated_at?: string | null
  flagged?: boolean
  is_overridden?: boolean
  original_ai_result?: { cultivar: ScanResult["cultivar"]; ripeness: ScanResult["ripeness"]; confidence: number; finger_count: number; spoilage_days?: string } | null
  has_notes?: boolean
  images?: { camera_id: string; file_path: string }[]
  detections?: ScanResult["detections"]
}

export interface ApiScanNote {
  id: string
  scan_id: string
  text: string
  author_name: string
  timestamp: string
}

function storedTimestamp(value: string | undefined | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) throw new Error("A stored scan timestamp is missing or invalid. Please refresh or contact an administrator.")
  return value
}

export function mapApiScan(scan: ApiScan, imageUrl: (path: string) => string = path => path): ScanResult {
  return {
    id: scan.id,
    dateTime: storedTimestamp(scan.date_time ?? scan.scanned_at ?? scan.dateTime),
    cultivar: scan.cultivar,
    ripeness: scan.ripeness,
    confidence: scan.confidence,
    temperature: scan.temperature ?? undefined,
    humidity: scan.humidity ?? undefined,
    vpd: scan.vpd ?? undefined,
    treatment: scan.treatment ?? undefined,
    spoilageDays: scan.spoilage_days,
    fingerCount: scan.finger_count,
    operator: scan.operator_name ?? scan.operator ?? "Unknown",
    source: scan.source_text ?? scan.supplier_name ?? scan.source ?? undefined,
    thumbnailUrl: scan.thumbnail_url ? imageUrl(scan.thumbnail_url) : undefined,
    intakeId: scan.intake_id ?? undefined,
    inventoryStatus: scan.inventory_status,
    statusUpdatedAt: scan.status_updated_at ? storedTimestamp(scan.status_updated_at) : undefined,
    flagged: scan.flagged,
    isOverridden: scan.is_overridden,
    originalAiResult: scan.original_ai_result ? {
      cultivar: scan.original_ai_result.cultivar,
      ripeness: scan.original_ai_result.ripeness,
      confidence: scan.original_ai_result.confidence,
      fingerCount: scan.original_ai_result.finger_count,
      spoilageDays: scan.original_ai_result.spoilage_days,
    } : undefined,
    hasNotes: scan.has_notes ?? false,
    images: (scan.images ?? []).map(image => ({ ...image, file_path: imageUrl(image.file_path) })),
    detections: scan.detections ?? [],
  }
}

export function mapApiScanNote(note: ApiScanNote): ScanNote {
  return { id: note.id, scanId: note.scan_id, note: note.text, author: note.author_name, timestamp: storedTimestamp(note.timestamp) }
}

export interface RecordPage<T> { items: T[]; total: number; page: number; page_size: number }

/** Publish a complete history only after every page succeeds. */
export async function collectScanPages<T extends { id: string }>(
  fetchPage: (page: number, pageSize: number, signal?: AbortSignal) => Promise<RecordPage<T>>,
  signal?: AbortSignal,
): Promise<T[]> {
  const records = new Map<string, T>()
  const pageSize = 100
  for (let page = 1; ; page++) {
    signal?.throwIfAborted()
    const response = await fetchPage(page, pageSize, signal)
    signal?.throwIfAborted()
    if (!Array.isArray(response.items) || response.page !== page || !Number.isInteger(response.page_size) || response.page_size < 1 || !Number.isInteger(response.total) || response.total < 0) {
      throw new Error("The server returned an invalid scan history page.")
    }
    const previousSize = records.size
    response.items.forEach(record => records.set(record.id, record))
    if (page * response.page_size >= response.total) return [...records.values()]
    if (response.items.length === 0 || previousSize === records.size) throw new Error("Scan history is incomplete. Please retry.")
  }
}
