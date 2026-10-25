import { useState } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider, useScans } from "../src/context/ScanContext"
import { InventoryProvider, useInventory } from "../src/context/InventoryContext"
import { AppNotifications } from "../src/components/AppNotifications"
import Logs from "../src/pages/Logs"
import DeviceStatus from "../src/pages/DeviceStatus"
import "../src/index.css"

/** Expose only the committed provider state the multi-session assertions need. */
function Probe() {
  const scans = useScans()
  const inventory = useInventory()
  return <output data-testid="state" hidden>{JSON.stringify({
    scans: scans.scans.map(scan => ({
      id: scan.id, revision: scan.revision, inventoryStatus: scan.inventoryStatus,
      flagged: scan.flagged, cultivar: scan.cultivar,
    })),
    scansLoading: scans.scansLoading, scansError: scans.scansError,
    intakes: inventory.intakes.map(intake => ({
      id: intake.id, status: intake.status, scanCount: intake.scanCount, updatedAt: intake.updatedAt,
    })),
    suppliers: inventory.suppliers.map(supplier => ({
      id: supplier.id, name: supplier.name, status: supplier.status, updatedAt: supplier.updatedAt,
    })),
    activeIntakeId: inventory.activeIntake?.id ?? null,
    intakesReady: inventory.intakesReady, intakesLoading: inventory.intakesLoading,
    intakesError: inventory.intakesError,
  })}</output>
}

/**
 * Real provider mutations, invoked exactly as the pages invoke them. The harness
 * controls HTTP/WebSocket transport only, so these calls exercise the production
 * commit -> notify -> reconcile path without brittle table-menu interactions.
 */
function Actions() {
  const scans = useScans()
  const inventory = useInventory()
  const [result, setResult] = useState("idle")
  const revision = (id: string) => scans.scans.find(scan => scan.id === id)?.revision ?? 1
  const run = async (name: string, action: () => Promise<unknown>) => {
    setResult(`${name}:pending`)
    try { await action(); setResult(`${name}:ok`) }
    catch (error) { setResult(`${name}:error:${error instanceof Error ? error.message : String(error)}`) }
  }
  return <div data-testid="actions">
    <button onClick={() => void run("flag", () => scans.flagScan("scan-1", true))}>flag</button>
    <button onClick={() => void run("override", () => scans.updateScanData("scan-11", { cultivar: "Cardaba" }, "Cross-session cultivar check"))}>override</button>
    <button onClick={() => void run("bulk", () => inventory.bulkUpdateIntakeInventory(
      "intake-1", "Sold", "Cross-session dispatch",
      { "scan-1": revision("scan-1"), "scan-11": revision("scan-11") },
    ))}>bulk</button>
    <button onClick={() => void run("supplier", () => inventory.updateSupplier("supplier-1", { name: "Renamed Supplier" }))}>supplier</button>
    <button onClick={() => void run("intake", () => inventory.startIntake("supplier-1", "B-9"))}>intake</button>
    <output data-testid="action-result">{result}</output>
  </div>
}

function Shell() {
  return <>
    <Probe />
    <Actions />
    <AppNotifications />
    <Routes>
      <Route path="/logs" element={<Logs />} />
      <Route path="/devices" element={<DeviceStatus />} />
      <Route path="*" element={null} />
    </Routes>
  </>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <AdminProvider><ScanProvider><InventoryProvider><Shell /></InventoryProvider></ScanProvider></AdminProvider>
  </BrowserRouter>,
)
