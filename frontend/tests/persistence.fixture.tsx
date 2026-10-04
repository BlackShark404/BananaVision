import { useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider, useAdmin } from "../src/context/AdminContext"
import { ScanProvider, useScans } from "../src/context/ScanContext"
import { InventoryProvider, useInventory } from "../src/context/InventoryContext"
import QualityControl from "../src/pages/admin/QualityControl"
import Inventory from "../src/pages/Inventory"
import "../src/index.css"

function Probe() {
  const scans = useScans()
  const admin = useAdmin()
  const inventory = useInventory()
  const [result, setResult] = useState("")
  const operations: Record<string, () => Promise<unknown>> = {
    flag: () => scans.flagScan("scan-0", true),
    note: () => scans.addScanNote("scan-0", "Review note"),
    override: () => scans.updateScanData("scan-0", { cultivar: "Cardaba" }),
    supplierAdd: () => inventory.addSupplier({ name: "New supplier", status: "Active" }),
    supplierUpdate: () => inventory.updateSupplier("supplier-1", { name: "Edited supplier" }),
    supplierStatus: () => inventory.updateSupplierStatus("supplier-1", "Inactive"),
    userAdd: () => admin.addUser({ username: "new", fullName: "New User", role: "Operator", status: "Active", lastActive: "Never" }),
    userUpdate: () => admin.updateUser("admin-1", { fullName: "Edited Admin" }),
    password: () => admin.resetPassword("admin-1"),
    pin: () => admin.resetPin("admin-1"),
    config: () => admin.updateConfig({ confidenceThreshold: 70 }),
    intake: () => inventory.startIntake("supplier-1", "new-batch"),
    bulk: () => inventory.bulkUpdateIntakeInventory("intake-1", "Sold"),
    refresh: () => scans.refreshScans(),
  }
  useEffect(() => {
    if (inventory.intakes[0] && !inventory.activeIntake) inventory.setActiveIntake(inventory.intakes[0])
  }, [inventory])
  async function perform(name: string) {
    setResult("pending")
    try { await operations[name](); setResult("success") }
    catch (error) { setResult(`error: ${error instanceof Error ? error.message : error}`) }
  }
  const screen = new URLSearchParams(location.search).get("screen")
  return <>
    <output data-testid="state" hidden>{JSON.stringify({
      scans: scans.scans, loading: scans.scansLoading, error: scans.scansError,
      notes: scans.getScanNotes("scan-0"), users: admin.users, config: admin.config,
      activity: admin.activityLogs, activityLoading: admin.activityLoading, activityError: admin.activityError,
      suppliers: inventory.suppliers, intakes: inventory.intakes, activeIntake: inventory.activeIntake,
    })}</output>
    {screen ? <main className="p-6">{screen === "quality" ? <QualityControl /> : <Inventory />}</main> : <>
      <output data-testid="operation-result">{result}</output>
      {Object.keys(operations).map(name => <button key={name} onClick={() => void perform(name)}>{name}</button>)}
    </>}
    <Toaster />
  </>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider><Probe /></InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
