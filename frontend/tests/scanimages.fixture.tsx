import { useState } from "react"
import { createRoot } from "react-dom/client"
import { ScanImage } from "../src/components/ScanImage"
import { clearToken } from "../src/lib/auth"
import "../src/index.css"

function Offscreen() {
  return <>
    <div style={{ height: 2200 }} />
    <div id="deferred">
      <ScanImage src="/captures/offscreen/camera.jpg?variant=thumb" alt="Deferred evidence" defer className="w-14 h-14" />
    </div>
  </>
}

function Cached() {
  const [shown, setShown] = useState(true)
  return <>
    <button onClick={() => setShown(value => !value)}>Toggle image</button>
    <button onClick={() => clearToken()}>Clear session</button>
    {shown && <ScanImage src="/captures/cached/camera.jpg?variant=thumb" alt="Cached evidence" className="w-14 h-14" />}
  </>
}

const mode = new URLSearchParams(window.location.search).get("mode")

createRoot(document.getElementById("root")!).render(mode === "offscreen" ? <Offscreen /> : <Cached />)
