import { useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { clearAuth } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { toast } from "sonner"
import type { MaintenanceOperation, RestoreValidation } from "@/types/api"
import { inManila } from "@/lib/manilaTime"

export function StationBackupControls({ disabled, onBusy }: { disabled: boolean; onBusy: (busy: boolean) => void }) {
  const [restoreOpen, setRestoreOpen] = useState(false)
  const [operation, setOperation] = useState("")
  const [busy, setBusy] = useState(false)
  const [backup, setBackup] = useState<MaintenanceOperation | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [validation, setValidation] = useState<RestoreValidation | null>(null)
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [message, setMessage] = useState("")
  const pending = useRef(false)
  const backupId = useRef<string | null>(null)
  const restoreId = useRef<string | null>(null)
  const run = async (label: string, action: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setOperation(label); setBusy(true); onBusy(true); setMessage("")
    try { await action() }
    catch (error) { setMessage(error instanceof Error ? error.message : "Operation unavailable; check its status before retrying") }
    finally { pending.current = false; setBusy(false); onBusy(false) }
  }
  const create = () => run("Creating backup; waiting for active work to finish…", async () => {
    if (backup?.status === "completed" || backup?.status === "failed") backupId.current = null
    backupId.current ??= crypto.randomUUID()
    const result = await api.config.backup(backupId.current)
    setBackup(result)
    if (result.status !== "completed") throw new Error(result.message ?? `Backup ${result.status}; check operation status`)
    toast.success("Backup created on server")
  })
  const validate = () => run("Uploading and validating backup…", async () => {
    if (!file) return
    setValidation(null); setPassword(""); setConfirmation(""); restoreId.current = null
    setValidation(await api.config.validateRestore(file))
  })
  const restore = () => run("Restoring station data (this may take a minute)…", async () => {
    if (!validation || confirmation !== "REPLACE") return
    restoreId.current ??= crypto.randomUUID()
    const result = await api.config.restore({ operation_id: restoreId.current, validation_id: validation.validation_id,
      token: validation.token, password, confirmation: "REPLACE" })
    setPassword("")
    if (result.status !== "completed") {
      if (result.status === "failed") restoreId.current = null
      throw new Error(result.message ?? `Restore ${result.status}; check operation status`)
    }
    clearAuth()
    toast.success("Station data restored. Sign in with a restored account.")
    window.location.assign("/login")
  })
  const check = () => run("Checking operation status…", async () => {
    const id = restoreId.current ?? backupId.current
    if (!id) return
    const result = await api.config.operation(id)
    if (!restoreId.current) setBackup(result)
    setMessage(result.message ?? `Operation ${result.status}`)
  })
  const feedback = <div className="space-y-3">
    {busy && <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />{operation || "Waiting for active work, then processing the archive…"}</p>}
    {message && <p role="alert" className="text-sm text-destructive">{message}</p>}
    {(backupId.current || restoreId.current) && <Button variant="outline" size="sm" disabled={busy} onClick={check}>
      {busy && operation.startsWith("Checking") && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
      {busy && operation.startsWith("Checking") ? "Checking Status…" : "Check Operation Status"}
    </Button>}
  </div>
  return <>
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5">
      <div className="space-y-1">
        <h4 className="font-medium text-sm sm:text-base">Station Backup</h4>
        <p className="text-xs sm:text-sm text-muted-foreground">Restore accounts, settings, history, and referenced images from a station archive.</p>
        <p className="text-xs text-muted-foreground">Keep backups private: they include credential hashes. Deployment secrets and models are excluded.</p>
      </div>
      <div className="flex flex-col gap-2 shrink-0">
        <Button variant="outline" disabled={disabled || busy} onClick={create}>
          {busy && operation.startsWith("Creating backup") && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
          {busy && operation.startsWith("Creating backup") ? "Creating Backup…" : "Create Backup"}
        </Button>
        {backup?.status === "completed" && <Button variant="outline" disabled={busy} onClick={() => run("Downloading backup…", async () => {
          await api.config.downloadBackup(backup.id, backup.filename ?? "station.zip"); toast.info("Backup download started")
        })}>Download Backup</Button>}
      </div>
    </div>
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5">
      <div className="space-y-1">
        <h4 className="font-medium text-sm sm:text-base">Restore Station Data</h4>
        <p className="text-xs sm:text-sm text-muted-foreground">Replace this station's data from a validated backup archive.</p>
      </div>
      <Dialog open={restoreOpen} onOpenChange={open => {
        if (pending.current) return
        setRestoreOpen(open)
        if (!open) { setPassword(""); setConfirmation("") }
      }}>
        <DialogTrigger asChild><Button variant="outline" disabled={disabled || busy} className="shrink-0">Restore from Backup</Button></DialogTrigger>
        <DialogContent className="sm:max-w-xl max-h-[85dvh] overflow-y-auto" showCloseButton={!busy}
          onEscapeKeyDown={event => { if (pending.current) event.preventDefault() }}
          onInteractOutside={event => { if (pending.current) event.preventDefault() }}>
          <DialogHeader>
            <DialogTitle>Restore Station Data</DialogTitle>
            <DialogDescription>Validate an archive before replacing this station. Active scans will finish first. A verified rollback backup is required; all sessions will be invalidated.</DialogDescription>
          </DialogHeader>
          <ol aria-label="Restore progress" className="flex gap-2 text-xs text-muted-foreground border-y py-3">
            {["Choose archive", "Validate", "Confirm"].map((step, index) => <li key={step} aria-current={(validation ? 2 : file ? 1 : 0) === index ? "step" : undefined}
              className="flex-1 aria-[current=step]:text-foreground aria-[current=step]:font-semibold">{index + 1}. {step}</li>)}
          </ol>
          <div className="space-y-3">
            <Label htmlFor="station-backup">Backup archive</Label>
            <Input id="station-backup" type="file" accept=".zip" disabled={busy || disabled} onChange={event => {
              setFile(event.target.files?.[0] ?? null); setValidation(null); setPassword(""); setConfirmation("")
            }} />
            {file && <p className="text-xs text-muted-foreground break-all">Selected: {file.name}</p>}
            {!validation && <Button variant="outline" onClick={validate} disabled={!file || disabled || busy}>
              {busy && operation.startsWith("Uploading") && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              {busy && operation.startsWith("Uploading") ? "Validating Backup…" : "Validate Backup"}
            </Button>}
          </div>
          {validation && <div className="space-y-3 border-t pt-4">
            <p className="text-xs text-muted-foreground">Archive validated. Confirmation expires {new Date(validation.expires_at).toLocaleString(undefined, inManila())}.</p>
            <Label htmlFor="restore-password">Administrator password</Label>
            <Input id="restore-password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} disabled={busy} />
            <Label htmlFor="restore-confirm">Type REPLACE to confirm</Label>
            <Input id="restore-confirm" value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} />
            <Button variant="destructive" onClick={restore} disabled={busy || disabled || !password || confirmation !== "REPLACE"}>
              {busy && operation.startsWith("Restoring") && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              {busy && operation.startsWith("Restoring") ? "Restoring Station Data…" : "Replace Station Data"}
            </Button>
            <Button variant="ghost" disabled={busy || disabled} onClick={validate}>Validate Again</Button>
          </div>}
          {feedback}
        </DialogContent>
      </Dialog>
    </div>
    {!restoreOpen && (busy || message || backupId.current || restoreId.current) && <div className="pt-4">{feedback}</div>}
  </>
}
