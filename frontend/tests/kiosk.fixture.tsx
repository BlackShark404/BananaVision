import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Toaster } from "sonner"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider, useScans } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import Kiosk from "../src/pages/Kiosk"
import "../src/index.css"

function StateProbe() {
  const { scans, scanState } = useScans()
  return <output hidden data-testid="persisted-scans">{JSON.stringify({ ids: scans.map(scan => scan.id), lastResult: scanState.lastResult?.id })}</output>
}

createRoot(document.getElementById("root")!).render(<StrictMode><BrowserRouter>
  <AdminProvider><ScanProvider><InventoryProvider>
    <StateProbe /><Kiosk /><Toaster />
  </InventoryProvider></ScanProvider></AdminProvider>
</BrowserRouter></StrictMode>)
