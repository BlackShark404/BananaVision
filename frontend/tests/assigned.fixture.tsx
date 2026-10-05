import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Toaster } from "sonner"
import { useState } from "react"
import { AuthProvider, useAuth } from "./assigned.auth"
import { AdminProvider } from "../src/context/AdminContext"
import { ThemeProvider } from "../src/components/theme-provider"
import Profile from "../src/pages/Profile"
import UserManagement from "../src/pages/admin/UserManagement"
import SystemConfig from "../src/pages/admin/SystemConfig"
import "../src/index.css"

function SetupProbe() {
  const auth = useAuth()
  const [status, setStatus] = useState("")
  return <>
    <output>{status}</output>
    <button onClick={async () => setStatus(await auth.login("owner", "temporary-password"))}>Authenticate password</button>
    <button onClick={async () => setStatus(String(await auth.setupPasswordAndLogin("owner", "replacement-password")))}>Set password</button>
    <button onClick={async () => setStatus(await auth.switchOperator("owner", "1357"))}>Authenticate PIN</button>
    <button onClick={async () => setStatus(String(await auth.setupPinAndLogin("owner", "2468")))}>Set PIN</button>
  </>
}

const screen = new URLSearchParams(location.search).get("screen")
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AuthProvider><AdminProvider><ThemeProvider>
    <main className="p-6">{screen === "profile" ? <Profile /> : screen === "config" ? <SystemConfig /> : screen === "auth" ? <SetupProbe /> : <UserManagement />}</main>
    <Toaster />
  </ThemeProvider></AdminProvider></AuthProvider></BrowserRouter>,
)
