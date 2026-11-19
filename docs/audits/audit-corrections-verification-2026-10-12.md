# Audit corrections verification — 2026-10-12

The authorized correction scope is implemented and verified on **main**. The original
[2026-10-10 audit](system-audit-2026-10-10.md) is historical characterization, not a list
of current failures. This follow-up records the approved decisions and current evidence.
It does not authorize deployment or live acceptance.

Implementation commits: `65b9de0`, `893cae8`, and `6b1006d`; the final verification commit
contains this report, scoped lint corrections, the credential-rotation test and checkpoint.
Printer commits `c4d44c0`/`8b0f605`, maintenance, scan hardening and logout remain preserved.
No branches/worktrees, reverts, cherry-picks, pushes, merges or deployments were performed.

## Finding disposition

| Finding | Final disposition and acceptance evidence |
| --- | --- |
| F01 / F04 | Review shortcuts use the complete review predicate; daily group links retain the selected Manila day and stable identity. Dashboard browser/backend regressions pass. |
| F02 | Inventory uses server eligibility and remaining life, ages estimates from server risk time, distinguishes unknown/invalid from zero and overdue, and includes eligible unlinked FIFO stock. PostgreSQL/Python parity and Inventory browser cases pass. |
| F03 | One shared server policy excludes deleted-intake, depleted, sold, spoiled/processing and ambiguous unverified/excluded stock. Valid active genuinely unlinked stock is eligible. Removed records are not resurrected; no new deletion workflow/status was added. Migration0006 and archive adapters preserve known origins and quarantine unknown legacy links. Admin reconciliation requires reason, revision, current authorization and idempotent request identity, preserves stock status, and writes history without inventing relationships. |
| F05 | Operator success KPI opens all-time successful records under the exact server predicate/account scope; NULL confidence remains excluded. |
| F06 | Analytics source/date/cultivar/status filters intersect consistently across summary/operator metrics and the documented fixed 14-day trend. Backend and browser combinations pass. |
| F07 | Intake failures have explicit unavailable/stale/retry states, including successful empty snapshots. Late reads cannot overwrite accepted local writes. |
| F08 | Deployment guide now names migration0006 and archive v1/v2/v3 rehearsal. Current-model adoption and legacy schema upgrades preserve evidence. |
| F09 / G03 | Maintenance polling cancels scheduled work on unmount and rejects old responses after newer recovery results. Existing server admission remains intact. |
| G01 | History and Logs support frozen, account/session/role/filter/station-generation-bound snapshots, deterministic ordering and ten-minute expiry. Same-snapshot CSV exports the complete captured population independent of page. Explicit refresh/filter changes create a new capture. Expired/invalid captures fail explicitly; retry cannot silently publish mixed pages. |
| G02 | Current Dashboard/Logs confidence is labelled distinctly from original AI confidence in Analytics. Analytics displays definition/time/range metadata; Inventory's all-time Sold label is accurate. No measured human accuracy is invented. |
| G04 | Approved no-delete workflow retained. Existing historical hard-delete limitations remain documented; no universal post-delete audit ledger is claimed or introduced. |
| G05 | Shared intake registry retained as approved; scan counts are Operator-owned or Admin-global. Inventory's existing name-based source selector remains a display grouping, not an authorization boundary or a newly invented supplier identity. |
| G06 | Isolated SQL, browser, concurrency, migration, archive and API acceptance completed. Production volume/storage, physical hardware, real power and deployment acceptance remain deferred. |

## Final regression evidence

All backend imports ran **after changing to a fresh generated temporary cwd**, with the
resolved backend directory on `sys.path`; station `.env` was never read. PostgreSQL tests
used only a new disposable cluster bound to 127.0.0.1:49828 and uniquely named test schemas.
Browser fixtures use mocked API/WebSocket traffic, local Vite with `envFile:false`, and
explicit test API configuration. No real cameras, captures or power controls were used.

| Executed check | Actual result |
| --- | --- |
| Full backend, including PostgreSQL: venv Python `-X utf8 -B`; `pytest -p no:cacheprovider -q --basetemp <temp>/fixtures -c <backend>/pyproject.toml <backend>/tests --tb=short` | **244 passed**, 0 failed/skipped, **137.50s**. Includes maintenance HTTP restore/recovery, concurrent mutations, migration0006, archive compatibility, eligibility and snapshots. |
| Full frontend: `PLAYWRIGHT_MODULE=<installed runtime>`; `node --test --test-concurrency=1 tests/*.test.mjs` | **72 passed**, 0 failed/skipped, **109.900s**. |
| After final lint/import changes and one added credential-rotation test: same isolated pytest harness, `test_scan_snapshots.py test_audit_corrections_postgresql.py test_backup_archive.py test_migrations.py` | **48 passed**, 0 failed/skipped, **23.57s**. The earlier full suite is reused for unchanged behavior; this is not represented as a second full run. |
| After Logs callback dependency adjustment: browser `--test-name-pattern='provenance conflict\|Logs retains\|oversized snapshot' tests/scanrecords.test.mjs` | **3 passed**, 0 failed/skipped, **14.570s**. |
| `npm run typecheck`; `tsc -b`; programmatic Vite `build({envFile:false,logLevel:'warn'})` | All passed, exit0; final output `PRODUCTION_BUILD_PASSED`. Earlier full build also passed in8.46s. |
| Configured Ruff0.17.0 `check backend/app backend/tests` | **613 existing diagnostics**, exit1. Changed-file comparison against pre-correction `d1e0220` found **zero introduced diagnostics** after focused formatting/import fixes. No broad autofix. New PG/snapshot tests and migration0006 separately pass lint. |
| Configured ESLint `lintFiles(['.'])`, same configuration/scope as `npm run lint` | **42 errors, 8 warnings**, existing debt. Per-file baseline comparison found **zero introduced diagnostics**. |
| Final source/diff checks | `git diff --check` passes. AST comparison against tested `6b1006d` confirms backend formatting preserves runtime expressions; changes are import ordering and explicit equal-length `zip(strict=True)`, exercised by snapshot regression. |

## Reproduced failures and corrections

- A provenance conflict reload erased the review reason. The draft now belongs to the
  keyed parent record and survives reload; retries use the refreshed revision.
- Oversized browse rejection disabled CSV. Full filtered streaming export is now still
  available when no browse snapshot can be captured, without presenting partial rows.
- Independent review identified opposite scan lock ordering between history capture and
  intake bulk writes. A real PostgreSQL test reproduced it with distinct accounts and
  a blocked low-ID row. Both paths now lock in ascending scan ID order, then history
  sorts the captured values for display. The test also exposed stale ORM relationships
  preloaded before the wait; `populate_existing=True` refreshes those under the locks.
- v2 archives already contain history; the new v2 test initially reused v1's zero-history
  expectation. The correction verifies v1 has no fabricated events and v2 retains its
  real event/receipt. Both versions and current v3 pass isolated restore tests.
- SQL and Python interpreted uncommon Unicode padding differently. Both now use the
  existing explicit whitespace set, retaining unknown estimates consistently.
- One intermediate generated restore fixture timed out running existing `whoami` after
  five seconds during a long host-delayed run. No production timeout was weakened.
  Targeted rerun4 passed and the full244-test run passed without recurrence.
- Early new test fixtures used an incorrect status field and nonexistent Removed enum;
  these setup errors were corrected to actual existing contracts, then the parity defect
  above was reproduced and fixed. They are not reported as production defects.

## Security and scoped review

An independent read-only review covered provenance reconciliation, frozen archive
adapters, migration mapping, snapshot authorization/filter binding and exports. It found
one lock-order issue, reproduced and fixed as above. Its follow-up invocation was blocked
by the subagent account usage limit; no follow-up independent approval is claimed.
The primary agent completed the final scoped source/diff review and targeted verification.
No new durable Codex Security scan is claimed for this correction scope.

Current-account locking, owner/role checks, credential version and durable station
restore generation prevent reuse of a privileged snapshot after account changes.
Cross-account rejection, credential rotation, expiry, filter mismatch, invalid tokens,
quota eviction, row/byte overflow and mutation consistency have executable regressions.
Provenance writes keep existing Admin/CAS/idempotency/audit protections; known deleted
origins cannot be relabelled as unlinked. Strict v3 validation rejects inconsistent
provenance; legacy adapters preserve available history. CSV retains quoting, Unicode and
formula-prefix protections. No additional confirmed security finding remains in this scope.

## Limits and deployment prerequisites

- Snapshots last ten minutes and are limited to four per account, 50,000 rows and20MiB
  serialized payload each. Overflow rejects capture; it never publishes a partial set.
  Expired data is reclaimed on the next capture. Snapshots are excluded from backups.
  Large full CSV without a token reflects the export query time, not an earlier page.
  Production-scale sizing, disk/memory behavior and end-to-end interrupted downloads
  still require a separately authorized deployment rehearsal.
- Migration0006 conservatively marks legacy NULL-linked stock unverified. An Admin must
  examine real evidence and record reconciliation reasons after rollout. No historical
  relationship is reconstructed or stock silently deleted/status-changed.
- Before deployment, take a recoverable station backup, rehearse migration0006 and
  v1/v2/v3 restore on an isolated copy, then approve coordinated deployment and live
  acceptance separately. Real storage permissions, installer behavior, device mappings,
  physical cameras/sensors and OS power/autostart were not exercised here.
- Existing lint debt and the approved no-delete/historical deletion limits remain.
  Current implementation/testing completion is not blanket production acceptance.

## Cleanup and Git

The recorded disposable PostgreSQL instance was verified by its postmaster PID43032,
exact data directory and port49828 before `pg_ctl -D <exact data> -m fast -w stop`.
Shutdown succeeded; the listener was absent. Only its generated cluster and18 other
exact task-generated temp roots (including the disposable Ruff installation) were removed.
The two recorded empty sandbox setup directories were already absent. No unrelated
process, database, runtime installation or station data was stopped or removed.

The active [checkpoint](../../TASK_PROGRESS.txt) and its [archived execution ledger](../history/2026-10-12-audit-corrections-verification-checkpoint.txt)
record the final state. The final local commit is on main; use `git log -1` and
`git status --short` to verify its identity and cleanliness rather than a stale checkpoint SHA.
