import React, { createContext, useContext, useState, useCallback, useEffect } from "react"
import { api } from "@/lib/api"
import { scanWrite } from "@/lib/scanWrites"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import type { DailyIntake, Supplier, InventoryStatus } from "@/types"
import { useLocation } from "react-router-dom"

// ── Types ───────────────────────────────────────────────────────────────────

interface InventoryContextType {
  intakes: DailyIntake[]
  activeIntake: DailyIntake | null
  setActiveIntake: (intake: DailyIntake | null) => void
  startIntake: (supplierId: string, batchNumber: string, treatment?: string) => Promise<DailyIntake>
  bulkUpdateIntakeInventory: (intakeId: string, status: InventoryStatus, reason: string, revisions: Record<string, number>) => Promise<void>
  suppliers: Supplier[]
  addSupplier: (supplierData: Omit<Supplier, "id" | "dateAdded">) => Promise<void>
  updateSupplier: (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => Promise<void>
  updateSupplierStatus: (id: string, status: "Active" | "Inactive") => Promise<void>
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
  dateAdded: s.date_added || s.dateAdded || "",
})

const mapApiIntake = (i: any): DailyIntake => ({
  id: i.id,
  supplierId: i.supplier_id || i.supplierId,
  supplierName: i.supplier_name || i.supplierName || i.source || "Unknown",
  source: i.source || i.supplier_name || i.supplierName,
  batchNumber: i.batch_number || i.batchNumber,
  qrCode: i.qr_code || i.qrCode,
  date: i.intake_date || i.date || "",
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
  return <InventoryStore key={`${user?.id}:${user?.role}`}>{children}</InventoryStore>
}

function InventoryStore({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { updateScansForIntake } = useScans()
  const { pathname } = useLocation()

  const [intakes, setIntakes] = useState<DailyIntake[]>([])
  const [activeIntake, setActiveIntake] = useState<DailyIntake | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])

  // ── Load data on mount / navigation ─────────────────────────────────────

  useEffect(() => {
    if (!user) return

    let cancelled = false
    const loadData = async () => {
      try {
        const [suppliersRes, intakesRes] = await Promise.allSettled([
          api.suppliers.list(),
          api.intakes.list(),
        ])

        if (cancelled) return
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

    void loadData()
    return () => { cancelled = true }
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
    const resp = await api.intakes.create({ supplier_id: supplierId, batch_number: batchNumber, source: "Kiosk", treatment: treatment || "Natural" })
    const newIntake = mapApiIntake(resp)
    setIntakes((prev) => [newIntake, ...prev])
    setActiveIntake(newIntake)
    return newIntake
  }, [])

  const bulkUpdateIntakeInventory = useCallback(async (intakeId: string, status: InventoryStatus, reason: string, revisions: Record<string, number>) => {
    const result = await scanWrite(`${user?.id}:${intakeId}:bulk`, { inventory_status: status, reason, expected_revisions: revisions }, body => api.intakes.bulkInventory(intakeId, body))
    setIntakes((prev) => prev.map((i) => (i.id === intakeId ? { ...i, status: result.intake_status } : i)))
    setActiveIntake((current) => current?.id === intakeId ? { ...current, status: result.intake_status } : current)
    // Only change records and timestamps confirmed by the persisted response.
    updateScansForIntake(result.updated_scan_ids, status, result.status_updated_at)
  }, [updateScansForIntake, user?.id])

  // ── Supplier Operations ─────────────────────────────────────────────────

  const addSupplier = useCallback(async (supplierData: Omit<Supplier, "id" | "dateAdded">) => {
    const apiData = {
      name: supplierData.name,
      contact_person: supplierData.contactPerson,
      contact_phone: supplierData.contactPhone,
      status: supplierData.status,
    }
    const newSup = await api.suppliers.create(apiData)
    setSuppliers((prev) => [...prev, mapApiSupplier(newSup)])
  }, [])

  const updateSupplier = useCallback(async (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => {
    const apiData: Record<string, unknown> = {}
    if (data.name !== undefined) apiData.name = data.name
    if (data.status !== undefined) apiData.status = data.status
    if (data.contactPerson !== undefined) apiData.contact_person = data.contactPerson
    if (data.contactPhone !== undefined) apiData.contact_phone = data.contactPhone

    const updated = await api.suppliers.update(id, apiData)
    setSuppliers((prev) => prev.map((s) => (s.id === id ? mapApiSupplier(updated) : s)))
  }, [])

  const updateSupplierStatus = useCallback(async (id: string, status: "Active" | "Inactive") => {
    const updated = await api.suppliers.update(id, { status })
    setSuppliers((prev) => prev.map((s) => (s.id === id ? mapApiSupplier(updated) : s)))
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
