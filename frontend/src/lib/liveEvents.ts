/** Coarse browser-wide notifications for data already fetched through the API. */
export const SCAN_CHANGED_EVENT = "bananavision:scan-changed"
export const SCANS_ADDED_EVENT = "bananavision:scans-added"
export const NOTIFICATIONS_CHANGED_EVENT = "bananavision:notifications-changed"
export const LIVE_RESUMED_EVENT = "bananavision:live-resumed"

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
