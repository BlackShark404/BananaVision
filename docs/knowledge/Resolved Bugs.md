# Resolved Bugs

Documented log of confirmed bug root causes, verified solutions, and test coverage in BananaVision.

## 2026-11-13: Cardaba misclassification, V2 checkpoint Top profile bypass, and radial flank undercounting

- **Symptoms:**
  - Cardaba bunches placed on the Kiosk platter with the crown at the bottom of the Top camera frame (`18925BD8-B4A9-47FA-89CE-829A91362C6C`) were misclassified as `Lakatan` (`82.7%`).
  - 15-finger two-tier bunches reported `8` (`53.3%`) or `11` (`73.3%`) fingers instead of `13–14` (`86.7%–93.3%`), and `"Est. Fingers"` was abbreviated on Kiosk, Logs, and Quality Control.
- **Root causes:**
  - `TOP_CALIBRATED_CHECKPOINTS` in `backend/app/services/classification.py` lacked the SHA-256 digests for `banana_yolovsV2.pt` and `banana_yolovn26V2.pt`, disabling both `iou=0.65` overlap refinement and the `180°` rotation pass on the live station.
  - Even when rotation fallback ran, `classification.py` discarded Pass 2 (`180°`) votes on overlapping boxes and kept Pass 1 (`0°`) as primary, even when Pass 2 (`180°`, matching the crown-at-top training orientation) had a higher-confidence `Cardaba` consensus (`0.948` vs `0.939`).
  - `_is_same_class_sub_box`, `_unique_box_detections`, and `_is_cluster_box` suppressed diagonal neighboring fingers in radial fans because their axis-aligned rectangles overlapped without sharing a longitudinal centerline, while partially occluded flank/tier fingers (`conf 0.31–0.46`) were dropped by the `0.50` primary cutoff.
  - `FusionEngine.fuse` allowed lower-confidence peripheral tip views to override a multi-finger overhead Top anchor and did not compensate for the `2–3` self-occluded second-tier fingers on 4-camera multi-tier scans (`baseline_max` in `8..12`).
- **Fixes:**
  - Added both V2 checkpoints to `TOP_CALIBRATED_CHECKPOINTS`, implemented canonical `180°` orientation promotion when Pass 2 has higher peak confidence and unconflicted consensus, restricted sub-box suppression to longitudinally aligned fragments (`_is_axially_aligned_or_enclosed`, `min_area / max_area <= 0.72`), guarded `_is_cluster_box` by `1.6 * median_area`, and added a TTA occluded flank recovery pass (`augment=True, conf=0.25, iou=0.70` with `_is_recovery_duplicate`) for calibrated bunches with `>= 5` primary fingers.
  - Updated `FusionEngine.fuse` so a multi-finger (`>= 4`) Top anchor with higher confidence than competing peripheral views prevails cleanly, while keeping `final_fingers = max(finger_counts, default=0)` so `Estimated Fingers` always equals the actual maximum detected camera bounding-box count rather than clamping to a fixed `14` offset.
  - Renamed `"Est. Fingers"` to `"Estimated Fingers"` in `Kiosk.tsx`, `Logs.tsx`, `QualityControl.tsx`, and `kiosk.test.mjs`.
- **Verification:**
  - Verified on the four uploaded Kiosk screenshots: Scan 0 (`Latundan`, Rear `12` boxes / `80.0%`), Scan 1 (`Lakatan`, Top `11–12` boxes), Scan 2 (`Cardaba`, `88.3%` confidence, `conflict=False`), Scan 3 (`Lakatan`, Top/Right `11–12` boxes, Rear `10–11` boxes, no fixed `14` clamp), and across all 168 validation/test Top-view dataset images (`168/168 = 100%` cultivar accuracy).
  - Backend suites `test_top_view_inference.py`, `test_classification_fusion.py`, `test_scan_trigger.py`, and `test_time_and_writes.py`: **165 passed**. Frontend typecheck and production build passed.

## 2026-11-12: Duplicate create rows from live-event races and enum text in activity details

- **Symptoms:** creating a supplier showed the same UUID twice in Supplier Management/Inventory and
  inflated the active-supplier KPI. Delivery intake creation had the same race. Profile and Activity
  Log rendered enum member names such as `RoleEnum.OPERATOR` and `IntakeStatusEnum.DEPLETED`.
- **Root causes:** the post-commit `supplier:changed`/`intake:changed` event could reach the browser
  before the create HTTP response. `InventoryContext.addSupplier`/`startIntake` appended the
  response row without checking whether the id already existed. Audit `details` f-strings
  interpolated `str, Enum` members; on this runtime `str()` renders `EnumName.MEMBER`.
- **Fixes:** create responses now upsert by id, merging into a row already applied from the live
  event. `users.py` and `intakes.py` activity details use `.value`.
- **Verification:** new persistence regression tests hold the create response until after the
  matching event and then assert exactly one row and the correct active intake (17/17 suite).
  `test_time_and_writes.py` asserts activity details contain `Operator`/`Depleted`, not enum reprs.
  Full backend on disposable PostgreSQL: **645 passed, 37 skipped**. Full frontend suite, typecheck
  and production build passed; live UI confirmed one supplier row and the corrected activity text.
  See [[Testing and Validation]] and [[Frontend]].

## 2026-10-24: Cross-session mutation sync and sensor freshness

- **Symptoms:** a scan edited in one session (flag, correction, status, note, provenance) stayed stale in
  other sessions until a manual refresh; intake and supplier changes behaved the same way. Device Status
  could label a reading **Live**/**Optimal** because only `sensor_connected` was checked, even when
  `recorded_at` was minutes old.
- **Root causes:**
  - Scan edit endpoints persisted mutations but emitted no events, so other authenticated sessions had
    no invalidation signal. Where a signal existed, it was either a coarse refresh that discarded the
    frozen Logs snapshot or arrived before the transaction had committed.
  - `recorded_at` existed in storage but was not compared against the actual polling interval, and the
    client trusted the workstation clock.
- **Fixes:**
  - `backend/app/ws/mutations.py` publishes post-commit `scan:changed`, `intake:changed` and
    `supplier:changed` events to account-scoped rooms. `mutate_scan`, intake and supplier endpoints now
    commit explicitly before broadcasting.
  - Frontend consumers merge by stable ID and revision (or `updated_at` for intakes/suppliers), reject
    stale payloads, drop duplicate `event_id`s and reconcile on reconnect/focus/visibility/online.
  - Logs patches a visible frozen row instead of replacing the snapshot, and only raises a notice when
    an edit lands during an active edit or focused control.
  - Sensor payloads carry `server_time` and `stale_after_seconds` (`max(3 × polling interval, 15)`).
    Device Status computes age from the server clock, advances it monotonically, rejects out-of-order
    readings and delayed untimestamped initial fetches.
- **Second-order regression caught and fixed:** accepting legacy payloads without `recorded_at` was
  necessary for compatibility, but they must display with unknown freshness and can never be **Live**
  or **Optimal**; the first implementation dropped them entirely.
- **Verification:** backend `test_mutation_events.py` 7 passed; full backend 603 passed / 66 skipped.
  Frontend `crosssession.test.mjs` 9 passed in three separate browser contexts, including deferral of
  a remote edit while a control is focused; full browser suite 263 passed. Details and the PostgreSQL
  gap are in [[Testing and Validation]].
- **Follow-up resolved 2026-10-25:** missed edits and KPI changes now reconcile automatically through
  an authorized live read of the frozen page IDs plus whole-filter metrics. Deleted/inaccessible/
  filtered-out rows disappear on reconciliation, focused controls defer values until blur, and
  rounded event values cannot invent at-risk membership. Page order and frozen exports remain
  unchanged. See [[Frontend]] and the latest [[Testing and Validation]] results.

## 2026-10-24: Final integration corrections

- **Expired risk membership:** Logs could reuse at-risk IDs from an expired snapshot after retrying with a new one. The retry clears the old membership, keeping the replacement rows, indicators and snapshot counts aligned.
- **Ordinary completion refresh:** Notification invalidation previously depended on the initiating HTTP response. Accepted, deduplicated WebSocket completions now refresh notifications in other authenticated sessions as well.
- **Concurrent read receipts:** Simultaneous single/read-all requests could both attempt the same composite key. Conflict-safe database insertion preserves incoming per-user ownership and the first read timestamp; four overlapping request combinations are tested against PostgreSQL.
- **Late socket callbacks:** A closed hook could still deliver open/message callbacks after cleanup. Socket ownership checks now reject them. Connectivity tests assert the actual per-hook/query-token protocol, excluding Vite's development socket, rather than an obsolete shared/auth-first-message assumption.
- **Kiosk test readiness:** The operator-reset test now waits for the asynchronous intake selection to enable Scan Now before asserting readiness; the product workflow is unchanged.
- **Verification:** PostgreSQL 658 passed; final notification-only rerun 7 passed. All 248 frontend cases passed across the full run and fresh-browser partitions. The full Edge run recorded 231 passes/17 browser-closure errors; the affected tail passed 18/18 in a fresh browser. See [[Testing and Validation]] for exact limitations and lint baselines.

## 2026-10-23: Live-data, persistence and refresh audit

- **Issues**:
  - A scan could be saved against an intake that had just been marked `Depleted`.
  - A completed scan could be processed more than once because the Kiosk/Dashboard WebSocket rooms and the HTTP response all delivered it; later HTTP fields then raced the stored record.
  - Scan Logs treated an expired browse snapshot as a terminal refresh failure, did not invalidate the snapshot for live scan changes, and used a different stock population from Inventory.
  - A personal notification could be marked read by an account that did not own it.
  - Reloading the Kiosk did not restore the open `Active` intake, so another intake could be created.
  - Bulk inventory status could set an intake back to `Active` even when every resulting scan was sold or spoiled.
  - Activity Log showed the raw timestamp, the Delivery Intake toast claimed complete success for partially skipped scans, and the Kiosk Accept copy implied the scan had not already been saved.
- **Root causes and fixes**:
  - `trigger_scan` now locks and rechecks the intake status before persisting; inactive intakes return `409` and propagate their message instead of a generic pipeline error. `source_text` is capped at 100 characters in the request schema to match storage.
  - Intake list counts use a grouped subquery with `noload(Intake.scans)`; bulk inventory derives the resulting intake state from the final scan statuses (including the empty-intake case).
  - `ScanProvider` deduplicates completion IDs, merges newer HTTP `print_job`/`print_error` revisions, and emits a coarse scan-changed event. Logs invalidates its snapshot on that event, refreshes on resume, and retries an expired/superseded snapshot once without the token. A `stock_eligible` filter keeps Logs, Inventory and stock links on the same eligibility rule.
  - Notification single-read updates require the notification owner or a visible broadcast; incoming revision 0010 isolates broadcast read state per account.
  - The Kiosk restores the newest active intake on load. Dashboard resume refresh is immediate but timestamp-throttled, and Scan Detail refreshes in place on focus/visibility/30 seconds while aborting and pausing during edits; failed background reads keep the current record instead of replacing it with a skeleton.
  - Activity Log formats in Asia/Manila, Delivery Intake reports the actual skipped/recorded outcome, and Kiosk/QC labels now describe the persisted state. `OperatorProfile.scans` and `UserAccount.activity_logs` use `lazy="raise"` to prevent implicit full-history loads on auth reads.
- **Verification**: Isolated SQLite **586 passed, 62 skipped** (117.02s); disposable PostgreSQL 18.6 **648 passed** (236.89s, port 55446, stopped and removed). Seed contract suite **24 passed** (44.96s). Full tracked browser suite runs: **246 tests, 243 passed** (about 414s), with the two existing `connectivity.test.mjs` socket-isolation failures at lines 34 and 45 plus one intermittent unrelated `kiosk resets operator selection after ...` timing failure; the Kiosk file passes **18/18** in isolation and `scanrecords` passes **46/46** including the new in-place refresh case. `npm run typecheck` and `npm run build` passed; configured lint remains at the **41-problem baseline (36 errors, 5 warnings)**. `git diff --check` passed.
- **Remaining boundary**: The former shared broadcast read flag was superseded by incoming revision 0010 per-user receipts. Status/flag edits made by another client are not broadcast; Logs can show them until its snapshot refresh/expiry. Sensor staleness, QR label formats, camera-apply ordering and intake-status PATCH last-write-wins were left unchanged. No live station database, captures, physical cameras, OS power, restore or deployment was used.

## 2026-10-22: Shared broadcast notification read state

- **Issue**: A flagged-scan notification was stored once with `USER_ID = NULL`, so its single `IS_READ` value was shared by every account. Marking it read for one user marked it read for everyone. The single mark-read endpoint also looked up notifications by ID only, allowing a user to mark another user's private notification read.
- **Root Cause**: `scan_service` created one global `scan_flagged` row, while `APP_NOTIFICATION` stored only one read flag. The single mark-read route lacked recipient scoping.
- **Fix**: Notification content remains in `APP_NOTIFICATION`; per-user read state now lives in `APP_NOTIFICATION_READ`, keyed by `(NOTIFICATION_ID, USER_ID)` with `READ_AT`. A null `USER_ID` is a broadcast, and `scan_flagged` creates one such row; `scan_complete` remains private to its operator. The list derives `read` from the current account's receipt. Single mark-read returns 404 for invisible notifications and inserts only the current account's receipt; read-all does the same for all visible notifications. Migration `0010_notification_read_receipts` creates the table, preserves existing private read flags for their owner and broadcast read flags for active accounts, then drops `IS_READ`. The downgrade is blocked because receipts cannot be reconstructed. The frontend `read` field is unchanged.
- **Verification**: `backend/tests/test_notifications.py` covers per-user broadcast read state, idempotent mark-read, private visibility, unauthorized mark-read returning 404 without mutation, and read-all isolation. `backend/tests/test_migrations.py` verifies the receipt backfill and `IS_READ` removal. Targeted notification, migration and archive suites: **47 passed, 2 skipped**. Full backend from a fresh temporary cwd: **545 passed, 99 skipped, 4 pre-existing macOS power-control failures**. See [[Testing and Validation]].
- **Archive note**: Archive format remains v4 because the schema is pre-release. Local v4 archives created before this revision must be recreated; v1/v2/v3 adapters drop the removed shared flag while retaining notification content.

## 2026-10-22: NULL optional values in XLSX exports

- **Issue**: Scan Logs XLSX wrote the literal text `None` for a NULL original shelf life. System Configuration XLSX wrote `None` for NULL cultivar/ripeness and `N/A` for a NULL confidence even when a classification record existed; CSV wrote blanks for the same values.
- **Root Cause**: The XLSX row builders stringified optional values unconditionally (`str(value)`) and treated NULL confidence like an absent classification.
- **Fix**: XLSX now emits blank cells for NULL optional fields. `N/A` remains reserved for a wholly absent classification/status block, matching CSV.
- **Verification**: `backend/tests/test_exports.py::test_xlsx_null_optional_values_are_blank_like_csv` failed before the fix (`None`/`None`/`N/A`) and passes afterward. Full backend runs: 575 passed/62 skipped on SQLite and 637 passed/0 skipped on a disposable PostgreSQL cluster. See [[Testing and Validation]] and [[Frontend]].

## 2026-10-21: Extra document scrolling on Logs and Activity Log

- **Issue**: On short screens, the whole application could scroll away, exposing blank space below the sidebar in addition to the main content scrollbar.
- **Root cause**: `PaginationEllipsis` contained an absolutely positioned `sr-only` label without a positioned ancestor inside the scroll area. Its position below the table extended the document height (1,487px in a 650px viewport), despite the app shell's `overflow-hidden`.
- **Fix**: Added `relative` to the ellipsis container so its hidden label stays inside the pagination control. No global overflow lock, page layout or row-count change was needed.
- **Verification**: All six `tests/layout.test.mjs` cases failed before the fix and pass afterward, covering Logs and Activity Log at 1280×650, 1024×600 and 390×700. Tests confirm document bounds, independent main/table scrolling, reachable pagination and stationary desktop sidebar. See [[Frontend]] and [[Testing and Validation]].

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

### 10. Overhead Top-Camera Cultivar Anchoring and Peripheral Background Filtering (2026-10-19)
- **Issue**: Latundan and Lakatan bunches suffered from 2-vs-2 camera split deadlocks where noisy peripheral camera views (Left and Rear) disagreed with the clear overhead Top view, triggering `cultivar_conflict` and forcing Kiosk to display "Uncertain". Additionally, peripheral side cameras looking out into open backgrounds detected non-banana objects (e.g. vertical door jambs detected as `Lakatan Overripe - 76%`).
- **Root Cause**:
  1. Peripheral cameras looking out horizontally have open backgrounds with vertical wooden door frames and ceiling fixtures that mimic elongated brown/yellow banana fingers.
  2. The fusion engine previously treated all cameras identically with symmetric majority voting. When Left and Rear cameras dissented due to background noise or severe backlighting, the 2-vs-2 tie resulted in `no_camera_majority` and `cultivar_conflict`, blocking scan-level cultivar harmonization and triggering the Kiosk "Uncertain" safeguard.
- **Fix**:
  1. Implemented peripheral camera background filtering in `classification.py`: suppressed detections on Left, Right, and Rear views that are either completely within the upper background ($y_2 < 0.22 \cdot H$) or slender vertical pillars touching the top edge ($y_1 < 0.08 \cdot H, h/w \ge 2.5, y_2 < 0.65 \cdot H$).
  2. Implemented Top-Camera Cultivar Anchoring in `fusion_engine.py`: when the overhead Top camera has a confident, unconflicted detection ($\ge 50\%$ confidence, $\ge 1$ finger, `not conflict_detected`), it anchors the bunch cultivar. Peripheral split/tied camera disagreements are resolved by the Top anchor without triggering `no_camera_majority` or `cultivar_conflict`, unless a competing cultivar has a strict camera majority ($> 50\%$).
  3. Added settings `top_camera_cultivar_anchor` and `yolo_peripheral_background_filter` in `config.py`.
- **Verification**: 102 passed in targeted fusion & top-view tests; 76 passed in scan & write tests; clean frontend typecheck and production build (`tsc -b && vite build`).

