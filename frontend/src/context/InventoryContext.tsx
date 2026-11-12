import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react"
import { api } from "@/lib/api"
import { scanWrite } from "@/lib/scanWrites"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import type { DailyIntake, Supplier, InventoryStatus } from "@/types"
import { useLocation } from "react-router-dom"
import { INTAKE_CHANGED_EVENT, LIVE_RESUMED_EVENT, SUPPLIER_CHANGED_EVENT } from "@/lib/liveEvents"

// ── Types ───────────────────────────────────────────────────────────────────

type BulkInventoryResponse = Awaited<ReturnType<typeof api.intakes.bulkInventory>>

interface InventoryContextType {
  intakes: DailyIntake[]
  intakesReady: boolean
  intakesLoading: boolean
  intakesError: string | null
  intakesStale: boolean
  refreshIntakes: () => void
  activeIntake: DailyIntake | null
  setActiveIntake: (intake: DailyIntake | null) => void
  startIntake: (supplierId: string, batchNumber: string, treatment?: string) => Promise<DailyIntake>
  bulkUpdateIntakeInventory: (intakeId: string, status: InventoryStatus, reason: string, revisions: Record<string, number>) => Promise<BulkInventoryResponse>
  suppliersLoading: boolean
  suppliersReady: boolean
  suppliersError: string | null
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
  updatedAt: s.updated_at || s.updatedAt,
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
  updatedAt: i.updated_at || i.updatedAt,
})

// ── Provider ────────────────────────────────────────────────────────────────

/** Minimal shape of the post-commit events; unknown fields are ignored. */
interface IntakeEventDetail {
  event_id?: string
  intake_id?: string
  status?: string
  intake?: {
    id?: string
    supplier_id?: string
    supplier_name?: string
    batch_number?: string
    intake_date?: string
    date?: string
    status?: string
    scan_count?: number
    treatment?: string
    created_at?: string
    updated_at?: string
    updatedAt?: string
  } | null
}

interface SupplierEventDetail {
  event_id?: string
  supplier?: {
    id?: string
    name?: string
    contact_person?: string
    contactPhone?: string
    status?: string
    date_added?: string
    updated_at?: string
    updatedAt?: string
  } | null
}

/** Timestamp order rejects an event or response that was overtaken by a local write. */
function isNewer(incoming?: string, current?: string) {
  if (!incoming) return true
  if (!current) return true
  const next = Date.parse(incoming)
  const previous = Date.parse(current)
  return !Number.isFinite(next) || !Number.isFinite(previous) || next >= previous
}

export function InventoryProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  return <InventoryStore key={`${user?.id}:${user?.role}`}>{children}</InventoryStore>
}

function InventoryStore({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { updateScansForIntake } = useScans()
  const { pathname } = useLocation()

  const [intakes, setIntakes] = useState<DailyIntake[]>([])
  const [intakesReady, setIntakesReady] = useState(false)
  const [suppliersReady, setSuppliersReady] = useState(false)
  const [suppliersLoading, setSuppliersLoading] = useState(Boolean(user))
  const [suppliersError, setSuppliersError] = useState<string | null>(null)
  const [intakesLoading, setIntakesLoading] = useState(true)
  const [intakesError, setIntakesError] = useState<string | null>(null)
  const [intakesStale, setIntakesStale] = useState(false)
  const [activeIntake, setActiveIntake] = useState<DailyIntake | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const loadSeq = useRef(0)
  const supplierSeq = useRef(0)
  const [supplierReload, setSupplierReload] = useState(0)
  const hasIntakeSnapshot = useRef(false)
  const intakesRef = useRef<DailyIntake[]>([])
  intakesRef.current = intakes
  const seenEvents = useRef(new Set<string>())
  const reconcileTimer = useRef<number | null>(null)
  const cancelLoad = useCallback(() => { ++loadSeq.current; ++supplierSeq.current }, [])
  const acceptWrite = useCallback(() => {
    ++loadSeq.current
    setIntakesLoading(false)
  }, [])
  const acceptSupplierWrite = useCallback(() => {
    ++supplierSeq.current
    setSuppliersLoading(false)
    setSuppliersError(null)
    if (!suppliersReady) setSupplierReload(value => value + 1)
  }, [suppliersReady])

  // ── Load data on mount / navigation ─────────────────────────────────────

  const loadData = useCallback(async () => {
    if (!user) return
    const mySeq = ++loadSeq.current
    setIntakesLoading(true)
    setSuppliersLoading(true)
    setSuppliersError(null)
    const mySupplierSeq = ++supplierSeq.current
    await Promise.allSettled([
      (async () => {
        try {
          const result = await api.suppliers.list()
          if (mySupplierSeq !== supplierSeq.current) return
          setSuppliers(result.map(mapApiSupplier))
          setSuppliersReady(true)
        } catch {
          if (mySupplierSeq === supplierSeq.current) setSuppliersError("Suppliers could not be loaded. Please reload to retry.")
        } finally {
          if (mySupplierSeq === supplierSeq.current) setSuppliersLoading(false)
        }
      })(),
      (async () => {
        try {
          const result = await api.intakes.list()
          if (mySeq !== loadSeq.current) return
          const loaded = result.map(mapApiIntake)
          setIntakes(loaded)
          setActiveIntake(current => {
            if (current) {
              const refreshed = loaded.find(intake => intake.id === current.id)
              // A record missing from the authoritative registry is deleted or
              // no longer accessible; never keep presenting it as the open batch.
              if (!refreshed) return null
              return refreshed.status === "Active" ? refreshed : null
            }
            // A reload must resume the open batch instead of forcing a duplicate intake.
            return loaded.find(intake => intake.status === "Active") ?? null
          })
          hasIntakeSnapshot.current = true
          setIntakesReady(true)
          setIntakesError(null)
          setIntakesStale(false)
        } catch {
          if (mySeq !== loadSeq.current) return
          setIntakesStale(hasIntakeSnapshot.current)
          setIntakesError("Intake data unavailable. Stock totals may be inaccurate.")
        } finally {
          if (mySeq === loadSeq.current) setIntakesLoading(false)
        }
      })(),
    ])
  }, [user])

  useEffect(() => {
    void loadData()
    return cancelLoad
  }, [loadData, cancelLoad, pathname, supplierReload])

  const refreshIntakes = useCallback(() => { void loadData() }, [loadData])

  const scheduleReconcile = useCallback(() => {
    if (!user) return
    if (reconcileTimer.current) window.clearTimeout(reconcileTimer.current)
    reconcileTimer.current = window.setTimeout(() => {
      reconcileTimer.current = null
      if (!document.hidden) void loadData()
    }, 250)
  }, [loadData, user])

  const acceptEventId = useCallback((detail: { event_id?: string } | null | undefined) => {
    const eventId = typeof detail?.event_id === "string" ? detail.event_id : ""
    if (!eventId) return true
    if (seenEvents.current.has(eventId)) return false
    seenEvents.current.add(eventId)
    if (seenEvents.current.size > 200) {
      const oldest = seenEvents.current.values().next().value
      if (oldest) seenEvents.current.delete(oldest)
    }
    return true
  }, [])

  const applyIntakeEvent = useCallback((detail: IntakeEventDetail) => {
    if (!acceptEventId(detail)) return
    const raw = detail?.intake && typeof detail.intake === "object" ? detail.intake : null
    const id = String(raw?.id ?? detail?.intake_id ?? "")
    if (!id) return
    const mapped = raw && (raw.intake_date || raw.date) ? mapApiIntake(raw) : null
    const status = (raw?.status ?? detail?.status) as DailyIntake["status"] | undefined
    const updatedAt = raw?.updated_at ?? raw?.updatedAt
    if (!mapped && !intakesRef.current.some(intake => intake.id === id)) {
      // A partial status event cannot reconstruct the registry row.
      scheduleReconcile()
      return
    }
    setIntakes(previous => {
      const index = previous.findIndex(intake => intake.id === id)
      if (index < 0) return mapped ? [mapped, ...previous] : previous
      const current = previous[index]
      if (!isNewer(updatedAt ?? mapped?.updatedAt, current.updatedAt)) return previous
      const merged = {
        ...current,
        ...(mapped ?? {}),
        id,
        status: status ?? mapped?.status ?? current.status,
        updatedAt: updatedAt ?? mapped?.updatedAt ?? current.updatedAt,
      }
      // A creation event carries zero scans; a later registry read is authoritative
      // for the computed count and must not flicker back to zero.
      if (mapped?.scanCount === 0 && current.scanCount) merged.scanCount = current.scanCount
      const next = [...previous]
      next[index] = merged
      return next
    })
    setActiveIntake(current => {
      if (!current || current.id !== id) return current
      if (!isNewer(updatedAt ?? mapped?.updatedAt, current.updatedAt)) return current
      const nextStatus = status ?? mapped?.status ?? current.status
      return nextStatus === "Active"
        ? { ...current, ...(mapped ?? {}), id, status: nextStatus,
            updatedAt: updatedAt ?? mapped?.updatedAt ?? current.updatedAt }
        : null
    })
    if (!intakesReady) setIntakesReady(true)
  }, [acceptEventId, intakesReady, scheduleReconcile])

  const applySupplierEvent = useCallback((detail: SupplierEventDetail) => {
    if (!acceptEventId(detail)) return
    const raw = detail?.supplier
    if (!raw?.id) return
    const mapped = mapApiSupplier(raw)
    setSuppliers(previous => {
      const index = previous.findIndex(supplier => supplier.id === mapped.id)
      if (index < 0) return [...previous, mapped]
      if (!isNewer(mapped.updatedAt, previous[index].updatedAt)) return previous
      const next = [...previous]
      next[index] = { ...previous[index], ...mapped }
      return next
    })
    if (!suppliersReady) setSuppliersReady(true)
    setSuppliersError(null)
  }, [acceptEventId, suppliersReady])

  useEffect(() => {
    const onIntake = (event: Event) => applyIntakeEvent((event as CustomEvent<IntakeEventDetail>).detail)
    const onSupplier = (event: Event) => applySupplierEvent((event as CustomEvent<SupplierEventDetail>).detail)
    const onResume = () => scheduleReconcile()
    const onVisibility = () => { if (!document.hidden) scheduleReconcile() }
    window.addEventListener(INTAKE_CHANGED_EVENT, onIntake)
    window.addEventListener(SUPPLIER_CHANGED_EVENT, onSupplier)
    window.addEventListener("focus", onResume)
    window.addEventListener("online", onResume)
    window.addEventListener(LIVE_RESUMED_EVENT, onResume)
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      window.removeEventListener(INTAKE_CHANGED_EVENT, onIntake)
      window.removeEventListener(SUPPLIER_CHANGED_EVENT, onSupplier)
      window.removeEventListener("focus", onResume)
      window.removeEventListener("online", onResume)
      window.removeEventListener(LIVE_RESUMED_EVENT, onResume)
      document.removeEventListener("visibilitychange", onVisibility)
      if (reconcileTimer.current) window.clearTimeout(reconcileTimer.current)
    }
  }, [applyIntakeEvent, applySupplierEvent, scheduleReconcile])

  // ── Reset on logout ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) {
      setIntakes([])
      setIntakesLoading(false)
      setIntakesError(null)
      setIntakesStale(false)
      setActiveIntake(null)
      setSuppliers([])
    }
  }, [user])

  // ── Intake Operations ───────────────────────────────────────────────────

  const startIntake = useCallback(async (supplierId: string, batchNumber: string, treatment?: string) => {
    const resp = await api.intakes.create({ supplier_id: supplierId, batch_number: batchNumber, source: "Kiosk", treatment: treatment || "Natural" })
    const newIntake = mapApiIntake(resp)
    acceptWrite()
    // The live creation event can land before this response; merge by id instead of prepending.
    setIntakes((prev) => prev.some((intake) => intake.id === newIntake.id)
      ? prev.map((intake) => (intake.id === newIntake.id ? { ...intake, ...newIntake } : intake))
      : [newIntake, ...prev])
    setActiveIntake(newIntake)
    return newIntake
  }, [acceptWrite])

  const bulkUpdateIntakeInventory = useCallback(async (intakeId: string, status: InventoryStatus, reason: string, revisions: Record<string, number>) => {
    return scanWrite(`${user?.id}:${intakeId}:bulk`, { inventory_status: status, reason, expected_revisions: revisions }, async body => {
      const result = await api.intakes.bulkInventory(intakeId, body)
      acceptWrite()
      setIntakes((prev) => prev.map((i) => (i.id === intakeId ? { ...i, status: result.intake_status } : i)))
      setActiveIntake((current) => current?.id === intakeId ? { ...current, status: result.intake_status } : current)
      // Only change records and timestamps confirmed by the persisted response.
      updateScansForIntake(result.updated_scan_ids, status, result.status_updated_at, result.revisions)
      return result
    })
  }, [updateScansForIntake, user?.id, acceptWrite])

  // ── Supplier Operations ─────────────────────────────────────────────────

  const addSupplier = useCallback(async (supplierData: Omit<Supplier, "id" | "dateAdded">) => {
    const apiData = {
      name: supplierData.name,
      contact_person: supplierData.contactPerson,
      contact_phone: supplierData.contactPhone,
      status: supplierData.status,
    }
    const newSup = await api.suppliers.create(apiData)
    acceptSupplierWrite()
    const mapped = mapApiSupplier(newSup)
    // The live creation event can land before this response; merge by id instead of appending.
    setSuppliers((prev) => prev.some((supplier) => supplier.id === mapped.id)
      ? prev.map((supplier) => (supplier.id === mapped.id ? { ...supplier, ...mapped } : supplier))
      : [...prev, mapped])
  }, [acceptSupplierWrite])

  const updateSupplier = useCallback(async (id: string, data: Partial<Omit<Supplier, "id" | "dateAdded">>) => {
    const apiData: Record<string, unknown> = {}
    if (data.name !== undefined) apiData.name = data.name
    if (data.status !== undefined) apiData.status = data.status
    if (data.contactPerson !== undefined) apiData.contact_person = data.contactPerson
    if (data.contactPhone !== undefined) apiData.contact_phone = data.contactPhone

    const updated = await api.suppliers.update(id, apiData)
    acceptSupplierWrite()
    setSuppliers((prev) => prev.map((s) => (s.id === id ? mapApiSupplier(updated) : s)))
  }, [acceptSupplierWrite])

  const updateSupplierStatus = useCallback(async (id: string, status: "Active" | "Inactive") => {
    const updated = await api.suppliers.update(id, { status })
    acceptSupplierWrite()
    setSuppliers((prev) => prev.map((s) => (s.id === id ? mapApiSupplier(updated) : s)))
  }, [acceptSupplierWrite])

  return (
    <InventoryContext value={{
      intakes,
      intakesLoading, intakesReady,
      intakesError,
      intakesStale,
      refreshIntakes,
      activeIntake,
      setActiveIntake,
      startIntake,
      bulkUpdateIntakeInventory,
      suppliers, suppliersLoading, suppliersReady, suppliersError,
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
