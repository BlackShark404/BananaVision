import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import ActivityLog from "../src/pages/admin/ActivityLog"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AdminProvider>
    <main className="p-6"><Routes>
      <Route path="/dashboard/activity" element={<ActivityLog />} />
    </Routes></main><Toaster />
  </AdminProvider></BrowserRouter>,
)
