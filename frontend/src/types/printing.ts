export interface LabelPreview {
  payload: string
  qr_data?: string
  panel: string[]
  printer_name: string
  max_quantity: number
  width_mm: number
  height_mm: number
}

export interface PrintJob {
  id: string
  status: "QUEUED" | "SUBMITTED" | "FAILED"
  printer_name: string
  quantity: number
  windows_job_id: number | null
  error: string | null
  attempt_count: number
}
