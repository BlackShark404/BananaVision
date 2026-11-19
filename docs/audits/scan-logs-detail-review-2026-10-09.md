# Scan Logs and Scan Detail review — 2026-10-09

Scope: repository/history review and implementation planning only. No scan product
code was changed, restored, reverted or cherry-picked. Maintenance was finalized
first. This review supersedes the unfinished 2026-10-07 scan-record plan.

## Maintenance status

- Production maintenance corrections are committed through `d99c772`; verification
  and workflow documentation through `7e83cf7`.
- `b6d69e7` committed the full HTTP backup/download/validation/confirmed restore,
  database/evidence recovery, session invalidation and post-restore login test.
  Its PostgreSQL run was **12 passed in 27.78 s**, supplementing the earlier full
  backend/PostgreSQL **186 passed**, frontend **38 passed**, typecheck and build.
- `1f0eded` changed the historical checkpoint, not application code. The working
  tree was clean there when this audit started; the pending-commit text was stale.
- `8676ad7` records the corrected maintenance status and archives the stale checkpoint.
- On this audit, both disposable cluster directories, the acceptance Ruff directory
  and machine-specific helper were absent. No acceptance/final-test temporary folders
  or listeners on ports 56843/56844 remained. Nothing needed destructive cleanup.
- No approved maintenance production work remains. Full lint still has documented
  existing debt; live camera, power and deployment acceptance are explicitly deferred
  by the user. Isolated automated completion does not certify real hardware.

See [maintenance verification](system-maintenance-verification-2026-10-08.md) for
the results, security-review scope and limitations. Successful full suites were not
repeated for this documentation-only audit.

## Exact revert history

| Change | Revert | What actually changed |
| --- | --- | --- |
| `7528544` — Add scan revision history and idempotent writes | `bc3ed4c` | Added scan revision/event/receipt/tombstone models and a mutation service, strict write schemas, frontend revision/retry plumbing, detail history and missing-image rendering, plus tests and an unfinished plan. |
| `ed80acb` — Update Logs.tsx | `58d7337` | Only changed the spoilage cell to put remaining life first and original estimate second. No pagination, export, inventory endpoint or history implementation. |

Both reverts exactly restored their respective parents' trees (`git diff` between
each original parent and the revert is empty). Both commit messages say only
"This reverts commit ...". **The reason for either revert is not recorded in Git.**
The incomplete integration below is a demonstrable risk, not a claim about why the
user reverted it.

The browsing/direct-link improvements predate these changes, notably `2b4452c`
(scoped Scan Logs API/integration), `a31a9e4` (Manila timestamps/async flows) and
`37ad33b` (nullable metrics/persistence). They were not removed by these reverts.
The current Logs.tsx blob is identical to its blob before `7528544`.

## Already present — preserve

| Feature | Current implementation and evidence |
| --- | --- |
| Server browsing | Logs uses `api.scanLogs.list`, URL query state and `AppDataTable.serverState`. The backend SQL pipeline applies search, filters, sort, offset and limit across the complete authorized population. |
| Complete filtered exports | `/scan-logs/export` uses the same predicates/order, ignores pagination, and streams batches of 200. Existing regression verifies 205 rows across batches. |
| Deterministic order | `services/scan_logs.py:_ordering` adds scan time and UUID tiebreakers with nulls last. Equal-key ordering is stable; offset pages are not a frozen snapshot under concurrent dataset changes. |
| Business dates | Backend day bounds and response serializers reuse the Manila helpers. Logs' date picker, URL date/operator/source filters and existing timezone formatting remain intact. |
| Stored scan timestamps | `scanData.ts:mapApiScan` prefers `date_time`; `storedTimestamp` rejects invalid/missing stored dates instead of substituting now. |
| Shared history pagination | `ScanContext` uses `collectScanPages` and `page_size=100`, fetches successive pages, detects incomplete totals and publishes only a complete result. Logs itself does not use that in-memory list. |
| Direct historical links | Detail fetches `/scans/{id}` directly with timeout, cancellation and a keyed account/record component. Images, detections, classification and original AI fields are mapped; an absent shared-list entry is not treated as not found. |
| Inventory operation | Logs calls `/scans/{id}/status` with `inventory_status`, awaits success and refreshes. This operation does not set `is_overridden`. The original wrong-endpoint bug is already fixed. |
| Recorded camera identity | Detail builds views from stored image/detection camera IDs and stored detection labels, not today's configurable camera array. Missing stored labels fall back to the recorded ID. |
| CSV encoding | `csv.writer`, UTF-8 BOM and `_safe_cell` handle delimiters/quotes/newlines and neutralize dangerous string prefixes (`=`, `+`, `-`, `@`, leading tab/CR/LF). Expand regression cases rather than replacing this working exporter. |
| Error/loading and stale responses | Logs' resource hook has request sequence/abort guards, initial unavailable state and explicit stale-data retention after refresh failure. Detail has direct-load timeout/retry. Remaining write/read races below are distinct. |
| Persistence before success | Function-scoped DB dependencies commit before HTTP success. Existing rollback tests cover failed writes; frontend writes await the server before success messages. |

Sources: [Logs](../../frontend/src/pages/Logs.tsx),
[query/export service](../../backend/app/services/scan_logs.py),
[Scan Detail](../../frontend/src/pages/ScanDetail.tsx),
[mapping/pagination](../../frontend/src/lib/scanData.ts),
[shared state](../../frontend/src/context/ScanContext.tsx).

## Confirmed gaps

1. **Inconsistent authorization.** `/scan-logs` scopes Operators to their account;
   legacy `/scans`, direct detail, flag and status routes merely require a logged-in
   user. They do not enforce ownership. Detail also includes admin notes for every
   authenticated caller although the separate notes routes are Admin-only. In an
   isolated fixture, another persisted Operator received another operator's detail
   and private note, listed the scan, and successfully flagged/changed its status.
   See `api/v1/scans.py` list/detail/flag/status and detail `notes` construction.
   Fix this before adding new history endpoints.
2. **Classification override semantics.** `override_scan` unconditionally sets
   `scan.is_overridden = True` and snapshots original AI data before establishing
   that a classification field changed. Source-only and empty/no-op edits therefore
   count as overrides. A source-only API probe reproduced this. Original spoilage
   days are not in the current original-AI model/response, so they cannot be recovered
   later from that snapshot. Nullable legacy classifications need explicit handling.
3. **No revision/CAS or request replay.** Status always inserts another status row;
   request ID/revision/reason fields are not in its schema and are silently ignored.
   Two identical retries produced two rows, and another write using the same stale
   revision was accepted. There is no current scan revision column, event ledger,
   receipt table or compare-and-swap. Simultaneous writes have no conflict protection.
4. **Incomplete audit history.** Status logs retain new status/time, but no actor,
   reason or explicit old state. Notes preserve author-name snapshots; activity logs
   retain actor IDs and free text. Detail returns neither a chronological status
   timeline nor structured correction history. Current account names cannot safely
   reconstruct historical actors. Missing old evidence must remain explicitly unknown.
5. **Missing versus deleted/forbidden.** Current deleted and unknown IDs both return
   404; no deletion ledger exists. The UI uses one not-found description and a generic
   load-error state for other errors. Known-deleted 410 requires actual retained
   deletion evidence. Historical deletions without it cannot honestly be identified.
   There is no current scan deletion API, and protected retention no longer deletes
   stored scans; do not add deletion functionality as a side effect of this work.
6. **Detail note hydration/races.** Backend detail contains notes, but `ApiScan` and
   `mapApiScan` drop them. Detail separately reads the notes context, whose late list
   response can replace a newly saved note. Mutations lack revision-aware read guards.
   Logs uses one `pendingScan` ID, so writing row B can re-enable still-pending row A;
   its post-write refresh can also use the filter closure captured before navigation.
7. **Unavailable image files.** Missing image URLs have a placeholder, but URLs that
   return 404/load errors have no `onError` fallback. BoundingBoxOverlay retains image
   dimensions/load state across source changes. This does not prevent detail metadata
   loading, but can display broken evidence or stale overlays.

These are scan-domain gaps, not a reason to reopen or discard maintenance functionality.

## Why wholesale restoration is unsafe

`7528544` was partial integration, not a completed known-good implementation:

- Its new `mutate_scan`/`load_scan`/history service was **not called by the scan API
  routes**, intake bulk handler or scan pipeline in that commit. Its advertised
  endpoint behavior was therefore not delivered by the committed service alone.
- No scan-revision migration accompanied the models. At that point even the inherited
  missing configuration migration was still pending; maintenance has since fixed it.
- `api.scans.updateStatus` changed from 2 to 4 required arguments, but Logs still
  called it with 2. The bulk API required reason/revisions while InventoryContext
  still supplied only status. Restoring this unchanged would break contract/type checks.
- Frontend expected full scan mutation responses while unchanged flag/status handlers
  still returned message-only objects. Response `revision=1` defaults could conceal
  missing integration rather than establish real concurrency protection.
- Today's versioned backup service explicitly includes 18 tables and checks an exact
  schema. New history/receipt/tombstone tables and scan columns need deliberate archive,
  migration and restore integration; otherwise evidence could be omitted or old valid
  archives become incompatible. This work must preserve maintenance barriers, rollback
  semantics, session invalidation and the no-fabricated-history rule.

`ed80acb` was only a presentation choice. The current display already shows original
estimate and remaining life. Leave that reverted presentation unchanged under the
user's UI-preservation instruction.

## Verification performed for this review

Fresh isolated run: **12 passed in 12.17 s**:

- Seven existing `test_scan_logs.py` cases (combined filters/counts, scoping/renames,
  business day boundaries, risk/review, literal search/CSV, multi-batch export, API validation).
- Existing historical pagination/timestamp/direct-detail/export case from
  `test_time_and_writes.py`.
- Four temporary characterization probes documenting the authorization, source-only
  override, ignored revision/duplicate status, and deleted/unknown behaviors above.
  Their passing assertions confirm the gaps; they are **not fixes or security passes**.

The tests used in-memory SQLite adapters and a new temporary CWD, never the station
`.env`, production DB or application hardware lifespan. Initial sandbox fixture-file
creation was denied; the same isolated test setup ran with approved elevation.
Both task-generated review directories were removed afterward; no PostgreSQL instance
was started for this review.
This review did not rerun browser/TypeScript/build suites because product code is
unchanged. New frontend behavior remains unimplemented and needs browser tests later.

## Recommendation

**Selectively reimplement the confirmed gaps against the current architecture.** Keep
existing server browsing/export/direct links/timestamps/camera history and the current
spoilage layout. Use the old history service only as reference; do not revert a revert
or cherry-pick either commit wholesale. The focused
[implementation plan](../superpowers/plans/2026-10-09-scan-records-follow-up.md) starts with
authorization, then integrates atomic audited writes, migrations/backups and all callers,
followed by detail resilience and verification. It is a proposal, not executed work.
