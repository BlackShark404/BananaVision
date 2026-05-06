export type Cultivar = "Lakatan" | "Latundan" | "Saba"
export type Ripeness = "Unripe" | "Ripe" | "Overripe" | "Rotten"
export type Role = "Admin" | "Operator"
export type InventoryStatus = "In Stock" | "Sold" | "For Processing" | "Spoiled"
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
}

export interface DailyIntake {
  id: string
  supplierId?: string
  supplierName?: string
  batchNumber?: string
  qrCode?: string
  date: string
  status: "Active" | "Depleted"
  scanCount?: number
}

export interface Supplier {
  id: string
  name: string
  contactPerson?: string
  contactPhone?: string
  status: "Active" | "Inactive"
  dateAdded: string
}

export interface User {
  id: string
  username: string
  fullName: string
  role: Role
  lastActive: string
  status: "Active" | "Inactive"
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
  status: "Online" | "Offline"
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
    | "user_created"
    | "user_updated"
    | "config_changed"
    | "scan_flagged"
    | "supplier_created"
    | "supplier_updated"
    | "intake_created"
    | "intake_edited"
    | "intake_status_changed"
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
}

export interface ScanNote {
  id: string
  scanId: string
  note: string
  author: string
  timestamp: string
}

