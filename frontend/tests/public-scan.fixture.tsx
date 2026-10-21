import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import PublicScanView from "../src/pages/PublicScanView"
import "../src/index.css"

// Reuse the isolated auth adapter; the public route must run without a signed-in user.
window.kioskAuthTest.setUser(null)
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><Routes>
    <Route path="/scans/:scanId/track" element={<PublicScanView />} />
  </Routes></BrowserRouter>,
)
