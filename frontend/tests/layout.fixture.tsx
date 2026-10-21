import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import AppLayout from "../src/layouts/AppLayout"
import Logs from "../src/pages/Logs"
import SystemConfig from "../src/pages/admin/SystemConfig"
import ActivityLog from "../src/pages/admin/ActivityLog"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <Routes><Route element={<AppLayout />}>
      <Route path="/logs" element={<Logs />} />
      <Route path="/dashboard/config" element={<SystemConfig />} />
      <Route path="/dashboard/activity" element={<ActivityLog />} />
    </Route></Routes>
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
