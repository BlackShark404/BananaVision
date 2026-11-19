# `09_system_configuration_flow.md` — Module 9: System Configuration (Global Settings Shell, Optimistic Revision Locking, Backup/Restore & Station Power) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 9 (System Configuration) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Route & Admin Guard:** Maps `/admin/config` to `<ProtectedRoute reqAdmin><SystemConfig /></ProtectedRoute>`. |
| `frontend/src/pages/admin/SystemConfig.tsx` | **System Configuration Master View:** Renders the 4 configuration tabs (`Cameras`, `Detection`, `Data & Backups`, `Power`), polls `/api/v1/config/maintenance` every 5s, tracks unsaved draft changes (`localConfig` vs. `config`), renders the sticky `"Unsaved changes"` save/discard bar, handles `"Reset All Settings"`, and controls station Restart/Shutdown confirmation dialogs. |
| `frontend/src/components/StationBackupControls.tsx` | **Station Backup & Restore Wizard:** Creates full station `.zip` backups (`POST /api/v1/config/backups`), downloads them (`GET /api/v1/config/backups/{id}`), and runs the 3-step restore wizard (`Choose archive` → `Validate` → `Confirm` with admin password + typing `REPLACE`). |
| `frontend/src/context/AdminContext.tsx` | **Config State & Optimistic Concurrency Controller:** Loads `GET /api/v1/config` (`reloadConfig`), guards `acceptConfig` against stale revisions (`(previous.revision ?? 0) > saved.revision`), diffs changed fields in `updateConfig`, sends `expected_revision: config.revision`, and sets `configConflict = true` on HTTP 409. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Defines `api.config.get`, `api.config.update`, `api.config.export`, `api.config.maintenance`, `api.config.backup`, `api.config.downloadBackup`, `api.config.validateRestore`, `api.config.restore`, `api.config.shutdown`, `api.config.restart`, `api.config.recoverPower`, `api.config.recoverRestore`, and `api.config.applyCameras`. |
| `backend/app/api/v1/config.py` | **Config & Export Controller:** Handles `GET /api/v1/config`, `PATCH /api/v1/config` (acquiring `station_lock` when cameras change, recording `AuditAction.CONFIG_CHANGED`), and `GET /api/v1/config/export`. |
| `backend/app/services/configuration.py` | **Canonical Configuration Service:** Selects/initializes the singleton `SystemConfig` row (`canonical_key == 1`), performs optimistic revision updates (`WHERE id = :id AND canonical_key = 1 AND revision = :expected_revision` setting `revision = revision + 1`), raises HTTP 409 on revision mismatch, and applies camera changes after commit. |
| `backend/app/api/v1/maintenance.py` | **Maintenance, Backup/Restore & Power Controller:** Handles `/api/v1/config/maintenance`, `/backups`, `/restores/validate`, `/restores`, `/restart`, `/shutdown`, `/power/cancel`, `/maintenance/recover`, and `/maintenance/apply` with administrator password re-authentication (`reauthenticate`). |
| `backend/app/schemas/common.py` | **Pydantic Config Schemas:** Defines `SystemConfigResponse` and `SystemConfigUpdate` (requiring `expected_revision: StrictInt = Field(ge=1)`, rejecting explicit `null` values, and validating `camera_ids`, `camera_device_ids`, `confidence_threshold`, and `data_retention_enabled`). |
| `backend/app/models/system_config.py` | **SQLAlchemy ORM Model (`system_config`):** Singleton table enforced by `CheckConstraint('canonical_key IS NULL OR canonical_key = 1')` and `unique=True` on `canonical_key`, storing `revision`, `confidence_threshold`, `data_retention_enabled`, `updated_at`, and `updated_by_admin`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Configuration Loading, Draft Merging, Unsaved Changes Bar & Optimistic Revision Diffing

#### Step A1: Loading Config in `AdminContext.tsx` & Draft State Synchronization in `SystemConfig.tsx`
* **Step Title & Trigger:** `AdminProvider` loads `GET /api/v1/config` via `reloadConfig()`. When the admin opens `/admin/config`, `SystemConfig.tsx` merges incoming server updates into `localConfig` without clobbering any unsaved draft fields, polls `api.config.maintenance()` every 5 seconds, and displays the sticky `"Unsaved changes"` bar whenever `hasChanges` is true.
* **Exact File Path & Line Numbers:** `frontend/src/context/AdminContext.tsx` (Lines 81–89, 136–158, 314–332) and `frontend/src/pages/admin/SystemConfig.tsx` (Lines 37–102, 153–183, 242–283, 525–538)
* **Complete Uncut Code Block (`frontend/src/context/AdminContext.tsx`, Lines 81–89, 136–158, 314–332):**
```tsx
const mapConfig = (saved: ApiConfig): SystemConfig => ({
  cameraIds: saved.camera_ids, confidenceThreshold: saved.confidence_threshold,
  detectionConfidenceThreshold: saved.detection_confidence_threshold,
  dataRetentionEnabled: saved.data_retention_enabled, revision: saved.revision,
  cameraDeviceIds: saved.camera_device_ids, appliedRevision: saved.applied_revision,
  applicationStatus: saved.application_status, applicationError: saved.application_error,
  restartRequired: saved.restart_required, retentionDays: saved.retention_days,
  retentionPolicy: saved.retention_policy, legacyConflict: saved.legacy_conflict,
})
```
```tsx
  const [configReady, setConfigReady] = useScopedState(scope, false)
  const [configError, setConfigError] = useScopedState<string | null>(scope, null)
  const [configConflict, setConfigConflict] = useScopedState(scope, false)
  const configRequests = useRef(0)
  const acceptConfig = useCallback((saved: ApiConfig) => {
    setConfig(previous => (previous.revision ?? 0) > saved.revision ? previous : mapConfig(saved))
    setConfigReady(true)
    setConfigError(null)
  }, [setConfig, setConfigReady, setConfigError])
  const reloadConfig = useCallback(async () => {
    if (!user) return
    const generation = ++configRequests.current
    try {
      const saved = await api.config.get()
      if (generation !== configRequests.current) return
      acceptConfig(saved)
      setConfigConflict(false)
    } catch (error) {
      if (generation === configRequests.current) setConfigError(error instanceof Error ? error.message : "Configuration unavailable")
    }
  }, [acceptConfig, setConfigConflict, setConfigError, user])
  useEffect(() => { void reloadConfig(); return () => { configRequests.current++ } }, [reloadConfig])
```
```tsx
  const updateConfig = useCallback(async (cfg: Partial<SystemConfig>) => {
    if (!configReady || configConflict || !config.revision) throw new Error("Reload saved settings before making changes")
    const apiData: ApiConfigUpdate = { expected_revision: config.revision }
    if (cfg.cameraIds !== undefined && cfg.cameraIds !== config.cameraIds) apiData.camera_ids = cfg.cameraIds
    if (cfg.cameraDeviceIds !== undefined && JSON.stringify(cfg.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds)) apiData.camera_device_ids = cfg.cameraDeviceIds
    if (cfg.confidenceThreshold !== undefined && cfg.confidenceThreshold !== config.confidenceThreshold) apiData.confidence_threshold = cfg.confidenceThreshold
    if (cfg.dataRetentionEnabled !== undefined && cfg.dataRetentionEnabled !== config.dataRetentionEnabled) apiData.data_retention_enabled = cfg.dataRetentionEnabled
    if (Object.keys(apiData).length === 1) return config
    ++configRequests.current
    try {
      const saved = await api.config.update(apiData)
      acceptConfig(saved)
      if (apiData.camera_ids !== undefined || apiData.camera_device_ids !== undefined) api.devices.list().then(res => setDevices(res.map(mapApiDevice))).catch(console.error)
      return mapConfig(saved)
    } catch (error) {
      if ((error as { status?: number }).status === 409) setConfigConflict(true)
      throw error
    }
  }, [config, configReady, configConflict, acceptConfig, setConfigConflict, setDevices])
```
* **Complete Uncut Code Block (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 37–102, 153–183, 242–283, 525–538):**
```tsx
export default function SystemConfig() {
  const { config, updateConfig, configReady, configError, configConflict, reloadConfig, acceptConfig } = useAdmin()
  const cameraDiscovery = useCameraDiscovery()
  const [localConfig, setLocalConfig] = useState(config)
  const previousConfig = useRef(config)
  const [maintenance, setMaintenance] = useState<MaintenanceStatus | null>(null)
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const exportFlight = useRef(false)
  const [reloading, setReloading] = useState(false)
  const reloadFlight = useRef(false)
  const [checkingPower, setCheckingPower] = useState(false)
  const checkFlight = useRef(false)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [powerPending, setPowerPending] = useState(false)
  const [powerAccepted, setPowerAccepted] = useState(false)
  const [powerMessage, setPowerMessage] = useState("")
  const [recoveryPassword, setRecoveryPassword] = useState("")
  const powerId = useRef<string | null>(null)
  const powerFlight = useRef(false)
  const configFlight = useRef(false)
  const maintenanceSequence = useRef(0)
  const acceptMaintenance = (result: MaintenanceStatus) => {
    ++maintenanceSequence.current
    setMaintenance(result)
    setMaintenanceError(null)
  }
  const disabled = !configReady || configConflict || archiveBusy || powerPending || powerAccepted || Boolean(maintenance && maintenance.state !== "ready")
  useEffect(() => {
    if (archiveBusy) return
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      if (!live) return
      const mySeq = ++maintenanceSequence.current
      try {
        const result = await api.config.maintenance()
        if (live && mySeq === maintenanceSequence.current) { setMaintenance(result); setMaintenanceError(null) }
      } catch {
        if (live && mySeq === maintenanceSequence.current) setMaintenanceError("Maintenance status unavailable")
      }
      if (live) timer = setTimeout(refresh, 5000)
    }
    void refresh()
    return () => { live = false; clearTimeout(timer) }
  }, [archiveBusy])
  const [saving, setSaving] = useState(false)
  const [showShutdownDialog, setShowShutdownDialog] = useState(false)
  const [showRestartDialog, setShowRestartDialog] = useState(false)
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null)
  const [editCameraValue, setEditCameraValue] = useState("")

  useEffect(() => {
    const previous = previousConfig.current
    previousConfig.current = config
    setLocalConfig(draft => ({
      ...config,
      cameraIds: draft.cameraIds === previous.cameraIds ? config.cameraIds : draft.cameraIds,
      cameraDeviceIds: JSON.stringify(draft.cameraDeviceIds) === JSON.stringify(previous.cameraDeviceIds) ? config.cameraDeviceIds : draft.cameraDeviceIds,
      confidenceThreshold: draft.confidenceThreshold === previous.confidenceThreshold ? config.confidenceThreshold : draft.confidenceThreshold,
      dataRetentionEnabled: draft.dataRetentionEnabled === previous.dataRetentionEnabled ? config.dataRetentionEnabled : draft.dataRetentionEnabled,
    }))
  }, [config])

  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || JSON.stringify(localConfig.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds) || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)
```
```tsx
  const handleSave = async () => {
    if (disabled || configFlight.current) return
    const deviceIds = localConfig.cameraDeviceIds ?? []
    if (deviceIds.length !== activeCameraIds.length || new Set(deviceIds).size !== deviceIds.length || deviceIds.some(id => !Number.isSafeInteger(id) || id < 0)) {
      toast.error("Assign a distinct nonnegative device index to every camera")
      return
    }
    configFlight.current = true
    setSaving(true)
    try {
      const saved = await updateConfig(localConfig)
      setLocalConfig(saved)
      toast.success("Settings saved successfully", { description: saved.applicationError ?? "Applied to subsequent operations" })
    } catch (error) {
      toast.error("Settings could not be saved", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      configFlight.current = false
      setSaving(false)
    }
  }

  const handleUndo = () => {
    setLocalConfig(config)
    toast.info("Changes discarded")
  }

  const handleReset = () => {
    setLocalConfig({ ...config, cameraIds: (config.cameraDeviceIds ?? [0, 1]).map((_, index) => `CAM-${String(index + 1).padStart(3, "0")}`).join(", "), confidenceThreshold: 80, dataRetentionEnabled: true })
    toast.info("Settings reset to defaults")
  }
```
```tsx
      {(configError || configConflict) && <Alert>
        <AlertTitle>{configConflict ? "Configuration changed elsewhere" : configError ?? "Loading configuration…"}</AlertTitle>
        <AlertDescription>Your draft is preserved. Reload saved settings before making changes.</AlertDescription>
        <Button variant="outline" disabled={saving || reloading} onClick={async () => { if (reloadFlight.current) return; reloadFlight.current = true; setReloading(true); try { await reloadConfig() } finally { reloadFlight.current = false; setReloading(false) } }}>{reloading && <Loader2 className="w-4 h-4 animate-spin" />}{configConflict ? "Reload saved settings" : "Retry configuration"}</Button>
      </Alert>}
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Configuration details</summary>
        <div className="mt-3 space-y-3">
          {configReady && <p>Saved revision {config.revision} · Cameras {config.applicationStatus}. Threshold applies to the next scan. Deployment model changes require a backend restart.</p>}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <p>Reset camera names, review threshold (80%), and automatic cleanup (enabled). Device assignments stay at their saved values. Review and save to apply.</p>
            <Button variant="outline" size="sm" disabled={saving || disabled} onClick={handleReset} className="shrink-0 self-start">
              <RefreshCw className="w-4 h-4 mr-2" /> Reset All Settings
            </Button>
          </div>
        </div>
      </details>
```
```tsx
      {hasChanges && (
        <div role="region" aria-label="Unsaved configuration changes" className="sticky bottom-0 z-20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border rounded-xl bg-background p-4 shadow-lg">
          <div>
            <p className="text-sm font-medium">Unsaved changes</p>
            <p className="text-xs text-muted-foreground">Save applies pending edits across all settings tabs.</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button variant="outline" onClick={handleUndo} disabled={saving || disabled} className="flex-1 sm:flex-none">Discard</Button>
            <Button onClick={handleSave} disabled={saving || disabled} className="flex-1 sm:flex-none">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      )}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Field-Level Draft Preservation (`SystemConfig.tsx` Lines 89–99):** When `config` updates in `AdminContext` (e.g., on tab focus or when `toggleDataRetention` saves immediately), the `useEffect` compares each field in `draft` against `previousConfig.current`. Only untouched fields adopt the new `config` value; any field the admin is actively editing in `localConfig` is preserved!
  * **Optimistic Concurrency (`AdminContext.tsx` Lines 316–329):** `updateConfig` always attaches `expected_revision: config.revision` and only includes fields that actually changed from `config`. If another administrator saved a configuration change in the meantime, FastAPI returns HTTP 409, `AdminContext` sets `setConfigConflict(true)`, and `SystemConfig.tsx` (Lines 242–246) renders the `"Configuration changed elsewhere"` `<Alert>` with a `"Reload saved settings"` button.

---

### Phase C, D & E: Backend Config Controller (`config.py`), Singleton Service (`configuration.py`) & ORM (`system_config.py`)

#### Step D1: `GET /api/v1/config` and `PATCH /api/v1/config` Execution
* **Step Title & Trigger:** FastAPI handles `GET /api/v1/config` and `PATCH /api/v1/config`.
* **Exact File Path & Line Numbers:**
  * `backend/app/api/v1/config.py` (Lines 29–72)
  * `backend/app/schemas/common.py` (Lines 219–269)
  * `backend/app/models/system_config.py` (Lines 1–36)
  * `backend/app/services/configuration.py` (Lines 118–194 & 242–282)
* **Complete Uncut Code Block (`backend/app/api/v1/config.py`, Lines 29–72):**
```python
def audit_values(config) -> dict:
    """Saved settings as plain values, read before the update refreshes the same objects."""
    camera_ids, device_ids = configuration.camera_slot_values(config.camera_slots)
    return {
        'camera_ids': camera_ids,
        'camera_device_ids': ', '.join(str(value) for value in device_ids),
        'confidence_threshold': config.confidence_threshold,
        'data_retention_enabled': config.data_retention_enabled,
    }


@router.get("", response_model=SystemConfigResponse)
async def get_config(db: DbSession, user: CurrentUser):
    return configuration.config_response(await configuration.get_config(db))


@router.patch("", response_model=SystemConfigResponse)
async def update_config(body: SystemConfigUpdate, db: DbSession, admin: AdminUser, request: Request):
    if body.camera_ids is None and body.camera_device_ids is None:
        return await _update_config(body, db, admin, request)
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan or mapping before changing cameras")
    async with station_lock:
        return await _update_config(body, db, admin, request)


async def _update_config(body, db, admin, request):
    changes = body.model_dump(exclude_unset=True, exclude={'expected_revision'})
    admin_profile_id = await db.scalar(select(AdminProfile.id).where(AdminProfile.account_id == admin.id))
    before = audit_values(await configuration.get_config(db))
    config = await configuration.update_config(db, changes, body.expected_revision, admin_profile_id)
    described = audit.describe_changes(before, audit_values(config))
    if described:  # Saving unchanged values is not an event.
        await audit.record(
            db, audit.AuditAction.CONFIG_CHANGED,
            f"Config revision {body.expected_revision} → {config.revision}: {described}",
            actor=admin, ip=get_client_ip(request),
        )
    await db.commit()
    if 'camera_ids' in changes or 'camera_device_ids' in changes:
        await configuration.apply_camera_config(config)
        await configuration.sync_devices(db)
    return configuration.config_response(config)
```
* **Complete Uncut Code Block (`backend/app/models/system_config.py`, Lines 1–36):**
```python
"""
SystemConfig ORM model — typed system configuration.
"""

from __future__ import annotations

from datetime import datetime
from app.core.time import now_manila
import uuid

from sqlalchemy import Integer, ForeignKey, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class SystemConfig(Base):
    __tablename__ = "system_config"
    __table_args__ = (CheckConstraint('canonical_key IS NULL OR canonical_key = 1', name='ck_config_canonical_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_key: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    legacy_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    confidence_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    data_retention_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )
    updated_by_admin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_profile.id", ondelete="SET NULL"), nullable=True
    )

    admin = relationship("AdminProfile", lazy="selectin")
```
* **Complete Uncut Code Block (`backend/app/services/configuration.py`, Lines 242–282):**
```python
async def update_config(db, changes, expected_revision, admin_id) -> SystemConfig:
    config = await get_config(db)
    camera_ids, device_ids = camera_slot_values(config.camera_slots)
    values = dict(camera_ids=camera_ids, camera_device_ids=device_ids,
        confidence_threshold=config.confidence_threshold,
        data_retention_enabled=config.data_retention_enabled)
    unknown = set(changes) - set(values)
    if unknown:
        raise HTTPException(422, 'Unknown configuration fields')
    camera_changed = 'camera_ids' in changes or 'camera_device_ids' in changes
    values.update(changes)
    try:
        values = _validated_values(values['camera_ids'], values['camera_device_ids'],
            values['confidence_threshold'], values['data_retention_enabled'])
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    changed = await db.execute(update(SystemConfig).where(
        SystemConfig.id == config.id, SystemConfig.canonical_key == 1,
        SystemConfig.revision == expected_revision).values(
            confidence_threshold=values['confidence_threshold'],
            data_retention_enabled=values['data_retention_enabled'],
            revision=SystemConfig.revision + 1,
            updated_by_admin=admin_id,
            updated_at=now_manila(),
        ).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        current = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
            .execution_options(populate_existing=True))
        if current is not None:
            await _ensure_camera_slots(db, current)
        raise HTTPException(409, {'message': 'Configuration changed; reload before saving',
                                  'current': config_response(current)})
    if camera_changed:
        await _replace_camera_slots(
            db, config.camera_slots, values['camera_ids'], values['camera_device_ids'],
        )
    await db.flush()
    saved = await db.scalar(select(SystemConfig).where(SystemConfig.canonical_key == 1)
        .execution_options(populate_existing=True))
    return await _with_camera_slots(db, saved)
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Singleton Enforcement (`system_config.py` Line 21 & 24):** `canonical_key` has a `UNIQUE` constraint and a `CHECK (canonical_key IS NULL OR canonical_key = 1)` constraint in PostgreSQL, guaranteeing at the database level that at most one canonical configuration row can ever exist.
  * **Atomic Compare-And-Swap (`configuration.py` Lines 258–267):** Executes `UPDATE system_config SET confidence_threshold = ..., data_retention_enabled = ..., revision = revision + 1, updated_by_admin = :admin_id, updated_at = :now_manila WHERE id = :id AND canonical_key = 1 AND revision = :expected_revision`. If `changed.rowcount != 1`, another transaction incremented `revision` first, so it raises HTTP 409 (`"Configuration changed; reload before saving"`).
  * **Selective `station_lock` Acquisition (`config.py` Lines 47–52):** Changing only `confidence_threshold` or `data_retention_enabled` does **not** acquire `station_lock`, so admins can save AI threshold or retention settings even while an operator is actively scanning. Only camera changes acquire `station_lock`.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **Route & Component** | `/admin/config` → `frontend/src/pages/admin/SystemConfig.tsx` |
| **Config Endpoints** | `GET /api/v1/config` (any `CurrentUser`), `PATCH /api/v1/config` (`AdminUser`) in `backend/app/api/v1/config.py` |
| **4 Configuration Tabs** | `scanner` (`Cameras`), `ai` (`Detection`), `data` (`Data & Backups`), `power` (`Power`) (`SystemConfig.tsx` Lines 275–280) |
| **Singleton DB Constraint** | `canonical_key = 1` with `CheckConstraint('canonical_key IS NULL OR canonical_key = 1')` on `system_config` |
| **Optimistic Concurrency** | `expected_revision` in `SystemConfigUpdate`; raises HTTP `409` if `SystemConfig.revision != expected_revision` |
| **Default Reset Values** | `confidenceThreshold: 80`, `dataRetentionEnabled: true`, `cameraIds: "CAM-001, CAM-002..."` (`SystemConfig.tsx` Line 180) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Change the Default Reset Confidence Threshold in `"Reset All Settings"` from 80% to 85%
* **Examiner Prompt:** *"In `SystemConfig.tsx`, change the `'Reset All Settings'` button (`handleReset`) so that resetting defaults sets the Review Confidence Threshold to `85%` instead of `80%`, and update the description text accordingly."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 179–182 & 252)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 179–182 & 252):**
```tsx
  const handleReset = () => {
    setLocalConfig({ ...config, cameraIds: (config.cameraDeviceIds ?? [0, 1]).map((_, index) => `CAM-${String(index + 1).padStart(3, "0")}`).join(", "), confidenceThreshold: 80, dataRetentionEnabled: true })
    toast.info("Settings reset to defaults")
  }
```
```tsx
            <p>Reset camera names, review threshold (80%), and automatic cleanup (enabled). Device assignments stay at their saved values. Review and save to apply.</p>
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 179–182 & 252):**
```tsx
  const handleReset = () => {
    setLocalConfig({ ...config, cameraIds: (config.cameraDeviceIds ?? [0, 1]).map((_, index) => `CAM-${String(index + 1).padStart(3, "0")}`).join(", "), confidenceThreshold: 85, dataRetentionEnabled: true })
    toast.info("Settings reset to defaults")
  }
```
```tsx
            <p>Reset camera names, review threshold (85%), and automatic cleanup (enabled). Device assignments stay at their saved values. Review and save to apply.</p>
```

---

#### Drill Scenario 2: Automatically Reload Configuration When a 409 Conflict Occurs If the User Has No Unsaved Local Edits
* **Examiner Prompt:** *"In `SystemConfig.tsx`, if `configConflict` becomes `true` while `!hasChanges`, automatically call `reloadConfig()` so the user doesn't have to click the reload button manually."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (After Line 101)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Line 101):**
```tsx
  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || JSON.stringify(localConfig.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds) || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 101–107):**
```tsx
  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || JSON.stringify(localConfig.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds) || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)

  useEffect(() => {
    if (configConflict && !hasChanges && !reloading) {
      void reloadConfig()
    }
  }, [configConflict, hasChanges, reloading, reloadConfig])
```

---

#### Drill Scenario 3: Require Administrator Password Confirmation Before Triggering a Station Shutdown
* **Examiner Prompt:** *"In `backend/app/api/v1/maintenance.py`, `POST /api/v1/config/shutdown` currently calls `await reauthenticate(db, admin)` without requiring a password parameter. Explain how `reauthenticate(db, admin, password)` works when a `SecretStr` password is provided (as in `/restores` and `/power/cancel`)."*
* **Exact Code Reference (`backend/app/api/v1/maintenance.py`, Lines 44–73 & 204–217):**
  * When `password: SecretStr` is passed to `reauthenticate(db, admin, body.password)`, Lines 54–72 check `credential_limiter.is_locked(f"reauth:{current.id}")`, run `verify_password(password.get_secret_value(), current.password_hash)`, record failures under `AuditAction.REAUTH_FAILED`, and lock after 5 bad attempts (`AuditAction.ACCOUNT_LOCKED`).
