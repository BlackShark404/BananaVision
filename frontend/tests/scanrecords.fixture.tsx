import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import ScanDetail from "../src/pages/ScanDetail"
import Logs from "../src/pages/Logs"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <main className="p-6"><Routes>
      <Route path="/scans/:scanId" element={<ScanDetail />} />
      <Route path="/logs" element={<Logs />} />
    </Routes></main><Toaster />
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
