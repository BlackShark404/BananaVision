import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "../src/App"
import "../src/index.css"

// The whole app as shipped (real routes, providers and auth), as main.tsx renders it.
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>)
