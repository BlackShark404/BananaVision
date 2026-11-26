import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NumberField } from "@/components/ui/number-field"
import { Progress } from "@/components/ui/progress"
import { useAuth } from "@/context/AuthContext"
import { useInventory } from "@/context/InventoryContext"
import { CULTIVARS, type Cultivar, type DailyIntake } from "@/types"
import type { ScanResult } from "@/types"
import { verifySupplier, type IntakeVerification, type ScanVerificationStatus } from "@/lib/supplierVerification"
import { CheckCircle2, ClipboardCheck, Loader2, Package, Pencil, Truck, X } from "lucide-react"

const VERDICT_STYLES: Record<ScanVerificationStatus, { badge: string; dot: string; text: string }> = {
  Complete: {
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500", text: "text-emerald-700",
  },
  Partial: {
    badge: "bg-yellow-50 text-yellow-700 border-yellow-200",
    dot: "bg-yellow-500", text: "text-yellow-700",
  },
  Incomplete: {
    badge: "bg-red-50 text-red-700 border-red-200",
    dot: "bg-red-500", text: "text-red-700",
  },
  Discrepancy: {
    badge: "bg-orange-50 text-orange-700 border-orange-200",
    dot: "bg-orange-500", text: "text-orange-700",
  },
  "Not recorded": {
    badge: "bg-muted text-muted-foreground border-border",
    dot: "bg-muted-foreground", text: "text-muted-foreground",
  },
}

export function VerdictBadge({ verdict }: { verdict: ScanVerificationStatus }) {
  const style = VERDICT_STYLES[verdict]
  return (
    <Badge variant="outline" className={`gap-1.5 ${style.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {verdict}
    </Badge>
  )
}

function fmtDate(value: string) {
  const date = new Date(value)
  return Number.isFinite(date.getTime())
    ? date.toLocaleDateString("en-US", { timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric" })
    : value
}

function ExpectedEditor({ intake, onSaved }: { intake: IntakeVerification; onSaved: () => void }) {
  const { setIntakeExpectedStock } = useInventory()
  const [values, setValues] = useState<Record<Cultivar, string>>(() => {
    const current = Object.fromEntries(intake.expected.map(line => [line.cultivar, String(line.expectedBunches)]))
    return Object.fromEntries(CULTIVARS.map(cultivar => [cultivar, current[cultivar] ?? ""])) as Record<Cultivar, string>
  })
  const [saving, setSaving] = useState(false)
  const invalid = CULTIVARS.some(cultivar => {
    const raw = values[cultivar].trim()
    return raw !== "" && (!/^\d+$/.test(raw) || Number(raw) < 1)
  })
  const total = CULTIVARS.reduce((sum, cultivar) => {
    const raw = values[cultivar].trim()
    return sum + (/^\d+$/.test(raw) ? Number(raw) : 0)
  }, 0)
  const save = async () => {
    if (invalid || saving) return
    setSaving(true)
    try {
      await setIntakeExpectedStock(intake.id, CULTIVARS.flatMap(cultivar => {
        const raw = values[cultivar].trim()
        return raw === "" ? [] : [{ cultivar, expectedBunches: Number(raw) }]
      }))
      toast.success("Expected stock recorded")
      onSaved()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Expected stock could not be saved")
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="mt-3 rounded-lg border bg-muted/20 p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {CULTIVARS.map(cultivar => (
          <label key={cultivar} className="space-y-1 text-xs">
            <span className="text-muted-foreground">{cultivar} bunches</span>
            <NumberField
              min={1}
              max={1_000_000}
              value={values[cultivar]}
              disabled={saving}
              clampOnBlur={false}
              aria-label={`Expected ${cultivar} bunches`}
              className="w-full"
              onChange={value => setValues(current => ({ ...current, [cultivar]: String(value) }))}
            />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className={`text-xs ${invalid ? "text-destructive" : "text-muted-foreground"}`}>
          {invalid ? "Use whole numbers of at least 1, or leave blank." : `Expected total: ${total} bunches`}
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={saving} onClick={onSaved}>
            <X className="w-3.5 h-3.5 mr-1" />Cancel
          </Button>
          <Button size="sm" disabled={saving || invalid} onClick={() => void save()}>
            {saving && <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />}Save expected stock
          </Button>
        </div>
      </div>
    </div>
  )
}

function IntakeRow({ intake, isAdmin }: { intake: IntakeVerification; isAdmin: boolean }) {
  const [editing, setEditing] = useState(false)
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-sm">{intake.batchNumber || "No batch number"}</p>
        <Badge variant="outline" className="text-[10px]">{intake.status}</Badge>
        <VerdictBadge verdict={intake.verdict} />
        <span className="text-xs text-muted-foreground ml-auto">{fmtDate(intake.date)}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div><span className="text-muted-foreground">Expected</span><p className="font-semibold">{intake.expectedTotal || "Not recorded"}</p></div>
        <div><span className="text-muted-foreground">Scanned</span><p className="font-semibold">{intake.scannedTotal}</p></div>
        <div className="col-span-2 sm:col-span-2">
          <span className="text-muted-foreground">Variety match</span>
          <div className="flex flex-wrap gap-1.5 mt-0.5">
            {intake.varieties.length === 0 ? <span className="text-muted-foreground">Nothing recorded</span> : intake.varieties.map(row => (
              <Badge
                key={row.cultivar}
                variant="outline"
                className={`text-[10px] ${row.scanned === row.expected && row.expected > 0
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : row.expected === 0
                    ? "bg-orange-50 text-orange-700 border-orange-200"
                    : row.scanned < row.expected
                      ? "bg-yellow-50 text-yellow-700 border-yellow-200"
                      : "bg-orange-50 text-orange-700 border-orange-200"}`}
              >
                {row.cultivar}: {row.scanned}/{row.expected || "—"}
              </Badge>
            ))}
          </div>
        </div>
      </div>
      {isAdmin && !editing && (
        <Button size="sm" variant="ghost" className="mt-2 h-7 px-2 text-xs" onClick={() => setEditing(true)}>
          <Pencil className="w-3.5 h-3.5 mr-1" />{intake.expectedTotal ? "Edit expected stock" : "Record expected stock"}
        </Button>
      )}
      {isAdmin && editing && (
        <ExpectedEditor
          intake={intake}
          onSaved={() => setEditing(false)}
        />
      )}
    </div>
  )
}

export function SupplierInventoryModal({
  supplier, intakes, scans, open, onOpenChange,
}: {
  supplier: string | null
  intakes: DailyIntake[]
  scans: ScanResult[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { user } = useAuth()
  const verification = useMemo(
    () => supplier ? verifySupplier(supplier, intakes, scans) : null,
    [supplier, intakes, scans],
  )
  if (!verification) return null
  const style = VERDICT_STYLES[verification.verdict]
  const recorded = verification.intakes.filter(intake => intake.expectedTotal > 0)
  const progress = verification.expectedTotal > 0
    ? Math.min(100, (verification.scannedTotal / verification.expectedTotal) * 100)
    : 0
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl rounded-2xl max-h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="p-4 sm:p-6 pb-3 border-b">
          <DialogTitle className="flex items-center gap-2">
            <Truck className="w-5 h-5 text-primary" />
            {verification.supplier}
          </DialogTitle>
          <DialogDescription>
            Inventory verification for received stock, scanned bunches and variety matches.
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto p-4 sm:p-6 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={verification.verdict} />
            <p className={`text-xs ${style.text}`}>
              {verification.verdict === "Complete" && "All received stock was scanned and matches the recorded varieties."}
              {verification.verdict === "Partial" && "Only part of the received stock has been scanned."}
              {verification.verdict === "Incomplete" && "No stock has been scanned for this supplier yet."}
              {verification.verdict === "Discrepancy" && "Scanned quantity or variety does not match the recorded stock."}
              {verification.verdict === "Not recorded" && "No expected stock recorded yet. An administrator can add it below."}
            </p>
          </div>

          <div className="rounded-lg border p-3 sm:p-4">
            <div className="flex items-center gap-2 mb-2">
              <Package className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold">Supplier Inventory</h3>
              <Badge variant="outline" className="ml-auto text-[10px]">{verification.intakes.length} {verification.intakes.length === 1 ? "delivery" : "deliveries"}</Badge>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><span className="text-muted-foreground">Expected</span><p className="text-lg font-bold">{verification.expectedTotal || "—"}</p></div>
              <div><span className="text-muted-foreground">Scanned</span><p className="text-lg font-bold">{verification.scannedTotal}</p></div>
              <div><span className="text-muted-foreground">Remaining</span><p className="text-lg font-bold">{Math.max(0, verification.expectedTotal - verification.scannedTotal)}</p></div>
            </div>
            <Progress value={progress} className="h-2 mt-2" />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {verification.varieties.length === 0 ? (
                <span className="text-xs text-muted-foreground">No expected or scanned varieties yet.</span>
              ) : verification.varieties.map(row => (
                <Badge key={row.cultivar} variant="outline" className="text-[10px]">
                  {row.cultivar}: {row.scanned} scanned / {row.expected || "—"} expected
                </Badge>
              ))}
            </div>
            {verification.unlinkedScans > 0 && (
              <p className="text-[11px] text-muted-foreground mt-2">
                {verification.unlinkedScans} {verification.unlinkedScans === 1 ? "scan has" : "scans have"} a supplier name but no delivery intake; included in scanned totals.
              </p>
            )}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <ClipboardCheck className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold">Scan Verification by Delivery</h3>
            </div>
            {verification.intakes.length === 0 ? (
              <p className="text-sm text-muted-foreground" role="status">No delivery intakes recorded for this supplier.</p>
            ) : (
              <div className="space-y-2">
                {verification.intakes.map(intake => (
                  <IntakeRow key={intake.id} intake={intake} isAdmin={user?.role === "Admin"} />
                ))}
              </div>
            )}
            {recorded.length > 0 && recorded.every(intake => intake.verdict === "Complete") && (
              <p className="flex items-center gap-1.5 text-xs text-emerald-700 mt-3">
                <CheckCircle2 className="w-4 h-4" />Every recorded delivery is fully scanned and matches its expected varieties.
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}