/** Preset periods the backend accepts (`range`). "custom" is UI-only: see lib/analyticsPeriod. */
export type AnalyticsRange = "today" | "week" | "month" | "all"

export type AnalyticsMetricKey =
  | "throughput" | "classifications" | "model_confidence" | "low_confidence"
  | "inventory_risk" | "confidence_by_ripeness" | "trend" | "sources"
  | "operators" | "hourly" | "human_verified_accuracy"

export interface AnalyticsOperator {
  operator_id: string
  name: string
  total_scans: number
  avg_confidence: number | null
  confidence_sample_count: number
  flagged_scans: number
  flag_rate: number
  overridden_scans: number
}

export interface AnalyticsSummary {
  total_scans: number
  avg_confidence: number | null
  most_common_cultivar: string
  low_confidence_count: number
  low_confidence_rate: number | null
  at_risk_count: number
  classification_count: number
  incomplete_count: number
  confidence_sample_count: number
  confidence_threshold: number
  current_stock_count: number
  risk_unknown_count: number
  human_verified_accuracy: number | null
  verified_scan_count: number
  source_options: { key: string; name: string }[]
  generated_at: string
  business_date: string
  next_refresh_at: string
  timezone: string
  range_start: string | null
  range_end: string
  trend_start: string
  trend_end: string
  metric_definitions: Record<AnalyticsMetricKey, string>
  ripeness_distribution: { name: string; value: number }[]
  cultivar_counts: { name: string; count: number }[]
  scan_trend: { date: string; count: number }[]
  cultivar_ripeness: { name: string; Unripe: number; "Semi Ripe": number; Ripe: number; Overripe: number }[]
  ripeness_confidence: { ripeness: string; avgConfidence: number | null; count: number }[]
  scans_by_source: { key: string; name: string; count: number }[]
  hourly_distribution: { hour: string; count: number }[]
  operator_performance: AnalyticsOperator[]
}
