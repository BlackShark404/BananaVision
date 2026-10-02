import { useEffect, useState } from "react"
import { ArrowRight, ChevronLeft, ChevronRight, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { DashboardScanPage, DashboardScanParams, DashboardSummary, DashboardView } from "@/types/dashboard"

interface DashboardRecordsProps {
  summary: DashboardSummary | null
  view: string | null
  onClose: () => void
  onSelectView: (view: string, filters?: { source_key?: string; operator_id?: string }) => void
  sourceKey?: string
  operatorId?: string
  businessDate?: string
  revision?: number
}

const TITLES: Record<DashboardView, string> = {
  today: "Today's scans",
  confidence: "Confidence by scan",
  sources: "Delivery sources",
  operators: "Active operators",
  all: "All scan records",
  review: "Scans awaiting review",
  expiring: "Stock expiring soon",
}
const PAGE_SIZE = 15
const REQUEST_TIMEOUT_MS = 15_000
const TIMEOUT_MESSAGE = "Loading took too long. Check your connection and try again."

function LoadingRecords() {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
      <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading records…
    </div>
  )
}

function RecordError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-5">
      <p className="font-medium">Records could not be loaded</p>
      <p className="text-sm text-muted-foreground">{message}</p>
      <Button variant="outline" onClick={onRetry}>Retry</Button>
    </div>
  )
}

function GroupRecords({ summary, view, onSelectView, revision = 0 }: Pick<DashboardRecordsProps, "summary" | "onSelectView" | "revision"> & { view: "sources" | "operators" }) {
  const [retry, setRetry] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; data: DashboardSummary | null; error: string | null } | null>(null)
  const key = `${revision}:${retry}`

  useEffect(() => {
    if (summary) return
    const controller = new AbortController()
    let cancelled = false
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      if (!cancelled) setLoaded({ key, data: null, error: TIMEOUT_MESSAGE })
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
    api.dashboard.summary(controller.signal).then(data => {
      if (!cancelled && !timedOut) setLoaded({ key, data, error: null })
    }).catch((error: unknown) => {
      if (!cancelled) setLoaded({ key, data: null, error: timedOut ? TIMEOUT_MESSAGE : error instanceof Error ? error.message : "Check your connection and try again." })
    }).finally(() => window.clearTimeout(timeout))
    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort() }
  }, [summary, key])

  const current = loaded?.key === key ? loaded : null
  const data = summary ?? current?.data
  if (!data) return current?.error ? <RecordError message={current.error} onRetry={() => setRetry(value => value + 1)} /> : <LoadingRecords />

  const groups = view === "sources" ? data.sources : data.operators
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{data.business_date} · Select a row to see its scans.</p>
      {groups.length === 0 ? <p className="py-10 text-center text-muted-foreground">No {view === "sources" ? "delivery sources" : "operators"} recorded.</p> : (
        <ul className="divide-y rounded-lg border">
          {view === "sources" ? data.sources.map(source => (
            <li key={source.key}>
              <button type="button" onClick={() => onSelectView("all", { source_key: source.key })} className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2">
                <span className="min-w-0 flex-1 break-words font-medium">{source.name}</span>
                <span className="shrink-0 text-sm text-muted-foreground">{source.count} {source.count === 1 ? "scan" : "scans"}</span>
                <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
              </button>
            </li>
          )) : data.operators.map(operator => (
            <li key={operator.operator_id}>
              <button type="button" onClick={() => onSelectView("all", { operator_id: operator.operator_id })} className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2">
                <span className="min-w-0 flex-1"><span className="block break-words font-medium">{operator.name}</span><span className="block text-xs text-muted-foreground">@{operator.username}</span></span>
                <span className="shrink-0 text-right text-sm text-muted-foreground"><span className="block">{operator.scan_count} {operator.scan_count === 1 ? "scan" : "scans"}</span><span className="block text-xs">{operator.avg_confidence == null ? "Confidence unavailable" : `${operator.avg_confidence.toFixed(1)}% average confidence`}</span></span>
                <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ScanRecords({ view, sourceKey, operatorId, businessDate, revision = 0 }: Pick<DashboardRecordsProps, "sourceKey" | "operatorId" | "businessDate" | "revision"> & { view: Exclude<DashboardView, "sources" | "operators"> }) {
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; data: DashboardScanPage | null; error: string | null } | null>(null)
  const key = JSON.stringify([view, sourceKey, operatorId, businessDate, page, revision, retry])

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      if (!cancelled) setLoaded({ key, data: null, error: TIMEOUT_MESSAGE })
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
    const params: DashboardScanParams = {
      view: view === "confidence" ? "today" : view,
      sort: view === "confidence" ? "confidence" : "date",
      page,
      page_size: PAGE_SIZE,
      business_date: businessDate,
      source_key: sourceKey,
      operator_id: operatorId,
    }
    api.dashboard.scans(params, controller.signal).then(data => {
      if (cancelled || timedOut) return
      const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
      if (page > lastPage) { setPage(lastPage); return }
      setLoaded({ key, data, error: null })
    }).catch((error: unknown) => {
      if (!cancelled) setLoaded({ key, data: null, error: timedOut ? TIMEOUT_MESSAGE : error instanceof Error ? error.message : "Check your connection and try again." })
    }).finally(() => window.clearTimeout(timeout))
    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort() }
  }, [key, view, sourceKey, operatorId, businessDate, page])

  const current = loaded?.key === key ? loaded : null
  if (!current) return <LoadingRecords />
  if (current.error) return <RecordError message={current.error} onRetry={() => setRetry(value => value + 1)} />
  if (!current.data) return <LoadingRecords />
  const data = current.data
  const pageCount = Math.max(1, Math.ceil(data.total / PAGE_SIZE))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
        <p>{data.total.toLocaleString()} matching {data.total === 1 ? "scan" : "scans"}{view === "today" || view === "confidence" ? ` · ${data.business_date}` : ""}</p>
        <p>Updated {new Date(data.generated_at).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila", hour: "2-digit", minute: "2-digit" })}</p>
      </div>
      {data.items.length === 0 ? <p className="py-10 text-center text-muted-foreground">No scans match this view.</p> : (
        <Table>
          <TableHeader><TableRow><TableHead>Scan / time</TableHead><TableHead>Classification</TableHead><TableHead>Confidence</TableHead><TableHead>Source / operator</TableHead><TableHead>Inventory / estimate</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map(scan => (
            <TableRow key={scan.id}>
              <TableCell className="max-w-52 whitespace-normal"><span className="break-all font-mono text-xs">{scan.id}</span><span className="mt-1 block text-xs text-muted-foreground">{new Date(scan.date_time).toLocaleString("en-PH", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span></TableCell>
              <TableCell>{scan.cultivar ?? "Unclassified"}<span className="block text-xs text-muted-foreground">{scan.ripeness ?? "Ripeness unavailable"}</span></TableCell>
              <TableCell>{scan.confidence == null ? "Unavailable" : `${scan.confidence.toFixed(1)}%`}{scan.flagged && <Badge variant="outline" className="mt-1 block w-fit">Flagged</Badge>}</TableCell>
              <TableCell className="max-w-52 whitespace-normal break-words">{scan.source_name}<span className="block text-xs text-muted-foreground">{scan.operator_name}</span></TableCell>
              <TableCell><span className="block">{scan.inventory_status ?? "Status unavailable"}</span><span className="mt-1 block text-xs text-muted-foreground">{scan.remaining_days == null ? "Estimate unavailable" : scan.remaining_days <= 0 ? "Estimated expiry reached" : `${scan.remaining_days.toFixed(1)} days remaining`}</span></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      )}
      <nav aria-label="Scan results pages" className="flex items-center justify-between gap-3 border-t pt-3">
        <Button variant="outline" onClick={() => setPage(value => value - 1)} disabled={page <= 1}><ChevronLeft aria-hidden="true" /> Previous</Button>
        <span className="text-sm text-muted-foreground" aria-live="polite">Page {page} of {pageCount}</span>
        <Button variant="outline" onClick={() => setPage(value => value + 1)} disabled={page >= pageCount}>Next <ChevronRight aria-hidden="true" /></Button>
      </nav>
    </div>
  )
}

export function DashboardRecords({ summary, view, onClose, onSelectView, sourceKey, operatorId, businessDate, revision }: DashboardRecordsProps) {
  const validView = view && Object.hasOwn(TITLES, view) ? view as DashboardView : null
  const groupedView = validView === "sources" || validView === "operators"
  const title = groupedView && summary ? `${validView === "sources" ? "Delivery sources" : "Active operators"} for ${summary.business_date}` : validView === "today" && businessDate ? `Scans for ${businessDate}` : validView ? TITLES[validView] : "Dashboard records"
  const filterName = !groupedView ? sourceKey ? summary?.sources.find(source => source.key === sourceKey)?.name : operatorId ? summary?.operators.find(operator => operator.operator_id === operatorId)?.name : undefined : undefined
  const description = validView === "review" ? "Flagged scans and scans below the configured confidence threshold, across all dates."
    : validView === "expiring" ? "In-stock scans with an estimated two days or less remaining, including estimates already reached."
      : validView === "all" ? "Browse the complete scan history."
        : groupedView ? summary ? `Records for ${summary.business_date}.` : "Records for the current business date."
          : validView === "confidence" ? "Scans for the selected business date, ordered by confidence."
            : "Records for the selected business date."

  return (
    <Dialog open={validView !== null} onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-5xl">
        <DialogHeader className="shrink-0 pr-8"><DialogTitle>{title}</DialogTitle><DialogDescription>{description}{filterName ? ` Filtered to ${filterName}.` : !groupedView && (sourceKey || operatorId) ? " A source or operator filter is applied." : ""}</DialogDescription></DialogHeader>
        <div className="min-h-0 overflow-y-auto">
          {validView === "sources" || validView === "operators" ? <GroupRecords summary={summary} view={validView} onSelectView={onSelectView} revision={revision} /> : validView ? <ScanRecords key={JSON.stringify([validView, sourceKey, operatorId, businessDate])} view={validView} sourceKey={sourceKey} operatorId={operatorId} businessDate={businessDate} revision={revision} /> : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}
