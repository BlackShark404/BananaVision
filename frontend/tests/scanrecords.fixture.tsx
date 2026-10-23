import { AppChangePreview } from "../src/components/AppChangePreview"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route, Link } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import { useScans, ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import DeliveryIntake from "../src/pages/admin/DeliveryIntake"
import ScanDetail from "../src/pages/ScanDetail"
import Logs from "../src/pages/Logs"
import QualityControl from "../src/pages/admin/QualityControl"
import "../src/index.css"

function NoteProbe() {
  const scans = useScans()
  const id = '10000000-0000-4000-8000-000000000001'
  return <><button onClick={() => scans.loadScanNotes(id)}>Test reload notes</button>
    <button onClick={() => scans.acceptScan({ id, revision: 3, inventory_status: 'Spoiled', date_time: '2024-05-05T08:10:00+08:00', cultivar: null, ripeness: null, confidence: null, spoilage_days: null, finger_count: 0 })}>Test newer scan</button>
    <button onClick={() => scans.updateScansForIntake([id], 'Sold', '2024-05-05T08:10:00+08:00', { [id]: 2 })}>Test older bulk</button>
    <output data-testid="scans-state" hidden>{JSON.stringify(scans.scans)}</output>
    <button onClick={() => scans.startScan('Fixture')}>Test start scan</button>
    <output data-testid="last-result" hidden>{JSON.stringify(scans.scanState.lastResult)}</output>
    <div data-testid="unknown-preview"><AppChangePreview originalData={{}} editData={{ spoilageDays: '3' }} /></div>
    <div data-testid="range-preview"><AppChangePreview originalData={{ spoilageDays: '4-6' }} editData={{ spoilageDays: '3' }} /></div>
    <output data-testid="notes-state" hidden>{JSON.stringify(scans.getScanNotes(id))}</output></>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <Link to="/logs">Test logs link</Link><Link to="/scans/10000000-0000-4000-8000-000000000001">Test detail link</Link><NoteProbe /><main className="p-6"><Routes>
      <Route path="/scans/intakes" element={<DeliveryIntake />} />
      <Route path="/scans/quality" element={<QualityControl />} />
      <Route path="/scans/:scanId" element={<ScanDetail />} />
      <Route path="/logs" element={<Logs />} />
    </Routes></main><Toaster />
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
