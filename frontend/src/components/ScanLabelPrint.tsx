import { useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"
import QRCode from "qrcode"
import { Printer } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import type { LabelPreview, PrintJob } from "@/types/printing"

export function ScanLabelPrint({ scanId, children }: { scanId: string; children?: ReactNode }) {
  const [preview, setPreview] = useState<LabelPreview | null>(null)
  const [qr, setQr] = useState("")
  const [quantity, setQuantity] = useState("1")
  const [job, setJob] = useState<PrintJob | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [pollingStopped, setPollingStopped] = useState(false)
  const inFlight = useRef(false)
  // Retain a request identity after a network error: retrying cannot print twice.
  const pending = useRef<{ request_id: string; quantity: number } | null>(null)

  useEffect(() => {
    let active = true
    api.scans.label(scanId).then(async data => {
      const image = await QRCode.toDataURL(data.payload, { margin: 4, errorCorrectionLevel: "M", width: 256 })
      if (active) { setPreview(data); setQr(image) }
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Label preview unavailable") })
    return () => { active = false }
  }, [scanId])

  useEffect(() => {
    if (job?.status !== "QUEUED") return
    let active = true
    let count = 0
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const result = await api.scans.printStatus(scanId, job.id)
        if (!active) return
        setJob(result)
        if (result.status !== "QUEUED") return
      } catch { /* A read failure must never resubmit a label. */ }
      if (!active) return
      if (++count < 30) timer = setTimeout(poll, 1000)
      else setPollingStopped(true)
    }
    timer = setTimeout(poll, 500)
    return () => { active = false; clearTimeout(timer) }
  }, [scanId, job?.id, job?.status])

  const submit = async () => {
    if (inFlight.current) return
    const copies = Number(quantity)
    if (!pending.current && (!Number.isInteger(copies) || copies < 1 || copies > 10)) {
      setError("Choose between 1 and 10 labels.")
      return
    }
    inFlight.current = true
    setBusy(true)
    setError("")
    setPollingStopped(false)
    try {
      if (job?.status === "FAILED") {
        setJob(await api.scans.retryPrint(scanId, job.id, job.attempt_count))
      } else {
        pending.current ??= { request_id: crypto.randomUUID(), quantity: copies }
        setJob(await api.scans.print(scanId, pending.current))
        pending.current = null
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit labels")
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const refresh = async () => {
    if (!job) return
    try { setJob(await api.scans.printStatus(scanId, job.id)); setError("") }
    catch (err) { setError(err instanceof Error ? err.message : "Status unavailable") }
  }

  return <div className="space-y-3">
    {qr && <div className="bg-white rounded-xl p-4 border">
      <img src={qr} alt="Prediction QR label" className="w-full h-auto" />
    </div>}
    {children}
    {preview && <p className="text-xs text-muted-foreground">
      {preview.width_mm} × {preview.height_mm} mm · {preview.printer_name}<br />
      Saved prediction · {preview.panel[2]} · {preview.panel[3]} · {preview.panel[4]}
    </p>}
    <div className="flex items-center justify-between gap-3">
      <Label htmlFor="label-quantity">Labels (1–10)</Label>
      <Input id="label-quantity" type="number" min={1} max={10} step={1}
        value={quantity} onChange={event => setQuantity(event.target.value)}
        disabled={busy || !!pending.current || (!!job && job.status !== "SUBMITTED")}
        className="w-20" />
    </div>
    <div role="status" className="text-xs">
      {job?.status === "QUEUED" && "Label queued"}
      {job?.status === "SUBMITTED" && `${job.quantity} label(s) sent to ${job.printer_name}. Submission confirmed; check the printed labels.`}
      {job?.status === "FAILED" && <p className="text-destructive">{job.error}</p>}
      {pollingStopped && job?.status === "QUEUED" && <p>Submission is still unconfirmed. Check the print queue before creating another batch.</p>}
    </div>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {error && job && job.status !== "QUEUED" && <Button variant="outline" className="w-full" onClick={refresh}>Refresh print status</Button>}
    {job?.status === "FAILED" && <p className="text-xs text-muted-foreground">Check for partially printed labels before retrying the full batch of {job.quantity}.</p>}
    {job?.status === "QUEUED" ? <Button variant="outline" className="w-full" onClick={refresh}>Refresh print status</Button>
      : <Button variant="outline" className="w-full gap-2" onClick={submit} disabled={busy || !preview}>
        <Printer className="w-4 h-4" />
        {busy ? "Submitting…" : job?.status === "FAILED" ? "RETRY PRINT" : pending.current ? "Check / retry request" : job?.status === "SUBMITTED" ? "Print another batch" : "Print labels"}
      </Button>}
  </div>
}
