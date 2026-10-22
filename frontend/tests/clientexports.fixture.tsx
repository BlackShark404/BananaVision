import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import ActivityLog from "../src/pages/admin/ActivityLog"
import DeliveryIntake from "../src/pages/admin/DeliveryIntake"
import QualityControl from "../src/pages/admin/QualityControl"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <main className="p-6"><Routes>
      <Route path="/dashboard/activity" element={<ActivityLog />} />
      <Route path="/dashboard/intakes" element={<DeliveryIntake />} />
      <Route path="/dashboard/quality" element={<QualityControl />} />
    </Routes></main><Toaster />
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
