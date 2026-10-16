import { useEffect, useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { PrintJob } from "@/types/printing"

/** Polling only reads status. Initial submission belongs to the backend POST. */
export function KioskPrintStatus({ scanId, initialJob }: { scanId: string; initialJob: PrintJob }) {
  const [job, setJob] = useState(initialJob)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const inFlight = useRef(false)

  useEffect(() => {
    if (job.status !== "QUEUED") return
    let active = true
    let polls = 0
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const updated = await api.scans.printStatus(scanId, job.id)
        if (!active) return
        setJob(updated)
        if (updated.status !== "QUEUED") return
      } catch { /* Never resubmit on a failed status read. */ }
      if (!active) return
      if (++polls < 30) timer = setTimeout(poll, 1000)
      else setWaiting(true)
    }
    timer = setTimeout(poll, 500)
    return () => { active = false; clearTimeout(timer) }
  }, [scanId, job.id, job.status])

  const act = async (retry: boolean) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError("")
    setWaiting(false)
    try {
      setJob(retry ? await api.scans.retryPrint(scanId, job.id, job.attempt_count)
        : await api.scans.printStatus(scanId, job.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Print status unavailable")
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return <div className="rounded-xl border border-border bg-muted/30 p-3 space-y-2 text-xs" role="status">
    {job.status === "QUEUED" && <p>Label queued</p>}
    {job.status === "SUBMITTED" && <p>Sent to {job.printer_name}. Check the printed label.</p>}
    {job.status === "FAILED" && <>
      <p className="text-destructive">{job.error}</p>
      <p className="text-muted-foreground">Check for a partially printed label before retrying.</p>
      <Button variant="outline" size="sm" disabled={busy} onClick={() => act(true)}>{busy && <Loader2 className="w-4 h-4 animate-spin" />}RETRY PRINT</Button>
    </>}
    {waiting && job.status === "QUEUED" && <p>Submission is unconfirmed. Check the print queue.</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {(job.status === "QUEUED" || error) && <Button variant="outline" size="sm" disabled={busy}
      onClick={() => act(false)}>{busy && <Loader2 className="w-4 h-4 animate-spin" />}Refresh print status</Button>}
  </div>
}
