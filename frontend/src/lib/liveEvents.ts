import type { ApiScan } from "@/lib/scanData"

/** Coarse browser-wide notifications for data already fetched through the API. */
export const SCAN_CHANGED_EVENT = "bananavision:scan-changed"
export const SCANS_ADDED_EVENT = "bananavision:scans-added"
export const NOTIFICATIONS_CHANGED_EVENT = "bananavision:notifications-changed"
export const LIVE_RESUMED_EVENT = "bananavision:live-resumed"
/** A committed scan edit with the revision-aware row needed to patch a view. */
export const SCAN_UPDATED_EVENT = "bananavision:scan-updated"
export const INTAKE_CHANGED_EVENT = "bananavision:intake-changed"
export const SUPPLIER_CHANGED_EVENT = "bananavision:supplier-changed"

export interface ScanUpdateDetail {
  eventId: string
  scanId: string
  revision: number
  kind: string
  actorId: string
  changed: string[]
  partial: boolean
  deleted?: boolean
  /** Authorized row fields plus the derived source/operator identity the event adds. */
  scan: Partial<ApiScan> & {
    operator_id?: string
    source_key?: string
    source_name?: string
  }
}

export function newEventId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function notifyScanChanged() {
  window.dispatchEvent(new Event(SCAN_CHANGED_EVENT))
}

/** A newly committed Kiosk scan exists; snapshots must stay frozen until asked. */
export function notifyScansAdded() {
  window.dispatchEvent(new Event(SCANS_ADDED_EVENT))
}

export function notifyNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT))
}

/** A WebSocket connection resumed after dropping; missed changes may exist. */
export function notifyLiveResumed() {
  window.dispatchEvent(new Event(LIVE_RESUMED_EVENT))
}

/** Local or remote committed edit; consumers merge by revision. */
export function notifyScanUpdated(detail: ScanUpdateDetail) {
  window.dispatchEvent(new CustomEvent<ScanUpdateDetail>(SCAN_UPDATED_EVENT, { detail }))
}

export function notifyIntakeChanged(detail: Record<string, unknown>) {
  window.dispatchEvent(new CustomEvent(INTAKE_CHANGED_EVENT, { detail }))
}

export function notifySupplierChanged(detail: Record<string, unknown>) {
  window.dispatchEvent(new CustomEvent(SUPPLIER_CHANGED_EVENT, { detail }))
}
