import type { ScanLogParams } from "@/types/scanLogs"

export interface ScanLogNavigation {
  date?: string
  operator_id?: string
  source_key?: string
  source?: string
  attention?: "at-risk" | "review" | "success"
  status?: string
  cultivar?: string
  ripeness?: string
  stock?: "eligible"
  sort?: ScanLogParams["sort"]
  direction?: ScanLogParams["direction"]
  page?: number
  page_size?: number
  limit?: number
}

export function buildScanLogsUrl(filters: ScanLogNavigation = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== "") params.set(key, String(value))
  return `/logs${params.size ? `?${params}` : ""}`
}

export const VALID_PAGE_SIZES = [10, 25, 50, 100] as const

export function scanLogParams(params: URLSearchParams): ScanLogParams {
  const page = Number(params.get("page"))
  const sort = params.get("sort")
  const attention = params.get("attention")
  const status = params.get("status")
  const rawPageSize = Number(params.get("limit") || params.get("page_size"))
  const pageSize = (VALID_PAGE_SIZES as readonly number[]).includes(rawPageSize) ? rawPageSize : 10
  return {
    business_date: params.get("date") || undefined,
    source_key: params.get("source_key") || undefined,
    source: params.get("source") || undefined,
    operator_id: params.get("operator_id") || undefined,
    intake_id: params.get("intake") || undefined,
    cultivar: params.get("cultivar") || undefined,
    ripeness: params.get("ripeness") || undefined,
    inventory_status: status && status !== "Flagged" ? status : undefined,
    stock_eligible: params.get("stock") === "eligible",
    flagged_only: status === "Flagged" && attention !== "review",
    attention: attention === "at-risk" || attention === "review" || attention === "success" ? attention : "all",
    search: params.get("search") || undefined,
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    page_size: pageSize,
    sort: sort === "cultivar" || sort === "confidence" || sort === "spoilage_days" || sort === "finger_count" ? sort : "date_time",
    direction: params.get("direction") === "asc" ? "asc" : "desc",
  }
}

