# Scan Logs and Scan Detail verification

Verified on 2026-10-10 (Asia/Manila), branch `codex/scan-record-hardening`.
Implementation reviewed and tested through `4094852`, against task base `e3e1c07`.
The finalization commit containing this report changes documentation and removes a
machine-specific test helper; it does not change production behavior.

The [approved plan](../superpowers/plans/2026-10-09-scan-records-follow-up.md) is complete
for implementation and isolated verification. No push, merge, deployment or live
station acceptance was performed. The existing maintenance implementation and the
logout fix `1a13e0b` remain intact. No reverted commits were replayed.

## Implemented and preserved behavior

| Requirement | Result and regression evidence |
| --- | --- |
| Complete dataset browsing/export | Existing SQL search, intersecting filters, sorting, pagination and full filtered CSV export retained. `test_scan_logs.py` covers equal-key page boundaries, ownership, null/numeric sorting, literal search and export across stream batches. |
| CSV safety | CSV round trips cover Unicode, commas, quotes, CR/LF/CRLF and formula prefixes, including preceding whitespace. Existing source-name trimming is preserved. Numeric values remain numeric. |
| Authorized access | Detail, legacy list, history, notes, mutations and evidence share persisted ownership/role checks. Administrators can access all scans; Operators only their own. Private notes and note history remain Admin-only. Authentication/revocation tests use real generated credentials. |
| Historical detail | Stable-ID backend loading works without shared-list membership and hydrates detections, original AI, notes and history. Stored camera IDs/labels and historical timestamps are used. Existing Asia/Manila conversions remain unchanged. |
| Inventory and classification | Status changes use the dedicated status operation, intended status, reason and revision. Source-only/no-op/status/flag/note edits do not mark classification overridden. Actual classification changes preserve the original AI snapshot, including unknown values. |
| Concurrent writes and retries | Transactions bind request UUIDs to actor, resource, action and payload. CAS rejects stale writes. Receipts replay before revision rejection. PostgreSQL regressions exercise simultaneous writers, exact retries, actor/session revocation, parent intake locking, membership changes and bulk/single conflicts. |
| Audit history | Persisted events contain revisions, actor snapshots, timestamps, reasons and previous/new values. Legacy status/note evidence is merged deterministically without duplication or invented metadata. New scans record initial history. |
| Schema/archive compatibility | Migration 0005 preserves existing rows and nullable classification data. Version-2 archives include history, receipts and deletion evidence; strict frozen version-1 validation/upgrade remains supported. PostgreSQL restore, compensation, recovery login and session invalidation regressions pass. |
| Missing/deleted evidence | Authenticated image delivery replaces static capture access. Shared image loading handles missing/unavailable files while detail remains usable. Authorized known deletions return 410; unknown absence is 404; inaccessible records return 403 without protected contents. Old deletions without a ledger cannot be inferred. |
| Frontend race/error handling | ScanContext and affected Logs, Detail, Quality Control, Kiosk and Delivery Intake callers use the revised contracts. Late reads cannot regress saved revisions/notes; obsolete searches are ignored. Conflicts preserve drafts and offer reload. Bulk responses update caches using returned revisions. |
| Uncertain writes | Explicit **Retry previous** replays the retained original body/UUID across navigation and changed drafts. A successful replay updates caches and clears only the submitted note draft. Definitive rejection neither clears the draft nor invokes a success callback. Auth lifecycle cleanup invalidates old pending retries. |
| Kiosk event privacy | All scan progress, capture, detection, completion and failure events are scoped to the initiating account or a currently authorized Admin. Session/role checks happen at delivery; another Operator does not receive scan data. |
| Existing UI/maintenance | Existing layouts, classes, components, navigation and timezone helpers are retained. Changes add necessary reason/history/error/retry content and authenticated image fallback. Maintenance changes are limited to required archive/schema integration; existing maintenance regressions remain green. |

Historical evidence uses saved actor/source/camera information where recorded. Unknown
legacy values remain unknown. Existing directory-label lookup behavior for ordinary
Logs/source filters was retained; it is not used to invent historical audit evidence.

## Final executed verification

| Check | Actual final result |
| --- | --- |
| Full isolated backend, including PostgreSQL | **222 passed, 71.19 seconds, exit 0**; no skipped PostgreSQL cases |
| Full frontend tests, serial execution | **54 passed, 0 failed, 0 skipped, 60.2775 seconds, exit 0** |
| TypeScript application check | **Exit 0** |
| Production TypeScript/Vite build | **Exit 0**, Vite build 9.44 seconds |
| Configured full ESLint | **43 errors, 8 warnings**, all existing at task base; **0 introduced diagnostics** |
| Configured full Ruff 0.16.10 | **620 diagnostics**, versus **660** at task base with the same version/config; **0 introduced diagnostics** |
| Scoped source/test/plan diff whitespace check | **Exit 0** |

The full backend run includes `test_scan_records.py`, `test_scan_records_postgresql.py`,
`test_scan_evidence.py`, `test_scan_logs.py`, migrations, archives, maintenance PostgreSQL
acceptance and existing security/time/write tests. The frontend run includes all six
browser suites plus `scanwrites.test.mjs`; `scanrecords.test.mjs` exercises the actual
Logs, Detail and Delivery Intake components with mocked APIs.

Backend command, run from the repository using its Python interpreter (all application
imports occur only after changing into a fresh OS temporary working directory):

```powershell
@'
import os, sys, tempfile
from pathlib import Path
b = Path('backend').resolve()
w = Path(tempfile.mkdtemp(prefix='bv-scan-final-lint-'))
os.environ['BANANAVISION_TEST_DATABASE_URL'] = 'postgresql+asyncpg://bvtest@127.0.0.1:56845/postgres'
os.chdir(w)
sys.path.insert(0, str(b))
import pytest
raise SystemExit(pytest.main([
    '-p', 'no:cacheprovider', '-q', '--basetemp', str(w / 'fixtures'),
    '-c', str(b / 'pyproject.toml'), str(b / 'tests'), '--tb=short',
]))
'@ | & './backend/venv/Scripts/python.exe' -X utf8 -B -
```

That URL identified the disposable test cluster, which has now been stopped and
removed. A future run must create and verify a new disposable instance rather than
assume anything at that port is a test database.

Frontend command from the repository root:

```powershell
$env:PLAYWRIGHT_MODULE='C:/Users/Roronoa Zoro/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
node --test --test-concurrency=1 frontend/tests/*.test.mjs
```

From `frontend`, type/build commands were `npx tsc --noEmit -p tsconfig.app.json`
and `npm run build`. Browser fixtures use localhost and mocked API responses.

Configured ESLint was run through `ESLint.lintFiles(['.'])`, equivalent to the
configured `eslint .` target. Baseline comparison used `lintText` on exact `e3e1c07`
contents at the same file paths/configuration. Ruff was run as
`ruff check --config backend/pyproject.toml --output-format json backend/app backend/tests`;
the exact baseline files were extracted into a disposable directory and checked with
the same tool/config. Diagnostic comparisons used file, rule and source-line content
to avoid treating line shifts as new errors. Task-introduced diagnostics were fixed;
unrelated lint debt was not refactored. The earlier checkpoint's 654 Ruff count is
superseded by the reproducible 660 baseline above. Neither full linter exits cleanly.

Earlier migration and CSV failures were test-fixture defects: the synthetic legacy
schema lacked its `scan` parent table, and a CSV expectation ignored existing source
trimming. Browser fixtures had outdated field/button expectations, a too-short parallel
startup timeout and a selector targeting a covered toast. Those failures were corrected
and are covered by the final passing runs. They are not unresolved failures.

## Security and final review

Codex Security scan `c49fcb93-82d3-4452-8183-9be1cf9571e9` is **completed**, with
38 changed source-inventory files reviewed and **zero newly introduced reportable
findings** in its immutable range:

```text
e3e1c07c49a6041ae57f9acbfa4add0a51d263a6
  ..1a13e0b6adf36ebfbd8a15e6b524b86e98536372
```

Canonical report, manifest, coverage, findings and SARIF are retained in the Codex
Security local scan store. This scan does **not** claim to cover the later `4094852`
snapshot. Its inherited kiosk broadcast finding was excluded from *diff-introduced*
findings after comparison with the base; the vulnerability was nevertheless fixed in
this task and tested for owner/Admin/other-Operator delivery and role changes.

A separate independent review covered the production/schema changes and supporting
authorization/archive/WebSocket paths. It identified uncertain-retry reachability,
stale bulk cache, fabricated zero-day original spoilage, note revision regression and
kiosk privacy issues. Those were corrected with focused regressions, followed by the
full suites above. Follow-up identified note-replay draft clearing and false success
callbacks after a rejected retry; both were fixed and browser-tested.

The final optional independent follow-up hit the account usage limit. The primary
agent directly reviewed those last corrections, their callers and regression tests;
there is no claim of an additional completed independent pass after those corrections.
No unresolved material finding remains from the completed reviews. Review and tests
reduce risk; they are not a guarantee that no defect exists.

The scan service reports aggregate session accounting of 9,201,206 tokens (9,165,749
input, 35,457 output, including 8,694,528 cached input across two threads). This includes
resumed conversation accounting and is not a measurement of incremental scan cost.

The scoped diff retains all existing maintenance/logout changes and contains no old
commit replay. Source/test whitespace verification passed. The full branch also includes
the user's existing scratch/logout artifacts and two historical checkpoint lines with
trailing whitespace; those unrelated/historical contents were preserved.

## Cleanup and limits

- Verified the exact recorded PostgreSQL root, `postmaster.pid`, PID 50664 and port
  56845 before stopping it with `pg_ctl -D <recorded data directory> -w stop`.
  Stop succeeded; PID file was absent and the port had no listener afterward.
- Removed all 26 exact recorded task-generated OS-temp directories, including the
  stopped cluster, test fixtures, isolated Ruff installation and lint comparison data.
  Every resolved absolute path was checked before deletion. The separate failed sandbox
  test directory was already absent.
- Removed six generated Vite fixture caches and `backend/tests/.scan-pg-path.txt`.
  Preserved user scratch/logout files, normal build output and durable security artifacts.
- No live `.env`, operational database, station captures, camera, hardware, retention,
  restore or power operation was used. Physical camera/OS behavior remains deferred
  by the user's explicit decision; this is not a deployment acceptance report.
- No push, merge or deployment. Keep this branch for the user's integration decision.

The compact [checkpoint](../../TASK_PROGRESS.txt) is authoritative for the next session;
superseded checkpoints in `docs/history` are historical evidence, not pending work.
