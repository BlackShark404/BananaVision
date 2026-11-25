import type { DashboardScan } from "@/types/dashboard"

export interface ScanLogRow extends DashboardScan {
  revision: number
  temperature: number | null
  humidity: number | null
  vpd: number | null
  finger_count: number
  thumbnail_url: string | null
  intake_id: string | null
  is_overridden: boolean
  status_updated_at: string | null
}

export interface ScanLogParams {
  format?: "xlsx" | "pdf"
  stable?: boolean
  snapshot_id?: string
  business_date?: string
  source_key?: string
  source?: string
  operator_id?: string
  intake_id?: string
  cultivar?: string
  ripeness?: string
  ripeness_scope?: "scanned" | "current"
  inventory_status?: string
  stock_eligible?: boolean
  flagged_only?: boolean
  attention?: "all" | "at-risk" | "review" | "success"
  search?: string
  page: number
  page_size: number
  sort: "date_time" | "cultivar" | "confidence" | "spoilage_days" | "finger_count"
  direction: "asc" | "desc"
}

export interface ScanLogPage {
  snapshot_id?: string
  snapshot_expires_at?: string
  items: ScanLogRow[]
  total: number
  page: number
  page_size: number
  avg_confidence: number | null
  at_risk_count: number
  review_count: number
  flagged_count: number
  generated_at: string
  confidence_threshold: number
  options: {
    sources: { key: string; name: string }[]
    operators: { operator_id: string; name: string; username: string }[]
  }
}

/** Live count relative to an immutable browse snapshot. */
export interface ScanLogPending {
  snapshot_id: string
  new_count: number
  generated_at: string
}

/** Live authorized rows for a frozen page, plus current whole-filter totals. */
export interface ScanLogReconciliation {
  snapshot_id: string
  items: ScanLogRow[]
  at_risk_ids: string[]
  total: number
  avg_confidence: number | null
  at_risk_count: number
  review_count: number
  flagged_count: number
  generated_at: string
  confidence_threshold: number
}
