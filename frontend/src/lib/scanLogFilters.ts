import type { ScanLogParams } from "@/types/scanLogs"

export interface ScanLogNavigation {
  /** A YYYY-MM-DD Asia/Manila day, or "all" for every date. */
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

/** URL keys that only page or order the list; they never narrow it. */
const LAYOUT_KEYS = new Set(["page", "limit", "page_size", "sort", "direction"])

/** A real YYYY-MM-DD calendar day (2026-02-30 is not). */
function isCalendarDay(value: string | null): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split("-").map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

/** The selected Manila day, or "" for every date ("all", absent or invalid). */
export function selectedScanLogDay(params: URLSearchParams): string {
  const date = params.get("date")
  return isCalendarDay(date) ? date : ""
}

/**
 * The replacement Scan Logs query, or null when the URL is already canonical.
 * - A plain /logs (only paging or sorting, both kept) opens on today's Asia/Manila day.
 * - Any filter, or date=all, keeps every date, so backlog links (expiring stock,
 *   the review queue, inventory) show their full lists.
 * - The legacy attention=review is the review queue, which is the flagged scans:
 *   it becomes Status Flagged unless another status is already selected.
 */
export function normalizeScanLogSearch(params: URLSearchParams, today: string): URLSearchParams | null {
  if (params.get("attention") === "review" && (!params.get("status") || params.get("status") === "Flagged")) {
    const next = new URLSearchParams(params)
    next.delete("attention")
    next.set("status", "Flagged")
    return next
  }
  if ([...params.keys()].every(key => LAYOUT_KEYS.has(key))) {
    const next = new URLSearchParams(params)
    next.set("date", today)
    return next
  }
  return null
}

export function scanLogParams(params: URLSearchParams): ScanLogParams {
  const page = Number(params.get("page"))
  const sort = params.get("sort")
  const attention = params.get("attention")
  const status = params.get("status")
  const rawPageSize = Number(params.get("limit") || params.get("page_size"))
  const pageSize = (VALID_PAGE_SIZES as readonly number[]).includes(rawPageSize) ? rawPageSize : 10
  return {
    business_date: selectedScanLogDay(params) || undefined,
    source_key: params.get("source_key") || undefined,
    source: params.get("source") || undefined,
    operator_id: params.get("operator_id") || undefined,
    intake_id: params.get("intake") || undefined,
    cultivar: params.get("cultivar") || undefined,
    ripeness: params.get("ripeness") || undefined,
    inventory_status: status && status !== "Flagged" ? status : undefined,
    stock_eligible: params.get("stock") === "eligible",
    // The review queue is the flagged scans, so Status Flagged and attention=review agree.
    flagged_only: status === "Flagged",
    attention: attention === "at-risk" || attention === "review" || attention === "success" ? attention : "all",
    search: params.get("search") || undefined,
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    page_size: pageSize,
    sort: sort === "cultivar" || sort === "confidence" || sort === "spoilage_days" || sort === "finger_count" ? sort : "date_time",
    direction: params.get("direction") === "asc" ? "asc" : "desc",
  }
}

