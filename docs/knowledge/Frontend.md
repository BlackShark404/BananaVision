# Frontend Architecture & UI Design System

BananaVision's frontend is a React 19 single-page application built with Vite, TypeScript, Tailwind CSS, and Radix UI primitives.

## Loading State Conventions

The UI distinguishes between initial loads, continuous/hardware actions, and background refreshes to prevent UI flicker, premature zero/empty states, and unexpected layout shifts:

1. **Initial Structured Loading**:
   - Uses `<Skeleton>` components (`components/ui/skeleton.tsx`) to match target layout dimensions for dashboards, tables, cards, and scan detail grids before data arrives.
   - Prevents empty state flashes ("No records found") while requests are in-flight.

2. **Background Refreshes & Retained Snapshots**:
   - Managed via `useDashboardResource<T>` hook (`hooks/useDashboardResource.ts`).
   - Supports `{ keepPreviousData: true }` and exposes `isPreviousData`; refresh activity is derived from `loading` with an existing `data` snapshot.
   - When a polling cycle or filter update triggers, previous data remains visible while subtle refresh indicators show activity.
   - Dashboard retains its snapshot with stale/error feedback. Analytics retains previous selections while fetching, but deliberately displays its error/retry panel after a failed refresh.

3. **Ongoing Actions & Hardware Operations**:
   - Hardware operations (camera calibration, backup, label printing, power commands) use explicit loading spinners, progress indicators, or status badges.
   - Buttons remain disabled during execution while preserving accessible labels (`"Shutdown Now"`, `"Restart Now"`).
   - Rejection and failure modes preserve entered form drafts (e.g. calibration settings, notes, or thresholds) and provide clear retry paths without discarding user input.

4. **Readiness, request ordering and recovery**:
   - Providers distinguish `ready` from `loading`: a successful empty response is ready; a failed initial request is an error, not an empty result. Users, suppliers and intakes settle independently.
   - Successful user/supplier writes invalidate older list requests. If the first list is still pending, fetch a complete new snapshot so untouched rows are not lost. Account changes discard old snapshots.
   - JSON reads through the shared API helper have a 15-second deadline covering response parsing, preserve caller cancellation and do not clear authentication on timeout. PIN swap/setup and idempotent notification mark-read writes opt into the same deadline so pending controls recover. PIN setup timeout explicitly reports an unknown result. Hardware mutations and archive downloads retain their separate operation/status workflows.
   - Notifications use initial skeletons, retained refresh content, retryable errors and guarded mark-read actions. A delayed read cannot undo a confirmed mark-read.
   - Kiosk operator selection has loading/error/empty recovery. Queued PIN verification is cancelled on Back/close; an active verification cannot be submitted twice or dismissed. Scan completion exposes a server review flag.
   - Device readings remain unknown until data arrives; no fabricated zero or unconditional "Optimal" status. New live readings supersede older HTTP responses.
   - Quality Control preserves the correction draft's baseline revision until explicit conflict recovery. Recovery actions are inside the modal so its focus/pointer boundary cannot block them. Once a retry is confirmed, a failed refresh offers read recovery; definitive rejection removes the consumed write retry and preserves the draft.
   - Scan count and print quantity editors retain the existing `NumberField` appearance with `clampOnBlur={false}` for explicit validation. Unchanged stored zero counts are omitted from unrelated corrections; invalid edited counts remain visible and cannot be saved. Printing rejects invalid quantities instead of silently changing them on blur and submitting a different number of labels.
   - Lazy routes inside the application shell use a content skeleton; the centered spinner is reserved for initial application/page initialization.

## Live-data synchronization (2026-10-23)

- Final integration: an expired snapshot retry discards old at-risk membership; accepted scan completions invalidate notifications once after ID deduplication across rooms and HTTP delivery. WebSocket open/message callbacks require current socket ownership, invalidated before cleanup/reconnect closes the previous socket. Authentication remains unchanged. See [[Resolved Bugs]] and [[Testing and Validation]] for regression evidence and the long-run Edge limitation.
- Coarse browser events in `lib/liveEvents.ts` connect the existing providers without adding another WebSocket: `SCAN_CHANGED_EVENT` refreshes scan consumers, and `NOTIFICATIONS_CHANGED_EVENT` refreshes the notification badge/list.
- `ScanProvider` merges newer revisions, preserves fields omitted by partial responses, and deduplicates a completed scan that arrives from the Kiosk room, dashboard room and HTTP response. Later print fields still merge through `acceptScan`. A bounded set prevents the dedupe memory from growing indefinitely.
- `useDashboardResource` coalesces focus, visibility and online events into one refresh. Logs invalidates its browse snapshot on edit events and retries an expired/superseded snapshot once without it, so a 10-minute snapshot expiry does not become a failed poll or a full-snapshot polling loop.
- Scan Detail refreshes in place on focus/visibility and every 30 seconds while visible, merging the latest record without replacing the open page with a loading skeleton. It aborts and pauses while an edit, status dialog, flag, or note is pending, and a failed background read preserves the current record.
- Kiosk restores the newest server-reported Active intake after remount/reload. Inventory stock, cultivar and ripeness links preserve the selected source, In Stock state and eligible-stock predicate; intake-linked spoilage rows intentionally open that intake's full log. Dashboard source links preserve the selected Asia/Manila business date.
- Activity Log renders stored timestamps in `Asia/Manila`, matching the rest of the business-date UI. Delivery Intake feedback reports the persisted changed-scan count and resulting intake status instead of claiming every scan changed.
- Known boundary: a status change accepted by another client is not broadcast as a scan event, so Logs can show that row until its snapshot is refreshed or expires. Incoming revision 0010 now isolates broadcast notification read receipts per account.

## Live Scan Logs notices (2026-10-24)

- `GET /api/v1/scan-logs/pending` returns the absolute count of committed scans newer than the frozen snapshot's newest included row. The watermark is the newest matching `date_time` plus its UUID tiebreak; the count reuses the same account scope, filter predicates and confidence threshold as the snapshot. It never extends, reorders or mutates the snapshot, and repeated checks do not double-count after reconnects.
- Page 1 automatically opens a fresh snapshot when a new matching scan is detected and no interaction is active (dialog, export, pending write, focused editor, open menu/listbox, loading data or hidden document). Page 2+ keeps its frozen rows, page, sort and scroll and shows **X new Kiosk scans available. Would you like to refresh Scan Logs?** with **View Latest Scans** and **Later**.
- **View Latest Scans** starts a fresh page-1 snapshot while preserving the applicable filters and sort. **Later** dismisses the prompt, retains the current snapshot and leaves a subtle pending indicator that can still open the latest scans.
- `SCANS_ADDED_EVENT` announces committed Kiosk completions, `LIVE_RESUMED_EVENT` triggers a check after a WebSocket reconnect, and normal `useDashboardResource` polling/focus refreshes also check the pending count, so missed events are caught without replacing Page 2. The existing `SCAN_CHANGED_EVENT` path is retained for edits; only newly committed scans use the non-destructive notice flow.
- Admins receive every completion through the `dashboard` room; Operators receive only their own account-scoped `kiosk` room events. The 30-second Logs polling path still catches any matching commit whose event was missed.
- Detection uses the newest included row rather than `generated_at`, so a scan already visible in the snapshot cannot also be announced as new. Older snapshots without a watermark fall back to `generated_at` until they refresh or expire.

## Recorded environmental measurements

Scan Logs and Scan Details display the scan's stored `vpd`, never a value calculated
from current sensor readings. Logs keeps it in the existing **IoT Data** cell, and
Details uses the existing environmental metric grid. Values use three decimals and
`kPa`; zero is `0.000 kPa`, while null/omitted values show an accessible unavailable
dash. The CSV export appends `VPD (kPa)` after the existing columns and leaves missing
values blank. Older browse snapshots without the field remain valid and unknown.

The scan pipeline already computes and stores VPD. Its enhanced six-feature spoilage
model consumes VPD; legacy four-feature models and the rule fallback do not. This UI
integration adds no calculation, backfill or model selection change. See the
[VPD audit](../audits/2026-10-18-vpd-integration.md) and [[Testing and Validation]].

## Spoilage display and stock risk (2026-10-20)

Kiosk, Scan Logs, Scan Details, public QR tracking and Quality Control use
`lib/spoilageDisplay.ts` for display only. New scalar predictions use whole-day bounds:
`3.487` becomes `3–4 days`, `0.9938` becomes `1 day`, and zero stays `0 days`.
Historical ranges retain their endpoints, with an en dash and consistent units.
Missing/invalid estimates show `Unknown`. These readable bounds are not RFR confidence
intervals. Scan Logs has only one spoilage value; Inventory formats its aged remaining
life with the same helper and retains `Overdue` for negative remaining life.

Raw `spoilage_days` stays intact in API responses, provider state, correction drafts,
history and CSV. Read-only correction inputs and change previews format their labels
without replacing draft values. Dashboard/Analytics show aggregate counts and link to
Scan Logs; they do not render a separate per-scan spoilage estimate.

The warning icon uses the server's at-risk decision, never a client parse of the
range or a comparison against rounded display values. Without introducing new database
or API response schema fields, row warnings consume the existing server-side at-risk
snapshot filter (`attention: "at-risk"`) against the same frozen browse snapshot. The server
uses the shared `dashboard._expiring` predicate across rows, KPI, filters and exports:
eligible In Stock records with unrounded remaining days <= 2, including overdue stock.
Sold, Spoiled, For Processing and unverifiable/depleted-intake stock are excluded. Browse
snapshots freeze flags and counts together; Refresh captures new values.

The predictor stores the unrounded RFR mean as a decimal string in the existing
`spoilage_days` field; fallback/historical records can contain ranges. No separate raw
prediction field is needed. The numeric remaining estimate is the scalar or valid
historical range midpoint minus elapsed days since the stored scan timestamp. Labels
in Kiosk/Logs/Details describe the estimate at capture, not an aged range:
`1-4` at capture is 2.5 days and is
not at risk, while `3-6` after three days is 1.5 days and is at risk if stock eligible.
No model calculations, historical predictions or Manila date rules changed.
See [[Testing and Validation]] for boundary and seed/Kiosk parity coverage.

## Quality Control camera evidence

Quality Control uses the scan's recorded image/detection camera IDs and saved position
labels, independent of the station's current camera configuration. Each tile joins its
image and detection by `camera_id`; a missing image never falls back to another camera
or the scan thumbnail. It reuses Scan Detail's `BoundingBoxOverlay` for saved pixel
coordinates, class labels, confidence, and image scaling.

The modal accepts full detail responses at the same revision as its list row because
list responses omit detections. This refresh preserves the correction draft and its
baseline revision. The 2026-10-20 fix removed repeated thumbnails and simulated boxes.
`tests/scanrecords.test.mjs` covers distinct camera images, reordered detections,
same-revision enrichment, non-4:3 box alignment, missing/unavailable images, and absent
detections/evidence. See [[Testing and Validation]] for the isolated browser workflow.

## Scan History actor attribution

Kiosk PIN login establishes the authenticated operator; scan requests do not supply
an actor identity. The trigger route passes the authenticated account ID/name into
the scan transaction, which saves a `created` event and links its initial status
evidence. Scan Detail displays that stored actor snapshot, even after an account rename.

`ScanProvider` and `InventoryProvider` reset their stores when account ID/role changes,
remounting Kiosk and clearing its operator/intake selection. Old status rows without
an audit event have no reliable actor evidence: keep **Actor not recorded**, rather
than substituting the scan owner or current login. See [[Testing and Validation]].

## CSV and XLSX exports (2026-10-22)

All five export surfaces offer CSV and XLSX through the shared `ExportDropdown`.
Scan Logs uses the server export route; System Configuration uses the admin config
export route. Activity Log, Delivery Intakes and Quality Control export the complete
filtered dataset after local sorting, not only the visible page. `AppDataTable` reports
its sorted rows through `onSortedData`; the pages keep that result in a ref so exports
do not re-render or mutate table state.

Server Scan Logs exports ignore `page`/`limit` and retain account scope, filters,
sort order and snapshot consistency. The snapshot binding intentionally excludes the
file format, so the same frozen snapshot can be exported as CSV or XLSX. CSV keeps its
existing column order, BOM, all-field quoting and three-decimal VPD contract. XLSX
adds typed cells, inline strings (no formulas or hyperlinks), preserved whitespace,
wrapped headers/data, estimated row heights, and column widths clamped to 12–81.
Empty exports still include headers.

Client CSV helpers quote every field and neutralize only formula-like text (`=`, `+`,
`@`, or non-numeric `-` prefixes); negative numeric strings such as `-1` stay numeric.
Client XLSX uses the same OpenXML styling and typing contract, keeps identifiers and
leading-zero values as text, and writes numbers/booleans as native cells. Missing
optional values export as blank cells rather than display dashes or fabricated zeros.
The server XLSX routes follow the same rule: NULL optional fields are blank, while
`N/A` is emitted only when the classification or status block is absent, so CSV and
XLSX agree for missing values. Stored ISO timestamps are exported unchanged by client
surfaces; backend exports emit Asia/Manila ISO timestamps. See [[Testing and Validation]].

## Key Components

The Analytics Operator Performance table shows **Total Scans** and **Avg Confidence**,
including the existing valid-confidence sample-count tooltip. It keeps sortable headers,
badges, avatars and mobile horizontal scrolling. Flag Rate/QC Overrides are omitted because
record state does not identify the actor performing a QC action. Rows use stable operator
IDs and current account names; confidence zero and unavailable values remain distinct.
See [[Development Decisions]] and [the operator audit](../audits/2026-10-19-operator-performance.md).

Analytics help text comes from the API's shared metric definitions. The existing disclosure
labels each metric, uses readable Manila dates, and explains confidence versus accuracy once
per relevant definition. The fixed 14-day trend applies source/cultivar/stock-status filters;
its date window remains independent of the selected KPI range. Wording changes do not alter
metric calculations, eligibility rules or API keys.

- **`AppDataTable`**: Structured table supporting skeleton placeholders, sortable headers, pagination, and multi-filter criteria.
- **`AppStatsCard`**: KPI indicator cards with support for skeleton loading and stale data indicators.
- **`useDashboardResource`**: Handles async data fetching with cancellation, request sequencing, and snapshot retention.
- **`ScanContext` / `InventoryContext` / `AdminContext`**: State management with authoritative server timestamps (Asia/Manila).

See [[Testing and Validation]] and [the loading recheck](../audits/2026-10-17-loading-recheck.md) for verified scope and remaining limitations.


## System Configuration layout (2026-10-21)

System Configuration uses horizontal Cameras, Detection, Data & Backups, and Power
sections within the existing app shell. Camera names, device selections, and observed
status share one row per slot; manual indices and discovery identifiers remain available
in advanced disclosures. The shared device picker uses compact labels only on this page.
Model information and saved revision details are secondary disclosures; camera application
errors and retry actions remain visible.

One sticky save bar applies pending changes across tabs. Automatic capture cleanup still
saves immediately and preserves unrelated camera/threshold drafts. The global Reset All
Settings action describes its scope and creates a reviewable draft; it retains saved
physical mappings and requires Save. API field names, revision conflict handling, and
backend operations are unchanged.

Restore opens a guided dialog with archive selection, validation, then administrator
password and explicit REPLACE confirmation. Pending archive work prevents dismissal;
closing clears password/confirmation. Data & Backups remains mounted across tab switches
so operation IDs, backup downloads, and status checks remain available. Existing power
confirmation and recovery flows remain intact; unavailable/busy station status no longer
uses the ready-state green styling.

`tests/maintenance.test.mjs` covers these interactions with mocked APIs, including
single save controls, immediate-cleanup draft preservation, reset/discard, pending-dialog
guards, validation invalidation after file changes, and backup results across tabs.
See [[Testing and Validation]].
