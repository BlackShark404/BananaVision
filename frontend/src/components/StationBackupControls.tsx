import { useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import type { MaintenanceOperation, RestoreValidation } from "@/types/api"

export function StationBackupControls({ disabled, onBusy }: { disabled: boolean; onBusy: (busy: boolean) => void }) {
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
  const restore = () => run("Restoring station data; waiting for active work to finish…", async () => {
    if (!validation || confirmation !== "REPLACE") return
    restoreId.current ??= crypto.randomUUID()
    const result = await api.config.restore({ operation_id: restoreId.current, validation_id: validation.validation_id,
      token: validation.token, password, confirmation: "REPLACE" })
    setPassword("")
    if (result.status !== "completed") throw new Error(result.message ?? `Restore ${result.status}; check operation status`)
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
  return <>
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
      <div>
        <h4 className="font-medium text-sm sm:text-base">Database Backup</h4>
        <p className="text-xs sm:text-sm text-muted-foreground">Restorable station data, accounts, settings, history and referenced images. Keep this private: it includes credential hashes. Deployment secrets and models are excluded.</p>
      </div>
      <Button variant="outline" disabled={disabled || busy} onClick={create}>Create Backup</Button>
      {backup?.status === "completed" && <Button variant="outline" disabled={busy} onClick={() => run("Downloading backup…", async () => {
        await api.config.downloadBackup(backup.id, backup.filename ?? "station.zip"); toast.info("Backup download started")
      })}>Download Backup</Button>}
    </div>
    <div className="space-y-3 p-4 rounded-xl border">
      <h4 className="font-medium text-sm sm:text-base">Restore Station Data</h4>
      <p className="text-xs sm:text-sm text-muted-foreground">Validate an archive before replacing this station. Active scans will finish first. A verified rollback backup is required; all sessions will be invalidated.</p>
      <Label htmlFor="station-backup">Backup archive</Label>
      <Input id="station-backup" type="file" accept=".zip" disabled={busy || disabled} onChange={event => {
        setFile(event.target.files?.[0] ?? null); setValidation(null); setPassword(""); setConfirmation("")
      }} />
      <Button variant="outline" onClick={validate} disabled={!file || disabled || busy}>Validate Backup</Button>
      {validation && <div className="space-y-3">
        <p className="text-xs text-muted-foreground">Archive validated. Confirmation expires {new Date(validation.expires_at).toLocaleString()}.</p>
        <Label htmlFor="restore-password">Administrator password</Label>
        <Input id="restore-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
        <Label htmlFor="restore-confirm">Type REPLACE to confirm</Label>
        <Input id="restore-confirm" value={confirmation} onChange={e => setConfirmation(e.target.value)} disabled={busy} />
        <Button variant="destructive" onClick={restore} disabled={busy || disabled || !password || confirmation !== "REPLACE"}>Replace Station Data</Button>
      </div>}
      {busy && <p role="status" className="text-xs text-muted-foreground">Waiting for active work, then processing the archiveâ€¦</p>}
      {message && <p role="alert" className="text-sm text-destructive">{message}</p>}
      {(backupId.current || restoreId.current) && <Button variant="outline" disabled={busy} onClick={check}>Check Operation Status</Button>}
    </div>
  </>
}
