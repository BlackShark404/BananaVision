# System configuration, export, and maintenance

Status: proposed design for review; no product implementation yet.
Baseline inspected: `ac5c809`.

## Intended outcome and constraints

Make saved configuration reliable, apply it to actual inference/capture behavior, protect
operational history during retention, provide a genuinely restorable station backup, and
drain operations safely before maintenance or power actions. Preserve the four existing
System Configuration tabs, layout, components, spacing, typography, and visual styling.
Add only the controls/status text needed for the requested functionality. Keep existing CSV
reporting available. All business timestamps remain backend-generated Asia/Manila values.

The user selected restoration into this station, with archive validation, explicit replacement
confirmation, and rollback protection. That product decision does not authorize executing a
restore, cleanup, reboot, or shutdown against this working station during development.

## Investigation findings

| Area | Confirmed behavior | Necessary change |
| --- | --- | --- |
| Configuration | No revision; arbitrary first row; different GET/PATCH defaults; frontend fallback is editable before loading | One canonical configuration, revision conflict detection, explicit load/error/saved/applied state |
| Inference | Async pipeline calls a synchronous threshold reader that returns the environment default when an event loop is running | Read the saved threshold once in the async scan transaction and pass it explicitly into inference |
| Validation | Slider accepts 0, API accepts floats from 1, DB truncates to integer; logical ID count/length not bounded | One integer 1–100 contract and bounded, unique camera identifiers |
| Camera health | Devices API derives physical positions from editable CAM-number strings; handles can appear Online without usable frames | Shared stable slot mapping and verified frame health |
| Camera changes | Logical renames already preserve device UUIDs; physical remapping already reopens handles but UI ignores partial failures | Preserve these protections, report saved/applied differences and physical failures accurately |
| Retention | Real scheduled worker deletes every old scan and audit record, cascading evidence deletion | Retain required scan/audit history; safely clean only eligible unreferenced captures by default |
| Export/backup | CSV is already accurately labeled scan summaries and non-restorable; no backup/restore exists | Keep CSV; add complete, validated data-recovery archives and restore |
| Power | OS exit status checked, but requests refuse active scans and reopen admission immediately after scheduling | Close admission first, drain, persist intent, request OS action, keep admission closed after acceptance |

Already working and to preserve: physical-device ID duplicate validation, commit-before-HTTP
success, scan commit-before-completion broadcasts, UUID-preserving logical renames, safe
capture-root checks, and orphan cleanup retries after filesystem errors.

## Approach and alternatives

Recommended: application-owned, versioned data archive containing typed table data and
referenced capture files, with strict validation and staged, journaled replacement. This can
be tested without importing executable SQL and requires no PostgreSQL client installation.
The existing CSV remains a report, not a recovery format.

Alternative: `pg_dump`/`pg_restore` plus capture archive. This delegates database serialization
to PostgreSQL but adds client/version/tooling dependencies and requires treating uploaded
dumps as executable database content. PostgreSQL client commands were not found on this
session's PATH. Alternative: restore to an empty separate target; the user selected in-place
station replacement instead.

## Configuration contract

- Add a canonical configuration marker and integer revision. Preserve legacy rows rather
  than deleting conflicting historical configurations during migration. Select the latest
  valid legacy configuration deterministically, flag conflicting legacy values for review,
  and enforce one canonical row at the database level. All readers use the same repository.
- PATCH requires the revision that the editor loaded and sends only changed fields. A
  conditional update increments the revision atomically; stale edits receive HTTP 409 with
  current saved state. Do not silently merge conflicting administrator changes.
- Return saved values/revision plus applied values/revision or application state, application
  error, restart-required fields, effective retention period/policy, and maintenance state.
  Do not persist ephemeral camera Online status as a configuration truth.
- Validate threshold as an integer 1–100, unique logical identifiers with maximum 50 characters,
  no empty or embedded delimiter entries, and one identifier for each configured physical slot
  (1–4 slots). Reject invalid requests before persistence or physical changes.
- Store user-editable physical mapping with the canonical configuration rather than maintaining
  two independent editable sources. Import existing effective host mapping initially; keep
  noneditable deployment settings as deployment prerequisites. Reuse the calibration modal.
- Threshold applies to the next admitted scan; an already-running scan keeps its immutable
  snapshot. Retention applies on the next cleanup cycle. Logical IDs and physical mapping
  apply under exclusive camera coordination after persistence. No OS restart is required for
  these supported runtime changes. Model paths and other startup-only deployment settings
  remain clearly identified as requiring backend restart when surfaced in this workflow.
- A persisted camera configuration that fails to initialize is explicitly saved-but-not-applied
  or partially applied, with actual camera status and a retry path. Never call it fully applied.
  Runtime publication follows commit; persistence failure leaves the previous runtime intact.

Frontend: distinguish draft, saved, and applied values within existing cards using existing
description/badge/error components. Disable save/reset/calibration while loading or saving;
show retry after load failure. Guard late reads by request generation and revision. Preserve
failed-save drafts and retain unrelated dirty fields when the retention toggle saves. A
conflict keeps the draft and offers reload; it must not overwrite another administrator.

## Inference and cameras

- Remove the classifier's synchronous database lookup. The scan service obtains the canonical
  configuration asynchronously once and passes threshold/100 explicitly to every camera's
  model invocation. Fail clearly if required configuration cannot be read; no hidden environment
  fallback after a failed saved-settings read. Preserve the separate fusion conflict/review policy.
- Run blocking capture/inference through controlled workers without allowing concurrent model
  mutation. A cancelled HTTP caller must not release the scan's maintenance protection while
  its hardware/thread work is still running.
- Represent a camera slot by stable device UUID, logical label, and physical index. Startup,
  listing, health monitoring, previews, capture, and calibration share that mapping. Names
  are display identifiers, never hardware indices. Renaming or reordering preserves appropriate
  device identities and never relies on CAM-number parsing or colliding fallback names.
- Protect each handle against simultaneous preview/read/release/reinitialize. Pausing capture
  must not wait forever for a persistent preview stream; close or suspend previews during remap.
- Initialization/read failure means Offline with an application error. Mark Online only after
  successful initialization and a usable frame probe; use one frame-validity rule. Database
  status publication follows successful persistence, with retries if that persistence fails.

## Maintenance coordination and power

- Introduce explicit ready, draining, maintenance, power-accepted, and recovery-required states.
  Admission closes atomically before draining; new scan requests are rejected with a useful
  retryable response instead of silently queuing behind shutdown/restore.
- Coordinate all mutation sources: HTTP writes (including writes in GET handlers), active scans,
  camera previews/health, sensor persistence, retention, and maintenance endpoints. In-process
  counters/locks alone are insufficient. Use database coordination for writers/maintenance
  and enforce one hardware-owning backend process for a station with an ownership lease/lock.
  A second owner fails startup clearly. Do not hold maintenance locks while waiting for writers
  that need the same lock to finish committing.
- Drain admitted scans through transaction completion and capture cleanup. A bounded drain
  timeout aborts the maintenance request, keeps active work intact, and reports failure; it
  does not kill a scan. Graceful application shutdown drains before releasing devices/pools.
- Persist an audited power request before invoking a fixed allowlisted OS command. On known
  command failure, record failure and restore admission. On accepted scheduling, return
  accepted (not reboot-completed) and leave admission closed until actual restart/shutdown.
- A command timeout or a lost connection after dispatch has an ambiguous outcome: keep the
  system blocked and reconcile status; do not automatically retry a potentially accepted command.
  A post-acceptance audit failure must not reopen scanning or tell the UI the OS rejected it.
- Persist power state and a reliable host boot identity. Restarting only the backend during an
  accepted/ambiguous OS request must preserve the closed-admission state. A verified new OS boot
  completes the old request. On the same boot, reopening requires verified cancellation through
  a fixed OS cancellation command or an explicit re-authenticated recovery action after showing
  the uncertain outcome. Do not infer successful power-off merely from elapsed time or an HTTP
  disconnect. If boot identity cannot be established, fail closed and expose recovery status.
- Power/calibration/restore requests are single-flight and carry an operation ID so retrying a
  lost frontend response does not duplicate a destructive operation. Existing dialogs show
  draining/accepted/failure states and prevent duplicate submissions without restyling.

## Retention policy

Recommended safe default: retain persisted scan history and all referenced evidence, stock
history, suppliers/intakes, accounts, configuration, and audit indefinitely. The configured
retention toggle runs real cleanup of old unreferenced UUID capture directories after the
existing configured grace period. Preserve current 6-hour scheduling, but coordinate it with
scans, backup, and restore. The worker must recheck references before deleting eligible files.

This intentionally removes unsafe age-only deletion, including deletion of sold-stock
history that is still needed for reports. Do not introduce automatic completed-scan deletion
without a separate explicit policy defining how long historical evidence remains required.
UI text states the actual policy and backend-provided period rather than promising all logs
will be deleted after a hardcoded 30 days. Keep last attempted/successful run and error status;
never report space freed when deletion failed. Path, symlink, reparse-point, root, and recent
file checks remain mandatory. Temporary backup artifacts have a separate conservative expiry;
recovery rollback material is never removed by ordinary retention.

## Backup format and creation

- Administrator-only archive version 1: manifest, schema/application version, station data,
  table counts, typed column values, capture references, exact file lengths and SHA-256 hashes,
  creation timestamp with offset, and deployment/model prerequisites.
- Include all 18 current application tables and any new persistent configuration tables,
  including credentials/PIN hashes, role/profile relationships, original AI results, notes,
  inventory history, audit, notifications, and sensor history. Include every referenced image
  and thumbnail. Normalize evidence paths relative to the capture root and remap on restore.
  Missing referenced evidence fails creation rather than producing an incomplete backup.
- Exclude `.env` secrets, JWT signing secrets, executable model weights, source code, logs,
  and machine-specific process state. Record compatible model identities/hashes and required
  deployment settings without secrets. This is a full station-data recovery archive, not a
  bootable operating-system image; make that distinction in the existing Data Storage card.
- Pause mutations and retention, drain, take a consistent database snapshot and evidence copy,
  then release the pause. Stream large table data/files to private temporary storage with
  bounded memory. Never expose temporary archives through the public captures directory.
- Check required space on every relevant filesystem, reserve rollback/staging headroom, enforce
  archive/row/file/expanded-size limits, and still catch ENOSPC/permissions/I/O failures during
  writes. A preflight free-space check alone is insufficient. Remove only operation-owned
  partial files. Validate the completed archive before atomic publication and success status.
- Downloads are authenticated and operation-bound, with no guessable public URL or secrets in
  logs. Display backup-created only after server completion; download-started wording must not
  claim the browser successfully saved a file to the user's disk. Existing CSV export uses
  streaming server output and retains its existing content/timestamp behavior.

## Restore validation and replacement

1. Upload into private bounded staging storage. Do not modify live data while validating.
2. Reject invalid/truncated archives, unexpected versions/schema/columns/tables, duplicate paths,
   traversal/absolute paths, symlinks/reparse points, excessive expansion, invalid types/enums,
   duplicate keys, broken relationships, missing files, size/hash/count mismatches, and archives
   without a usable active administrator. Do not execute SQL, pickle, model, or script content.
3. Load and validate all data against an isolated staging database/schema, including real foreign
   keys and uniqueness constraints. Confirm every file reference resolves inside staging.
   Hashes detect corruption, not authenticity; validation must not treat a hash as proof of trust.
4. Return a validation summary plus short-lived, one-use token bound to archive digest, requesting
   administrator/session, and current station generation. Require explicit replacement confirmation
   and re-authentication; revalidate before execution. The original upload path is never authority.
5. Enter maintenance, drain, and create a verified rollback snapshot of the current station.
   Abort if that snapshot or sufficient staging/rollback storage cannot be guaranteed.
6. Stage evidence on the target filesystem. Before promotion, persist and flush a durable recovery
   journal identifying old/new evidence directories, backup digest, and restore operation ID.
   Replace application table data in one database transaction in dependency order; reset generated
   sequences using application-controlled, transaction-safe restart statements; a precommit failure
   must also restore sequence behavior. Preserve maintenance control records outside the replaceable
   data. Promote evidence under blocked reads/writes, including public capture responses and existing
   preview streams. Record the restore ID and advance the non-restored authentication generation in
   the same database transaction as restored data.
7. On a known precommit failure, roll back database data and restore the previous evidence directory.
   On an uncertain commit outcome, query the committed operation marker from a new connection.
   If it cannot be determined, remain recovery-required; never guess which file tree matches DB.
8. Startup reconciles the journal BEFORE schema seeding, hardware startup, retention, or public
   routes are enabled. A committed marker finalizes the new tree; a confirmed absent marker restores
   the old tree. Move the current import-time capture-root creation and StaticFiles readiness behind
   this recovery boundary; importing the app must not create an empty root between recovery renames.
   Preserve rollback material until successful integrity verification. If postcommit verification
   fails, persist a compensating-restore phase and replace data from the verified pre-restore snapshot
   in a new transaction, using a separate rollback commit marker and another authentication-generation
   advance. Restore the old evidence tree under the same journal rules. Startup resumes or reconciles
   this phase deterministically if interrupted. A failed compensation keeps admission closed and
   retains both recovery materials and an actionable error; it never reports restore success.
9. Invalidate all pre-restore sessions using the authentication generation committed in step 6, not
   merely incrementing restored token counters (which could resurrect old tokens). Every HTTP and
   WebSocket authentication path checks the generation before admission resumes. Reinitialize
   runtime settings and verify physical cameras; restored Online database values are never trusted.
   Data restoration and hardware initialization have separate outcomes; camera failure is explicit.
10. Return success only after restored data/evidence checks complete. Close stale clients' sessions
    and require login with a restored account. A lost response is recoverable through operation status,
    not a second restore attempt.

All actual replacement operations require the application's explicit confirmation flow. Development
verification uses isolated databases/directories and mocked power/capture only.

## Verification and acceptance

Backend regression cases: two edits with one revision; concurrent initialization; invalid settings;
threshold forwarded through the real async orchestration; rename/reorder/CAM-000 mapping; duplicate
IDs; unusable camera frames; partial initialization; config/commit failures; active-stock, flagged,
noted, overridden, and audit retention protection; cleanup failure; bounded archive creation;
disk-full at multiple stages; complete all-table/evidence round-trip on isolated PostgreSQL;
corruption/version/type/FK/traversal/expansion rejection; missing captures; restore failures before
and after evidence promotion and commit; uncertain commit recovery; startup journal reconciliation;
import with a temporarily absent capture root; interrupted postcommit compensating restore;
sequence behavior after a precommit rollback followed by new inserts; session revocation;
non-admin access denial; draining during scan, queued scans, cancelled callers,
power failures/timeouts/duplicate requests; maintenance overlap with retention/camera/DB writes.
Include backend-process restart during a scheduled power delay and after ambiguous command failure,
verified OS-boot change, and cancellation/recovery of a request that never actually powers off.

Frontend regression cases: load/save errors, stale responses, revision conflicts, dirty drafts,
partial camera application, threshold bounds, truthful backup/download/restore messages,
validation errors, confirmation, lost-response status recovery, failed writes, and single-flight
power dialogs. Check existing tabs and component styles for accidental changes.

Run relevant backend/frontend suites, application TypeScript checking, configured lint, production
build, scoped Codex Security review of new sensitive boundaries, and final Git diff review.
Tests using SQLite do not establish PostgreSQL restore/locking correctness; real isolated PostgreSQL
round-trip and failure tests are required before calling restore verified. Physical camera and real
power behavior cannot be proven with mocks; report these limitations without executing live actions.

Baseline already run: 70 isolated backend tests passed, 5 PostgreSQL/bootstrap cases excluded.
No product changes, new regression tests, live hardware operations, or live restore have been run.
