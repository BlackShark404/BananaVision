import type { ScanLogParams } from "@/types/scanLogs"

export interface ScanLogNavigation {
  date?: string
  operator_id?: string
  source_key?: string
  attention?: "at-risk" | "review"
  status?: string
  sort?: ScanLogParams["sort"]
  direction?: ScanLogParams["direction"]
}

export function buildScanLogsUrl(filters: ScanLogNavigation = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value)
  return `/logs${params.size ? `?${params}` : ""}`
}

export function scanLogParams(params: URLSearchParams): ScanLogParams {
  const page = Number(params.get("page"))
  const sort = params.get("sort")
  const attention = params.get("attention")
  const status = params.get("status")
  return {
    business_date: params.get("date") || undefined,
    source_key: params.get("source_key") || undefined,
    source: params.get("source") || undefined,
    operator_id: params.get("operator_id") || undefined,
    intake_id: params.get("intake") || undefined,
    cultivar: params.get("cultivar") || undefined,
    ripeness: params.get("ripeness") || undefined,
    inventory_status: status && status !== "Flagged" ? status : undefined,
    flagged_only: status === "Flagged",
    attention: attention === "at-risk" || attention === "review" ? attention : "all",
    search: params.get("search") || undefined,
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    page_size: 10,
    sort: sort === "cultivar" || sort === "confidence" || sort === "spoilage_days" || sort === "finger_count" ? sort : "date_time",
    direction: params.get("direction") === "asc" ? "asc" : "desc",
  }
}
