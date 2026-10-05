import type { ActiveStatus, ActivityLog, DeviceStatus, IntakeStatus, NotificationType, Role, Treatment, User } from "@/types"

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

export interface ApiConfig {
  camera_ids: string
  confidence_threshold: number
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
  created_at: string
}

export interface ApiSensor {
  temperature: number
  humidity: number
  recorded_at: string
  source: string
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
