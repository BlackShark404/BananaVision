/**
 * Barrel re-export — backward-compatible `useApp()` hook that composes all domain contexts.
 *
 * New code should import from the specific domain context directly:
 *   import { useAuth } from "@/context/AuthContext"
 *   import { useScans } from "@/context/ScanContext"
 *   import { useInventory } from "@/context/InventoryContext"
 *   import { useAdmin } from "@/context/AdminContext"
 */

// Re-export providers & hooks for convenience
export { AuthProvider, useAuth } from "@/context/AuthContext"
export { AdminProvider, useAdmin } from "@/context/AdminContext"
export { ScanProvider, useScans } from "@/context/ScanContext"
export { InventoryProvider, useInventory } from "@/context/InventoryContext"
