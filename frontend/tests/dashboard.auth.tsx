import { useSyncExternalStore } from "react"
import type { AuthUser } from "../src/lib/auth"

declare global {
  interface Window {
    dashboardUser?: AuthUser
    dashboardTest: { setUser: (user: AuthUser) => void }
  }
}

let user: AuthUser = window.dashboardUser ?? { id: "admin-1", username: "admin", fullName: "Test Admin", role: "Admin" }
const listeners = new Set<() => void>()
window.dashboardTest = { setUser(next) {
  user = next
  // The intercepted backend keys its fixture response by authenticated ID.
  localStorage.setItem("bananavision_token", next.id)
  listeners.forEach(listener => listener())
} }

// Only the auth provider is substituted. Dashboard, API, resource hook,
// WebSocket hook, cards, and drilldown execute their production implementations.
export function useAuth() {
  return { user: useSyncExternalStore(
    listener => { listeners.add(listener); return () => { listeners.delete(listener) } },
    () => user,
  ) }
}
