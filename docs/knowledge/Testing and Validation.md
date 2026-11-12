# Testing and Validation

Comprehensive guide to testing strategies, verification requirements, test runners, and isolation boundaries across BananaVision.

## Out-of-distribution rejection — 2026-11-13

Design, thresholds and limits are in [[AI Models]]; the kiosk state is in [[Frontend]].

- **Gate evaluation** (`backend/scripts/evaluate_ood_gate.py gate`, Open Images V7 pools,
  report `docs/audits/ood-gate-evaluation-2026-11-13.json`). Held-out benchmark: near-OOD
  frame rejection **96.72 % → 97.31 %**, far-OOD **99.86 % → 100 %**, generic banana frames
  accepted **90.07 %**, AUROC **0.976**, FPR at 95 % TPR **2.83 %**. Box support keeps
  **94.92 %** of annotated banana boxes and passes **7.3 %** of near-OOD and **0.16 %** of
  far-OOD object boxes. Thresholds were chosen on the calibration pool only.
- **Not measured:** per-cultivar precision/recall/F1 and Stage 2's own false-cultivar rate.
  The trained weights and labeled dataset are not in the repository; `pipeline` mode
  produces those numbers where they exist. No retraining was run.
- **Backend:** full suite **664 passed, 104 skipped** (PostgreSQL-only cases; no disposable
  cluster in this environment), against **582 passed, 104 skipped** on the preceding commit
  `e8825a5`. The 82 new tests cover gate logic, classifier filtering (including cluster-box,
  rotated-pass, canonical-rotation and occluded-finger-recovery cases), the 422/503/WebSocket contract, the audit row, the dataset script (leakage, path
  safety, truncated, incomplete and non-JPEG payloads, merge isolation), evaluation metrics,
  and the real COCO verifier on 12 synthetic frames (blank, noise, blur, yellow/green shapes).
- **Frontend:** 280 browser tests including 5 new kiosk cases. Full run **279 passed,
  1 failed** (397.1 s). The failure was `kiosk-pin.test.mjs` "PIN verification sends
  once…", which stopped in its own setup with `clock.pauseAt: Cannot fast-forward to the
  past`: it installs the page clock and then pauses it at a `new Date()` taken in Node, so
  the two clocks can race. The test, its fixture and the harness are unchanged by this
  work, and the file passed **15/15 on three reruns**. Typecheck and production build
  passed (existing >500 kB chunk warning); lint **40 problems (35 errors, 5 warnings)**,
  unchanged baseline.
- **Ruff:** new files clean. Changed backend files **43 findings, the same as on
  `e8825a5`**; no introduced diagnostic.
- **Review:** an independent design review before the tests, then four separate reviews
  of the finished change (correctness, security, API/UI contract, tests and documentation).
  They raised 20 concrete points; each was addressed, and code defects are pinned by
  regression tests. Seven tests were checked by mutation: replacing the full JPEG decode,
  removing the redirect refusal, removing the image-ID leak check, removing the shared
  notice id, and removing each of the three classifier gate hooks made the matching test
  fail. No Codex Security service scan was run.
- **Running the new tests:** `test_ood_gate_model.py` needs `ultralytics` and the tracked
  `backend/yolo26n.pt`; it skips where either is missing. No test uses the network, the
  station database, captures, cameras or sensors.
- **Tools:** Graphify CLI/graph, ICM and Context7 were unavailable in this checkout, so
  the graph and project memory were not refreshed. Ultralytics behaviour for empty label
  files was checked in the installed 8.4.40 source.

## Live Logs reconciliation finalization — 2026-10-25

- Reproduced four browser failures before the fix: deferred edits, missed reconnect edits,
  off-page KPI changes, and failed reconciliation recovery. All now have passing coverage.
- Full backend with disposable PostgreSQL 18: **681 passed, 0 failed, 0 skipped**, 55 known
  enum/model fixture warnings (217.32s). Focused integration first passed **53/53**. After
  test-only lint cleanup, reconciliation/mutation cases passed **19/19**, then mutation/time-write
  fixtures **44/44**. All four fresh clusters on loopback port 55449 stopped cleanly and were removed.
- The new PostgreSQL test uses independent Admin, owning Operator and other Operator sessions:
  committed revision/flag updates and exact stored prediction strings reconcile, other-account
  data stays absent, removed rows disappear, and original snapshots remain unchanged.
- Full frontend: **266 passed, 0 failed, 0 skipped** (338.09s). The strengthened focused-control
  case then passed **1/1**, explicitly waiting for a completed live read while focus remains held
  before proving values apply after blur. Cross-session tests use separate browser contexts and
  mock HTTP/WebSocket transport; this is not a browser-to-PostgreSQL hardware station run.
- Typecheck and production build passed (36.19s build; existing >500 kB warning). Frontend lint:
  **35 errors / 5 warnings**, unchanged baseline. Configured backend Ruff: **645 findings**;
  changed files **69 versus 72 at HEAD**, **no introduced diagnostics**. New regression files are
  clean. Test import/fixture lint issues from the interrupted work were corrected.
- Scoped source/security review covered snapshot ownership, role/token/generation binding, filter
  scope, expiry, immutable exports and exact risk decisions; no actionable new finding. No new
  Codex Security service scan was launched; this is source review plus isolated regression evidence.
- Graphify refreshed successfully: **4270 nodes, 12967 edges, 250 communities** after final test cleanup; SQL extraction
  remains unavailable because `tree_sitter_sql` is absent. No paid extraction enabled.
- Earlier PostgreSQL process failures were environment-bound: isolated runs with the necessary
  execution access now succeed. No live station data, camera, sensor, OS power or deployment used.

## Final integration verification — 2026-10-24

- Full isolated PostgreSQL 18.6 suite: **658 passed, 0 failed, 0 skipped** (173.87s). Focused notification/scan-log/write suites: **72 passed** (17.30s). After test-only import/fixture-name lint cleanup, all **7 notification tests passed** again (5.67s), including four simultaneous single/read-all combinations. Disposable clusters used loopback port 55447 were stopped after each run, and their generated cluster directories were removed after verification. No station environment or hardware was used.
- Full frontend command `node --test --test-concurrency=1 tests/*.test.mjs`: **248 tests, 231 passed, 17 failed, 0 skipped** (354.82s). Edge closed during Scan Records after 31 cases; all 17 errors were closed-browser/context errors. The file-only rerun reproduced that browser closure. A fresh-browser tail selection passed **18/18** (30.13s), covering every affected case, and the adjacent CSV-export/zero-count selection passed **3/3** (7.71s). Therefore all **248 distinct cases have passing evidence across partitions**, but a single uninterrupted Edge run remains an environment/harness limitation. No assertions were removed or relaxed to mask it.
- The updated connectivity file passes **5/5**, including late-callback rejection, reconnect and authentication lifecycle. Kiosk passes **18/18** in the full run. New expired-risk and ordinary-completion notification regressions pass **2/2**.
- TypeScript and production build pass (`npm run typecheck`, `npm run build`; build 24.32s). Existing bundle-size warning remains. Frontend ESLint: **36 errors, 5 warnings**, with diagnostic signatures matching HEAD. Configured backend Ruff: **620 baseline findings**; changed files have **67 versus 68 at HEAD**, no new findings, one existing long-line finding removed. Three introduced test-only Ruff findings were corrected and checked.
- Backend warnings: one Pydantic enum fixture warning, two scikit-learn artifact/runtime version warnings and 52 feature-name warnings. No model artifact or prediction logic was changed.
- Codex Security scan `9a6cf9e9-3384-47d0-a86f-7f980d354778` completed: **0 reportable findings**, all **28 inventoried source files** covered. Daybreak entitlement unavailable; supported scoped source review plus isolated regressions used. Scan identity remains the original working-tree target at `2da9d5c`; incoming receipt integration and final corrective edits received supplemental review.
- Graphify AST update: **4128 nodes, 12475 edges, 252 communities**, without graph loss. SQL extraction was unavailable (`tree_sitter_sql` missing); SQL/migration behavior was covered by source review and PostgreSQL tests. No paid semantic extraction was enabled.
- Pre-0010 v4 archives require recreation under the incoming pre-release policy. Historical results below describe earlier checkpoints, not the final integrated tree. Cross-client status/flag edits are now broadcast; see the cross-session sync verification below.

## Cross-session sync verification — 2026-10-24

- Scope: committed scan edits (flag, quality correction, inventory status, provenance, notes),
  intake status/bulk inventory, and supplier create/update now publish post-commit events to
  account-scoped rooms. Reconnect/focus/visibility/online reconciliation and sensor freshness were
  verified together.
- Backend `tests/test_mutation_events.py`: **7 passed**. It proves the event is emitted only after
  commit, carries revision and actor evidence, routes Admin to `dashboard` and the owning Operator to
  its account-scoped `kiosk` room without exposing another Operator's scans, emits one partial scan
  event per bulk-inventory change, and that sensor freshness uses recorded_at plus server time.
- Full backend suite (isolated SQLite fixture): **603 passed, 66 skipped, 1 warning**. The default
  pytest temp directory raises `PermissionError [WinError 5]` on this host, so an explicit
  `--basetemp` is required.
- Frontend `tests/crosssession.test.mjs`: **9 passed**, driving separate browser contexts for Admin,
  Operator A and Operator B against real providers and an account/room-aware WebSocket double. Cases
  cover flag propagation with actor suppression and Operator B isolation; Page 2 row patching with
  event-id dedupe and refresh-only-on-request; deferral of a remote edit while a control is focused
  (notice only, then apply after blur); Page 1 new-scan auto-refresh; Page 2 new-scan
  notice/Later/View Latest Scans; 410+409 snapshot recovery; intake/supplier propagation with
  `updated_at` ordering; reconnect reconciliation of scans, intakes, config, users and notifications
  with frozen rows preserved; and sensor stale/live/out-of-order/age-expiry handling.
- Full frontend browser suite: **263 passed, 0 failed, 0 skipped** (~277s).
- `npm run typecheck` and `npm run build` pass; only the existing >500 kB chunk warning remains.
  Frontend ESLint reports **40 problems (35 errors, 5 warnings)**; every remaining diagnostic is
  pre-existing debt, and this change set introduced none while removing one.
- `git diff --check` is clean. No live station database, captures, physical cameras or OS power was
  used.
- Historical limitation, superseded by the 2026-10-25 verification above: PostgreSQL-backed three-session runs. `BANANAVISION_TEST_DATABASE_URL` was unset and
  PostgreSQL 18 client backends on this host fail with `0xC0000142` followed by shared-memory error
  487. No physical Kiosk pair was exercised.
- The former missed-edit/KPI boundary is resolved by the authorized live reconciliation endpoint
  described above and in [[Frontend]]. Frozen page order and exports remain intentional.

## Live Scan Logs pagination verification — 2026-10-24

- Prior implementation run, full isolated PostgreSQL 18.6: **660 passed, 0 failed, 0 skipped** (216.46s, `127.0.0.1:55440`, `Asia/Manila`). This remains the implementation-time record; the independent re-verification below could not reproduce it because PostgreSQL 18 client backends terminate on this host with `0xC0000142` (followed by shared-memory error 487).
- Independent backend re-verification (SQLite contracts, fresh temporary working directory): full suite **596 passed, 66 skipped** (115.94s); focused `test_scan_logs.py` + `test_scan_snapshots.py` **37 passed** (5.66s). The focused total includes two added cases proving Admin/Operator pending scoping and pending **409** (changed filters) / **410** (expired or unknown snapshot) behavior. PostgreSQL-specific tests remain skipped and were not re-verified in this session.
- Frontend `tests/scanrecords.test.mjs`: **54 passed, 0 failed** (96.47s), including the two final regressions for hidden-tab deferral and a failed pending-count request retaining the frozen page. The full frontend suite before those additions was **252 passed, 0 failed, 0 skipped** (340.60s); both new cases then passed in the focused file.
- `npm run typecheck` and `npm run build` pass (build 15.00s); the existing >500 kB chunk warning remains. Frontend ESLint is unchanged at the **41-problem baseline (36 errors, 5 warnings)**; every diagnostic in a changed file also exists at HEAD.
- Backend Ruff on the five changed files reports **23 findings versus 25 at HEAD**, with no new findings; the change set resolves two pre-existing import-order diagnostics. Repository-wide Ruff with the backend configuration reports 645 findings; the five changed files introduce none.
- `git diff --check` passes. No live station database, captures, physical cameras or deployment was used. Disposable PostgreSQL clusters created during the attempt were stopped and removed.
- Cross-client status/flag edits are now broadcast; missed edits also recover through automatic
  live reconciliation (2026-10-25 follow-up above).

## Live-data and persistence audit — 2026-10-23

- Audited initial loading, refresh/resume, cache and snapshot invalidation, pagination,
  CRUD persistence, false-success prevention, lost updates and concurrent writes across the
  frontend, API, services, models and PostgreSQL behavior. Fixes and remaining boundaries are
  recorded in [[Resolved Bugs]] and [[Development Decisions]].
- Backend regressions cover Depleted-intake rejection under row locking, oversized
  `source_text`, notification ownership, bulk-intake status derivation, Kiosk intake restore,
  Logs snapshot-expiry recovery, dashboard date-preserving links and PostgreSQL seed
  precision. Seed tests use unique schemas and an explicitly disposable database.
- Final isolated SQLite suite: **586 passed, 62 skipped** (117.02s).
- Final disposable PostgreSQL 18.6 suite after the seed-fixture corrections: **648 passed**
  (236.89s, `127.0.0.1:55446`). The seed contract subset passed **24/24** (44.96s). The
  cluster and its temp data directory were stopped and removed.
- Browser coverage for the changed paths passed in focused runs: **70 passed** across
  `kiosk`, `scanrecords` and `scanlogfilters`, followed by the affected Dashboard and
  Analytics reruns. After the final Scan Detail edit, `scanrecords` passed **46/46**,
  including the new in-place refresh case. Full tracked suite runs finished **246 tests,
  243 passed** (about 414s) with the two pre-existing `connectivity.test.mjs`
  socket-isolation failures at lines 34 and 45 plus one intermittent
  `kiosk resets operator selection after ...` timing failure; the Kiosk file passes
  **18/18** in isolation and the flake is unrelated to the audited paths. All
  audit-related browser cases passed.
- `npm run typecheck` and `npm run build` passed. Configured frontend lint remains at the
  **41-problem baseline (36 errors, 5 warnings)**, with no count regression. Backend Ruff
  output remains dominated by pre-existing debt; reviewed changed lines add no >100-column
  violation. `git diff --check` passes.
- The PostgreSQL seed test fixture now supplies `camera_device_ids=[0, 1, 2, 3]`, loads the
  real configured spoilage model before recomputing predictions, and compares full-precision
  model output with a numeric tolerance when storage formatting differs. This corrected
  stale test assumptions; production seed/model behavior was not changed.
- Known boundary: cross-client status/flag edits are not broadcast to Logs. Incoming
  revision 0010 replaces the former shared broadcast read flag with per-user receipts. Sensor staleness, QR label formats, camera-apply ordering
  and intake-status PATCH last-write-wins remain unchanged. No live station database,
  captures, physical cameras, OS power, restore or deployment was used.

## Current schema reference — 2026-10-22

- Updated `docs/bananavision_schema_current.sql` to Alembic revision
  `0010_notification_read_receipts`. The reference omits `alembic_version` and pg_dump
  wrapper artifacts.
- Loaded the DDL into a fresh disposable PostgreSQL 17.10 database with
  `psql -v ON_ERROR_STOP=1`. The loaded schema has **25 application tables**, **198
  columns**, **7 enum types**, **20 foreign keys** and five sequence-backed `SERIAL`
  columns.
- Verified the normalized `device.slot_index`/`device_index` columns, the notification
  receipt composite primary key and foreign keys, the absence of
  `app_notification.is_read`, the absence of `system_config` camera arrays, operator scan
  counters and `alembic_version`.
- Compared the concise and detailed capstone dictionaries: 25/25 tables, 198/198 columns,
  7/7 enum types and 20/20 foreign-key references. Table, column, type, nullability, key and
  reference fields match; default notation differs by design (`—` in the detailed version).
- Backend regressions for the runtime and migration behavior are recorded in the
  per-user notification section below. `git diff --check` passed.
- No live station database, captures, physical cameras, OS power, restore or deployment was
  used. See [[Database]] for the current schema links.

## Per-user notification read receipts — 2026-10-22

- `backend/tests/test_notifications.py` verifies that a broadcast is stored once but its
  `read` state is per account, that marking it read is idempotent, that private
  notifications are visible only to their owner, that an unauthorized mark-read returns
  404 without creating a receipt, and that read-all creates receipts only for the current
  account's visible notifications.
- `backend/tests/test_migrations.py` verifies the `0010_notification_read_receipts`
  upgrade: private read flags become receipts for their owner, broadcast read flags become
  receipts for active accounts, unread rows remain unread, `read_at` is populated and
  `app_notification.is_read` is removed.
- `backend/tests/test_backup_archive.py` includes the new receipt table in the 22 archived
  application tables and verifies v4 round-trip behavior plus strict v1/v2/v3 adaptation.
- Targeted notification, migration and archive suites: **47 passed, 2 skipped**.
- Full backend suite from a fresh temporary working directory: **545 passed, 99 skipped,
  4 failed** (32.28s). The four failures are the pre-existing macOS power-control cases
  referencing `subprocess.CREATE_NO_WINDOW`; they are unrelated to notifications. Running
  from `backend/` loads the local `.env` and adds known CORS assertion failures; the
  fresh-cwd run is the isolated result. No disposable PostgreSQL URL was configured, so
  PostgreSQL-specific cases skipped.
- Ruff is clean on the new receipt model, migration, notification API and notification
  tests. The touched legacy modules retain their pre-existing I001/E501/SIM117 diagnostics;
  no new diagnostics were introduced.
- The frontend `read` boolean contract is unchanged, so no frontend source, test,
  type-check or build was rerun.
- Archive format remains v4 because this schema is pre-release. Local v4 archives created
  before this revision must be recreated.
- No live station database, captures, physical cameras, OS power, restore or deployment was
  used. See [[Resolved Bugs]] and [[Database]].

## CSV and XLSX exports — 2026-10-22

- `backend/tests/test_exports.py` covers 206-row exports beyond pagination, account scope,
  snapshot parity, empty workbooks, exact identifiers/whitespace, DECIMAL confidence,
  formula-like text, wrapping/width contracts, invalid formats, and NULL optional values.
  The NULL regression requires CSV and XLSX to leave missing cultivar, ripeness, confidence
  and shelf-life cells blank; `N/A` remains only when the whole classification/status block
  is absent. `test_scan_logs.py` retains CSV round-trip and numeric-prefix coverage.
- Backend full suites after the audit fix: **575 passed, 62 skipped** (75.72s) on isolated
  SQLite, and **637 passed, 0 skipped** (142.80s) on a disposable PostgreSQL 18.6 cluster
  (`127.0.0.1:55439`). The cluster and its temp data directory were stopped and removed.
  Export route tests still use SQLite fixtures; PostgreSQL coverage includes seed CSV export
  and the surrounding queries, not a PostgreSQL-backed XLSX route.
- Frontend full tracked suite: **241 passed / 3 failed / 0 skipped** (298.42s, 244 tests).
  The two known connectivity failures remain (`connectivity.test.mjs` lines 34 and 45).
  The third was a pre-existing Analytics clock race (`analytics.test.mjs` line 38); that
  file passes **9/9** in isolation (25.14s), and no export code participates. All
  export-related browser cases passed in the full run, including the 9 `clientexports` cases.
- `npm run build` (`tsc -b` + Vite) passed (16.34s). Configured lint reports the baseline
  **41 problems (36 errors, 5 warnings)**; Ruff on changed backend files reports only five
  pre-existing E501 findings and no new diagnostics. `py_compile` and `git diff --check` pass.
- The temporary `frontend/tests/probe-quality-debug.test.mjs` diagnostic was removed after
  approval. It was never tracked, had no assertions and was not referenced by the suite.
- No live station database, captures, physical cameras, OS power or deployment was used.

## Normalized camera slots and archive v4 — 2026-10-22

- `test_migrations.py` upgrades a legacy SQLite schema and verifies saved camera
  arrays become contiguous `device.slot_index`/`device_index` values, existing device
  identity/status is retained, unique indexes and range checks exist, and the dropped
  configuration/operator columns are gone. It also verifies the legacy inline
  `device.camera_id UNIQUE` is promoted to a named unique index before batch table
  recreation, so a duplicate camera name still raises `IntegrityError` after migration.
- `test_configuration.py` covers slot initialization and validation, legacy scalar-row
  selection, invalid-row rejection, rename/remap/expansion behavior, UUID preservation,
  failed-commit rollback, and cleanup of an unassigned row that collides with a reused
  camera name. The API still returns the existing comma-separated `camera_ids` and
  ordered `camera_device_ids` contract.
- `test_backup_archive.py` verifies v4 round trips plus strict v1/v2/v3 upgrades,
  including legacy camera arrays becoming slots, dropped fields disappearing, and
  invalid recorded legacy types being rejected before restore.
- Post-merge targeted export/scan-log/configuration/archive/migration suites:
  **97 passed, 2 skipped**, 1 warning (6.02s).
- Full backend suite from a fresh temporary cwd (documented isolation, so the station
  `.env` is not loaded): **541 passed, 99 skipped, 1 warning** (39.95s); the only 4
  failures are pre-existing macOS power-command tests that reference
  `subprocess.CREATE_NO_WINDOW` while `power_control.py` is unchanged. Running from
  `backend/` instead loads the station `.env` (`APP_CORS_ORIGINS=["*"]`) and adds
  unrelated CORS assertion failures; the CORS middleware and tests are unmodified.
  No disposable PostgreSQL URL was configured, so PostgreSQL-specific migration cases
  skipped; `0009_camera_slots` was exercised on isolated SQLite only.
- `npm run build` (`tsc -b` + Vite) passed in 3.46s. The API contract is unchanged, so no
  frontend source edits were required.
- Ad hoc `uvx ruff check backend` reports **649 findings versus 657 at `5dcbdda`**,
  predominantly existing E501/I001/F401 debt; new migration/archive long lines were
  corrected. No claim is made that every new line is lint-clean beyond the reviewed scope.
- `git diff --check` passed. No live station database, captures, physical cameras, OS
  power, restore, deployment or Git history operation was used.

## Current demo-seed regression coverage

`backend/tests/test_seed.py` runs only with an explicitly disposable
`BANANAVISION_TEST_DATABASE_URL`, using a unique PostgreSQL schema per case. It verifies
VPD from stored-precision readings, zero preservation, treatment/spoilage consistency,
original snapshots, synthetic actor history, consumer APIs, rollback, concurrent seeding
and default refusal of existing data. Explicit `--reset-demo` tests verify replacement of
application records, reapplied migration revision, unrelated-table preservation and rollback
to the previous records/schema on failure. Missing historical VPD and actor fixtures remain
intentional and must not be backfilled.

`test_setup_scripts.py` runs copied Windows/Git Bash scripts with fake installers/seeder,
checks exit statuses and existing `.env` preservation, and never runs workspace setup.
Setup/seed wrappers require Yes at an explicit deletion prompt before passing `--reset-demo`;
No/blank answers never invoke the seeder. Plain Python invocation still refuses existing data
with exit code 20. The wrapper tests verify confirmation, arguments, missing-script errors
and failure propagation; CLI tests verify that unexpected exceptions are not swallowed.
See [the seed audit](../audits/2026-10-19-seed-compatibility.md) and
[backend setup guidance](../../backend/README.md) for scope and limitations.

## Spoilage display and at-risk consistency — 2026-10-20

- `test_scan_logs.py` verifies raw boundaries (1.9999, 2, 2.00001), zero/overdue,
  overlapping ranges, missing/invalid estimates, stock status/provenance, Dashboard
  parity, sorted pagination, snapshot/refresh consistency and full CSV membership.
  The value 2.00001 rounds to 2 in the API's display estimate but remains **not at risk**.
- `test_seed_kiosk_contract.py` compares each generated/demo and mocked Kiosk record's
  risk-filter membership with the canonical detail remaining estimate and stock eligibility.
- Backend selected suites: 56 passed (17.04s); snapshot/predictor/legacy-snapshot
  follow-up: 28 passed (6.43s), including one repeated legacy case after its assertion
  was extended. Total distinct cases: **83**, no skips. Disposable PostgreSQL and
  isolated SQLite only; model tests use disposable synthetic artifacts.
- `node --test --test-concurrency=1 tests/scanrecords.test.mjs tests/dashboard.test.mjs
  tests/analytics.test.mjs tests/scanpages.test.mjs`: **71 passed**, no failures/skips
  (113.68s). New browser coverage verifies single-value cells, server-driven warning,
  KPI filtering, page reset, sorting and refresh. Mocked screenshot reviewed.
- `npm run typecheck` and `npm run build` passed (Vite 18.82s). Configured ESLint:
  37 errors/5 warnings; Ruff: 645 errors. Changed-file diagnostic comparisons match
  HEAD exactly (no new lint debt). Logs: ignored `frontend/node_modules/.tmp/bv-spoilage-*`.
- Focused access/snapshot/export review: existing account/role/filter bindings,
  expiry, CSV escaping and stock policy remain intact. Current response schemas have
  no `at_risk` field; warnings use membership in the existing snapshot risk filter.
  No DB migration, hardware access, model change or historical backfill.

## Numeric spoilage display formatting — 2026-10-21

- Root cause: Kiosk and other consumers interpolated `spoilage_days` directly after
  the predictor began preserving the full-precision model mean. Shared display-only
  whole-day formatting now handles numeric predictions, historical ranges, units,
  unknowns and zero. Sorting, risk predicates, API fields and saved values are unchanged.
- New browser reproductions failed before the fix (4 cases). Final affected coverage:
  **109 distinct cases passed**, including 29 formatter cases and 80 browser cases in
  `scanrecords`, `kiosk`, `persistence` and `public-scan`. The main run was 107 passed/2
  failed (136.90s); both failures were corrected assertions and passed focused reruns:
  the preview now says `3 days`, and the Inventory check must exclude the fixture's
  raw-state probe. No product change was needed for those assertion repairs.
- Browser coverage checks readable Kiosk result/recent cards, Logs, Details/history,
  QC, Inventory and unauthenticated QR tracking; unrelated corrections omit
  `spoilage_days` from writes. Risk warnings use snapshot membership without an
  `at_risk` response field and survive sorting, page changes, KPI filtering and refresh.
- TypeScript and production build pass (Vite 31.53s). Configured ESLint still reports
  37 errors/5 warnings; changed-file diagnostics match HEAD, and new TypeScript files
  have no diagnostics. Logs: ignored `frontend/node_modules/.tmp/bv-spoilage-format-*`.
- Backend/model/schema code was not changed. Prior checkpoint's 119 passing isolated
  backend tests remain applicable; they were not repeated for this display-only fix.
  No live data, physical hardware, model weights or historical predictions were changed.
- Final Codex Security diff scan `3ca86d46-6b2b-4208-a47d-8dc41a825460` completed for
  `0465a7a..a58dccf`: zero findings across eight runtime files and supporting tests/docs.
  Raw correction drafts, numeric risk calculations and public/authenticated boundaries
  were reviewed, including an independent architecture pass. This was not a full repository
  security audit; no live deployment or hardware was exercised.
- After integrating incoming `main` through `f3630e9`, affected Scan Records, Kiosk,
  Dashboard and layout browser suites passed 82/82 (146.98s); ISO-day units passed 3/3.
  Sandboxed Edge initially failed at launch; approved isolated execution outside the
  sandbox passed without source changes. Typecheck/build passed again (Vite 31.43s).
  Lint matches the incoming baseline of 36 errors/5 warnings. Application source matches
  incoming `main` exactly; both sides' checkpoint history and documentation are preserved.

## Testing Philosophy & Safety Rules

As mandated by `AGENTS.md` and `docs/development-workflow.md`:

1. **Isolation from Production Systems:**
   - **Never test against the live station database, captures, physical cameras, printer hardware, or OS power.**
   - All tests run against isolated mock fixtures, in-memory databases, or disposable PostgreSQL schemas.
   - Secrets, credentials, and live `.env` files must never be read or printed during test execution.

2. **Asia/Manila Timezone Requirements:**
   - Business operations and calendar boundaries operate on `Asia/Manila` (`UTC+8`).
   - Tests verify that midnight rollover transitions (`00:00:00` Manila) properly invalidate daily caches and advance the `business_date` without depending on client machine local timezones.

3. **Evidence Before Assertions:**
   - Verification commands must be executed and their output verified before asserting that any bug is resolved or feature is complete.
   - Distinguish existing pre-existing lint debt from newly introduced regressions.

---

## Backend Test Architecture

The backend test suite is built on **pytest** and **pytest-asyncio**, testing FastAPI routes, SQLAlchemy/asyncpg query services, YOLO/RFR model estimators, and business logic.

### Safe Execution Pattern
Backend tests must run from a fresh temporary working directory with the backend directory explicitly added to `sys.path`. This prevents test processes from accidentally loading `backend/.env` or writing SQLite/cache files into production paths.

**PowerShell execution from repository root:**
```powershell
@'
import os, sys, tempfile
from pathlib import Path
backend = Path('backend').resolve()
work = Path(tempfile.mkdtemp(prefix='bv-tests-'))
os.chdir(work)
sys.path.insert(0, str(backend))
import pytest
raise SystemExit(pytest.main([
    '-p', 'no:cacheprovider', '-q', '--basetemp', str(work / 'fixtures'),
    '-c', str(backend / 'pyproject.toml'), str(backend / 'tests'),
]))
'@ | & './backend/venv/Scripts/python.exe' -B -
```

### Disposable PostgreSQL Testing
For tests requiring PostgreSQL-specific constraints, advisory locks or schema migrations:
- Set `BANANAVISION_TEST_DATABASE_URL` to an isolated, disposable cluster.
- Each test run generates and drops a unique schema.
- Once tests conclude, the temporary cluster directory and port are stopped and removed.
- Suites using this isolation include `test_seed.py`, `test_setup_scripts.py`, and `test_seed_kiosk_contract.py` (which verifies end-to-end data propagation across Kiosk, Database, Scan Logs, Scan Detail, Dashboard, Inventory, Analytics, CSV Export, and QR Tracking).

---

## Frontend Test Architecture

The frontend uses Node.js native test runner (`node --test`) driving headless Chromium/Edge via Playwright, backed by isolated Vite dev servers and mocked API/WebSocket fixtures.

### Key Test Suites (`frontend/tests/`)

| Suite | Focus Areas |
|---|---|
| `dashboard.test.mjs` | KPI card loading, skeleton states, stale data detection, WebSocket re-connections, midnight rollover, `/logs` navigation routing |
| `scanrecords.test.mjs` | Scan logs data grid, snapshot token caching, filter criteria, CSV export, QC overrides, audit trails; recorded VPD precision/zero/missing data and isolation from live sensor updates |
| `analytics.test.mjs` | Summary KPI error alerts, model confidence isolation from `ScanOriginalAiResult`, date range aggregations |
| `maintenance.test.mjs` | System config, backup creation/validation/restore, shutdown/restart accessible button labels |
| `kiosk.test.mjs` & `kiosk-pin.test.mjs` | Operator intake workflow, action spinners, PIN verification, demo simulation |
| `printing.test.mjs` | Label printing queues, GDI driver recovery, Windows spooler error handling |
| `persistence.test.mjs` & `assigned.test.mjs` | One-time admin credential setup, role-based view scoping, session persistence |
| `scanlogfilters.test.mjs` | Unit tests for query string builders (`buildScanLogsUrl`) and filter parsing (`scanLogParams`) |
| `isoday.test.mjs` | Unit tests for the local calendar-day helpers (`parseIsoDay`, `formatIsoDay`) behind the Logs date filter `YYYY-MM-DD` values |
| `adminloading.test.mjs`, `loading.test.mjs`, `operationsloading.test.mjs` | First-load vs refresh/empty/error states, delayed reads after writes, read deadlines, notification account scope, operator-list recovery and sensor freshness |
| `crosssession.test.mjs` | Three isolated browser contexts (Admin, Operator A, Operator B): post-commit flag/edit propagation, account-scoped room isolation, event-id dedupe, frozen Page 2 row patching, new-scan notices, reconnect reconciliation, 409/410 snapshot recovery, timestamp-ordered intake/supplier merges and sensor freshness/out-of-order rejection |

### Running Frontend Tests

**From `frontend/` directory:**
```powershell
# When Playwright is not locally resolvable, set PLAYWRIGHT_MODULE to the existing
# installed playwright/index.mjs path. Do not install duplicate runtimes.
$env:PLAYWRIGHT_CHANNEL = 'msedge' # or an installed supported browser

# Run all browser regression suites:
node --test --test-concurrency=1 tests/*.test.mjs

# Run specific suite:
node --test tests/dashboard.test.mjs
node --test tests/scanlogfilters.test.mjs
```

### Static Analysis & Type Checking

```powershell
# TypeScript Typecheck (0 errors required):
npm run typecheck

# Production Vite Build (also checks the referenced TypeScript projects with tsc -b):
npm run build

# Configured Linting:
npm run lint
```

---

## Historical VPD regression coverage

- `backend/tests/test_scan_logs.py` checks authenticated list/export values, operator
  scope, frozen snapshot values and older snapshots without a VPD key. VPD is
  deliberately different from a value derived from the fixture's temperature and
  humidity, so accidental recalculation is detectable.
- `backend/tests/test_spoilage_models.py` checks existing kPa formula reference
  values and explicit VPD (including zero) passed into a synthetic six-feature model.
- `backend/tests/test_time_and_writes.py` checks detail/trigger serialization.
- Ten browser cases in `scanrecords.test.mjs` cover Logs/Details with `1.555`,
  `1.25`, zero, null and omitted VPD, including unchanged output after a newer sensor
  event. Mocked visual checks cover the desktop table/detail and mobile detail grid.

The [2026-10-18 VPD audit](../audits/2026-10-18-vpd-integration.md) records exact
results and separates pre-existing connectivity/lint failures from these passing
regressions. PostgreSQL tests require a disposable cluster; synthetic model tests
do not establish the deployed model's identity or prediction accuracy.

## Station Cultivar Recognition Protocol

The October 17 station case predicts a known Lakatan bunch as Lakatan from
Top/Right and Latundan from Left/Rear, with some wrong-view scores above 90%.
Raising a detection threshold does not establish correct cultivar recognition.
The current split-camera safeguard exposes uncertainty; it is not retraining.

1. Save original, unannotated copies of all four result images into a separate
   offline case folder. Keep the checkpoint hash, saved input resolution,
   inference settings and per-camera predictions. Browser screenshots with drawn
   labels/resizing are useful evidence but are not the original model inputs.
2. Record a trusted cultivar label and a stable physical `bunch_id`. Confirm the
   physical finger total separately, and annotate every visible finger in each
   image. Cultivar ground truth follows the same physical bunch across views;
   model predictions must not become training labels without human verification.
3. Collect additional independently identified Lakatan and Latundan bunches in
   the station setup, including all four angles, lighting/placement variations,
   ripeness coverage and overlapping fingers. Review cultivar labels with a
   knowledgeable person; preserve the source dataset and edit a training copy.
4. Split by physical bunch before augmentation. All views, repeat scans and dates
   of a bunch stay together. Use separate training, validation and untouched
   station test bunches. The already examined failing bunch is diagnostic data,
   not final independent accuracy evidence.
5. Fine-tune candidate weights offline with balanced class coverage; compare with
   the unchanged baseline on validation. Freeze the checkpoint and inference
   policy before evaluating the untouched station test cohort. Do not select a
   model solely because it fixes one bunch, or favor Top/Right without evidence.
6. Report per-view cultivar confusion, per-bunch cultivar decisions, incorrect
   accepted decisions and review/abstention rate. Report box precision/recall,
   visible-count MAE and exact physical-count rate separately. Review routing
   improves disclosure and must not be reported as recognition accuracy gain.

The prepared dataset's 137 VALID images occupy only three inferred filename
groups (`cardaba_1`, `lakatan_7`, `latundan_4`). Its 137 TEST images likewise occupy
three (`cardaba_6`, `lakatan_2`, `latundan_5`). These are grouping proxies with
uncertain physical identities; they do not prove either three or 137 independent
bunches. The existing checkpoint's training provenance is also incomplete.
This limits claims about unseen bananas despite high agreement with those labels.

Ultralytics recommends [representative data and annotation review](https://docs.ultralytics.com/guides/data-collection-and-annotation/)
and [testing in deployment conditions while avoiding leakage](https://docs.ultralytics.com/guides/model-testing/).
See [[Development Decisions]] for the implemented conflict/count safeguards.

## Knowledge & Decision Links

### Scan actor attribution verification (2026-10-19)

- `test_scan_trigger.py` exercises the real trigger/persistence/detail/history path with
  mocked hardware and SQLite: authenticated IDs/names, ignored forged actor fields,
  immutable names after rename, a second operator's scan and missing-profile rejection.
  Both Operator and Admin readers see the stored creation actor without a duplicate
  unattributed initial-status event. Final file run: 11 passed.
- `kiosk.test.mjs` verifies that account switches, same-account role changes and logout
  clear Kiosk selection and disable scanning; final file run: 10 passed. Scan Records
  browser coverage distinguishes saved creation actors from unknown legacy status actors.
- Affected backend suites initially passed 60 tests; after splitting reader roles, the
  final changed-file rerun makes 61 distinct passing cases with unchanged suites retained.
  The four affected browser suites initially passed 61 tests; splitting the three session
  cases makes 63 distinct passing cases across the original run and final Kiosk rerun.
- Typecheck and production build passed. Frontend lint remains 37 errors/5 warnings;
  backend Ruff remains 652 errors after fixing a new test closure warning. No runtime,
  schema, permission, UI or historical data changes were necessary.
- Scoped authorization/persistence review found no new boundary change: identity comes
  from the server session, history reads retain ownership checks, and old actorless status
  rows are not backfilled. This is a focused source/test review, not a repository-wide scan.
  Existing full-suite connectivity failures and unavailable PostgreSQL coverage remain
  separate historical limitations; no live station or hardware was used.

### Operator Performance verification (2026-10-19)

- `backend/tests/test_analytics.py`: 15 passed. Covers historical name changes, namesakes,
  role scope, original model confidence, zero/missing values, date boundaries and combined filters.
- `frontend/tests/analytics.test.mjs`: 9 passed. Covers column removal, retained tooltip,
  sorting, filters, empty selections, both roles and 1440px/390px responsive layout.
- Related Dashboard, Scan Records and Time/Writes backend suites: 59 passed. Browser
  Dashboard, Scan Records and Operation Loading suites: 48 passed. Fixtures are isolated.
- TypeScript and production build passed. Configured frontend lint remains 37 errors/5
  warnings; backend Ruff remains 652 errors. Changed-file diagnostics match HEAD.
- Full-suite connectivity failures and PostgreSQL skips are historical baseline limits,
  not results of these focused runs. See [the operator audit](../audits/2026-10-19-operator-performance.md).

- [[Frontend]] — UI architecture, component patterns, and loading state conventions.
- [[Development Decisions]] — Architectural choices regarding snapshot retention and review queues.
- [[Resolved Bugs]] — Confirmed defect root causes and regression test references.
- [[Home]] — Knowledge base index.
- [2026-10-17 loading recheck](../audits/2026-10-17-loading-recheck.md) — current verification results, baseline failures and coverage limits.

## Finger-count inflation regression (2026-10-21)

- Synthetic Top/Left/Right/Rear counts 7/9/10/13 reproduced the previous fused 21. Regression cases now require an estimate of 13, review on positive-count disagreement, original per-camera counts, and unchanged classification confidence. Legacy fusion settings, camera labels, equal counts, duplicate boxes, and partial views are covered.
- Backend: 171 passed across `test_classification_fusion.py`, `test_scan_trigger.py`, `test_top_view_inference.py`, `test_detection_sensitivity.py`, and `test_time_and_writes.py`. The trigger regression checks the API/detail response, committed SQLite record, original AI result, and completion event. Models, cameras, printing and events use fixtures/mocks; tests run from a fresh temporary directory without loading the station `.env`.
- Kiosk browser: 17/17 passed, including estimated 13, review feedback and unchanged per-camera evidence. Typecheck and production build passed.
- Frontend lint retains 36 errors / 5 warnings; backend Ruff reports 640 findings. Comparison against HEAD confirms no new diagnostics in affected backend files; the modified browser test passes scoped ESLint.
- No station camera test, PostgreSQL run, detector retraining or physical-count accuracy validation performed. The user reports approximately 15 fingers; the fix prevents cross-view additions and does not claim to recover hidden fingers. See [[Development Decisions]].


## System Configuration layout verification (2026-10-21)

- `tests/maintenance.test.mjs`: 20 passing mocked browser cases, including camera mapping,
  revision conflicts, cross-tab save/discard, immediate-cleanup draft preservation, global
  reset, restore dialog confirmation/dismissal guards, backup persistence and power recovery.
- `tests/layout.test.mjs`: 9 passing cases in the full run. SystemConfig covers all four
  tabs, independent app scrolling, a reachable save bar and bounded restore dialog at
  1280×650, 1024×600 and 390×700. The final three-case recheck also verifies the replacement
  button remains reachable after mock archive validation expands the dialog.
- Optional `SYSTEMCONFIG_SCREENSHOT_DIR` writes local QA screenshots; screenshot animations
  are disabled to avoid capturing a faded-out dialog under the fixture's paused clock.
- Full frontend run: 233 passed / 2 failed. Existing, unchanged connectivity tests fail on
  the StrictMode shared-socket count (6 versus 1) and disconnect/retry socket-count timeout.
  The first failure reproduces independently; no SystemConfig component participates in it.
- Typecheck and production build pass. Lint exactly matches the prior 41 findings
  (36 errors, 5 warnings). No live hardware/database/maintenance testing was performed;
  backend tests were not rerun for this frontend-only change. See [[Frontend]].
