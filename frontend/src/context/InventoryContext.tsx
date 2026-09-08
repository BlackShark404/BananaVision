import React, { createContext, useContext, useState, useCallback, useEffect } from "react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import type { DailyIntake, Supplier, InventoryStatus } from "@/types"
import { useLocation } from "react-router-dom"

// ── Types ───────────────────────────────────────────────────────────────────

interface InventoryContextType {
  intakes: DailyIntake[]
  activeIntake: DailyIntake | null
  setActiveIntake: (intake: DailyIntake | null) => void
  startIntake: (supplierId: string, batchNumber: string, treatment?: string) => Promise<DailyIntake | undefined>
  bulkUpdateIntakeInventory: (intakeId: string, status: InventoryStatus) => void
  suppliers: Supplier[]
  addSupplier: (supplierData: Omit<Supplier, "id" | "dateAdded">) => void
  updateSupplier: (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => void
  updateSupplierStatus: (id: string, status: "Active" | "Inactive") => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const InventoryContext = createContext<InventoryContextType | null>(null)

// ── Mappers ─────────────────────────────────────────────────────────────────

const mapApiSupplier = (s: any): Supplier => ({
  id: s.id,
  name: s.name,
  contactPerson: s.contact_person || s.contactPerson,
  contactPhone: s.contact_phone || s.contactPhone,
  status: s.status,
  dateAdded: s.date_added || s.dateAdded || new Date().toISOString(),
})

const mapApiIntake = (i: any): DailyIntake => ({
  id: i.id,
  supplierId: i.supplier_id || i.supplierId,
  supplierName: i.supplier_name || i.supplierName || i.source || "Unknown",
  batchNumber: i.batch_number || i.batchNumber,
  qrCode: i.qr_code || i.qrCode,
  date: i.intake_date || i.date || new Date().toISOString().split("T")[0],
  status: i.status as "Active" | "Depleted",
  treatment: i.treatment,
  harvestedAt: i.harvested_at || i.harvestedAt,
  treatedAt: i.treated_at || i.treatedAt,
  spoiledAt: i.spoiled_at || i.spoiledAt,
  scanCount: i.scan_count || i.scanCount || 0,
})

// ── Provider ────────────────────────────────────────────────────────────────

export function InventoryProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { updateScansForIntake } = useScans()
  const { pathname } = useLocation()

  const [intakes, setIntakes] = useState<DailyIntake[]>([])
  const [activeIntake, setActiveIntake] = useState<DailyIntake | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])

  // ── Load data on mount / navigation ─────────────────────────────────────

  useEffect(() => {
    if (!user) return

    const loadData = async () => {
      try {
        const [suppliersRes, intakesRes] = await Promise.allSettled([
          api.suppliers.list(),
          api.intakes.list(),
        ])

        if (suppliersRes.status === "fulfilled") {
          setSuppliers((suppliersRes.value as any[]).map(mapApiSupplier))
        } else {
          console.warn("[InventoryContext] Suppliers API unavailable")
        }

        if (intakesRes.status === "fulfilled") {
          setIntakes((intakesRes.value as any[]).map(mapApiIntake))
        } else {
          console.warn("[InventoryContext] Intakes API unavailable")
        }
      } catch (err) {
        console.warn("[InventoryContext] Backend unreachable", err)
      }
    }

    loadData()
  }, [user, pathname])

  // ── Reset on logout ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) {
      setIntakes([])
      setActiveIntake(null)
      setSuppliers([])
    }
  }, [user])

  // ── Intake Operations ───────────────────────────────────────────────────

  const startIntake = useCallback(async (supplierId: string, batchNumber: string, treatment?: string) => {
    try {
      const resp = await api.intakes.create({ supplier_id: supplierId, batch_number: batchNumber, source: "Kiosk", treatment: treatment || "Natural" })
      const newIntake = mapApiIntake(resp)
      setIntakes((prev) => [newIntake, ...prev])
      setActiveIntake(newIntake)
      return newIntake
    } catch (error) {
      console.error("[InventoryContext] Failed to create intake", error)
    }
  }, [])

  const bulkUpdateIntakeInventory = useCallback((intakeId: string, status: InventoryStatus) => {
    const intakeStatus = status === "In Stock" ? "Active" : "Depleted"
    api.intakes.update(intakeId, { status: intakeStatus, inventory_status: status }).catch(() => {})
    setIntakes((prev) => prev.map((i) => (i.id === intakeId ? { ...i, status: intakeStatus as "Active" | "Depleted" } : i)))
    // Update scans via ScanContext
    updateScansForIntake(intakeId, status)
  }, [updateScansForIntake])

  // ── Supplier Operations ─────────────────────────────────────────────────

  const addSupplier = useCallback((supplierData: Omit<Supplier, "id" | "dateAdded">) => {
    const apiData = {
      name: supplierData.name,
      contact_person: supplierData.contactPerson,
      contact_phone: supplierData.contactPhone,
      status: supplierData.status,
    }
    api.suppliers.create(apiData)
      .then((newSup) => setSuppliers((prev) => [...prev, mapApiSupplier(newSup)]))
      .catch(() => {
        const newSupplier: Supplier = {
          ...supplierData,
          id: `SUP-${Math.floor(Math.random() * 1000000)}`.padStart(11, "0"),
          dateAdded: new Date().toISOString(),
        }
        setSuppliers((prev) => [...prev, newSupplier])
      })
  }, [])

  const updateSupplier = useCallback((id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => {
    const apiData: any = { ...data }
    if (data.contactPerson !== undefined) apiData.contact_person = data.contactPerson
    if (data.contactPhone !== undefined) apiData.contact_phone = data.contactPhone

    api.suppliers.update(id, apiData)
      .then((updated) => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...mapApiSupplier(updated) } : s))))
      .catch(() => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...data } : s))))
  }, [])

  const updateSupplierStatus = useCallback((id: string, status: "Active" | "Inactive") => {
    api.suppliers.update(id, { status })
      .then((updated) => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, ...mapApiSupplier(updated) } : s))))
      .catch(() => setSuppliers((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s))))
  }, [])

  return (
    <InventoryContext value={{
      intakes,
      activeIntake,
      setActiveIntake,
      startIntake,
      bulkUpdateIntakeInventory,
      suppliers,
      addSupplier,
      updateSupplier,
      updateSupplierStatus,
    }}>
      {children}
    </InventoryContext>
  )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useInventory() {
  const ctx = useContext(InventoryContext)
  if (!ctx) throw new Error("useInventory must be inside InventoryProvider")
  return ctx
}
