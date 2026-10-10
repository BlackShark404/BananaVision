# Scan Logs and Detail follow-up implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` task by task under the
> selective repository workflow. Approved by the user and completed on 2026-10-10; do not repeat completed work merely
> because this plan is present. Do not restore old commits wholesale.

**Goal:** Preserve working server browsing/export and historical direct links while
fixing scan authorization, audited/concurrent writes and detail evidence handling.

**Architecture:** Extend the current scan API with one scoped loader/serializer and
transactional mutation service. Keep the existing SQL query/export service authoritative.
Integrate schema evolution with the verified versioned backup/restore service and all
existing write callers, rather than reintroducing the partial `7528544` implementation.

**Tech stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL; React/TypeScript,
existing UI components; pytest and the existing Vite/Playwright fixture harness.

**Spec:** Current user request and [verified repository review](../../scan-logs-detail-review-2026-10-09.md).
The old `7528544` plan/service is reference only. Maintenance constraints remain in
[the approved design](../specs/2026-10-05-system-maintenance-design.md).

## Global constraints

- Preserve layout, spacing, colors, typography, existing components and navigation.
  Only necessary reason inputs, history content and truthful error states may be added.
- Keep server pagination/search/filtering/export, QR/direct links, stored camera IDs,
  source keys, existing expiry presentation and current Asia/Manila helpers.
- No live DB, captures, camera, retention, restore or power operations. PostgreSQL
  tests must use a recorded disposable cluster; never load the station `.env`.
- No automatic revert/cherry-pick, deployment, push, merge or unrelated refactor.
- Keep commit-before-success, admission/draining, rollback/recovery and session revocation.
- Historical unknown actors/reasons/labels remain unknown. Do not generate retrospective
  human-verified accuracy or manufacture old classification values.

## Review focus

- Notes and history must not bypass the Admin-only note policy (Tasks 1, 4, 5).
- Lost HTTP acknowledgments and simultaneous bulk/single updates must not duplicate or
  silently overwrite writes (Tasks 3–4).
- New schema must preserve usable pre-upgrade backups and recovery evidence (Task 2).
- A late note/list/detail response or changed filters must not overwrite a newer save
  or display the wrong record (Tasks 4–5).
- Deleted and unavailable evidence must not be confused with an absent scan; previously
  deleted records lacking a ledger cannot be retroactively identified (Tasks 2, 5).

## Task 1 — Align scan authorization and detail privacy

**Files:** modify `backend/app/api/v1/scans.py`; create
`backend/app/services/scan_records.py`, `backend/tests/test_scan_records.py`.
Reuse `api/deps.py` authentication and the role/ownership policy of `services/dashboard.py`.

**Interfaces:** `load_authorized_scan(db, scan_id, user) -> Scan`;
`serialize_scan(scan, user) -> ScanResponse`;
`serialize_detail(db, scan, user) -> ScanDetailResponse`.

- [x] Write failing route regressions: Admin reads all; owning Operator reads own;
  another Operator cannot list/read/flag/status that scan; missing record is 404;
  absent/inactive/revoked credentials remain rejected by existing authentication.
- [x] Assert notes and note-history payloads are hidden from Operators on every detail
  path, even though a separate notes endpoint is already Admin-only. Notes and
  classification editing remain Admin-only. Retain existing action permissions for
  flag/status, constrained to authorized records; do not add new Operator UI controls.
- [x] Scope legacy `/scans` list and its total before pagination; use the loader for
  detail and every scan mutation. Preserve complete detail hydration and null/zero values.
- [x] Run the new route cases plus existing scan-logs and time/write tests in isolation;
  verify commit failures still roll back and return failure. Commit this coherent fix.

## Task 2 — Add durable revision/history with migration and archive compatibility

**Files:** modify `backend/app/models/scan.py`, `models/scan_original_ai_result.py`,
`models/__init__.py`, `schemas/scan.py`, `schemas/scan_logs.py`,
`services/scan_records.py`, `services/dashboard.py`, `services/scan_logs.py`;
create `models/scan_history.py` and
`migrations/versions/0005_scan_record_history.py` after `0004_maintenance_state`.
Integrate `services/backup_archive.py` and, only where needed, `backup_restore.py`.
Tests: scan records, migrations, backup archives and maintenance PostgreSQL fixtures.

**Interfaces:** server-produced `revision: int` on scan list/detail/log responses;
events with `id`, `scan_id`, `revision`, `kind`, `timestamp`, `actor_id`, snapshot
`actor_name`, `reason`, `previous_values`, `new_values`, linked legacy evidence ID;
mutation receipt keyed by `request_id` with actor/resource/kind/payload binding.
Original AI snapshot adds nullable original spoilage days and permits incomplete legacy AI.

- [x] Write migration tests over existing records, including null AI values, notes,
  equal-time status logs and absent status history. Backfill revision 1 only; preserve
  all timestamps, IDs, relationships and recorded evidence. Do not backfill invented events.
- [x] Add deterministic history projection: new events plus unrepresented legacy status
  logs/notes ordered by timestamp, revision and stable ID. Missing actor/reason remains
  null; use saved note authors. Explicitly mark legacy evidence with incomplete metadata.
- [x] Add a minimal known-deletion ledger and authorized lookup only for actual recorded
  deletions. Capture owner/scan ID/time when an existing ORM deletion occurs; do not
  create a deletion API, retention deletion or infer deletion from an empty lookup.
  Ensure archive replacement/compensation never manufactures tombstones/history.
  Unknown old absence remains 404; a known deletion is 410 only after scope checks.
- [x] Freeze a generated version-1 fixture from the current schema before altering it.
  Introduce explicit version-2 archive schema including new evidence/receipts/ledger;
  retain a strict version-1 validator/upgrade adapter with deterministic defaults.
  Never relax unknown-table/type/path/hash checks or execute uploaded SQL.
- [x] Test new and legacy archive round trips, history/receipt preservation, rejected
  malformed compatibility data, sequence resets, partial-restore compensation and
  session invalidation using disposable PostgreSQL. Do not silently omit new tables.
- [x] Update all response constructors to expose the actual persisted revision rather
  than a response default that hides missing integration. Commit once migration and
  archive regressions pass. Do not change the already-correct 0003/0004 migrations.

## Task 3 — Integrate atomic audited writes and all backend writers

**Files:** `services/scan_records.py`, `api/v1/scans.py`, `api/v1/intakes.py`,
`schemas/scan.py`, the intake request schemas and `services/scan_service.py`.
Tests: `test_scan_records.py` and a new isolated `test_scan_records_postgresql.py`.

**Interfaces:**
`mutate_scan(db, scan_id, user, kind, body) -> ScanDetailResponse` for flag/status/correction;
note replies contain the saved note plus new revision;
request envelope `{request_id: UUID, expected_revision: int >= 1}` with required trimmed
reason for status/correction. Bulk request adds `expected_revisions: {scan_id: revision}`.
Server rejects unknown request fields. Existing URL endpoints remain stable.

- [x] Write failing tests for simultaneous updates at one revision (one success, one
  409), exact retry (original response, one event), reused key with changed payload or
  actor (rejected), failed commit (no receipt/event/state survives), and no-op behavior.
- [x] Claim/replay a request within the same transaction as CAS and mutation; authorize
  before revealing receipts. Replay precedes stale-revision checks. Bind receipts to
  actor, target, action and canonical payload; never persist passwords/access tokens.
- [x] Only an actual changed classification field sets `is_overridden` and stores the
  original AI result once. Source-only, empty/no-op, status, notes and flag changes do
  not. Persist explicit old/new values, actor snapshot and reason for real changes.
- [x] Update pipeline initialization and intake bulk writes to use the same evidence
  rules. Serialize bulk and scan-attachment changes through the parent intake lock;
  lock affected scan rows in stable ID order, compare the supplied membership/revisions,
  and fail the whole batch on conflict. Preserve current eligibility rules for sold/
  spoiled stock and existing intake status semantics. Exact bulk retries return once.
- [x] Prove role revocation, note privacy and maintenance admission are not bypassed;
  test same-time ordering and actor rename after mutation. Verify on real disposable
  PostgreSQL, not only SQLite. Integrate Task 4 callers before landing mandatory requests.

## Task 4 — Synchronize every frontend caller without redesign

**Files:** `frontend/src/lib/api.ts`, `lib/scanData.ts`, new `lib/scanWrites.ts`,
`types/index.ts`, `types/scanLogs.ts`, `context/ScanContext.tsx`,
`context/InventoryContext.tsx`, `pages/Logs.tsx`, `pages/ScanDetail.tsx`;
adapt existing Kiosk flag, Quality Control edits/notes and Delivery Intake bulk actions.
Tests: new `tests/scanrecords.fixture.tsx`/`scanrecords.test.mjs` plus existing suites.

**Interfaces:** typed scan mutation envelope/result matching Task 3;
`scanWrite(scope, payload, send)` retains one request ID and exact payload after an
uncertain network/5xx outcome; clears identity on confirmed result/definite rejection.
Scope is account+record+action with auth-lifecycle cleanup, not persisted raw tokens.

- [x] Write failing browser cases for all existing callers, two row writes in flight,
  repeated clicks, uncertain retry, changed payload during retry, stale revision and
  failed persistence. Keep user draft/reason on failure and show explicit 409 reload.
- [x] Use per-record pending state. Read the actual server revision and send status
  only to `/status`. Collect reasons using existing dialog/input styles. Avoid sending
  unchanged classification fields from a source-only editor.
- [x] Ensure bulk action snapshots cover all eligible scans, not a Logs page; retain
  the exact revision/membership snapshot through retries. On conflict refresh without
  losing the user's action/reason. Do not silently retarget new scans.
- [x] Hydrate notes/history from authoritative detail replies. Reject late reads older
  than a known saved revision; preserve images/detections on summary-only refreshes.
  Keep mutation completion from refreshing an obsolete filter closure or prior account.
- [x] Run focused browser regressions and TypeScript/build across every caller, then
  commit Tasks 3–4 as one synchronized contract change. No partial deployment.

## Task 5 — Detail history, missing evidence and truthful states

**Files:** `pages/ScanDetail.tsx`, `components/BoundingBoxOverlay.tsx`,
new `components/ScanImage.tsx` if shared fallback is needed, and Logs image cells.
Backend history remains in `services/scan_records.py`; no second history calculation.

- [x] Write browser cases for old QR links with empty shared context, complete detail
  hydration, renamed/currently absent cameras, missing image URL, image 404, rapid
  source/record/account changes and original classification null values.
- [x] Display chronological server history in the existing card style: responsible
  actor when recorded, Manila timestamp, prior/new values, reason, explicit unavailable
  legacy metadata. Never substitute today's account/camera label as historical evidence.
- [x] Distinguish loading, unavailable/retry, forbidden, unknown 404 and evidence-backed
  deleted 410. A missing image must leave scan details/history usable. Reset overlay
  dimensions/load state when the image changes; hide boxes on unavailable evidence.
- [x] Verify notes remain Admin-only, no duplicate legacy events appear and polling/
  slow note responses do not undo a successful save. Commit after targeted tests pass.

## Task 6 — Preserve query/export behavior and close verification

**Files:** extend `backend/tests/test_scan_logs.py`, scan-record PostgreSQL/browser
tests, relevant existing persistence/maintenance tests, and verification documentation.

- [x] Add equal-key page-boundary tests for every supported sort and null handling;
  retain complete SQL filtering and the >200-row export test. Add CSV round trips for
  Unicode, quotes, commas, CR, LF, CRLF, whitespace before every formula prefix and
  legitimate numeric values. Assert filters intersect account scope across all pages.
- [x] Test latest-filter-wins and stale refresh after a write with the actual Logs
  component; current dashboard navigation fixtures alone do not mount Logs/Detail.
- [x] Run targeted backend/browser regressions during changes, then the full isolated
  backend suite including PostgreSQL concurrency/migration/restore cases, full frontend
  suites, TypeScript, configured lint and production build. Record exact commands/results;
  distinguish baseline lint debt from new findings. Do not count skipped PG tests as passed.
- [x] Review security-sensitive scope/replay/history/archive boundaries with Codex Security
  and an independent focused review. Inspect the final diff for UI drift, maintenance
  changes beyond required schema integration, broken callers or accidental old-commit replay.
- [x] Stop only the recorded disposable PostgreSQL instance, remove only verified
  task-generated resources, update TASK_PROGRESS.txt and commit verified work locally.
  No push/merge/deploy or live acceptance without explicit authorization.

## Original implementation sequence (completed)

Implement Task 1 first because it closes a verified access-control gap. Then deliver
Tasks 2–5 as the smallest coherent persistence/API/UI integration, preserving the
working query/export pipeline; finish with Task 6. No wholesale restoration is needed.
The reason for the original reverts remains unknown and is not a prerequisite to this
evidence-based plan. A new scan deletion workflow or expiry-layout change is out of scope.

Completion evidence: [final verification report](../../scan-records-verification-2026-10-10.md).
