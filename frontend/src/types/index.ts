import type { PrintJob } from "./printing"

export const CultivarEnum = {
  LAKATAN: "Lakatan",
  LATUNDAN: "Latundan",
  CARDABA: "Cardaba",
} as const
export const CULTIVARS = Object.values(CultivarEnum)
export type Cultivar = typeof CultivarEnum[keyof typeof CultivarEnum]

export const RipenessEnum = {
  UNRIPE: "Unripe",
  SEMI_RIPE: "Semi Ripe",
  RIPE: "Ripe",
  OVERRIPE: "Overripe",
} as const
export const RIPENESS_LEVELS = Object.values(RipenessEnum)
export type Ripeness = typeof RipenessEnum[keyof typeof RipenessEnum]

export const RoleEnum = {
  ADMIN: "Admin",
  OPERATOR: "Operator",
} as const
export const ROLES = Object.values(RoleEnum)
export type Role = typeof RoleEnum[keyof typeof RoleEnum]

export const InventoryStatusEnum = {
  IN_STOCK: "In Stock",
  SOLD: "Sold",
  FOR_PROCESSING: "For Processing",
  SPOILED: "Spoiled",
} as const
export const INVENTORY_STATUSES = Object.values(InventoryStatusEnum)
export type InventoryStatus = typeof InventoryStatusEnum[keyof typeof InventoryStatusEnum]

export const ActiveStatusEnum = {
  ACTIVE: "Active",
  INACTIVE: "Inactive",
} as const
export const ACTIVE_STATUSES = Object.values(ActiveStatusEnum)
export type ActiveStatus = typeof ActiveStatusEnum[keyof typeof ActiveStatusEnum]

export const DeviceStatusEnum = {
  ONLINE: "Online",
  OFFLINE: "Offline",
} as const
export const DEVICE_STATUSES = Object.values(DeviceStatusEnum)
export type DeviceStatus = typeof DeviceStatusEnum[keyof typeof DeviceStatusEnum]

export const IntakeStatusEnum = {
  ACTIVE: "Active",
  DEPLETED: "Depleted",
} as const
export const INTAKE_STATUSES = Object.values(IntakeStatusEnum)
export type IntakeStatus = typeof IntakeStatusEnum[keyof typeof IntakeStatusEnum]

export const TreatmentEnum = {
  NATURAL: "Natural",
  ETHEPHON: "Ethephon",
} as const
export const TREATMENTS = Object.values(TreatmentEnum)
export type Treatment = typeof TreatmentEnum[keyof typeof TreatmentEnum]
export type NotificationType =
  | "scan_complete"
  | "scan_flagged"
  | "intake_update"
  | "system_alert"
  | "quality_warning"

export interface BoundingBox {
  x: number
  y: number
  w: number
  h: number
  cls: string
  conf: number
}

export interface ScanDetection {
  camera_id: string
  camera_label: string
  detected_cultivar: string | null
  detected_ripeness: string | null
  confidence: number | null
  finger_count: number
  bounding_boxes: BoundingBox[]
  inference_time_ms: number | null
}

export interface ScanHistory {
  id: string
  kind: string
  timestamp: string
  actor_id: string | null
  actor_name: string | null
  reason: string | null
  previous_values: Record<string, unknown> | null
  new_values: Record<string, unknown>
  revision: number | null
  legacy: boolean
}

export interface ScanResult {
  printJob?: PrintJob
  printError?: string
  id: string
  revision?: number
  notes?: ScanNote[]
  history?: ScanHistory[]
  dateTime: string
  cultivar: Cultivar | "Unknown"
  ripeness: Ripeness | "Unknown"
  confidence: number | null
  temperature?: number
  humidity?: number
  vpd?: number
  treatment?: Treatment
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
  intakeOriginId?: string
  intakeProvenance?: string
  inventoryEligible?: boolean
  remainingDays?: number | null
  riskAsOf?: string
  qrCode?: string
  hasNotes?: boolean
  images?: { camera_id: string; file_path: string }[]
  detections?: ScanDetection[]
}

export interface DailyIntake {
  id: string
  supplierId?: string
  supplierName?: string
  batchNumber?: string
  qrCode?: string
  date: string
  status: IntakeStatus
  treatment?: Treatment
  harvestedAt?: string
  treatedAt?: string
  spoiledAt?: string
  scanCount?: number
  source?: string
  updatedAt?: string
}

export interface Supplier {
  id: string
  name: string
  contactPerson?: string
  contactPhone?: string
  status: ActiveStatus
  dateAdded: string
  updatedAt?: string
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
    | "login_failed"
    | "pin_failed"
    | "logout"
    | "scan_created"
    | "scan_edited"
    | "scan_deleted"
    | "user_created"
    | "user_updated"
    | "config_changed"
    | "scan_flagged"
    | "scan_rejected"
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
  revision?: number
  cameraDeviceIds?: number[]
  appliedRevision?: number | null
  applicationStatus?: "pending" | "applied" | "partial" | "failed"
  applicationError?: string | null
  restartRequired?: boolean
  retentionDays?: number
  retentionPolicy?: string
  legacyConflict?: boolean
  cameraIds: string
  confidenceThreshold: number
  readonly detectionConfidenceThreshold?: number
  dataRetentionEnabled: boolean
}

export interface ScanNote {
  id: string
  scanId: string
  note: string
  author: string
  timestamp: string
}

