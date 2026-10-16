import { Skeleton } from "@/components/ui/skeleton"

/** Placeholders occupy the existing content area; loaded pages keep their own layout. */
export function TableSkeleton({ columns = 4, rows = 5, label = "Loading records…" }: { columns?: number; rows?: number; label?: string }) {
  return <div role="status" aria-label={label} className="rounded-xl sm:rounded-2xl border bg-card overflow-hidden">
    <span className="sr-only">{label}</span>
    <div aria-hidden="true" className="divide-y">
      {Array.from({ length: rows + 1 }, (_, row) => <div key={row} className={`flex gap-4 p-4 ${row === 0 ? "bg-muted/30" : ""}`}>
        {Array.from({ length: columns }, (_, col) => <Skeleton key={col} className="h-5 flex-1" />)}
      </div>)}
    </div>
  </div>
}

export function ContentSkeleton({ label = "Loading content…", cards = 4, chart = false }: { label?: string; cards?: number; chart?: boolean }) {
  return <div role="status" aria-label={label} className="space-y-4 sm:space-y-6">
    <span className="sr-only">{label}</span>
    <div aria-hidden="true" className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      {Array.from({ length: cards }, (_, index) => <div key={index} className="rounded-2xl border border-border/40 bg-card p-5 sm:p-6 space-y-3">
        <Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-24" /><Skeleton className="h-4 w-3/4" />
      </div>)}
    </div>
    {chart ? <div aria-hidden="true" className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
      {[0, 1].map(index => <div key={index} className="rounded-xl sm:rounded-2xl border bg-card p-4 sm:p-6 space-y-4"><Skeleton className="h-6 w-40" /><Skeleton className="h-[240px] sm:h-[280px] w-full" /></div>)}
    </div> : <TableSkeleton label={label} />}
  </div>
}

export function DetailSkeleton() {
  return <div role="status" aria-label="Loading scan…" className="space-y-4 sm:space-y-6">
    <span className="sr-only">Loading scan…</span>
    <div aria-hidden="true" className="space-y-4 sm:space-y-6">
      <Skeleton className="h-9 w-48" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className="lg:col-span-2 space-y-4"><Skeleton className="aspect-video w-full rounded-xl" /><Skeleton className="h-24 w-full" /></div>
        <div className="rounded-xl border bg-card p-4 sm:p-6 space-y-6">{Array.from({ length: 6 }, (_, index) => <div key={index} className="space-y-2"><Skeleton className="h-4 w-24" /><Skeleton className="h-7 w-3/4" /></div>)}</div>
      </div>
    </div>
  </div>
}
