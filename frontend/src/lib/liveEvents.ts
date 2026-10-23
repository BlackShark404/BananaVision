/** Coarse browser-wide notifications for data already fetched through the API. */
export const SCAN_CHANGED_EVENT = "bananavision:scan-changed"
export const NOTIFICATIONS_CHANGED_EVENT = "bananavision:notifications-changed"

export function notifyScanChanged() {
  window.dispatchEvent(new Event(SCAN_CHANGED_EVENT))
}

export function notifyNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT))
}
