import { useEffect, useState } from "react"
import { ArrowRight, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { DashboardSummary, DashboardView } from "@/types/dashboard"

interface DashboardRecordsProps {
  summary: DashboardSummary | null
  view: string | null
  onClose: () => void
  onSelectView: (view: string, filters?: { source_key?: string; operator_id?: string; business_date?: string }) => void
  businessDate?: string
  revision?: number
}

const REQUEST_TIMEOUT_MS = 15_000
const TIMEOUT_MESSAGE = "Loading took too long. Check your connection and try again."

function GroupRecords({ summary, view, onClose, onSelectView, businessDate, revision = 0 }: Omit<DashboardRecordsProps, "view"> & { view: DashboardView }) {
  // Keep the selected day even if the live dashboard crosses midnight.
  const [selectedDate] = useState(() => businessDate ?? summary?.business_date ?? new Date(Date.now() + 28_800_000).toISOString().slice(0, 10))
  const [retry, setRetry] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; data: DashboardSummary | null; error: string | null } | null>(null)
  const key = `${selectedDate}:${revision}:${retry}`
  const suppliedSummary = summary?.business_date === selectedDate ? summary : null

  useEffect(() => {
    if (suppliedSummary) return
    const controller = new AbortController()
    let cancelled = false
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      if (!cancelled) setLoaded({ key, data: null, error: TIMEOUT_MESSAGE })
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
    api.dashboard.summary(controller.signal, selectedDate).then(data => {
      if (cancelled || timedOut) return
      if (data.business_date !== selectedDate) {
        setLoaded({ key, data: null, error: "The selected day's records could not be loaded. Please retry." })
        return
      }
      setLoaded({ key, data, error: null })
    }).catch((error: unknown) => {
      if (!cancelled) setLoaded({ key, data: null, error: timedOut ? TIMEOUT_MESSAGE : error instanceof Error ? error.message : "Check your connection and try again." })
    }).finally(() => window.clearTimeout(timeout))
    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort() }
  }, [suppliedSummary, key, selectedDate])

  const current = loaded?.key === key ? loaded : null
  const data = suppliedSummary ?? current?.data
  const groups = data ? view === "sources" ? data.sources : data.operators : null

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-5xl">
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle>{view === "sources" ? "Delivery sources" : "Active operators"} for {selectedDate}</DialogTitle>
          <DialogDescription>Select a row to see its scans.</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto">
          {!data ? current?.error ? (
            <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-5">
              <p className="font-medium">Records could not be loaded</p>
              <p className="text-sm text-muted-foreground">{current.error}</p>
              <Button variant="outline" onClick={() => setRetry(value => value + 1)}>Retry</Button>
            </div>
          ) : (
            <div role="status" className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading records…
            </div>
          ) : groups?.length === 0 ? (
            <p className="py-10 text-center text-muted-foreground">No {view === "sources" ? "delivery sources" : "operators"} recorded.</p>
          ) : (
            <ul className="divide-y rounded-lg border">
              {view === "sources" ? data.sources.map(source => (
                <li key={source.key}>
                  <button type="button" onClick={() => onSelectView("all", { source_key: source.key, business_date: selectedDate })} className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2">
                    <span className="min-w-0 flex-1 break-words font-medium">{source.name}</span>
                    <span className="shrink-0 text-sm text-muted-foreground">{source.count} {source.count === 1 ? "scan" : "scans"}</span>
                    <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
                  </button>
                </li>
              )) : data.operators.map(operator => (
                <li key={operator.operator_id}>
                  <button type="button" onClick={() => onSelectView("all", { operator_id: operator.operator_id, business_date: selectedDate })} className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2">
                    <span className="min-w-0 flex-1"><span className="block break-words font-medium">{operator.name}</span><span className="block text-xs text-muted-foreground">@{operator.username}</span></span>
                    <span className="shrink-0 text-right text-sm text-muted-foreground"><span className="block">{operator.scan_count} {operator.scan_count === 1 ? "scan" : "scans"}</span><span className="block text-xs">{operator.avg_confidence == null ? "Confidence unavailable" : `${operator.avg_confidence.toFixed(1)}% average confidence`}</span></span>
                    <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function DashboardRecords(props: DashboardRecordsProps) {
  if (props.view !== "sources" && props.view !== "operators") return null
  return <GroupRecords key={`${props.view}:${props.businessDate ?? "current"}`} {...props} view={props.view} />
}
