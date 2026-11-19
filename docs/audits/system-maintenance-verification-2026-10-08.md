# System maintenance final verification — 2026-10-08

Production corrections are in user commit `d99c772`, following `931b54b`, `e4dc9cc`
and `9f2dba2`. The final local changes add the PostgreSQL HTTP regression, fix the
camera-apply test's token-version fixture, correct deployment/retention documentation,
remove machine-specific test residue, and streamline repository guidance. No reverted
Scan Logs/Scan Detail product changes were restored. UI components/styles were untouched
in this final continuation.

## Four final review findings

| Finding | Correction | Evidence |
| --- | --- | --- |
| HTTP admission was not installed | Production installs `StationAdmissionMiddleware` inside CORS | Actual ASGI recovery requests are blocked; actual HTTP backup completes with PostgreSQL advisory locks |
| Cancel could overtake power scheduling | Request and cancellation share `_power_lock` | Event-controlled dispatch/cancel ordering regression |
| Queued controls retained stale authority | Original token and current Admin/password are checked using fresh sessions after locks and draining | Generation, token-version and role-revocation tests; independent source review of backup/restore/apply/recovery/power paths |
| Initial camera probe could kill monitoring | Initial state is acquired within the regular retry loop | Blocked-start and failed-persistence-before-broadcast tests |

The independent final reviewer rechecked all four fixes and reported no residual
Critical/Important findings within that scope. The reviewer did not independently rerun
the root agent's tests or exercise real hardware.

## Fresh checks

| Check | Result |
| --- | --- |
| Complete backend suite, including disposable PostgreSQL | **186 passed**, 54.57 s |
| Complete frontend browser suites | **38 passed**, 47.88 s |
| `npm run typecheck` | Passed |
| `npm run build` (`tsc -b` and Vite) | Passed; Vite 12.47 s |
| Scoped frontend ESLint | 0 errors; 1 existing AdminContext hook warning |
| Full frontend ESLint | 43 errors, 8 warnings in existing code |
| Full configured backend Ruff 0.16.10 | 654 existing diagnostics; no added diagnostics from the final test changes versus `d99c772` |
| Final test syntax, project TOML and documentation links | Passed |
| Scoped diff / `git diff --check` | Reviewed / passed |

The backend suite ran from a new temporary CWD with the backend on `sys.path`, an explicit
temporary pytest base directory, and the isolated PostgreSQL URL. It did not load the
station `.env`. Browser suites used mocked API fixtures. Final formatting/link/config
changes did not alter runtime behavior; those received targeted syntax/document checks.
Full lint is **not green**. Existing lint findings were not hidden or bulk-autofixed.

## Security review

Codex Security scan `7c3170e8-68cb-4b5c-acaa-5fa94ac258ec` is completed and sealed. It covers
the earlier immutable working-tree snapshot based on `58d7337`, not the later fixes.
Its two retained findings are queued authorization (medium) and missing admission (low).
Power/camera failures were retained as correctness issues rather than escalated into
unsupported security claims. No direct archive exfiltration was demonstrated.

The report is in the local Codex Security workbench at:

`C:/Users/Roronoa Zoro/.codex/state/plugins/codex-security/scans/BananaVision/58d73375afee15507768c2226ef0516b4b9dc2bb_20261007T184734Z_mpr58yvf/report.md`

Use current correction anchors in `app/main.py` (middleware registration),
`api/v1/maintenance.py` (`fresh_authorization`), `services/backup_restore.py`
(`backup`/`restore`), `services/power_control.py` (`_power_lock`), and
`core/startup.py` (`camera_health_monitor`). Historical report line offsets/excerpts can
differ from this checkout. The sealed historical report remains unchanged; the current
corrections were verified separately by the tests and independent review above.

Tool-reported cumulative scan usage: 8,942,054 total tokens; 8,908,834 input tokens,
including 8,167,040 cached input tokens. This is the workbench's multi-thread measurement,
not a new charge or a cost estimate.

## Cleanup and limits

The identified disposable PostgreSQL instance on port 56843 was stopped successfully.
Twenty verified task-generated temporary directories were removed, including that
cluster, test fixtures and the isolated Ruff installation. Temporary lint reports and
the tracked `.maintenance-pg-path.txt` machine-specific helper were removed. No station
database, captures, camera hardware or OS power action was used for testing.

Real physical-camera initialization, real host shutdown/reboot privileges, deployed
storage permissions and interruption by actual power loss remain unverified here.
These require a separately authorized deployment acceptance check. Automated tests
cover mocked camera/power failures and isolated storage/database recovery boundaries.

## Acceptance follow-up and repository audit — 2026-10-09

The full HTTP acceptance test was committed in `b6d69e7`, after the final verification
commit `7e83cf7`. Its isolated PostgreSQL run finished with **12 passed in 27.78 s**.
This supplements the earlier 186-test full-suite run; it is not a new combined count.
The production ASGI routes (without the hardware-owning lifespan) exercised backup
creation, download, archive validation, rejection of an unconfirmed restore, confirmed
restore, restored database/evidence contents, rejection of the pre-restore session,
and successful login with the restored credentials. The existing separate integration
test covers administrator-only, read-only login during recovery mode.

On 2026-10-09 the repository was clean at `1f0eded`. That commit changed the archived
checkpoint only. The current checkpoint's pending-commit message was stale: the
acceptance implementation was already committed. No maintenance production code has
changed since `d99c772`; the later changes are tests, documentation and workflow files.
No new full-suite execution was warranted for this documentation audit.

Cleanup was checked again: the disposable PostgreSQL cluster directories for ports
56843 and 56844, the acceptance Ruff directory and the machine-specific test helper are
absent; no matching acceptance/final-test temporary directories remain. `netstat`
reported no listeners on either disposable port (the sandbox denied the CIM-based
network query). Current acceptance-test AST parsing and `git diff --check` passed.
The user explicitly chose to keep live tests deferred. Existing lint debt and the
physical-camera/OS/deployment limitations above remain; no production operations were
performed. The approved implementation and isolated acceptance work are finalized.
