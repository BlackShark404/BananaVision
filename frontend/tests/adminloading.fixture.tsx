import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route, Link } from "react-router-dom"
import { AdminProvider, useAdmin } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider, useInventory } from "../src/context/InventoryContext"
import UserManagement from "../src/pages/admin/UserManagement"
import SupplierManagement from "../src/pages/admin/SupplierManagement"
import DeliveryIntake from "../src/pages/admin/DeliveryIntake"
import ActivityLog from "../src/pages/admin/ActivityLog"
import "../src/index.css"

function WriteProbe() {
  const admin = useAdmin(), inventory = useInventory()
  return <><button onClick={() => void admin.updateUser("fixture", { fullName: "Saved User" })}>Write user</button>
    <button onClick={() => void inventory.updateSupplier("fixture", { name: "Saved Supplier" })}>Write supplier</button>
    <output data-testid="provider-state">{JSON.stringify({ users: admin.users, suppliers: inventory.suppliers, usersLoading: admin.usersLoading, suppliersLoading: inventory.suppliersLoading, intakesLoading: inventory.intakesLoading })}</output></>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
    <WriteProbe /><Link to="/dashboard/intakes">Intakes page</Link><Link to="/dashboard/users">Users page</Link><Link to="/dashboard/suppliers">Suppliers page</Link>
    <Link to="/dashboard/activity">Activity page</Link>
    <Routes>
      <Route path="/dashboard/intakes" element={<DeliveryIntake />} />
      <Route path="/dashboard/users" element={<UserManagement />} />
      <Route path="/dashboard/suppliers" element={<SupplierManagement />} />
      <Route path="/dashboard/activity" element={<ActivityLog />} />
    </Routes>
  </InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>,
)
