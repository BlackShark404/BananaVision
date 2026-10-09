import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import { useScans, ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import DeliveryIntake from "../src/pages/admin/DeliveryIntake"
import ScanDetail from "../src/pages/ScanDetail"
import Logs from "../src/pages/Logs"
import "../src/index.css"

function NoteProbe() {
  const scans = useScans()
  const id = '10000000-0000-4000-8000-000000000001'
  return <><button onClick={() => scans.loadScanNotes(id)}>Test reload notes</button>
    <output data-testid="notes-state" hidden>{JSON.stringify(scans.getScanNotes(id))}</output></>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <NoteProbe /><main className="p-6"><Routes>
      <Route path="/scans/intakes" element={<DeliveryIntake />} />
      <Route path="/scans/:scanId" element={<ScanDetail />} />
      <Route path="/logs" element={<Logs />} />
    </Routes></main><Toaster />
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
