# Testing and Validation

Comprehensive guide to testing strategies, verification requirements, test runners, and isolation boundaries across BananaVision.

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
