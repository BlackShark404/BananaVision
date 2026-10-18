# Testing and Validation

Comprehensive guide to testing strategies, verification requirements, test runners, and isolation boundaries across BananaVision.

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
