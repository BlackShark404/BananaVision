# BananaVision comprehensive system audit — 2026-10-10

Audit finalized **2026-10-11** on **`main` at `5483861`** (initial source target
`0a4c87e`; subsequent commits contain audit evidence only). This is an audit and
proposed correction plan,
not authorization to implement changes or a deployment acceptance certificate.
Application source, schemas, migrations, UI and working behavior were not changed.
No branches/worktrees were created or switched, and the assistant performed no commit,
push, merge or deployment in this audit continuation.

The 82 requirement rows below are classified as **64 VERIFIED, 11 PARTIAL,
4 DEFECTIVE, 1 MISSING and 2 NOT VERIFIED**. Related rows can describe the same
root cause; these counts are not counts of independent bugs. Nine actionable findings
(including a policy-dependent inconsistency) and six gap categories are detailed below.

The completed Scan Logs/Detail and maintenance implementations remain present. The
broader cross-view requirements are **not all satisfied**: review navigation and
Inventory risk have confirmed defects, inventory eligibility differs by view, and
several requested interactions are absent. The earlier approval-infrastructure block
was resolved through normal approval: targeted backend, actual PostgreSQL and mocked
browser characterization now passed. The audit is complete with explicit volume,
deployment and live-acceptance limitations. Recommended fixes require separate authorization.

## Scope, method and evidence

Requirements are the original comprehensive audit request and its main-only resume
request. The existing [scan plan](superpowers/plans/2026-10-09-scan-records-follow-up.md),
[maintenance design](superpowers/specs/2026-10-05-system-maintenance-design.md) and
[maintenance plan](superpowers/plans/2026-10-06-system-maintenance.md) remain completed
implementation references, not instructions to repeat their work. The separate
[product roadmap](SYSTEM_DESIGN_GAP_ANALYSIS_AND_PRODUCT_ROADMAP.md) contains proposed
future product scope; its proposals are not assumed to be current requirements or
authorized fixes.

Evidence labels used throughout:

- **S:** current source/contract inspection on `main`, tracing callers to services and
  persistence. Source-derived counterexamples are identified as such.
- **R:** actual recorded verification in
  [scan verification](scan-records-verification-2026-10-10.md) and
  [maintenance verification](system-maintenance-verification-2026-10-08.md), reused
  after a fresh Git comparison. These are previous executed results, not newly run tests.
- **P:** new dependency-free source-function characterization probes, executed during
  this audit. They confirm observed defects and do **not** certify corrected behavior.
- **T:** new executed runtime characterization in the [PostgreSQL probes](audits/test_system_audit_metrics.py)
  and [browser probes](audits/system-audit-browser-2026-10-11.mjs), plus the targeted
  backend run listed below. Passing characterization can confirm a defect; it does
  not mean the observed behavior was fixed. Browser HTTP/WebSocket traffic is mocked.
- **G:** a specific verification or policy gap; no passing result is claimed.

`git diff --name-status fa63f5d..HEAD -- backend frontend` reports only
`backend/.env.example`. Runtime application code and test files are unchanged from the
recorded final verification. The complete intervening diff also includes `setup.bat`
and documentation: the installer now checks seeding failure. Neither the example
configuration change nor executing that installer is covered by reused runtime results.
No live environment file was read, and the installer was not run.

Status meanings:

| Status | Meaning |
| --- | --- |
| VERIFIED | Current implementation and sufficient scoped source/test evidence support the requirement. Runtime results may be explicitly reused (R). |
| PARTIAL | Useful behavior exists, but a stated part, guarantee or cross-view alignment is incomplete. |
| DEFECTIVE | Current behavior contradicts the requested behavior; evidence and a concrete counterexample are supplied. |
| MISSING | The requested capability is not implemented. |
| NOT VERIFIED | Evidence is insufficient or execution is blocked; this is not a claim of failure. |

## Requirement matrix

### Dashboard

Primary paths: [Dashboard.tsx](../frontend/src/pages/Dashboard.tsx),
[DashboardRecords.tsx](../frontend/src/components/DashboardRecords.tsx),
[useDashboardResource](../frontend/src/hooks/useDashboardResource.ts),
[Dashboard API](../backend/app/api/v1/dashboard.py),
[dashboard service](../backend/app/services/dashboard.py),
[backend tests](../backend/tests/test_dashboard.py),
[browser tests](../frontend/tests/dashboard.test.mjs).

| ID | Requirement | Status | Evidence and boundary |
| --- | --- | --- | --- |
| D01 | Every KPI opens its underlying authorized records | PARTIAL | S/R: Scans Today, source/operator groups and System Health navigate. Operator Scan Success Rate has `onClick=undefined` (Dashboard:204); F05. Group rows also drop their displayed day; F04. |
| D02 | Loading, unavailable, error, stale and genuine zero states differ | VERIFIED | S/R: resource holds a successful snapshot on failure; Dashboard labels stale/unavailable and offers retry. Browser tests `loading and unavailable are not zero` and `failed refresh preserves last snapshot`. |
| D03 | Meaningful successful refresh timestamp | VERIFIED | S/R: `generated_at` rendered in explicit Asia/Manila formatting; no-success label before a successful response; age/error/day rollover mark stale. Timestamp is server snapshot time, not completion of a live hardware operation. |
| D04 | Pending quality review shortcut matches KPI population | DEFECTIVE | S/P/R/T: service `_review` is flagged OR confidence below configured threshold; current/legacy UI links use `status=Flagged`. Actual PostgreSQL: KPI and attention=review count 2, Flagged shortcut count 1; other-user scan excluded. F01. |
| D05 | Expiring stock shortcut matches Dashboard stock risk | VERIFIED | S/R: shortcut sends `attention=at-risk`; Logs reuses `dashboard._expiring`. Cross-view intake-policy disagreement remains F03. |
| D06 | Disconnected/delayed live updates are visible and recover | VERIFIED | S/R: connection label, delayed-update message, 30-second polling, reconnect/focus refresh and 90-second stale indication. Browser disconnect/reconnect and completion/polling tests. |
| D07 | My Sources is the authenticated operator's activity | VERIFIED | S/R: `_scoped_projection` constrains persisted `OperatorProfile.account_id` before aggregates. UI uses server sources; account/role key discards another user's snapshot. |
| D08 | Stable operator IDs, duplicate names and renames | VERIFIED | S/R: grouping/filtering by operator UUID, ownership by account UUID; `test_namesakes_and_renames_use_ids_and_filters_cannot_broaden_scope`. Display names can reflect current directory names without changing ownership. |
| D09 | Deactivated staff and unknown roles | VERIFIED | S/R: current authentication rejects inactive/revoked accounts; historical scans join retained accounts without requiring their current active status. Unknown roles are denied. “Active Operators” means operators who scanned on that day, not the HR active-account total. |
| D10 | No confidence mislabeled Accuracy Today / human accuracy | VERIFIED | S/R: current Dashboard has Scan Success Rate (“Auto-approved scans”), not Accuracy Today. Rule-based approval and model confidence do not constitute measured accuracy. Group average confidence uses current classification values; see X03. |
| D11 | Asia/Manila day and midnight boundaries | VERIFIED | S/R: `business_day_bounds`, server response day, explicit browser Manila clock; backend boundary test and browser running in a different timezone. |
| D12 | Zero configured/connected cameras and failed preview | VERIFIED | S/R: no-camera/unknown/offline states are explicit; physical ID used for preview; camera failures leave metrics usable. Mock browser coverage only, not physical acceptance. |
| D13 | Rapid refresh, out-of-order responses and account switching | VERIFIED | S/R: sequence + AbortController + source identity in `useDashboardResource`, keyed account/role content; same-name account-switch browser test. |
| D14 | Selected-day group records remain the selected population | DEFECTIVE | S/P: modal rows count `selectedDate` but pass `business_date:""`; Logs URL omits date. F04. An explicitly labeled all-history link would be a valid alternative workflow. |

### Scan Logs and Scan Detail

Primary paths: [scan logs service](../backend/app/services/scan_logs.py),
[scan APIs](../backend/app/api/v1/scans.py),
[scan records service](../backend/app/services/scan_records.py),
[history models](../backend/app/models/scan_history.py),
[ScanContext](../frontend/src/context/ScanContext.tsx),
[Logs](../frontend/src/pages/Logs.tsx), [ScanDetail](../frontend/src/pages/ScanDetail.tsx),
[scan writes](../frontend/src/lib/scanWrites.ts),
[ScanImage](../frontend/src/components/ScanImage.tsx).
Tests: [logs](../backend/tests/test_scan_logs.py),
[records](../backend/tests/test_scan_records.py),
[PostgreSQL records](../backend/tests/test_scan_records_postgresql.py),
[evidence](../backend/tests/test_scan_evidence.py),
[browser records](../frontend/tests/scanrecords.test.mjs),
[retry unit tests](../frontend/tests/scanwrites.test.mjs).

| ID | Requirement | Status | Evidence and boundary |
| --- | --- | --- | --- |
| S01 | Complete-dataset search, intersecting filters, sorting and pagination | VERIFIED | S/R: SQL `_conditions` and `_ordering`; authorization before counts/rows; server-provided totals/options. Literal search escapes wildcard input. Combined-filter, scope and API validation tests. |
| S02 | Deterministic ordering on equal/null/numeric sort keys | VERIFIED | S/R: requested key NULLS LAST, timestamp DESC, UUID DESC. `test_equal_key_pages_are_deterministic_and_account_scoped`; numeric spoilage/finger-count tests. |
| S03 | Stable page membership while the dataset changes | PARTIAL | S/T/G: deterministic offset order does not pin membership across requests. PostgreSQL probe inserts ahead of page 2 and observes a repeated row (totals 5 then 6). Counts/rows also use separate statements; count-row interleavings and deletion skips were not separately injected. Snapshot semantics require a product decision. |
| S04 | CSV covers all matching rows independent of loaded/current page | VERIFIED | S/R/T: same scoped SQL filters, no offset/limit, streamed batches of 200. Actual PostgreSQL filtered exports ignore page limits; a 205-row cursor retains its query snapshot across a concurrent insert/source change. This verifies batch crossing, not unlimited-volume performance. |
| S05 | CSV commas, quotes, Unicode, CR/LF/CRLF and formula injection | VERIFIED | S/R: `csv.writer`, UTF-8 BOM, `_safe_cell` prefixes dangerous text including leading whitespace followed by = + - @; numeric values retain numeric types. Round-trip special-character tests. Spreadsheet products are not exhaustively tested. |
| S06 | Chronological inventory/status/correction/override history | VERIFIED | S/R: persisted `ScanEvent` with revision, timestamp, actor snapshot, reason, previous/new values; deterministic legacy-status/note merge. Actual classification changes are separate from source/status edits. |
| S07 | Historical actor/source/camera metadata is preserved | PARTIAL | S/R: new events and new scans persist snapshots; image/detection camera labels are stored. Unknown legacy actor/reason data is not invented. Legacy detail may fall back to the current account name; ordinary Logs/source options intentionally use current directory labels. Original legacy names cannot always be recovered. |
| S08 | Historical stable-ID/QR detail independent of shared list | VERIFIED | S/R: detail GET loads by UUID; `ScanDetailRecord` performs its own request and is keyed by account/role/scan ID. Historical direct-link browser tests use records absent from the shared list. |
| S09 | Complete detail hydration | VERIFIED | S/R: `serialize_detail` returns classification, original AI, images, detections, authorized notes and merged history; mapper preserves stored timestamps/nulls. No detections-only replacement. |
| S10 | Correct status operation with intended status/reason | VERIFIED | S/R: callers use `/status` with intended status, expected revision, request UUID and reason. Browser Logs status and bulk Intake tests inspect the actual envelope. |
| S11 | Source/status/no-op changes do not set classification overridden | VERIFIED | S/R: `apply_scan_change` compares actual classification changes and snapshots original values only when needed. `test_source_only_and_noop_do_not_override_classification`. |
| S12 | Classification override permissions and original values | VERIFIED | S/R: Admin-only override endpoint and shared service authorization; null original classifications remain unknown; actual corrected fields set override. Original AI retained. |
| S13 | Concurrent writes use CAS and transactional locking | VERIFIED | S/R: request-ID advisory lock, current actor lock and row revision checks. PostgreSQL simultaneous-writer test permits one revision commit; stale writer gets conflict. |
| S14 | Bulk membership/parent and single/bulk races | VERIFIED | S/R: parent lock and stable membership/revision snapshot; PostgreSQL tests cover membership changes and single/bulk conflicts. Bulk response returns IDs/revisions for client cache updates. |
| S15 | Duplicate, delayed and uncertain retries | VERIFIED | S/R: exact request UUID/fingerprint/actor/resource, receipt replay before revision rejection; changed payload/actor rejected. Retry previous retains the submitted request across navigation and changed drafts; no false success callback on definitive rejection. |
| S16 | Frontend/backend names, types and mutation envelopes | VERIFIED | S/R: ScanContext, Logs, Detail, Quality Control, Kiosk and Delivery Intake integrated; request/response fixtures, type check and build covered current source. |
| S17 | Detail/history/note/write/evidence authorization | VERIFIED | S/R: shared `scan_scope`/loader plus Admin note/override policy; real credentials, revocation and cross-operator regression cases. Operator detail and history omit private notes. |
| S18 | Missing/deleted/forbidden distinction | VERIFIED | S/R: 404 unknown absence, 410 authorized known tombstone, 403 inaccessible record/tombstone; browser states differ. Distinguishing 403 from 404 discloses that an opaque ID is inaccessible; protected record contents are not returned. This follows the requested distinction, not universal existence concealment. |
| S19 | Missing/unavailable image evidence does not break detail | VERIFIED | S/R: authenticated evidence endpoint validates registered path and containment; shared blob loader uses abort/revoke/fallback. Page text/history survives missing files. Unregistered paths are denied. |
| S20 | Stale reads and asynchronous notes do not overwrite newer state | VERIFIED | S/R: sequence/abort/account keys plus monotonic revisions; draft-preserving conflict reload and latest-note guards. Browser race/retry/navigation tests. |
| S21 | Edits and migrations preserve history | VERIFIED | S/R: immutable application events, legacy evidence merge; migration 0005 preserves rows/nulls. Strict v1 adapter does not fabricate historical events; v2 archives include history/receipts/tombstones. PostgreSQL restore/compatibility tests. |
| S22 | Full historical event retention after hard deletion | PARTIAL | S: `ScanEvent.scan_id` has ON DELETE CASCADE; ORM deletion retains only owner/id/time tombstone. No scan-delete API exists and retention does not delete records. Universal post-delete audit retention is not provided; see G04 before adding any destructive workflow. |
| S23 | Large/changing datasets and mid-stream export failures | PARTIAL | R/T: 205-row PostgreSQL stream retains its query snapshot across concurrent changes; a fresh export reflects the changes. Injected failure after 200 rows propagates and closes the cursor. Production-scale load/memory and end-to-end HTTP disconnect/download-failure behavior remain unmeasured; a 200 header alone does not prove complete delivery. |
| S24 | Preserve UI layout/navigation and completed functionality | VERIFIED | S/R: prior scoped diff and browser suites cover existing styles/components and required functional additions. Current audit changes no UI/application files; no new visual redesign. |

### Analytics

Primary paths: [Analytics UI](../frontend/src/pages/Analytics.tsx),
[API](../backend/app/api/v1/analytics.py),
[service](../backend/app/services/analytics.py),
[schema](../backend/app/schemas/analytics.py),
[backend tests](../backend/tests/test_analytics.py),
[browser tests](../frontend/tests/analytics.test.mjs).

| ID | Requirement | Status | Evidence and boundary |
| --- | --- | --- | --- |
| A01 | Clearly defined population, range and business timezone | PARTIAL | S/R: API definitions/range/timezone fields and UI metric help explain cohorts. Business-day computation is correct. UI does not explicitly render the returned timezone or successful refresh timestamp; add a concise existing-style label if required. |
| A02 | Throughput/risk/confidence/human accuracy are distinct | VERIFIED | S/R: all scans for throughput, complete classification denominator, valid original-model confidence, scoped active-stock risk. Human-verified accuracy is explicitly unavailable, not replaced with confidence. |
| A03 | Source/date filters reach the authoritative SQL aggregates | VERIFIED | S/R: `_conditions` includes selected source/range and excludes future-dated scans. Range and source tests independently check populations. |
| A04 | Fixed 14-day chart clearly independent of selected range | VERIFIED | S/R: server separate trend window; UI title and explicit fixed start/end/source description. Empty selected cohort still explains separate trend. |
| A05 | Today and calendar ranges use Asia/Manila | VERIFIED | S/R: shared time helpers and local-hour aggregation; exact lower bounds and midnight fixture tests. No UTC-day substitution. |
| A06 | Risk ages shelf life and respects current inventory state | VERIFIED | S/R: remaining midpoint minus elapsed seconds/days; latest status with ID tie-break; <=2 includes overdue. Unknown/invalid estimates counted separately. F02 concerns Inventory UI, not this calculation. |
| A07 | Sold/spoiled/processing/depleted stock excluded | VERIFIED | S/R: `_current_stock` requires In Stock and Active-or-absent intake. Explicit inactive/sold tests. Dashboard uses a different depleted-intake policy (F03), so cross-view agreement is not verified. |
| A08 | Source options stable across filters and renames | VERIFIED | S/R: options drawn from all authorized source history, linked supplier UUID keys and text fallback; selected key remains authoritative on rename. Filtered-empty response retains choices. |
| A09 | Incomplete/null classifications use correct denominators | VERIFIED | S/R: known cultivar AND ripeness for classification charts; valid original score 0..100 for confidence; human overrides without original excluded. Independent arithmetic cross-check below. |
| A10 | Empty/zero/unavailable are distinct | VERIFIED | S/R: null confidence renders unavailable, zero samples/counts are explicit; request errors replace charts with retry, not successful zero/stale filter result. |
| A11 | Rapid filter changes cannot publish obsolete results | VERIFIED | S/R: resource load identity/sequence/abort; source-option setter checks abort; browser deliberately delays the old response. |
| A12 | Combined date/source/cultivar/status filters | MISSING | S: UI and API offer date/source; no cultivar/status filter contract or controls. F06. Classification breakdown charts are not those filters. |
| A13 | Operator scope/renames and aggregation identity | VERIFIED | S/R: reuses account-scoped projection; UUID grouping and role guards; namesake/rename tests. |
| A14 | PostgreSQL execution of Dashboard/Analytics metric SQL | VERIFIED | T: actual PostgreSQL 18 queries executed for review/risk populations, exact Manila lower-day boundary, incomplete classifications, original confidence (0/75/60 => 45 mean, 66.7% low), namesake operator exclusion, supplier rename and filtered-empty source options. No compiler-only inference. |

Independent arithmetic checked against existing fixture assertions (not a new database
execution): `test_confidence_excludes_missing_invalid_and_unrecoverable_overrides`
creates eight scans. Six have recognized current class labels. Valid AI confidence
samples are 0, 75 and saved original 60: sample count 3, mean `(0+75+60)/3 = 45`,
strictly below 75 count 2, rate `round(2/3*100,1) = 66.7`. A manual 100 without an
original, -1, 101, missing and unknown-class scores are not model samples. The range
fixture expects Today/7-day/30-day/all totals **1/2/4/5**, while all selections share
the independently defined 14-day trend total **3**.

The new PostgreSQL probe separately executes a smaller midnight/original-confidence
fixture: four own scans today (three classified, one incomplete), three valid original
scores 0/75/60, mean 45 and low-confidence rate 66.7%. The scan one microsecond before
Manila midnight and the other operator's scan are excluded. This supplements the
broader earlier fixture; it does not reclassify its eight-scan assertions as a new run.

### System Configuration, Export and Maintenance

Primary paths: [config API](../backend/app/api/v1/config.py),
[configuration service](../backend/app/services/configuration.py),
[schemas](../backend/app/schemas/common.py),
[camera manager](../backend/app/services/camera_manager.py),
[scan pipeline](../backend/app/services/scan_service.py),
[retention](../backend/app/services/data_retention.py),
[maintenance API](../backend/app/api/v1/maintenance.py),
[archive](../backend/app/services/backup_archive.py),
[restore](../backend/app/services/backup_restore.py),
[coordinator](../backend/app/services/runtime_operations.py),
[database locks](../backend/app/services/maintenance_database.py),
[power control](../backend/app/services/power_control.py),
[SystemConfig UI](../frontend/src/pages/admin/SystemConfig.tsx),
[backup controls](../frontend/src/components/StationBackupControls.tsx).

| ID | Requirement | Status | Evidence and boundary |
| --- | --- | --- | --- |
| M01 | Saved versus applied state and configuration persistence | VERIFIED | S/R: canonical versioned row, revision/CAS, separate runtime mapping/application status/error/applied revision. Commit failure does not publish hardware configuration. `test_configuration.py`. |
| M02 | Validation, invalid thresholds and duplicate IDs | VERIFIED | S/R: strict integer threshold 1..100, required revision, distinct nonnegative physical IDs, logical limits/uniqueness and slot-count agreement. Invalid/null/fractional/out-of-range inputs rejected before persistence. |
| M03 | Restart/reconfiguration requirements clear | VERIFIED | S/R: editable settings apply live or on next scan; camera mapping has explicit apply status. Runtime response sets restart-required false for these fields; deployment model changes are identified as backend restart work. No claim that arbitrary deployment/environment changes apply live. |
| M04 | Saved threshold affects real async inference | VERIFIED | S/R: pipeline reads a single saved threshold snapshot, converts percent to fraction and passes it explicitly to worker classifier prediction. Async worker regression. Separate fusion/flag policy is not silently changed. |
| M05 | Physical slot mapping, stable device UUID and truthful online state | VERIFIED | S/R: persisted physical/logical lists, reconfiguration through CameraManager, rename by slot preserves UUID, new devices Offline until usable frame verification. Partial initialization records applied failure/partial state. Mock frame tests, not hardware acceptance. |
| M06 | Concurrent configuration edits and frontend drafts | VERIFIED | S/R: expected revision mismatch 409; no lost persisted update. Frontend conflict state/reload, single-flight save and draft merge. No broad UI restyling. |
| M07 | Genuine restorable backup, distinct from CSV | VERIFIED | S/R: versioned archive contains application tables and referenced evidence; CSV explicitly described as scan summary/non-restorable. HTTP download/validate/restore acceptance covers real production routes with mocked hardware lifespan. |
| M08 | Corrupt/incomplete/incompatible/unsafe archives rejected | VERIFIED | S/R: hashes, typed rows, schema/constraints, version compatibility, bounded members/expanded size, safe contained paths and no executable SQL. Frozen strict v1 adapter and current v2 round-trip tests. |
| M09 | Restore preparation, confirmation, authentication and ownership | VERIFIED | S/R: Admin, password/REPLACE confirmation, actor/session-bound expiring validation, model prerequisites, private staging and validation before station replacement. One-use validation/replay regressions. |
| M10 | Partway failure, rollback, uncertain commit and startup recovery | VERIFIED | S/R: validated rollback archive, durable journal/phases, staged evidence, compensation and fail-closed recovery. PostgreSQL injected pre/post-commit failures, preparation failures and data-verified/hardware-refresh crash boundary. |
| M11 | Session invalidation and recovery login | VERIFIED | S/R: non-restored auth generation invalidates old sessions; sockets close. HTTP acceptance verifies old-session rejection and restored-credential login. Separate test verifies administrator-only read-only recovery login. |
| M12 | Full disk, missing evidence and partial backup failures | VERIFIED | S/R: disk checks plus caught write failures; validate/fsync before publication, no false created success. Tests for disk full, truncated archive and missing referenced evidence. Backup will fail safely if required evidence is absent; fallback detail display does not make that archive complete. |
| M13 | Operational retention enforcement | VERIFIED | S/R: startup worker and six-hour cycle under exclusive coordination; configured age and enable flag. Only expired unreferenced capture directories are eligible. This is the approved orphan-only policy, not deletion of old scan rows. |
| M14 | Retention protects active-stock evidence, audits and history | VERIFIED | S/R: all persisted scan IDs and image/thumbnail references protected, stronger than active-stock-only protection. Symlink/path guards and failure status; no historical DB deletion. `test_retention_preserves_all_persisted_history`. |
| M15 | Restart/shutdown stop admission and drain active scans | VERIFIED | S/R: StationCoordinator admission/drain, protected blocking work/disconnect handling, station lock, production HTTP middleware and PostgreSQL barrier. Timeout does not cancel active scan into a partial transaction. |
| M16 | Failed/uncertain OS commands and power cancellation | VERIFIED | S/R: shared request/cancel lock; persisted intent before dispatch; rejected command fails, uncertain timeout remains blocked; accepted means OS accepted, not powered off. Idempotent cancellation and boot identity reconciliation tested with mocks. |
| M17 | Queued operations recheck current authorization | VERIFIED | S/R: `fresh_authorization` evaluates original token/current role/version/generation/password after locks/drain. Queued role, token and generation revocation cases. |
| M18 | Concurrent processes/controls cannot bypass maintenance state | VERIFIED | S/R: single station-owner advisory lock, transaction shared/exclusive barriers, middleware, durable states. Owner-loss fail-closed and PostgreSQL HTTP admission tests. Production must retain the single camera-owner deployment model. |
| M19 | Startup monitoring and idempotent recovery/apply | VERIFIED | S/R: retry-loop initial probe, publish device status only after persistence, deferred runtime starts once; apply operation IDs and recovery markers avoid repeated initialization. Historical four maintenance blockers are resolved. |
| M20 | Latest maintenance status wins under overlapping polls | DEFECTIVE | S/T: actual SystemConfig mocked browser holds an old ready response, delivers recovery-required, then releases old ready. Reset Defaults becomes enabled again with exactly two requests. Missing sequence/single-flight guard; backend admission still authoritative. F09/G03. |
| M21 | Very large config CSV export and streaming resource limits | NOT VERIFIED | S/G: Logs CSV uses bounded batches; config summary export materializes its limited columns for all records. No volume/peak-memory acceptance proof. Its fields are ID/enum/date/numeric rather than arbitrary user text. |
| M22 | Real physical cameras, host power, storage and abrupt power loss | NOT VERIFIED | Explicitly deferred by user; no live operations. Isolated/mocked verification is not proof of deployed device drivers, filesystem permissions, OS privileges or actual power-loss durability. |

### Cross-system consistency and preservation

| ID | Requirement | Status | Evidence and boundary |
| --- | --- | --- | --- |
| X01 | Consistent stable identifiers and authorization | PARTIAL | S/R: scan/metrics/history/evidence share account/profile UUID scope; kiosk events owner/current Admin only. Inventory source UI still filters strings; supplier/intake registry APIs are shared and their intake `scan_count` is global. Clarify shared-registry metadata policy before treating this as private scan access or changing it (G05). |
| X02 | Consistent business timezone and elapsed age | DEFECTIVE | S/P/R: server and historical timestamp handling use shared Manila helpers; Inventory risk uses original estimate without age, not a timezone conversion (F02). Keep existing timezone helpers; fix risk logic rather than shift timestamps. |
| X03 | Consistent classification/confidence terminology | PARTIAL | S/R: no measured-accuracy claim. Analytics uses original AI confidence; Dashboard group/Logs averages use current classification confidence. These are different populations after overrides, with insufficient cross-view labeling to treat the same numeric label as the same metric. |
| X04 | Stock status and eligibility give consistent information | PARTIAL | S/R/T: latest status is shared, but depleted/unlinked eligibility differs (F03), confirmed in PostgreSQL. The authoritative population requires a business decision, so no one predicate is declared defective. Inventory's distinct age bug remains X02/F02. Selected date-cohort differences are legitimate. |
| X05 | Mutation propagation and refresh consistency | VERIFIED | S/R: commit-before-success, revision-aware caches, bulk revision map, scan completion events and polling/focus refresh. Metrics are eventually refreshed, not an atomic multi-page snapshot immediately after every write. |
| X06 | Historical evidence after edits/deletion/migration | PARTIAL | S/R: edits/migrations preserve recorded history; null legacy values stay unknown. Hard-delete cascades are not full audit retention (S22/G04). Archive restoration intentionally replaces station history with the validated backup snapshot. |
| X07 | Stale data and partial API failures handled across views | PARTIAL | S/R/T: Dashboard/Analytics/Logs/Detail guards are verified. Mocked actual Inventory reproduces successful-zero and silently stale eligibility after intake failure (F07); delayed maintenance ready replaces recovery-required (F09). |
| X08 | No current audit regression to existing UI/maintenance/hardening | VERIFIED | S/R: runtime/test files unchanged versus final verified source; current diff contains audit documents/probes/checkpoint only. No old commit restoration. Installer/example changes pre-exist this audit and are not covered by this statement. |

## Confirmed findings and proposed corrections

All priorities below are **Medium or Low**. No Critical/High vulnerability was
demonstrated by this scoped audit. That is not a guarantee of system-wide security.
The old scan authorization, retry and maintenance review findings are resolved and
are not relabeled as outstanding defects here.

### F01 — Medium: pending-review shortcut omits part of its count

- **Current path:** `Dashboard.tsx:41-51,134-148,231`; `scanLogFilters.ts:16-40`;
  `dashboard.py:_review`; `scan_logs.py:_conditions`.
- **Expected:** shortcut records equal all authorized scans counted by the KPI.
- **Actual/root cause:** backend count is `flagged OR confidence < threshold`; both
  current and legacy Dashboard links send `status=Flagged`, which becomes only
  `flagged_only=true`. An unflagged 60% scan under the 85% threshold is counted but
  absent from that shortcut. Backend `attention=review` already implements the right
  predicate; no new query engine or schema is necessary.
- **Evidence:** P review-URL probe; R backend threshold/review test; current browser
  test explicitly expects `{status:"Flagged"}` and therefore misses semantic parity.
  T actual PostgreSQL at threshold 75: low 60 + flagged 95 => review count 2,
  Flagged count 1; equal 75 and other-operator records excluded from review. Filtered
  CSV returns both review IDs even with page=4/page_size=1.
- **Minimal fix:** use `attention=review` in both Dashboard link paths; preserve
  ordinary explicit Flagged filtering. Correct the browser expectation and connect
  actual review fixtures to the click result.
- **Acceptance:** flagged high-confidence + unflagged low-confidence scans both appear;
  equal-threshold/unflagged and other operators do not; displayed count equals the
  filtered export total. Existing all-time review scope is preserved.

### F02 — Medium: Inventory spoilage alerts ignore age and misclassify unknowns

- **Current path:** `Inventory.tsx:40-46,85-108`; `utils.ts:100-106`;
  `scanData.ts` maps missing estimates to `Unknown`. Server equivalents are
  `dashboard._prediction_days/_remaining_days/_expiring`.
- **Expected:** evaluate remaining shelf life, keep unknown estimates unknown, use
  one definition for actionable stock risk.
- **Actual/root cause:** Inventory compares `parseSpoilageAvg(original estimate)` to
  two days. A four-day-old `5-7` scan is omitted (6 > 2), while server remaining life
  is 2. `Unknown`, `NaN` and empty strings become 0; reversed `3-1` becomes 2 and
  also alerts. The Inventory “oldest scan” grouping does not correct this calculation.
- **Evidence:** P actual parser/predicate probe; R server aged/invalid prediction tests.
  T actual PostgreSQL returns remaining_days=2 for the four-day-old 5-7 scan;
  Analytics and Logs correctly classify its aged risk. No timezone adjustment is needed.
- **Minimal fix:** consume server-produced remaining/unknown-risk data for Inventory
  (preferred), or a single explicitly aligned client contract if necessary. Do not
  change timezone conversions, retrospectively rewrite predictions or globally alter
  a shared utility without auditing its other callers.
- **Acceptance:** aged ranges, overdue, exact two-day boundary, unknown/reversed/
  nonfinite/negative estimates agree with authoritative risk at a frozen instant;
  sold/spoiled/processing excluded; clock refresh ages stock without needing a new scan.

### F03 — Medium: stock eligibility differs across views; policy decision required

At the same instant, source and all-time scope:

| Record (latest status In Stock, one day remaining) | Dashboard / Logs risk | Analytics risk | Inventory risk population |
| --- | --- | --- | --- |
| Linked Active intake | Included | Included | Included |
| Linked Depleted intake | Included | Excluded | Excluded |
| No intake | Included | Included | Excluded |

- **Source:** `dashboard._expiring`; `analytics._current_stock:117-121`;
  `Inventory.tsx:21-22`. This is not merely a timezone/range bug.
- **Evidence:** R `test_supplier_identity_precedes_text_and_depleted_intake_keeps_stock`
  explicitly asserts Dashboard inclusion; `test_risk_ages_estimates_and_excludes_removed_stock_and_depleted_intakes`
  explicitly asserts Analytics exclusion. Intake status PATCH can change the parent
  independently, so these states are representable without inventing corrupt fixtures.
  T PostgreSQL fixture confirms Dashboard/Logs risk=3 (aged Active, Depleted, unlinked)
  while Analytics risk=2 and unknown=1. Inventory's membership restriction is also
  traced in source; browser F07 confirms that its eligibility depends on the intake list.
- **Decision:** is latest per-scan stock status authoritative despite depleted intake,
  and should unlinked scans count as inventory? Current service documentation supports
  conflicting answers. Do not silently pick one or rewrite operational records.
  This is a confirmed inconsistency with **policy-dependent correctness**, not proof
  that Dashboard or Analytics alone is wrong. Choose whether Depleted parents override
  child In Stock state and whether unlinked scans are real stock or awaiting intake.
- **Minimal fix after decision:** centralize the agreed eligibility predicate, retain
  each view's explicit date cohort and actor scope, update metric definitions and
  parity fixtures. Reconcile legacy contradictory state only through a separately
  approved, audited operation if needed; no migration is automatically necessary.
- **Acceptance:** same authorized fixture/date scope yields the same eligible IDs and
  risk count in all four views; test every intake/status combination and transitions.

### F04 — Medium: daily group counts navigate to all history without a scope label

- **Current path:** `DashboardRecords.tsx:79,87` deliberately supplies empty business
  date; `Dashboard.openRecords` passes that through; URL builder omits falsy date.
- **Expected:** selecting “N scans” underneath a daily KPI opens those N scans, or
  clearly offers a distinct all-history action.
- **Actual:** selected-day group count remains N but next page can contain M lifetime
  scans. P proves empty date removal; existing browser tests check group opening,
  not row cohort parity. This does not broaden account authorization.
- **Minimal fix:** preserve `selectedDate` for the row action. If all history is
  intentional, label it explicitly and retain a path to the counted daily records.
- **Acceptance:** fixtures with yesterday/today scans for one source/operator, and an
  open modal crossing Manila midnight, retain the selected day and stable ID filter.

### F05 — Low: Operator success KPI lacks required drilldown

`Dashboard.tsx:204` intentionally omits `onClick` for Operators. Its percentage is
server-derived from all accessible scans not matching the rule-based review predicate,
not a today's-only or human-verified accuracy metric. Add a scoped, clearly defined
drilldown using that exact population if this “every KPI” requirement is approved.
Test empty denominator, flagged/null/threshold boundary and other-user exclusion.
Do not simply navigate to all scans and call that the numerator. No redesign required.

### F06 — Low: requested Analytics cultivar/status filter combinations are absent

`analytics.py:analytics_summary`, service `_conditions`, API types and Analytics UI
accept date/source but not cultivar/status. These are missing capabilities relative
to the audit request, not regressions in the implemented two-filter feature. Agree
which charts (including fixed trend) inherit them, then add optional validated fields
through the existing contract. Acceptance: intersecting date/source/cultivar/status,
stable source options, clear denominators, empty results and delayed-response tests.
Use existing controls/design; do not rewrite working aggregation.

### F07 — Medium: failed intake loading can look like successfully empty Inventory

- **Source:** `InventoryContext.tsx:73-101` catches rejected intake fetch by logging
  a warning; it exposes neither intake loading nor intake error. `Inventory.tsx:21-22`
  requires membership in that list, but its unavailable state at 136 onward checks
  only scansLoading/scansError.
- **Counterexample:** fresh account/store, scans load successfully, `/intakes` fails;
  intake IDs stay empty and stock totals become zero. After a previous load, a failure
  can instead silently reuse old intake eligibility.
- **Evidence:** T actual Inventory/InventoryContext in a mocked browser: one loaded
  scan plus failed initial `/intakes` shows Total Hands=0 with no alert. A subsequent
  failed refresh preserves the earlier Active intake and Total Hands=1 even though
  the mocked server's latest intake is Depleted; there is no stale indication.
- **Minimal fix:** expose intake load/error/snapshot status and use the existing
  loading/error/retry pattern for inventory calculations; preserve last snapshot only
  with an explicit stale indication. No supplier/scan behavior rewrite.
- **Acceptance:** independently reject intake vs scan endpoints; neither failure
  produces a successful empty stock result; retry and account switch behave correctly.

### F08 — Low: deployment migration target is outdated

`backend/README.md:94` tells deployers to confirm `0004_maintenance_state`, while the
current code includes `0005_scan_record_history`. The updater/schema tests are present;
this is documentation drift, not a missing migration. After authorization update the
rollout instructions to the current head and mention revision/history/archive-v2
compatibility. Acceptance: documented head matches the migration registry on a
disposable upgrade/restore rehearsal. Do not run migration against the live station.

### F09 — Low: delayed maintenance polling overwrites newer recovery status

- **Source/root cause:** `SystemConfig.tsx:46-55` starts overlapping five-second polls
  with only an unmount guard; response completion order becomes state order.
- **Evidence:** T actual SystemConfig browser fixture holds the first `ready` response,
  returns `recovery-required` from the second, and observes Reset Defaults disabled.
  Releasing the first response enables that button again; exactly two requests occurred.
- **Impact:** misleading availability and avoidable rejected actions. This does not
  demonstrate a maintenance bypass: backend admission remains authoritative and no
  real maintenance/hardware operation was performed.
- **Minimal fix:** a request sequence/identity or single-flight poll guard that also
  invalidates in-flight reads after local operation state updates and unmount/account
  changes. Preserve existing controls and backend power/restore coordination.
- **Acceptance:** old ready cannot replace newer recovery-required or an operation's
  newer status; failed polls do not fabricate ready; retry and unmount remain correct.

## Partial implementations, policy and verification gaps

- **G01 — changing dataset semantics:** deterministic offset sorting is implemented;
  a cross-page snapshot is not. `collectScanPages` detects some incomplete/duplicate
  traversals and throws instead of publishing partial history, but equal-count changes
  cannot universally be detected. Agree whether cursor/snapshot semantics are required
  before increasing complexity. T reproduces an insertion-driven repeated page row,
  while complete filtered export remains unique. The single export cursor preserves
  its 205-row query snapshot during concurrent changes and closes on injected failure.
  Cross-request paging snapshots, count/row interleavings, production-scale resource
  limits and end-to-end interrupted-download acceptance remain separate requirements.
- **G02 — metadata and terminology:** Analytics returns timezone/range/refresh metadata
  but doesn't render all of it; Dashboard group/Logs averages are current confidence,
  Analytics is original AI confidence. Label populations rather than silently changing
  valid historical values. Human-verified accuracy remains unmeasurable without a
  separate ground-truth workflow; this audit does not authorize one.
- **G03 — maintenance polling:** now reproduced in an actual-component browser test
  and promoted to F09/M20 DEFECTIVE. Backend admission still denies prohibited requests;
  the UI race does not establish an unsafe operation or invalidate prior backend tests.
- **G04 — deletion scope:** tombstones distinguish known ORM deletions; historical raw
  SQL deletions have no guaranteed ledger and old deletions without evidence are 404.
  Hard deletion cascades events/status/notes rather than retaining a complete audit.
  No delete API exists and approved retention keeps all persisted scans. A universal
  deletion/audit policy requires an explicit product decision before adding one.
- **G05 — shared metadata policy:** `/intakes` is authenticated but lists shared intake
  metadata/global scan counts; per-scan endpoints/aggregates remain owner-scoped for
  Operators. Inventory source filtering uses labels rather than stable supplier keys.
  Clarify whether shared registry/count visibility is intended. No claim that private
  note/evidence contents are exposed, and no new permission expansion is proposed.
- **G06 — runtime/environment:** PostgreSQL metric SQL, cross-view fixtures, F07 browser
  failures, F09 poll race and streamed-export failure characterization are now executed.
  Remaining limits: production-scale volume/memory, actual HTTP mid-download failure,
  physical cameras, real OS power, deployed storage permissions and abrupt power loss
  remain expressly deferred. Installation changes in the merge need separate safe
  setup validation before deployment; do not run the setup script on the live station.

## Verification performed and reused

| Check | Actual outcome and scope |
| --- | --- |
| Current Git branch/status/history | `main`, initial HEAD `0a4c87e`; user committed audit evidence in `26577da` and `5483861`. No assistant commit/branch/worktree operations. Final report/checkpoint changes listed in checkpoint. |
| `git diff --name-status fa63f5d..HEAD -- backend frontend` | Only `backend/.env.example`; current runtime/test source unchanged. Full diff also includes installer and docs, preserved. |
| `node --test docs/audits/system-audit-probes-2026-10-10.mjs` | **3 passed, 0 failed/skipped, 100.1355 ms, exit 0**. Pure source-function characterization of F01/F02/F04, no app/server/DB imports or writes. Passing means defects were observed. |
| Targeted backend audit run, 2026-10-11 (T) | **84 passed, 14.43 s, exit 0**, seven backend files below. Earlier usage/approval block resolved through normal approval; the historical blocked attempt itself produced no result. |
| PostgreSQL metric/cross-view probes (T) | **4 passed, 2.91 s, exit 0**. Actual PostgreSQL 18 service queries, frozen time, isolated generated schema. Review mismatch, eligibility policy, Manila midnight, original confidence, source scope and changing offset pages. |
| PostgreSQL streamed export/failure probes (T) | **2 passed, 4 deselected, 2.00 s, exit 0** with `-k 'streamed_export or midstream'`. Added after the first four passed; all six new tests covered without repeating them. Real 205-row result plus injected cursor failure. |
| Actual-component mocked browser probes (T) | **3 passed, 0 failed/skipped, 28.7514411 s, exit 0**. F07 initial/refresh intake failures and F09 delayed maintenance response. Vite explicitly `configFile:false, envFile:false`; all API/WebSocket traffic mocked. No frontend environment contents read. |
| Reused final backend/PostgreSQL run (R) | **222 passed, 71.19 s, exit 0**, no skipped PostgreSQL cases. Includes current scan, security, migration, archive and maintenance HTTP acceptance tests. |
| Reused frontend run (R) | **54 passed, 0 failed/skipped, 60.2775 s, exit 0**. Includes Dashboard, Analytics, maintenance, persistence, scan browser and retry tests. |
| Reused TypeScript / production build (R) | Application type check exit 0; `npm run build` exit 0, Vite 9.44 s. No app changes warrant another build for audit documents. |
| Reused lint comparison (R) | ESLint 43 errors/8 warnings; Ruff 620 diagnostics vs 660 same-tool baseline. Zero introduced diagnostics in the completed task. Full lint is **not clean**; no unrelated autofixes. |
| Audit syntax/link/matrix/diff checks | Both JavaScript files pass `node --check`; Python probe passes stdlib AST parse without application imports. Updated report: 52 local links, 0 missing; 82 unique IDs with counts 64/11/4/1/2. Whitespace/conflict-marker and `git diff --check` pass. No production paths changed. |

Executed targeted backend command (repository-root PowerShell):

```powershell
@'
import os,sys,tempfile
from pathlib import Path
b=Path('backend').resolve()
w=Path(tempfile.mkdtemp(prefix='bv-audit-final-'))
print('AUDIT_TEMP='+str(w), flush=True)
os.environ.pop('BANANAVISION_TEST_DATABASE_URL',None)
os.chdir(w);sys.path.insert(0,str(b))
import pytest
files=['test_dashboard.py','test_analytics.py','test_scan_logs.py','test_scan_records.py','test_scan_evidence.py','test_configuration.py','test_maintenance_integration.py']
raise SystemExit(pytest.main(['-p','no:cacheprovider','-q','--basetemp',str(w/'fixtures'),'-c',str(b/'pyproject.toml'),*[str(b/'tests'/f) for f in files],'--tb=short']))
'@ | & './backend/venv/Scripts/python.exe' -X utf8 -B -
```

Executed PostgreSQL probe command while the newly created and verified audit cluster
was running (these identifiers are historical evidence, not permission to connect to
whatever later occupies the port). Fixture verifies both URL and `SHOW data_directory`
before creating a random schema, and drops only that schema in `finally`:

```powershell
@'
import os,sys,tempfile
from pathlib import Path
b=Path('backend').resolve();test=Path('docs/audits/test_system_audit_metrics.py').resolve()
w=Path(tempfile.mkdtemp(prefix='bv-audit-metrics-'));print('AUDIT_TEMP='+str(w),flush=True)
os.environ['BV_AUDIT_DATABASE_URL']='postgresql+asyncpg://bv_audit@127.0.0.1:56846/postgres'
os.environ['BV_AUDIT_PG_DATA']='C:/Users/Roronoa Zoro/AppData/Local/Temp/bv-audit-pg-8227c7618dff479eb059aab1d0424c38/data'
os.chdir(w);sys.path.insert(0,str(b));import pytest
raise SystemExit(pytest.main(['-p','no:cacheprovider','-q','--basetemp',str(w/'fixtures'),'-c',str(b/'pyproject.toml'),str(test),'--tb=short']))
'@ | & './backend/venv/Scripts/python.exe' -X utf8 -B -
```

The first invocation contained four tests. After adding the two export tests, the
second invocation used exactly the same script with prefix `bv-audit-stream-` and
pytest arguments `'-k','streamed_export or midstream'` appended. The first four were
deselected, not skipped or rerun. Aggregate new backend coverage is 84 + 4 + 2 passing
tests across three runs, not a single 90-test full-suite run.

Executed browser command (installed local Playwright runtime):

```powershell
$env:PLAYWRIGHT_MODULE='C:/Users/Roronoa Zoro/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
node --test --test-concurrency=1 docs/audits/system-audit-browser-2026-10-11.mjs
```

No denied command was bypassed. The initial blocked attempt remains historical only;
no outstanding approval/usage blocker remains for this audit. The
[verification report](scan-records-verification-2026-10-10.md)
contains exact previously executed full-suite/type/build/lint commands and cleanup
evidence. No historical test result is relabeled as a new audit run.

## Security, data integrity and deployment boundaries

Current source inspection plus reused tests support the scan ownership, Admin-note,
evidence containment, CAS/idempotency, queued-authorization and maintenance barriers.
No new whole-repository Codex Security scan was run. Completed scan
`c49fcb93-82d3-4452-8183-9be1cf9571e9` has zero newly introduced reportable findings
in immutable `e3e1c07..1a13e0b`; it does **not** cover later `4094852`. The latter had
separate scoped review and regression verification. Older maintenance scan findings
were fixed and checked separately. Preserve those precise scope limits.

The main data-integrity concerns remaining here are wrong risk/action populations,
silent partial inventory loading and changing-dataset snapshots, not evidence of
new unauthorized mutation bypass. F03/G05 need policy clarification rather than an
unreviewed permission or historical-data change. Backups include sensitive records
and password hashes and require protected deployment storage/access; this audit is
not a proof of production filesystem ACLs or operational key/backup management.

Prior cleanup is documented: the task PostgreSQL cluster on 56845/PID 50664 was stopped
and its exact directory removed, with all 26 recorded task-temp directories and the
machine-specific helper. Maintenance disposable instances were previously removed too.
This continuation created and subsequently stopped a **different** PostgreSQL 18
instance: `bv-audit-pg-8227c7618dff479eb059aab1d0424c38/data`, PID 41200,
localhost port 56846. Cleanup verified its exact data directory, `postmaster.pid`,
PostgreSQL executable and listener ownership before `pg_ctl -D <exact-data> -w -t 30 stop`.
Stop exited 0; the recorded process and listener were absent afterward. Vite/Chrome
were closed by browser-test teardown.

All seven exact generated OS-temp roots were then checked for containment and reparse
points, removed with PowerShell `Remove-Item -LiteralPath`, and verified absent:

- `bv-audit-pg-8227c7618dff479eb059aab1d0424c38`
- `bv-audit-final-yd0_aetp`
- `bv-audit-metrics-5rsedin0`
- `bv-audit-stream-xs354sca`
- `bv-audit-browser-V9v2AE`
- `bv-audit-browser-QbTHjT`
- `bv-audit-browser-K7o7Um`

No unrelated process/directory was targeted. Do not stop arbitrary processes now using
these historical ports. The committed audit probes/report and archived checkpoint
are intentional durable evidence, not cleanup residue.

## Prioritized implementation and verification plan (not executed)

1. **Resolve scope decisions:** F03 eligible stock/depleted/unlinked policy; F04 daily
   versus explicitly labeled all-history drilldown; G05 shared registry/count visibility.
   Keep per-user scan authorization and Manila cohort definitions unchanged.
2. **Small independent corrections:** F01 review navigation, F04 chosen date behavior,
   F07 intake error/loading states, F09 maintenance poll ordering, F08 deployment
   documentation. Write behavior-level regressions before application edits;
   no schema redesign required.
3. **Risk consistency:** implement F02 using the chosen F03 predicate and authoritative
   elapsed/unknown estimate data. Freeze time and compare IDs/counts in all views,
   including source rename, sold/processing, incomplete estimates and midnight.
4. **Requested additions:** F05 exact success-population drilldown, F06 optional Analytics
   cultivar/status filters, G02 concise definition/time labels. Keep current components
   and styling; align contracts and source-option behavior.
5. **Close remaining acceptance gaps only where required:** agree dataset-size and
   latency/memory budgets for config/Logs exports, then measure them in a disposable
   environment; inject HTTP disconnects at the client/server boundary. Choose whether
   stable cross-request page snapshots are required before changing pagination.
   PostgreSQL metrics and F07/F09 reproduction are complete and need no repeat until
   a fix changes behavior. Live acceptance remains a separately authorized operation.
6. **Final authorized implementation checks:** targeted tests first, then applicable
   full backend/PG and frontend tests, type/build, baseline-aware lint and scoped security/
   diff review. Keep maintenance acceptance and scan hardening suites intact. No live
   acceptance, production migration, push or deployment without explicit authorization.

The audit's approved source inspection, targeted runtime characterization, evidence
review and cleanup are complete. Remaining unverified scenarios and policy choices
are explicitly bounded above; recommended corrections are **not implemented** by
design. The current [checkpoint](../TASK_PROGRESS.txt) records final Git/check results
and the next authorization-dependent actions. Audit completion does not mean that
all 82 implementation requirements passed or that deployment/live acceptance occurred.
