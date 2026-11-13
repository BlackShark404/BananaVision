import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router-dom"
// Loads the isolated auth adapter (kiosk.auth.tsx via the test alias); the page itself
// no longer reads the signed-in user.
import "@/context/AuthContext"
import type { AuthUser } from "../src/lib/auth"
import Landing from "../src/pages/Landing"
import PublicScanView from "../src/pages/PublicScanView"
import "../src/index.css"

// Reuse the isolated auth adapter. Nobody is signed in unless a test sets
// window.publicScanViewer before the page loads (a staff member scanning a QR code).
declare global { interface Window { publicScanViewer?: AuthUser | null } }
window.kioskAuthTest.setUser(window.publicScanViewer ?? null)
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><Routes>
    <Route path="/scans/:scanId/track" element={<PublicScanView />} />
    {/* Test-only path for the normal public landing page, which keeps its login buttons. */}
    <Route path="/scans/landing-check" element={<Landing />} />
  </Routes></BrowserRouter>,
)
