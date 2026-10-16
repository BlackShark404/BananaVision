import { useRef, useState, type Dispatch, type SetStateAction } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { scanWrite, scanRevision } from "@/lib/scanWrites"
import { scanRetryAction } from "@/lib/scanWriteFeedback"
import { useScans } from "@/context/ScanContext"
import { useAuth } from "@/context/AuthContext"
import type { ScanResult } from "@/types"

export function InventoryProvenanceReview({ scan, reason, setReason, onSaved, onConflict }: {
  scan: ScanResult; reason: string; setReason: Dispatch<SetStateAction<string>>; onSaved: (scan: ScanResult) => void; onConflict: () => void
}) {
  const { user } = useAuth()
  const { acceptScan } = useScans()
  const inFlight = useRef(false)
  const [pending, setPending] = useState(false)
  if (!["unverified", "excluded"].includes(scan.intakeProvenance ?? "")) return null
  const save = async (provenance: "unlinked" | "excluded") => {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    try {
      const result = await scanWrite(`${user?.id}:${scan.id}:provenance`, {
        expected_revision: scanRevision(scan.revision), intake_provenance: provenance, reason: reason.trim(),
      }, async body => acceptScan(await api.scans.reviewProvenance(scan.id, body)))
      onSaved(result)
      setReason("")
      toast.success("Inventory provenance review saved")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Review could not be saved", {
        action: scanRetryAction(error, request => { setReason(current => current.trim() === request.reason ? "" : current); onConflict() }),
      })
      if (typeof error === "object" && error !== null && "status" in error && error.status === 409) onConflict()
    } finally { inFlight.current = false; setPending(false) }
  }
  return <Card><CardContent className="p-4 sm:p-6 space-y-3">
    <p className="text-sm" role="status">Inventory provenance needs review. This historical record is preserved but excluded from active stock and spoilage risk.</p>
    {user?.role === "Admin" && <>
      <Label htmlFor="provenance-reason">Evidence and reason for provenance review</Label>
      <Textarea id="provenance-reason" value={reason} onChange={e => setReason(e.target.value)} disabled={pending} />
      {pending && <p role="status" className="flex items-center gap-2 text-sm"><Loader2 className="w-4 h-4 animate-spin" />Saving provenance review…</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={pending || !reason.trim()} onClick={() => void save("unlinked")}>Verify genuinely unlinked</Button>
        <Button size="sm" variant="outline" disabled={pending || !reason.trim()} onClick={() => void save("excluded")}>Keep excluded</Button>
      </div>
    </>}
  </CardContent></Card>
}
