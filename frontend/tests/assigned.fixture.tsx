import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Toaster } from "sonner"
import { useState } from "react"
import { AuthProvider, useAuth } from "./assigned.auth"
import { AdminProvider, useAdmin } from "../src/context/AdminContext"
import { useWebSocket } from "../src/hooks/useWebSocket"
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

function ScopeProbe() {
  const auth = useAuth(), admin = useAdmin()
  const [count, setCount] = useState(0)
  const [result, setResult] = useState("")
  return <>
    <output data-testid="scope-state">{JSON.stringify({ users: admin.users, role: auth.user?.role, count, result })}</output>
    <button onClick={() => setCount(value => value + 1)}>Keep child state</button>
    <button onClick={() => auth.updateAuthUser({ role: "Operator" })}>Become operator</button>
    <button onClick={async () => {
      setResult("pending")
      try {
        await admin.addUser({ username: "late-owner", fullName: "Late private owner", role: "Operator", status: "Active", lastActive: "Never" })
        setResult("complete")
      } catch { setResult("failed") }
    }}>Create pending user</button>
    <button onClick={async () => {
      setResult("pending")
      try { await admin.updateOwnProfile({ avatar: "private-avatar.png" }); setResult("complete") }
      catch { setResult("failed") }
    }}>Update pending profile</button>
  </>
}

function SocketProbe() {
  const { status } = useWebSocket({ rooms: ["kiosk"] })
  return <output data-testid="socket-state">{status}</output>
}

const screen = new URLSearchParams(location.search).get("screen")
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><AuthProvider><AdminProvider><ThemeProvider>
    <main className="p-6">{screen === "profile" ? <Profile /> : screen === "config" ? <SystemConfig /> : screen === "auth" ? <SetupProbe /> : screen === "scope" ? <ScopeProbe /> : screen === "socket" ? <SocketProbe /> : <UserManagement />}</main>
    <Toaster />
  </ThemeProvider></AdminProvider></AuthProvider></BrowserRouter>,
)
