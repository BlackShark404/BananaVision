import { useSyncExternalStore } from "react"
import type { AuthUser } from "../src/lib/auth"

let user: AuthUser | null = { id: "operator-1", username: "fixture", fullName: "Fixture Operator", role: "Operator" }
const listeners = new Set<() => void>()
declare global {
  interface Window { kioskAuthTest: { setUser: (next: AuthUser | null) => void } }
}
window.kioskAuthTest = { setUser(next) { user = next; listeners.forEach(listener => listener()) } }

/** Isolated auth boundary: exercise the real kiosk chooser without real credentials. */
export function useAuth() {
  return {
    user: useSyncExternalStore(listener => {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    }, () => user),
    switchOperator: async () => "success",
    setupPinAndLogin: async () => true,
    updateAuthUser: () => {},
  }
}
