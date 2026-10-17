# Loading states implementation plan

Goal: distinguish first load, refresh, action, empty and failure states without changing BananaVision's design.
Scope follows the user's 2026-10-16 loading audit request; continue authorized implementation on main.

- [x] Audit routes, providers, operations and their API boundaries before implementation.
- [x] Reuse Skeleton for structured initial content; extend AppDataTable/AppStatsCard with optional loading flags.
- [x] Keep successful resource snapshots during selected filter/refresh operations, explicitly mark previous data, suppress stale mutations and reject late responses.
- [x] Add readiness/error states to admin/inventory consumers; initial failure must not appear empty.
- [x] Add local busy feedback/guards for actions, retaining stage/status feedback for hardware and maintenance.
- [x] Bound public scan/GET waits; preserve timeout vs cancellation distinction and retry paths.
- [x] Verify delayed, failed, empty, reordered, timed-out and duplicate-submission cases with mocked browser tests.
- [x] Run frontend suites, typecheck, lint, build; review diff and synchronize graph/documentation/progress. Existing connectivity/lint failures are documented, not represented as passing checks.

Review focus: successful empty snapshots during refresh; old responses after filters/account changes;
unknown action outcomes must not be presented as definite failure/success; initial API failures;
retained content must be identified as previous/stale rather than attributed to new filters.

No backend contract, schema or business-time changes are intended. Do not touch live devices or station data.
Existing authenticated/account-keyed providers and request revision guards remain authoritative.

2026-10-17 integration: user authorized commit/merge/push. Preserve incoming camera/inference
work and NumberField UI from origin/main; verify invalid scan counts and label quantities after blur. Final results
and known baseline failures are tracked in TASK_PROGRESS.txt and docs/audits/2026-10-17-loading-recheck.md.
