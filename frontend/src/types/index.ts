export const CULTIVARS = ["Lakatan", "Latundan", "Saba"] as const
export type Cultivar = typeof CULTIVARS[number]

export const RIPENESS_LEVELS = ["Unripe", "Ripe", "Overripe", "Rotten"] as const
export type Ripeness = typeof RIPENESS_LEVELS[number]

export const ROLES = ["Admin", "Operator"] as const
export type Role = typeof ROLES[number]

export const INVENTORY_STATUSES = ["In Stock", "Sold", "For Processing", "Spoiled"] as const
export type InventoryStatus = typeof INVENTORY_STATUSES[number]

export const ACTIVE_STATUSES = ["Active", "Inactive"] as const
export type ActiveStatus = typeof ACTIVE_STATUSES[number]

export const DEVICE_STATUSES = ["Online", "Offline"] as const
export type DeviceStatus = typeof DEVICE_STATUSES[number]

export const INTAKE_STATUSES = ["Active", "Depleted"] as const
export type IntakeStatus = typeof INTAKE_STATUSES[number]
export type NotificationType =
  | "scan_complete"
  | "scan_flagged"
  | "intake_update"
  | "system_alert"
  | "quality_warning"

export interface ScanResult {
  id: string
  dateTime: string
  cultivar: Cultivar
  ripeness: Ripeness
  confidence: number
  temperature?: number
  humidity?: number
  spoilageDays: string
  fingerCount: number
  operator: string
  thumbnailUrl?: string
  flagged?: boolean
  source?: string
  inventoryStatus?: InventoryStatus
  statusUpdatedAt?: string
  isOverridden?: boolean
  originalAiResult?: Partial<ScanResult>
  intakeId?: string
  qrCode?: string
}

export interface DailyIntake {
  id: string
  supplierId?: string
  supplierName?: string
  batchNumber?: string
  qrCode?: string
  date: string
  status: IntakeStatus
  scanCount?: number
  source?: string
}

export interface Supplier {
  id: string
  name: string
  contactPerson?: string
  contactPhone?: string
  status: ActiveStatus
  dateAdded: string
}

export interface User {
  id: string
  username: string
  fullName: string
  role: Role
  lastActive: string
  status: ActiveStatus
  avatar?: string
  pin?: string
  requiresPasswordChange?: boolean
  passwordSetupReason?: "new_account" | "password_reset"
  requiresPinChange?: boolean
  pinSetupReason?: "new_account" | "pin_reset"
  password?: string
}

export interface Device {
  id: string
  cameraId: string
  label: string
  status: DeviceStatus
  resolution: string
  lastSeen: string
}

export interface ActivityLog {
  id: string
  timestamp: string
  user: string
  action:
    | "login"
    | "logout"
    | "scan_created"
    | "scan_edited"
    | "scan_deleted"
    | "user_created"
    | "user_updated"
    | "config_changed"
    | "scan_flagged"
    | "supplier_created"
    | "supplier_updated"
    | "supplier_deleted"
    | "intake_created"
    | "intake_edited"
    | "intake_deleted"
    | "intake_status_changed"
    | "system_shutdown"
    | "system_restart"
  details: string
  ipAddress?: string
}

export interface AppNotification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: Date
  read: boolean
  href?: string
}

export interface SystemConfig {
  cameraIds: string
  confidenceThreshold: number
  dataRetentionEnabled: boolean
}

export interface ScanNote {
  id: string
  scanId: string
  note: string
  author: string
  timestamp: string
}

