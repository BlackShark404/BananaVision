# Resolved Bugs

Documented log of confirmed bug root causes, verified solutions, and test coverage in BananaVision.

## 2026-10-16: Loading States & Frontend Robustness Audit

### 1. Analytics KPI Refresh Failure Stale Values
- **Issue**: When an Analytics refresh failed, previous summary cards remained visible without clearly signalling the failed refresh state.
- **Root Cause**: `Analytics.tsx` computed summary cards even when `resource.error` was populated, bypassing the error alert.
- **Fix**: Nullified `summary` when `resource.error` is present so the `<Alert variant="destructive">` with `<Button onClick={resource.reload}>Retry</Button>` is rendered directly.
- **Verification**: `tests/analytics.test.mjs` ("failed Analytics refresh shows an error with retry instead of stale values").

### 2. Dashboard Review Link Predicate Truncation
- **Issue**: Dashboard review links navigated to `/logs?attention=review&status=Flagged`, accidentally excluding unreviewed low-confidence scans from the review queue.
- **Root Cause**: `Dashboard.tsx` added `status: "Flagged"` to review query links.
- **Fix**: Removed `status: view === "review" ? "Flagged" : undefined` from `legacyScanLogsUrl` and `openRecords` to ensure the complete review predicate (`attention=review`) is used.
- **Verification**: `tests/dashboard.test.mjs` ("legacy review links use the complete review predicate").

### 3. Oversized 413 Snapshot CSV Export
- **Issue**: In `Logs.tsx`, if a scan log snapshot was too large (HTTP 413 Payload Too Large), the CSV export button was disabled because `response` was null.
- **Root Cause**: The export trigger was guarded by `response !== null`.
- **Fix**: Allowed export when active query filters exist (`canExport = response !== null || hasActiveFilters`), allowing direct server-side filtered export.
- **Verification**: `tests/scanrecords.test.mjs` ("an oversized snapshot still permits a complete filtered CSV export").

### 4. SystemConfig Button Accessible Labels & Error Alert
- **Issue**: In `SystemConfig.tsx`, when shutdown or restart were requested, the button labels were replaced with status strings ("Shutting Down..."), breaking accessible tests expecting "Shutdown Now" and "Restart Now". Additionally, application errors like "Camera 0 failed" were not rendered in a role="alert" container.
- **Root Cause**: In-button text replacement and missing alert container for `config.applicationError`.
- **Fix**: Preserved button text ("Shutdown Now", "Restart Now") with `disabled={powerPending}`, and added an `<Alert variant="destructive" role="alert">` displaying the specific application error.
- **Verification**: `tests/maintenance.test.mjs` (14/14 passed).

### 5. Windows CP1252 / UTF-8 Mojibake in Frontend Files
- **Issue**: Several frontend components had corrupted characters (`0x85` horizontal ellipsis, `\u00e2\u20ac\u2014` em dash, `\u00c2\u00b7` middle dot) caused by inconsistent Windows encoding during prior edits, causing decode errors and Playwright regex failures.
- **Root Cause**: Double-encoded UTF-8 strings or raw CP1252 bytes written into files.
- **Fix**: Systematically normalized all corrupted characters across 11 frontend files to clean UTF-8 literals (`…`, `—`, `·`).
- **Verification**: Successful AST parsing in `graphify update .`, clean `npm run typecheck`, and 100% test pass rate across 101 tests.

### 6. Kiosk Operator Action Feedback Missing Spinners
- **Issue**: In `Kiosk.tsx`, clicking `Start Intake Session` or `Flag for Review` disabled the buttons without visual progress indication, leading to uncertain operator state on touchscreen kiosks.
- **Root Cause**: Submit buttons lacked conditional `<Loader2>` spinners and dynamic busy labels.
- **Fix**: Added `<Loader2 className="animate-spin" />` and dynamic labels (`"Starting Intake Session…"`, `"Flagging..."`).
- **Verification**: `tests/kiosk.test.mjs` (4/4 passed).

### 7. Quality Control Refresh Phrasing & Note Metadata Corruption
- **Issue**: In `QualityControl.tsx`, background scan refresh claimed to be `"Loading complete scan history…"` even when records were already loaded. In addition, note timestamps contained mojibake `â€¢` instead of bullet `•`.
- **Root Cause**: Static string conditional on `scansLoading` without checking `scansReady`, plus double-encoded UTF-8 bullet byte sequence.
- **Fix**: Rendered `scansReady ? "Refreshing scan history…" : "Loading complete scan history…"` and replaced `â€¢` with clean `•`.
- **Verification**: `tests/scanrecords.test.mjs` (15/15 passed).

### 8. Station Backup & Restore Critical Action Feedback
- **Issue**: In `StationBackupControls.tsx`, `Create Backup`, `Validate Backup`, `Replace Station Data`, and `Check Operation Status` disabled on `busy` without identifying which action was running or displaying a spinner.
- **Root Cause**: Generic `busy` state flag without action-specific button indicators.
- **Fix**: Added action-matching `<Loader2 className="animate-spin mr-2" />` spinners and active verb labels (`"Creating Backup…"`, `"Validating Backup…"`, `"Restoring Station Data…"`) and an enhanced status bar.
- **Verification**: `tests/maintenance.test.mjs` (14/14 passed).

## 2026-10-18: Multi-Camera Cultivar Disagreement & Bounding Box Inconsistencies

### 9. Side-Camera Cultivar Ambiguity, False Saucer Lip Detection & Finger Counting
- **Issue**: Side cameras (Right, Left) produced rogue Latundan detections on Lakatan bunches due to edge-on perspective foreshortening. The Rear camera detected the brown wooden tray lip on the turntable as an extra banana. Massive cluster boxes engulfed multiple individual fingers, and peripheral finger counts were inaccurate.
- **Root Cause**:
  1. Foreshortened, blunt edge-on views of curved Lakatan fingers on side cameras visually mimic Latundan in YOLO weights, producing dissenting labels even when Top and overall consensus decisively confirmed Lakatan.
  2. The wooden saucer edge on the Rear camera had an elongated horizontal aspect ratio ($w/h > 2.0$) at the bottom of the frame ($y_1 > 0.55 \cdot H$) with marginal confidence ($< 0.60$).
  3. YOLO produced both individual finger boxes and enclosing cluster boxes that engulfed multiple distinct fingers.
  4. Peripheral finger fusion in `fusion_engine.py` used restrictive flank bounds ($0.38$ / $0.62$).
- **Fix**:
  1. Added scan-level cultivar harmonization in [scan_service.py](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/scan_service.py): when the bunch achieves decisive cultivar consensus without conflict (`not fused.cultivar_conflict`), dissenting detection records and bounding box `cls` labels are harmonized to the verified bunch cultivar.
  2. Added table lip / saucer edge suppression on Rear view in [classification.py](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/classification.py).
  3. Added multi-finger cluster box suppression `_is_cluster_box` in [classification.py](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/classification.py).
  4. Adjusted flank cutoffs in [fusion_engine.py](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/fusion_engine.py) ($0.42$ / $0.58$) and exposed `cultivar_conflict` on `FusedResult`.
- **Verification**: 112 passed in targeted backend suite; full backend 484 passed, 38 skipped; `tsc -b && vite build` passed; `scanpages.test.mjs` 12/12 passed; verified clean 11-finger Lakatan detection and saucer removal on capture `10d7c3df` and across all 5 offline test placements.

