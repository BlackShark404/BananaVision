import type { ActiveStatus, ActivityLog, Cultivar, DeviceStatus, IntakeStatus, NotificationType, Role, Treatment, User } from "@/types"

export interface ApiUser {
  id: string
  username: string
  full_name: string
  role: Role
  status: ActiveStatus
  avatar_url: string | null
  requires_password_change: boolean
  requires_pin_change: boolean
  last_active: string | null
  created_at: string
}

export interface ApiUserCreate {
  username: string
  full_name: string
  role: Role
  status: ActiveStatus
  password?: string
  pin?: string
}

export interface ApiUserUpdate extends Partial<Pick<ApiUser, "username" | "full_name" | "role" | "status" | "avatar_url" | "requires_password_change" | "requires_pin_change">> {
  password_setup_reason?: User["passwordSetupReason"]
  pin_setup_reason?: User["pinSetupReason"]
}

export interface ApiUserCreated extends ApiUser {
  temporary_password: string
  temporary_pin: string | null
}

export interface ApiDevice {
  id: string
  camera_id: string
  label: string
  status: DeviceStatus
  resolution: string | null
  last_seen: string | null
}

export interface ApiActivity {
  id: string
  created_at: string
  user_name: string | null
  action: ActivityLog["action"]
  details: string | null
  ip_address: string | null
}

export interface ApiActivityPage {
  items: ApiActivity[]
  total: number
  page: number
  page_size: number
  /** Boundary the page was read at; later pages pass it back so new rows cannot shift them. */
  as_of: string
}

export interface ApiConfig {
  revision: number
  camera_device_ids: number[]
  applied_camera_ids: string | null
  applied_camera_device_ids: number[]
  applied_revision: number | null
  application_status: "pending" | "applied" | "partial" | "failed"
  application_error: string | null
  restart_required: boolean
  retention_days: number
  retention_policy: string
  legacy_conflict: boolean
  camera_ids: string
  confidence_threshold: number
  readonly detection_confidence_threshold?: number
  data_retention_enabled: boolean
}

export interface ApiSupplierWrite {
  name: string
  contact_person?: string | null
  contact_phone?: string | null
  status?: ActiveStatus
}

export interface ApiSupplier extends ApiSupplierWrite {
  id: string
  status: ActiveStatus
  date_added: string
  updated_at?: string
}

export interface ApiIntake {
  id: string
  supplier_id: string | null
  supplier_name: string | null
  source: string | null
  batch_number: string | null
  qr_code: string | null
  intake_date: string
  status: IntakeStatus
  treatment: Treatment | null
  harvested_at: string | null
  treated_at: string | null
  spoiled_at: string | null
  scan_count: number
  expected_stock?: { cultivar: Cultivar; expected_bunches: number }[]
  created_at: string
  updated_at?: string
}

export interface ApiSensor {
  temperature: number
  humidity: number
  recorded_at: string
  source: string
  server_time?: string
  stale_after_seconds?: number
}

export interface ApiNotification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: string
  read: boolean
  href: string | null
}

export interface ApiMessage { message: string }

export type ApiConfigUpdate = Partial<Pick<ApiConfig, "camera_ids" | "camera_device_ids" | "confidence_threshold" | "data_retention_enabled">> & { expected_revision: number }
export interface MaintenanceOperation { id: string; status: string; message?: string; filename?: string; manifest?: Record<string, unknown> }
export interface MaintenanceStatus { state: string; active_operations: number; power?: { status?: string; operation_id?: string }; retention?: Record<string, unknown> }
export interface RestoreValidation { validation_id: string; token: string; manifest: Record<string, unknown>; expires_at: string }
