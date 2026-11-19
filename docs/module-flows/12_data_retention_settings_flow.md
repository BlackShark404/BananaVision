# `12_data_retention_settings_flow.md` — Module 12: Data Retention Settings (Immediate Toggle, Orphan Capture Cleanup Worker & Scan Summary Export) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 12 (Data Retention Settings) |
| :--- | :--- |
| `frontend/src/pages/admin/SystemConfig.tsx` | **Data & Backups Tab UI (`<TabsContent value="data">`):** Renders the `"Automatic Capture Cleanup"` toggle button (`role="switch"`, `onClick={toggleDataRetention}`) displaying `config.retentionDays` (`30` days), the `"Export Scan Summaries"` `ExportDropdown` (`handleExportData("csv" \| "xlsx")`), and `<StationBackupControls>`. |
| `frontend/src/context/AdminContext.tsx` | **Config Mutation Controller (`updateConfig`):** Sends `PATCH /api/v1/config` with `{ expected_revision: config.revision, data_retention_enabled: newState }` and updates `config.dataRetentionEnabled`. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Defines `api.config.update` (`PATCH /api/v1/config`) and `api.config.export` (`GET /api/v1/config/export?format=csv\|xlsx`). |
| `backend/app/api/v1/config.py` | **Config & Export Controller:** Handles `PATCH /api/v1/config` (updating `data_retention_enabled` and logging `AuditAction.CONFIG_CHANGED`) and `GET /api/v1/config/export` (streaming CSV or building XLSX of all scans and logging `AuditAction.DATA_EXPORTED`). |
| `backend/app/services/configuration.py` | **Config Service (`config_response` & `update_config`):** Persists `data_retention_enabled` in `system_config` and returns `retention_days = get_settings().max_captures_retention_days` (`30`) and `retention_policy = 'orphan_captures_only'`. |
| `backend/app/core/startup.py` | **Background Task Launcher (`start_background_tasks`):** Spawns `asyncio.create_task(data_retention_worker())` when the station runtime starts. |
| `backend/app/services/data_retention.py` | **Data Retention Background Worker (`data_retention_worker`):** Runs every 6 hours (`RETENTION_CHECK_INTERVAL_SECONDS = 6 * 60 * 60`) under `coordinator.exclusive('retention')`. Checks `get_config(db).data_retention_enabled`; collects all referenced scan UUIDs from `Scan.id`, `ScanImage.file_path`, and `ScanClassification.thumbnail_url`; deletes only unreferenced orphan capture folders older than `max_captures_retention_days`; updates `MaintenanceState.retention`; and records `AuditAction.RETENTION_CLEANUP` or `AuditAction.RETENTION_FAILED`. |
| `backend/app/services/capture_cleanup.py` | **Safe Capture Directory Remover (`remove_scan_captures`):** Validates UUID folder names, rejects symlinks or paths outside `capture_path`, and calls `shutil.rmtree(directory)`. |
| `backend/app/config.py` | **Storage Settings (`Settings`):** Configures `capture_dir = "captures"` and `max_captures_retention_days = Field(30, ge=1)`. |
| `backend/app/models/system_config.py` | **SQLAlchemy ORM Model (`system_config`):** Stores `data_retention_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: `"Data & Backups"` Tab UI & Immediate Retention Toggle (`SystemConfig.tsx`)

#### Step A1: Immediate Save Behavior of `toggleDataRetention()` & Scan Summary Export (`SystemConfig.tsx`)
* **Step Title & Trigger:** Administrator clicks the `"Data & Backups"` tab (`value="data"`) in `SystemConfig.tsx` and clicks the `"Enabled"` / `"Disabled"` switch button (`toggleDataRetention`), or clicks `"Export"` → CSV / Excel (`handleExportData`).
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 184–215 & 410–448)
* **Complete Uncut Code Block:**
```tsx
  const handleExportData = async (format: "csv" | "xlsx") => {
    if (exportFlight.current) return
    exportFlight.current = true; setExporting(true)
    try {
      await api.config.export(format)
      toast.success("Scan summaries exported", { description: `${format.toUpperCase()} download started` })
    } catch {
      toast.error("Export Failed", { description: "Could not export scan summaries" })
    } finally { exportFlight.current = false; setExporting(false) }
  }

  const toggleDataRetention = async () => {
    if (disabled || configFlight.current) return
    configFlight.current = true
    const newState = !localConfig.dataRetentionEnabled
    const draft = localConfig
    setSaving(true)
    try {
      const saved = await updateConfig({ dataRetentionEnabled: newState })
      // Retention saves independently; keep unsaved camera/threshold edits.
      setLocalConfig({ ...draft, dataRetentionEnabled: saved.dataRetentionEnabled })
      toast.success(
        saved.dataRetentionEnabled ? "Data Retention Enabled" : "Data Retention Disabled",
        { description: saved.dataRetentionEnabled ? `Unreferenced captures older than ${config.retentionDays} days will be cleaned; scan history is retained` : "Automatic orphan capture cleanup is disabled" }
      )
    } catch (error) {
      toast.error("Data retention could not be updated", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      configFlight.current = false
      setSaving(false)
    }
  }
```
```tsx
        <TabsContent value="data" forceMount className="m-0 border-0 outline-none data-[state=inactive]:hidden">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Data &amp; Backups</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Manage capture cleanup, reports, and station recovery.</CardDescription>
            </CardHeader>
            <CardContent className="divide-y px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Automatic Capture Cleanup</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Clean unreferenced captures older than {config.retentionDays ?? "—"} days. Scan records and referenced evidence are retained.</p>
                  <p className="text-xs text-muted-foreground mt-1">Saves immediately · Applies on the next cleanup cycle.</p>
                </div>
                <Button 
                  role="switch" aria-label="Automatic capture cleanup" aria-checked={localConfig.dataRetentionEnabled}
                  variant={localConfig.dataRetentionEnabled ? "default" : "outline"} 
                  onClick={toggleDataRetention} 
                  disabled={saving || disabled}
                  className="w-full sm:w-auto shrink-0"
                >
                  {localConfig.dataRetentionEnabled ? "Enabled" : "Disabled"}
                </Button>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5 first:pt-0 last:pb-0">
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Export Scan Summaries</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Download a CSV or XLSX report of scan summaries. This export cannot restore station data.</p>
                </div>
                <ExportDropdown
                  onExportCsv={() => void handleExportData("csv")}
                  onExportXlsx={() => void handleExportData("xlsx")}
                  disabled={exporting}
                  exporting={exporting}
                />
              </div>
              <StationBackupControls disabled={disabled || saving} onBusy={setArchiveBusy} />
            </CardContent>
          </Card>
        </TabsContent>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Why `toggleDataRetention()` Saves Immediately While Preserving Unsaved Camera/AI Drafts (Lines 195–215):** Unlike camera slots or the confidence slider (which wait for the bottom `"Save Changes"` bar), clicking the `"Enabled"` / `"Disabled"` button immediately calls `await updateConfig({ dataRetentionEnabled: newState })` (sending only `{ expected_revision, data_retention_enabled }` to `PATCH /api/v1/config`). Line 204 then runs `setLocalConfig({ ...draft, dataRetentionEnabled: saved.dataRetentionEnabled })`, keeping any unsaved camera or threshold edits in `draft` intact!
  * **`forceMount` on `<TabsContent value="data">` (Line 410):** Keeps `<StationBackupControls>` mounted across tab switches (`data-[state=inactive]:hidden`) so an in-progress backup or restore validation state is never lost if the admin switches tabs.

---

### Phase C, D & E: Backend Retention Execution (`startup.py`, `data_retention.py` & `capture_cleanup.py`)

#### Step D1: Background Worker Startup (`startup.py`) & 6-Hour Orphan Capture Cleanup Cycle (`data_retention.py` & `capture_cleanup.py`)
* **Step Title & Trigger:** At backend boot, `start_background_tasks()` launches `data_retention_worker()`. Every 6 hours (`21,600` seconds), `_retention_cycle()` acquires `coordinator.exclusive('retention')`, checks `data_retention_enabled`, identifies all referenced scan directories in PostgreSQL, and deletes unreferenced capture directories on disk older than `settings.max_captures_retention_days` (`30` days).
* **Exact File Path & Line Numbers:**
  * `backend/app/core/startup.py` (Lines 211–224)
  * `backend/app/services/data_retention.py` (Lines 1–114)
  * `backend/app/services/capture_cleanup.py` (Lines 1–24)
* **Complete Uncut Code Block (`backend/app/core/startup.py`, Lines 211–224):**
```python
async def start_background_tasks(*, allow_blocked=False):
    """
    Start long-running background tasks (called after startup).
    Returns list of tasks for cancellation on shutdown.
    """
    tasks = _background_tasks
    if tasks or (coordinator.state != "ready" and not allow_blocked):
        return tasks

    # Retention worker
    from app.services.data_retention import data_retention_worker
    retention_task = asyncio.create_task(data_retention_worker())
    tasks.append(retention_task)
```
* **Complete Uncut Code Block (`backend/app/services/data_retention.py`, Lines 1–114):**
```python
"""Clean old unreferenced captures; persisted history and evidence are retained."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.time import now_manila
from app.models.scan import Scan
from app.models.scan_image import ScanImage
from app.models.scan_classification import ScanClassification
from app.services import audit
from app.services.audit import AuditAction
from app.services.capture_cleanup import remove_scan_captures
from app.services.configuration import get_config
from app.services.maintenance_state import get_state
from app.services.runtime_operations import coordinator, run_blocking
from app.services.backup_archive import _no_links, _evidence_name, ArchiveError

logger = logging.getLogger(__name__)
settings = get_settings()
RETENTION_CHECK_INTERVAL_SECONDS = 6 * 60 * 60


async def data_retention_worker():
    while True:
        try:
            await _run_retention_cycle()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception('Retention cleanup failed; persisted records remain protected')
        await asyncio.sleep(RETENTION_CHECK_INTERVAL_SECONDS)


async def _run_retention_cycle():
    try:
        await _retention_cycle()
    finally:
        # Admission is open again: write events kept while the cleanup held it.
        await audit.flush_deferred(sessions=async_session_factory)


async def _retention_cycle():
    async with coordinator.exclusive('retention'):
        async with async_session_factory() as db:
            if not (await get_config(db)).data_retention_enabled:
                await db.commit()
                return
            state = await get_state(db)
            state.retention = {**(state.retention or {}), 'attempted_at': now_manila().isoformat(), 'error': None}
            await db.commit()
            try:
                referenced = {str(sid) for sid in (await db.execute(select(Scan.id))).scalars()}
                for column in (ScanImage.file_path, ScanClassification.thumbnail_url):
                    for value in (await db.execute(select(column).where(column.is_not(None)))).scalars():
                        relative = _evidence_name(value, settings.capture_path)
                        referenced.add(relative.split('/')[0])
                days = settings.max_captures_retention_days
                cutoff = now_manila() - timedelta(days=days)
                removed = await run_blocking(remove_expired_orphans, settings.capture_path, referenced, cutoff.timestamp())
                state.retention = {**state.retention, 'completed_at': now_manila().isoformat(),
                                   'directories_removed': removed, 'error': None}
                if removed:
                    noun = 'directory' if removed == 1 else 'directories'
                    await audit.record(db, AuditAction.RETENTION_CLEANUP,
                                       f'Capture retention removed {removed} unreferenced capture '
                                       f'{noun} older than {days} days; scan history and evidence '
                                       'kept')
                await db.commit()
            except Exception as exc:
                await db.rollback()
                state = await get_state(db)
                state.retention = {**(state.retention or {}), 'error': 'Cleanup failed; see server logs. No history was deleted.'}
                # Error text can hold paths: the server log keeps it, the audit row its type.
                await audit.record(db, AuditAction.RETENTION_FAILED,
                                   f'Capture retention cleanup failed ({type(exc).__name__}); '
                                   'no history was deleted; see server logs')
                await db.commit()
                raise


def remove_expired_orphans(root, referenced: set[str], cutoff_timestamp: float) -> int:
    removed = 0
    _no_links(root.absolute())
    if not root.exists():
        return 0
    for directory in root.iterdir():
        try:
            name = str(uuid.UUID(directory.name))
        except ValueError:
            continue
        if name != directory.name or name in referenced:
            continue
        try:
            _no_links(directory.absolute())
            if not directory.is_dir():
                continue
            newest = directory.stat().st_mtime
            for child in directory.rglob('*'):
                _no_links(child.absolute())
                newest = max(newest, child.stat().st_mtime)
            if newest < cutoff_timestamp:
                if not remove_scan_captures(root, name):
                    raise OSError('Could not remove eligible orphan capture directory')
                removed += 1
        except ArchiveError:
            logger.warning('Skipping linked capture directory %s', directory.name)
    return removed
```
* **Complete Uncut Code Block (`backend/app/services/capture_cleanup.py`, Lines 1–24):**
```python
"""Delete only a scan's UUID directory directly beneath the configured capture root."""
import logging
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def remove_scan_captures(root: Path, scan_id: str) -> bool:
    name = str(uuid.UUID(scan_id))
    base = root.resolve()
    directory = base / name
    if directory.is_symlink() or directory.resolve().parent != base:
        logger.warning("Refusing capture cleanup outside capture root: %s", directory)
        return False
    if not directory.exists():
        return False
    try:
        shutil.rmtree(directory)
        return True
    except OSError:
        logger.exception("Could not remove captures for scan %s", name)
        return False
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Orphan-Only Protection (`data_retention.py` Lines 59–64):** The cleanup policy (`retention_policy = "orphan_captures_only"`) **never deletes persisted `Scan` rows or referenced scan images**. It builds a `referenced` set containing every UUID in `Scan.id`, every top-level directory referenced by `ScanImage.file_path`, and every top-level directory referenced by `ScanClassification.thumbnail_url`.
  * **Symlink & Path-Traversal Defense (`data_retention.py` Lines 90–113 & `capture_cleanup.py` Lines 10–17):**
    1. Only inspects subdirectories of `captures/` whose folder name is a canonical lowercase UUID (`str(uuid.UUID(directory.name)) == directory.name`) and is **not** in `referenced`.
    2. Calls `_no_links()` on the root, the directory, and every child file (`directory.rglob('*')`) to reject symlinks or junction points.
    3. Computes `newest = max(directory.stat().st_mtime, ...)` across all files inside the directory. If `newest < cutoff.timestamp()` (`now_manila() - timedelta(days=30)`), calls `remove_scan_captures(root, name)`.
  * **Audit Logging (`data_retention.py` Lines 69–75):** If `removed > 0`, records `AuditAction.RETENTION_CLEANUP` (`"Capture retention removed X unreferenced capture directories older than 30 days; scan history and evidence kept"`).

---

### Phase F: Server-Side Scan Summary Export (`GET /api/v1/config/export`)

#### Step F1: Streaming CSV & OpenXML XLSX Export (`backend/app/api/v1/config.py`)
* **Step Title & Trigger:** Administrator clicks `"Export"` → `"Export as CSV"` or `"Export as Excel"` under `"Export Scan Summaries"`, calling `api.config.export(format)` (`GET /api/v1/config/export?format=csv|xlsx`).
* **Exact File Path & Line Numbers:** `backend/app/api/v1/config.py` (Lines 74–166)
* **Complete Uncut Code Block:**
```python
@router.get("/export")
async def export_database(
    db: DbSession,
    admin: AdminUser,
    request: Request,
    format: Annotated[Literal["csv", "xlsx"], Query()] = "csv",
):
    """Export scan summaries to CSV or XLSX. This file cannot restore the database."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.status_logs))
        .order_by(Scan.date_time, Scan.id)
    )
    scans = result.scalars().all()
    # The row commits with this request before the file is sent; without it, no file.
    await audit.record(
        db, audit.AuditAction.DATA_EXPORTED,
        f"Exported inventory summary ({format}): {len(scans)} scan{'' if len(scans) == 1 else 's'}",
        actor=admin, ip=get_client_ip(request),
    )

    headers = [
        "Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness",
        "Confidence", "Inventory Status",
    ]

    if format == "xlsx":
        xlsx_rows = []
        for scan in scans:
            cultivar = scan.classification.cultivar if scan.classification else "N/A"
            ripeness = scan.classification.ripeness if scan.classification else "N/A"
            confidence = scan.classification.confidence if scan.classification else "N/A"
            status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
            cultivar_text = (
                str(getattr(cultivar, "value", cultivar))
                if cultivar is not None else None
            )
            ripeness_text = (
                str(getattr(ripeness, "value", ripeness))
                if ripeness is not None else None
            )
            status_text = (
                str(getattr(status, "value", status))
                if status is not None else None
            )

            if confidence == "N/A":
                conf_cell = ("N/A", "inlineStr")
            elif confidence is None:
                conf_cell = None
            else:
                try:
                    float(confidence)
                    conf_cell = (number_text(confidence), "n")
                except (ValueError, TypeError):
                    conf_cell = (str(confidence), "inlineStr")
            xlsx_rows.append([
                (str(scan.id), "inlineStr"),
                (scan.date_time.isoformat(), "inlineStr"),
                (cultivar_text, "inlineStr") if cultivar_text is not None else None,
                (ripeness_text, "inlineStr") if ripeness_text is not None else None,
                conf_cell,
                (status_text, "inlineStr") if status_text is not None else None,
            ])
        xlsx_bytes = build_xlsx(headers, xlsx_rows, sheet_name="sheet1")
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": (
                'attachment; filename="bananavision_inventory_export.xlsx"'
            )},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([scan.id, scan.date_time.isoformat(), getattr(cultivar, "value", cultivar),
                         getattr(ripeness, "value", ripeness), confidence, getattr(status, "value", status)])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bananavision_inventory_export.csv"}
    )
```

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **UI Tab & Toggle** | `<TabsContent value="data">` → `toggleDataRetention()` in `frontend/src/pages/admin/SystemConfig.tsx` (Lines 195–215 & 410–448) |
| **DB Column** | `system_config.data_retention_enabled` (`Boolean`, default `True`) |
| **Retention Period Setting** | `settings.max_captures_retention_days = 30` (`backend/app/config.py` Line 127) |
| **Cleanup Policy** | `retention_policy = "orphan_captures_only"` — cleans only unreferenced UUID folders under `captures/`, never database history or referenced evidence |
| **Cleanup Interval** | `RETENTION_CHECK_INTERVAL_SECONDS = 6 * 60 * 60` (every 6 hours) in `backend/app/services/data_retention.py` Line 27 |
| **Audit Actions** | `AuditAction.CONFIG_CHANGED`, `AuditAction.RETENTION_CLEANUP`, `AuditAction.RETENTION_FAILED`, `AuditAction.DATA_EXPORTED` |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Display the Last Retention Cleanup Timestamp and Directories Removed in the Data & Backups Tab
* **Examiner Prompt:** *"The polled `/api/v1/config/maintenance` endpoint (`maintenance` state in `SystemConfig.tsx`) already includes `maintenance.retention` (`attempted_at`, `completed_at`, `directories_removed`, `error`). Display the last cleanup status under `'Automatic Capture Cleanup'` in `SystemConfig.tsx`."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 418–423)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 418–423):**
```tsx
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Automatic Capture Cleanup</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Clean unreferenced captures older than {config.retentionDays ?? "—"} days. Scan records and referenced evidence are retained.</p>
                  <p className="text-xs text-muted-foreground mt-1">Saves immediately · Applies on the next cleanup cycle.</p>
                </div>
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 418–428):**
```tsx
                <div>
                  <h4 className="font-medium text-sm sm:text-base">Automatic Capture Cleanup</h4>
                  <p className="text-xs sm:text-sm text-muted-foreground">Clean unreferenced captures older than {config.retentionDays ?? "—"} days. Scan records and referenced evidence are retained.</p>
                  <p className="text-xs text-muted-foreground mt-1">Saves immediately · Applies on the next cleanup cycle.</p>
                  {maintenance?.retention?.completed_at && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Last cleanup: {maintenance.retention.directories_removed ?? 0} orphan directories removed
                    </p>
                  )}
                </div>
```

---

#### Drill Scenario 2: Add `"Finger Count"` and `"Spoilage Days"` Columns to the System Config Inventory Summary Export
* **Examiner Prompt:** *"In `GET /api/v1/config/export` (`backend/app/api/v1/config.py`), add `'Finger Count'` and `'Spoilage Days'` columns to both the CSV and XLSX exports."*
* **File to Edit:** `backend/app/api/v1/config.py` (Lines 95–158)
* **Before (`backend/app/api/v1/config.py`, Lines 95–98 & 151–158):**
```python
    headers = [
        "Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness",
        "Confidence", "Inventory Status",
    ]
```
```python
    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([scan.id, scan.date_time.isoformat(), getattr(cultivar, "value", cultivar),
                         getattr(ripeness, "value", ripeness), confidence, getattr(status, "value", status)])
```
* **After (`backend/app/api/v1/config.py`, Lines 95–98 & 151–162):**
```python
    headers = [
        "Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness",
        "Confidence", "Finger Count", "Spoilage Days", "Inventory Status",
    ]
```
```python
    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        finger_count = scan.classification.finger_count if scan.classification else 0
        spoilage_days = scan.classification.spoilage_days if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([scan.id, scan.date_time.isoformat(), getattr(cultivar, "value", cultivar),
                         getattr(ripeness, "value", ripeness), confidence, finger_count,
                         spoilage_days, getattr(status, "value", status)])
```

---

#### Drill Scenario 3: Change the Default Orphan Capture Retention Window from 30 Days to 14 Days
* **Examiner Prompt:** *"Change the default orphan capture retention period from 30 days to 14 days in `backend/app/config.py`."*
* **File to Edit:** `backend/app/config.py` (Line 127)
* **Before (`backend/app/config.py`, Line 127):**
```python
    max_captures_retention_days: int = Field(30, ge=1)
```
* **After (`backend/app/config.py`, Line 127):**
```python
    max_captures_retention_days: int = Field(14, ge=1)
```
