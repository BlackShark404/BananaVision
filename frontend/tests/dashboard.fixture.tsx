import { createRoot } from "react-dom/client"
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom"
import Dashboard from "../src/pages/Dashboard"
import "./dashboard.auth"
import "../src/index.css"

function LocationDisplay() {
  const location = useLocation()
  return <output data-testid="route">{location.pathname}{location.search}</output>
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <LocationDisplay />
    <main className="p-4 md:p-6">
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<p>Destination reached</p>} />
      </Routes>
    </main>
  </BrowserRouter>,
)
