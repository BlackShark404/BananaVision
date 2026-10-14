import { useState } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"
import { AuthProvider, useAuth } from "../src/context/AuthContext"
import { api } from "../src/lib/api"
import KioskOperatorSwap from "../src/components/KioskOperatorSwap"
import "../src/index.css"

function PinFixture() {
  const { user, login } = useAuth()
  const [open, setOpen] = useState(true)
  const [swapped, setSwapped] = useState("")
  const [loginResult, setLoginResult] = useState("")
  return <>
    <output data-testid="auth-state">{JSON.stringify({ user, swapped, loginResult })}</output>
    <button onClick={async () => setLoginResult(await login("fixture", "fixture-password"))}>Submit password</button>
    <button onClick={() => { api.auth.changePin("1111", "2222").catch(() => {}) }}>Check protected request</button>
    <KioskOperatorSwap
      open={open}
      onOpenChange={setOpen}
      currentOperatorId={null}
      operators={[{ id: "operator-1", username: "fixture", fullName: "Fixture Operator", role: "Operator", status: "Active" }]}
      onSwapSuccess={setSwapped}
    />
    <Toaster />
  </>
}

createRoot(document.getElementById("root")!).render(<AuthProvider><PinFixture /></AuthProvider>)
