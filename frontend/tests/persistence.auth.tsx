import { useSyncExternalStore } from "react"
import type { AuthUser } from "../src/lib/auth"

let user: AuthUser = { id: "admin-1", username: "admin", fullName: "Test Admin", role: "Admin" }
const listeners = new Set<() => void>()

export function useAuth() {
  return {
    user: useSyncExternalStore(
      listener => { listeners.add(listener); return () => { listeners.delete(listener) } },
      () => user,
    ),
    updateAuthUser(next: Partial<AuthUser>) {
      user = { ...user, ...next }
      listeners.forEach(listener => listener())
    },
  }
}
