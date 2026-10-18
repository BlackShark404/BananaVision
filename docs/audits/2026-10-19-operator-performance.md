# Operator Performance audit — 2026-10-19

Scope: complete the interrupted Analytics table correction on `main`, based on
`70afc3cc86784bd18b25293d82b42c31006f7250`. No commits, merges, pushes or deployment.

## Findings and changes

The permission premise was partly incorrect: Operators can flag their own scans through
Kiosk and the backend flag endpoint. QC corrections, notes and provenance reconciliation
are Admin-only. Scan Detail hides its QC controls from Operators. Other operators' scan
reads/writes remain forbidden by persisted account/profile ownership checks.

| Action | Operator | Administrator |
| --- | --- | --- |
| Analytics | Own scan population | Station-wide population |
| Flag scan / update inventory status | Own scans | Accessible scans |
| QC correction, review notes, provenance reconciliation | Forbidden | Allowed |

Evidence: `backend/app/api/deps.py`, `backend/app/api/v1/scans.py`,
`backend/app/services/scan_records.py`, `backend/app/services/dashboard.py`,
`frontend/src/pages/Kiosk.tsx` and `frontend/src/pages/ScanDetail.tsx`.

Flag Rate and QC Overrides count scan states, not the actor who performed an action.
Flags can also be generated automatically (`scan_service.py`, `fused.auto_flagged`).
The table now omits these two columns and their local UI mappings. Legacy response
fields remain present in both API schemas/types for compatibility. No permissions or
QC/scan mutation behavior changed.

The table retains **Total Scans**, **Avg Confidence**, and the existing valid-sample
tooltip. Average confidence describes model output associated with the scans, not
operator accuracy. No replacement metric was added: the current data does not provide
a reliable measure of scan speed, attempts, or independent review completion. The existing
sample-count context is useful without introducing an unsupported performance measure.

The backend previously grouped by historical operator-name snapshots as well as ID,
splitting one person's historical activity into several rows. `_operators` now joins the
already scoped scan subquery to the current profile/account by primary keys, groups by
stable operator ID/current account name and username, and preserves all original
source/cultivar/status and Asia/Manila date conditions. Both Analytics endpoints use this
same aggregate. Distinct operators sharing a name remain separate; historical snapshots
are not rewritten. The original-AI-result confidence population is unchanged.

The table retains its components, avatars, badges, spacing, typography, name/numeric
sorting and responsive horizontal scroll container. Zero and missing confidence remain
distinct. VPD, loading, scan/model/printer behavior and all other pages are untouched.

## Verification

All runtime tests use mocked/disposable fixtures, never production data or hardware.

| Check | Actual result |
| --- | --- |
| RED column regression | Failed as expected: old six columns instead of four |
| RED stable-ID regression | Failed as expected: four rows for two operators |
| `node --test --test-concurrency=1 tests/analytics.test.mjs` | 9 passed, 28.44s |
| Isolated `pytest tests/test_analytics.py` | 15 passed; final test-cleanup rerun 2.79s |
| Isolated Dashboard / Scan Records / Time and Writes pytest suites | 59 passed, 12.62s |
| Browser Dashboard / Scan Records / Operation Loading suites | 48 passed, 54.02s |
| `npm run typecheck` | Passed |
| `npm run build` (`tsc -b` and Vite) | Passed; Vite 15.15s |
| `npm run lint` | Existing 37 errors, 5 warnings |
| `ruff check backend/app backend/tests` | Existing 652 errors |
| Changed-file lint comparison against HEAD | No diagnostic increases |
| `git diff --check` | Passed |

The analytics tests exercise namesakes, historical names, current-name display, preserved
snapshots, original model confidence, zero/null/invalid confidence, empty datasets, both
roles, both endpoints and combined source/cultivar/status filters across Today, 7 Days,
30 Days and All Time, including boundary/future timestamps. Browser tests preserve the
sample tooltip, sorting and filter updates. Real-route scan tests verify Operator flag
permission, rejection of other operators' scans and rejection of Operator corrections.

Mocked desktop (1440px) and mobile (390px) screenshots were inspected. Table content
remains accessible through its existing scroll container with no page-level horizontal
overflow. Local images and verification logs are in ignored
`frontend/node_modules/.tmp/bv-operator-*`.

## Security and limitations

Codex Security's scoped patch-risk review found no new blocker in the four source/test
files. The immutable patch SHA-256 is
`7aca3ac2a7c5c7529ea8988e94d7551977b0075df48a01bffcce2203a6e885df`.
Authorization/identity joins, cohort boundaries, API fields and historical persistence
were challenged against counterexamples and legitimate controls. The JSON assessment
validated successfully. The advisory recommendation is merge with human review; it is
not authorization for a Git action. Managed artifacts are named
`operator-performance-2026-10-19-risk.md` / `.json` in Codex Security's local collection.

There is no all-green repository claim. Full suites were not unnecessarily repeated:
the previous full frontend run had 159 passes and two pre-existing connectivity failures
(shared-socket/message-auth expectations versus unchanged per-hook/query-auth behavior).
The previous full backend run had 493 passes and 38 PostgreSQL skips. This task's focused
runs contain no skips, but no disposable PostgreSQL was configured, so PostgreSQL runtime
and production-scale query plans remain unverified. The executed SQLite fixtures and
existing SQL compilation checks do not replace that platform coverage.

Graphify's local AST refresh passed: 3711 to 3721 nodes, 11328 edges, 248 communities,
with no graph loss. Two SQL files remain omitted because the optional SQL parser is
unavailable; no paid semantic extraction was enabled. Frontend, Development Decisions
and Testing knowledge notes are synchronized. A project-local ICM decision records the
verified permission nuance and supersedes the earlier recommendation to show QC columns.

No live station data, hardware, historical backfill, permission expansion, migration,
dependency/configuration change, or deployment was performed. See
[Development Decisions](../knowledge/Development%20Decisions.md) and the current
`TASK_PROGRESS.txt` for final Git state.
