import type { ShelfLifeWindow } from "@/lib/shelfLifeWindow"

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
  /** Absent on rows frozen before the server sent it. */
  shelf_life_window?: ShelfLifeWindow | null
}

export interface DashboardFifoRecommendation {
  key: string
  intake_id: string | null
  scan_id: string | null
  source_name: string
  scanned_at: string
  hands: number
  earliest_remaining_days: number | null
}

export interface DashboardSummary {
  generated_at: string
  business_date: string
  timezone: "Asia/Manila"
  total_scans: number
  avg_confidence: number | null
  success_rate: number | null
  active_operator_count: number
  active_source_count: number
  sources: { key: string; name: string; count: number }[]
  operators: { operator_id: string; name: string; username: string; scan_count: number; avg_confidence: number | null }[]
  recent_scans: DashboardScan[]
  fifo_recommendations: DashboardFifoRecommendation[]
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
