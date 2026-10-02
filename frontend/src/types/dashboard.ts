export type DashboardView = "sources" | "operators"

export interface DashboardScan {
  id: string
  date_time: string
  cultivar: string | null
  ripeness: string | null
  confidence: number | null
  operator_id: string
  operator_name: string
  source_key: string
  source_name: string
  inventory_status: string | null
  flagged: boolean
  spoilage_days: string | null
  remaining_days: number | null
}

export interface DashboardSummary {
  generated_at: string
  business_date: string
  timezone: "Asia/Manila"
  total_scans: number
  avg_confidence: number | null
  active_operator_count: number
  sources: { key: string; name: string; count: number }[]
  operators: { operator_id: string; name: string; username: string; scan_count: number; avg_confidence: number | null }[]
  recent_scans: DashboardScan[]
  pending_review_count: number
  expiring_stock_count: number
  confidence_threshold: number
}

export interface DashboardScanParams {
  view: "today" | "review" | "expiring" | "all"
  page: number
  page_size: number
  business_date?: string
  source_key?: string
  operator_id?: string
  sort: "date" | "confidence"
}

export interface DashboardScanPage {
  items: DashboardScan[]
  total: number
  page: number
  page_size: number
  generated_at: string
  business_date: string
  timezone: "Asia/Manila"
}
