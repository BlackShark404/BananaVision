import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { ScanLabelPrint } from "../src/components/ScanLabelPrint"
import "../src/index.css"

createRoot(document.getElementById("root")!).render(<StrictMode>
  <div className="p-6 max-w-xs"><ScanLabelPrint scanId="saved-scan" /></div>
</StrictMode>)
