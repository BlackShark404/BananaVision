import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { AdminProvider } from "../src/context/AdminContext"
import { ScanProvider } from "../src/context/ScanContext"
import { InventoryProvider } from "../src/context/InventoryContext"
import DeviceStatus from "../src/pages/DeviceStatus"
import Kiosk from "../src/pages/Kiosk"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(<BrowserRouter><AdminProvider><ScanProvider><InventoryProvider>
  {location.pathname === "/devices" ? <DeviceStatus /> : <Kiosk />}
</InventoryProvider></ScanProvider></AdminProvider></BrowserRouter>)
