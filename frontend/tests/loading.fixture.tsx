import { useState } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { AppNotifications } from "../src/components/AppNotifications"
import { api } from "../src/lib/api"
import "../src/index.css"

function Fixture() {
  const [message, setMessage] = useState("")
  return <BrowserRouter><AppNotifications />
    <button onClick={() => { setMessage("Pending"); void api.scans.detail("deadline").then(() => setMessage("Loaded"), error => setMessage(error.message)) }}>Read data</button>
    <p data-testid="message">{message}</p>
  </BrowserRouter>
}
createRoot(document.getElementById("root")!).render(<Fixture />)
