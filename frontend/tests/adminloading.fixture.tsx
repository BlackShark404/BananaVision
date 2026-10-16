import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route, Link } from "react-router-dom"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import UserManagement from "../src/pages/admin/UserManagement"
import SupplierManagement from "../src/pages/admin/SupplierManagement"
import ActivityLog from "../src/pages/admin/ActivityLog"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <Link to="/dashboard/users">Users page</Link><Link to="/dashboard/suppliers">Suppliers page</Link>
    <Link to="/dashboard/activity">Activity page</Link>
    <Routes>
      <Route path="/dashboard/users" element={<UserManagement />} />
      <Route path="/dashboard/suppliers" element={<SupplierManagement />} />
      <Route path="/dashboard/activity" element={<ActivityLog />} />
    </Routes>
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
