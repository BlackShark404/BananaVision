# Frontend Architecture & UI Design System

BananaVision's frontend is a React 19 single-page application built with Vite, TypeScript, Tailwind CSS, and Radix UI primitives.

## Continuous sensor exposure and baseline indicators (2026-11-26)

Decision: [[Development Decisions]]. Helpers: `frontend/src/lib/shelfLifeWindow.ts`, `frontend/src/lib/ripenessProjection.ts`.

- `liveShelfLifeWindow` and `liveRipeness` preserve any server-computed continuous DHT22 exposure offset (`exposureOffset = window.elapsed_days - Math.max(0, asOf - scanDay)`) when rolling projections forward at `Asia/Manila` midnight in the browser, keeping Dashboard, Scan Logs, Scan Detail, Kiosk, and Public Scan View synchronized without extra API polling.
- `ScanResponse` and `PublicScanResponse` accept optional `storage_exposure` (`StorageExposureSummary`) from `/scans/{id}` and `/scans/{id}/track`. When present, `ScanDetail` and `PublicScanView` show average temperature, humidity, VPD, covered hours, and biological vs calendar days under storage/timeline notes; when DHT22 was disconnected or stale at scan time (`temperature === null || humidity === null`), `ScanDetail`, `Kiosk`, and `PublicScanView` disclose that spoilage uses the default `25 °C / 65%` baseline rather than live sensor readings.

## Inventory: Spoilage Alerts pagination (2026-11-25)

- Spoilage Alerts no longer scrolls (`max-h-64 overflow-y-auto` removed). It shows three alert groups per page with Previous / Next controls, a `Page X of Y` label and a `Showing A–B of N` summary (`frontend/src/pages/Inventory.tsx`).
- Page state resets on source-filter changes and clamps when the alert count shrinks, so the list never lands on an empty page. Controls appear only when more than one page exists.
- Each alert row gives the supplier and variety a full-width line with the ripeness badge; hand count and days-left badge share a wrapping second row, and the scan date sits on a third. Long supplier names no longer squeeze against the days-left badge.
- Test: the pagination case in `frontend/tests/persistence.test.mjs` proves three groups on page 1, the remaining two on page 2, and the return to page 1.
- Demo seed: `backend/seed.py` adds an open ethephon intake with five near-expiry cultivar/ripeness groups, so a reseeded development database always shows two Spoilage Alerts pages. All five scans are dated yesterday; with ethephon treatment their predicted shelf life keeps every group at two days or less while projected stages stay distinct. `backend/tests/test_seed.py` checks the five groups, their remaining life and their projected ripeness using the loaded RFR predictor.

## Inventory: supplier inventory verification (2026-11-25)

- The Inventory page's **Supplier Verification** card (`frontend/src/pages/Inventory.tsx`) replaces the Scan Logs redirect. Each supplier row opens `frontend/src/components/SupplierInventoryModal.tsx`; nothing in this checking flow navigates to Scan Logs, including the `Unknown Supplier` row for scans without a source.
- `frontend/src/lib/supplierVerification.ts` compares expected received stock (`daily_intake.expected_stock`, per variety) with the scans already loaded by `ScanContext`. Scans linked to an intake are matched to that delivery; scans that only carry the supplier name stay visible as unlinked.
- Statuses: **Complete** (all recorded stock scanned with matching varieties), **Partial** (same varieties, fewer scans than expected), **Incomplete** (expected stock but no scans), **Discrepancy** (extra scans, a scanned variety with no expected quantity, or any delivery-level mismatch), and **Not recorded** (legacy intake without expected stock).
- The modal shows supplier-level expected/scanned/remaining totals, a progress bar, per-variety scanned/expected badges, and one verification row per delivery with batch, date, status, variety match and expected vs scanned. Admins record or edit expected bunches per variety inline; `PATCH /api/v1/intakes/{id}/expected-stock` replaces the recorded rows and writes an `intake_expected_stock` audit entry.
- Tests: `frontend/tests/supplierVerification.test.mjs` (statuses, unlinked scans, aggregation) and the verification/modal cases in `frontend/tests/persistence.test.mjs` (color statuses, no navigation away from Inventory, admin expected-stock save).

## Public QR page shows only the scanned data (2026-11-13)

Decision: [[Development Decisions]]; tests: [[Testing and Validation]].

- Web QR codes open `/track/<scan id>` (`frontend/src/lib/qrcode.ts`), which renders
  `PublicScanView` outside the staff layout. The page is read-only. The first screen shows
  the logo and "BananaVision · Scan Tracking" header (plain text), the pending-review
  notice, cultivar, ripeness, `Est. Spoilage` with the Asia/Manila countdown and `Est. …
  from scan`, the scan date and the footer time.
- Secondary values sit in a collapsed native `<details>` disclosure labelled "Scan
  details": confidence, `Est. Fingers`, temperature, humidity, VPD, source, treatment and
  the scan ID. The public page does not show `inventory_status`; stock state stays on staff
  pages. The disclosure is not navigation, so the page still has no `<button>`, link or
  other way out.
- No link or button leaves the page: the header "Log in" button, the "Need more details?"
  login card and the error-screen "Log in" button were removed. The not-found screen has
  no button; the error screen keeps only "Retry".
- A signed-in staff member who scans a QR code sees the same page. The former redirect to
  `/scans/<id>` was removed and the page no longer reads the signed-in user.
- `App.tsx` mounts `/track/:scanId` in its own top-level route, outside `AdminProvider`,
  `ScanProvider`, `InventoryProvider` and the toaster (`StaffApp` holds them for every other
  route). With a stored staff session those providers loaded staff data and opened the
  staff socket on every page; an expired or revoked token then hit the 401 handler in
  `lib/api.ts` or the 4001 socket close in `useWebSocket.ts` and sent the phone to `/login`.
  The QR page now sends only its one public request.
- Login controls stay on the normal pages (landing, `/login`, the staff layout). Thermal
  printer labels hold a plain-text QR payload and are unaffected.

## Public HTTPS links (2026-11-13)

- An HTTPS page uses its own origin for HTTP and WebSocket traffic: `BASE_URL` is empty and `WS_BASE` is `wss://<same host>`. A reverse proxy therefore serves the built SPA, `/api`, `/captures`, `/health` and the WebSocket upgrade from one origin. Plain-HTTP station pages keep the historical `http://<host>:8000` backend and direct `ws://<host>:8000` socket.
- The socket sends `{"event":"ping"}` every 25 seconds while open, so a proxy does not drop an idle live connection. Reconnect logic, ownership checks and room handling are unchanged.
- Camera previews require a session. `<img>` cannot send headers, so `withMediaToken` appends the stored token as `?token=` for Kiosk, Dashboard and calibration previews; the backend accepts a bearer header or that query token.
- Authenticated evidence images are loaded through `ScanImage` with a bearer `fetch` and an object URL. Public QR tracking no longer renders camera evidence, because `/captures` is staff-only.
- Scan Logs and Quality Control table cells use a smaller preview: list APIs append `?variant=thumb` to `thumbnail_url`, and the evidence route generates and caches a 256 px JPEG beside the original on first request. Scan Detail and Kiosk keep the original evidence URLs. Table images also render with `loading="lazy"` and `decoding="async"`.
- Protected thumbnail blobs are cached in memory by `ScanImage`, keyed by user and URL, with entry/byte limits. Remounting a table row reuses the object URL; `clearToken()` revokes the cache on logout or session expiry. Originals keep their per-mount object URLs.
- Table thumbnails pass `defer`. An `IntersectionObserver` with a 200 px margin holds the authenticated request until the placeholder approaches the viewport, because native `loading="lazy"` cannot defer a JavaScript `fetch`.
- `VITE_PUBLIC_BASE_URL` overrides the origin embedded in printed QR labels, so a label scanned off-station resolves to the public HTTPS link. When unset, labels keep the kiosk origin.
- `VITE_API_URL`, `VITE_WS_URL` and `VITE_PUBLIC_BASE_URL` are build-time values; a production build written to `frontend/dist` is what Caddy serves. See [remote-access.md](../guides/remote-access.md).

## Live ripeness projection (2026-11-25)

Decision: [[Development Decisions]]. Helper: `frontend/src/lib/ripenessProjection.ts`.

- The server attaches derived `ripeness_projection` (`base_ripeness`, `current_ripeness`, `progressed`, `elapsed_days`, `transitions`, `scan_date`, `as_of_date`) wherever `shelf_life_window` is returned (`DashboardScan`, `ScanLogRow`, `ScanResponse`, `PublicScanResponse`, and `scan:changed` events). `liveRipeness(projection, now, inventoryStatus)` rolls forward at `Asia/Manila` midnight without extra requests, never moves backward behind `as_of_date`, and freezes at `base_ripeness` for closed inventory statuses (`Sold`, `For Processing`, `Spoiled`).
- **Scan Logs, Scan Details, and Dashboard Recent Scans:** render `Est. <Stage>` via `AppStatusBadge` (`label` prop) with `<Base> at scan` beneath when progressed for `In Stock` rows, and a plain scanned badge on Day 0 or closed stock. Edit dialogs always edit the scanned/verified ripeness anchor.
- **Quality Control:** keeps observed scan-time ripeness as the primary badge and dialog value, showing only a muted `Now Est. <Stage>` hint for progressed `In Stock` rows so static photo review is never ambiguous.
- **Inventory:** groups eligible `In Stock` hands in **Stock by Ripeness** and **Spoiling Soon** alerts by projected current ripeness and navigates to `/logs?...&ripeness_scope=current` so Inventory counts and Scan Logs match 1:1. Scan Logs shows an `Est. Current Ripeness` filter chip when `ripeness_scope=current` is active and resets to scanned ripeness if the user picks from the ripeness dropdown.
- **Public Scan View (`/track/:scanId`):** displays projected `Est. <Stage>` alongside the live spoilage countdown (`ignoreClosedStatus: true`) and reveals `Scanned as <Stage>` inside the collapsed `Scan details` disclosure when progressed.
- **Exports:** `SCAN_EXPORT_HEADERS` in `exportUtils.ts` and backend `export_format.py` share 15 columns with `Scanned Ripeness` and `Est. Current Ripeness` (`—` for closed stock).

## Analytics: Model Confidence vs. Verified Accuracy (2026-11-25)

Decision: [[Development Decisions]].

- The Analytics KPI row (`frontend/src/pages/Analytics.tsx`) shows **Verified Accuracy** alongside **Avg Confidence** and **Low Confidence** using `AppStatsCard` (`grid-cols-2 md:grid-cols-3 xl:grid-cols-5`). When `verified_scan_count === 0`, it renders `—` with `"No verified scans in range"`; otherwise it renders `"X of Y verified scans"` from `verified_correct_count` and `verified_scan_count`.
- The **Confidence vs. Verified Accuracy** chart (upgraded from *Confidence by Ripeness*) plots **Avg Model Confidence (%)** and **Verified Accuracy (%)** side-by-side per predicted ripeness stage (`Unripe`, `Semi Ripe`, `Ripe`, `Overripe`) on a shared `0–100%` Y-axis using Recharts `BarChart`, `ChartContainer`, and `ChartLegend`, while keeping its independent per-chart `PeriodControls` and `useDashboardResource` error/retry states.
- Stages with `verifiedCount === 0` keep `verifiedAccuracy: null` so Recharts omits the accuracy bar instead of plotting `0%`, and `ConfidenceAccuracyTooltip` displays `"No verified scans"`.
- Both KPI tooltips and the **Metric definitions** disclosure read `metric_definitions.model_confidence` and `metric_definitions.human_verified_accuracy` directly from `GET /api/v1/analytics/summary`.

## Analytics dates (2026-11-24)

- **Page period:** one state `{ range, from, to }` (`AnalyticsPeriod`,
  `frontend/src/lib/analyticsPeriod.ts`). `range` is always a backend preset (Today, Last 7
  Days, Last 30 Days, All Time). Date From / Date To are inclusive Asia/Manila days
  (`YYYY-MM-DD`) and replace the preset; the request then has `date_from`/`date_to` and no
  `range`. "Custom" is derived from the dates (`rangeChoice`), never stored. Clearing the
  dates returns to the preset chosen before.
- **One control:** `PeriodControls` (preset, Date From, Date To, X) serves the page header and
  every chart header.
- **Chart periods:** every chart follows the page period and shows it. A chart can pick its
  own; the badge then reads "… · this chart" and **Use page dates** (X) resets it. Its data
  loads through `useDashboardResource` (`enabled` only while the chart has its own dates, so a
  chart on the page dates makes no request); a failure shows the chart's own error and Retry.
- **Server rules:** Date From after Date To, or a day after today, returns 422. `range_end` is
  the last instant of Date To, never later than now.
- Scan Trend keeps its fixed 14 days.
- **Scan Detail notes:** Add asks "Add Review Note … Confirm"; empty text shows a toast
  and writes nothing.

## Dashboard FIFO card (2026-11-18)

- The Dashboard shows the oldest five in-stock batches from
  `GET /api/v1/dashboard` (`fifo_recommendations`), so the panel's FIFO ranking is
  reachable without opening Inventory. Each row opens its intake in Scan Logs
  (`/logs?intake=…`) or, for an unlinked stock scan, its Scan Detail page
  (`/scans/…`). **View Inventory** opens `/inventory` for the full list.
- The server groups eligible stock the same way Inventory does: one group per active
  intake, or one per unlinked scan; groups are ordered by their oldest scan. The group's
  earliest remaining life is the minimum known value in the group, and an all-unknown
  group reports `Risk unknown`.
- A group at or below two days, including overdue stock, shows **Sell immediately**;
  otherwise it shows **Stock is stable**. The earliest batch shelf life uses the same
  `Est.` wording as the rest of the UI. FIFO describes current stock, not the selected
  `business_date`, so it does not change when an older Dashboard day is viewed.
- The card is part of the existing summary response and refresh cycle; it adds no second
  scan-history request. Operators receive the same projection scoped to their own scans,
  like the rest of the Dashboard.

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
- Coarse browser events in `lib/liveEvents.ts` connect the existing providers without adding another WebSocket: `NOTIFICATIONS_CHANGED_EVENT` refreshes the notification badge/list. Committed edits now use the revision-aware `SCAN_UPDATED_EVENT`; see *Cross-session mutation sync* below.
- `ScanProvider` merges newer revisions, preserves fields omitted by partial responses, and deduplicates a completed scan that arrives from the Kiosk room, dashboard room and HTTP response. Later print fields still merge through `acceptScan`. A bounded set prevents the dedupe memory from growing indefinitely.
- `useDashboardResource` coalesces focus, visibility and online events into one refresh and retries an expired/superseded snapshot once without it, so a 10-minute snapshot expiry does not become a failed poll or a full-snapshot polling loop. Logs no longer discards its frozen snapshot for every edit; it patches the visible row by revision.
- Scan Detail refreshes in place on focus/visibility and every 30 seconds while visible, merging the latest record without replacing the open page with a loading skeleton. It aborts and pauses while an edit, status dialog, flag, or note is pending, and a failed background read preserves the current record.
- Kiosk restores the newest server-reported Active intake **started today in Asia/Manila** (`isManilaToday` in `lib/manilaTime.ts`) after remount/reload. An Active intake from an earlier day (for example one reopened by a stock correction) is not picked up on its own; the operator chooses a source. An intake already open in the kiosk stays open across midnight until a reload or operator swap. Inventory stock, cultivar and ripeness links preserve the selected source, In Stock state and eligible-stock predicate; intake-linked spoilage rows intentionally open that intake's full log. Dashboard source links preserve the selected Asia/Manila business date.
- Activity Log renders stored timestamps in `Asia/Manila`, matching the rest of the business-date UI. Delivery Intake feedback reports the persisted changed-scan count and resulting intake status instead of claiming every scan changed.
- Incoming revision 0010 isolates broadcast notification read receipts per account.

## Live Scan Logs notices (2026-10-24)

- `GET /api/v1/scan-logs/pending` returns the absolute count of committed scans newer than the frozen snapshot's newest included row. The watermark is the newest matching `date_time` plus its UUID tiebreak; the count reuses the same account scope, filter predicates and confidence threshold as the snapshot. It never extends, reorders or mutates the snapshot, and repeated checks do not double-count after reconnects.
- Page 1 automatically opens a fresh snapshot when a new matching scan is detected and no interaction is active (dialog, export, pending write, focused editor, open menu/listbox, loading data or hidden document). Page 2+ keeps its frozen rows, page, sort and scroll and shows **X new Kiosk scans available. Would you like to refresh Scan Logs?** with **View Latest Scans** and **Later**.
- **View Latest Scans** starts a fresh page-1 snapshot while preserving the applicable filters and sort. **Later** dismisses the prompt, retains the current snapshot and leaves a subtle pending indicator that can still open the latest scans.
- `SCANS_ADDED_EVENT` announces committed Kiosk completions, `LIVE_RESUMED_EVENT` triggers a check after a WebSocket reconnect, and normal `useDashboardResource` polling/focus refreshes also check the pending count, so missed events are caught without replacing Page 2. Ordinary edits never increment this count; they use the row-patch flow described below.
- Admins receive every completion through the `dashboard` room; Operators receive only their own account-scoped `kiosk` room events. The 30-second Logs polling path still catches any matching commit whose event was missed.
- Detection uses the newest included row rather than `generated_at`, so a scan already visible in the snapshot cannot also be announced as new. Older snapshots without a watermark fall back to `generated_at` until they refresh or expire.

## Cross-session mutation sync (2026-10-24)

- Committed scan and intake mutations now reach other authorized sessions over the existing
  authenticated WebSocket. Events are invalidation hints published only after commit, never a
  substitute for an authorized read.
- `scan:changed` carries `event_id`, `scan_id`, `revision`, `kind`, changed field names, `actor_id`,
  `partial`/`deleted` flags and the authorized row fields needed to patch a visible row. Editions
  include flag, quality correction, inventory status, provenance and notes.
- `intake:changed` and `supplier:changed` carry `event_id` plus the persisted row, including
  `updated_at`, because those records are readable by every authenticated role and have no revision.
- Rooms remain account-scoped: Admin receives scan edits in `dashboard`, the owning Operator in its
  account-scoped `kiosk` room, and other Operators receive nothing. Admin sockets subscribed to both
  rooms may see one scan event twice; the browser drops the duplicate `event_id`.
- Endpoints that previously relied on the request-scoped session commit now commit explicitly before
  broadcasting, so an event can never describe an uncommitted row. Bulk inventory emits one partial
  scan event per changed scan plus an intake event; note text and images are never broadcast.
- Consumers merge by stable ID. `ScanContext` keeps the higher revision, preserves fields omitted by
  partial payloads, drops stale events and removes rows for a `deleted` event (no delete endpoint
  currently emits one). `InventoryContext` orders intake and supplier events by `updated_at`, and
  its create responses merge into an already-received live row instead of appending a duplicate
  (fixed 2026-11-12; see [[Resolved Bugs]]).
- On WebSocket reconnect, browser focus, visibility restoration and `online`, `useDashboardResource`,
  `ScanContext`, `InventoryContext`, `AdminContext` and `AppNotifications` reconcile against the
  authoritative API with abort/sequence guards, so a stale response cannot overwrite newer data and
  duplicate resume events collapse into one debounced read.
- Logs keeps its frozen snapshot. A visible row is patched in place; if a control is focused or a
  write is pending, a remote change only raises a non-intrusive notice. Deleted or newly
  filtered-out rows are removed rather than shown as current. Page 1/Page 2+ new-scan behavior,
  exports, 409/410 recovery and snapshot expiry are unchanged.
- Follow-up (2026-10-25): `GET /api/v1/scan-logs/reconcile` validates the same snapshot owner,
  role, session generation, filters and expiry, then reads current authorized versions of only the
  frozen page IDs. Missing, inaccessible and filtered-out rows disappear without page backfilling.
  One SQL statement returns these rows, exact at-risk IDs and current whole-filter metrics together.
  It changes neither snapshot storage nor CSV/XLSX exports; no database migration is needed.
- Logs coalesces mutation bursts into a 200 ms reconciliation refresh and uses the existing 30-second
  polling/focus/online/reconnect path to recover missed edits. KPI cards use current totals; table
  order and export remain tied to the frozen browse session. Remote row values wait while a control
  is focused or a write is pending, then reconcile after blur/completion. Removed rows are not kept
  during editing. Failed reads retain the last verified data with the existing error/retry message.
  Exact risk membership comes from the server, never rounded event `remaining_days`.
- Sensor freshness: `/sensors/latest`, sensor WebSocket payloads and `/health` include
  `server_time` and `stale_after_seconds` (`max(3 × polling interval, 15)`). A reading is live only
  while its `recorded_at` age is inside that window. The age at receipt uses the server clock and
  subsequent elapsed time uses the monotonic browser clock, so workstation skew cannot make a stale
  reading look live. Out-of-order readings and delayed untimestamped initial fetches are rejected.
  Legacy payloads without `recorded_at` still display but report unknown freshness, never **Live** or
  **Optimal**.

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
intervals. Inventory formats its aged remaining life with the same helper and retains
`Overdue` for negative remaining life.

Public QR tracking (2026-11-12) now leads with a live countdown, e.g. `4 days left` or
`Overdue`, aged client-side from `remaining_days` and `risk_as_of` with the same
`lib/inventoryRisk.ts` helper used by Inventory. The stored range remains visible beneath
it as `Est. 5–7 days from scan`. `GET /api/v1/scans/{id}/track` gained those two derived
fields; the stored `spoilage_days` is unchanged, and missing predictions still show the
previous static/`Unknown` label. Scan Detail applies the same countdown/estimate pair for
In Stock records. Scan Logs (2026-11-12) keeps the static range as the primary cell value
and adds the aged label beneath it for In Stock rows only; it anchors the as-of to the
browse snapshot or reconciliation `generated_at`, because frozen rows carry
`remaining_days` computed at that instant. Logs sorting, snapshot membership and
CSV/XLSX exports remain static and unchanged. Sold/Spoiled records keep their existing
static estimate. (Superseded in part on 2026-11-13: the countdown now counts calendar days
and leads the Scan Logs cell. See "Live shelf-life window" below.)

Raw `spoilage_days` stays intact in API responses, provider state, correction drafts,
history and CSV. Read-only correction inputs and change previews format their labels
without replacing draft values. Dashboard/Analytics show aggregate counts and link to
Scan Logs; they do not render a separate per-scan spoilage estimate. The Dashboard FIFO
card is the batch-level exception: it shows the group's earliest `Est. … left` value.

## "Est." on AI-estimated numbers (2026-11-13)

Decision and reasons: [[Development Decisions]]. Helper: `src/lib/estimates.ts`.

| Surface | Finger count | Shelf life |
| --- | --- | --- |
| Kiosk result card | `Est. Fingers` label, bare number | under `Est. Spoilage` (unchanged) |
| Kiosk recent scans | `Est. 13 fingers` / `13 fingers` when corrected | `Est. 0–2 days left`, `Est. 1–3 days` |
| Kiosk camera badges | title `Est. N fingers in this camera view` | — |
| Scan Logs | column `Est. Fingers` (rows carry no per-field correction data) | `Est. Spoilage` column (unchanged) |
| Scan Detail | `Est. Fingers` / `Fingers` when corrected | `Est. Spoilage` (unchanged) |
| Quality Control dialog | `Est. Fingers` / `Fingers` when corrected | `Est. Spoilage` (unchanged) |
| Correction inputs (Scan Detail, QC) | `Fingers` (a person types the count) | `Est. Spoilage (days)` (read-only, recomputed) |
| Public QR | `Est. Fingers` always (no correction data) | `Est. Spoilage` (unchanged) |
| Inventory | `Est. Total Fingers`, `Est. 28 fingers • …`, `(Est. 7 fingers)`; plain when every scan in the total was corrected | alert badges and `Earliest spoilage:` values prefixed `Est.` |
| QC exports | `Est. Spoilage (days)`, `Est. Finger Count` headers | |

- `fingerCountText` handles singular (`Est. 1 finger`), zero (`Est. 0 fingers`) and missing
  values (`Fingers unknown`). `estimateText` leaves `Unknown` and `—` alone and never
  doubles the prefix.
- Unchanged on purpose: cultivar, ripeness, confidence, temperature, humidity, VPD, dates,
  IDs, the "Changes from AI result" preview and Scan History entries, and the printed
  label and its preview (they already say `PREDICTION` / `Saved prediction`).
- Live `scan:changed` events omit `original_ai_result`; `ScanContext.acceptScan` keeps the
  baseline it already has, so a corrected count does not turn back into `Est.`.
- The `Est. … from scan` sub-line is hidden when the stored estimate cannot be displayed,
  so the page never shows `Est. Unknown`. Empty Inventory reads `Total Fingers` / `No stock`.

## Asia/Manila time zone everywhere (2026-11-13)

Every date and time the app shows, groups by day or puts in a file name is Asia/Manila,
whatever zone the viewing machine uses. Rule and reasons: [[Development Decisions]].

- `src/lib/manilaTime.ts` is the only place that names the zone:
  `MANILA_TIME_ZONE`, `inManila(options)` (adds the zone to `toLocale*String` and
  `Intl.DateTimeFormat` options; it cannot be overridden), `manilaDayKey(time)` (Manila
  `YYYY-MM-DD`) and `manilaToday()` (the Manila day as a local `Date` for date pickers).
- Call sites keep their locale and format and only gain the zone, so screens look the
  same: `x.toLocaleDateString("en-US", inManila({ month: "short", day: "numeric" }))`.
- Export file names use `manilaDayKey(Date.now())`, so an export at 00:30 in Manila is
  named with that day, not the UTC date.
- `AppDateFilter` passes `today={manilaToday()}` to the calendar; the value stays a plain
  `YYYY-MM-DD` calendar day. The picker's experimental `timeZone` prop is not used.
- Dashboard, Analytics and `lib/shelfLifeWindow.ts` use the same helper instead of
  private copies.
- Guard: `tests/manilaTime.test.mjs` fails if any file in `src/` calls a
  `toLocale*String` or `Intl.DateTimeFormat` without the Manila zone, takes a date from
  `toISOString()`, or reads `getFullYear`/`getHours`-style local fields. Allowed by name:
  `lib/isoDay.ts` and `components/ui/calendar.tsx` (local calendar days of the picker)
  and `components/ui/chart.tsx` (numbers).

## Live shelf-life window (2026-11-13)

A record's estimate no longer reads as today's value days after the scan. The server adds
`shelf_life_window` to scan responses, the public track response, dashboard and scan-log
rows and the bulk-status event (rule and reasons in [[Development Decisions]]). It holds
the whole-day bounds of the stored estimate, the Asia/Manila calendar days elapsed, the
remaining bounds, `days_past`, a `state` (`active`, `final_day`, `expired`), the scan's
Manila `scan_date` and the server's Manila `as_of_date`. `spoilage_days`, `remaining_days`
and `risk_as_of` are unchanged, and nothing is written on read.

`lib/shelfLifeWindow.ts` turns the window into text and rolls it forward: it counts from
`scan_date` to the later of `as_of_date` and the page's own Manila date, so it never moves
backwards and a scan dated after the server's date stays at zero. An open tab, a frozen
browse snapshot and a replayed write therefore stay correct across Manila midnight
without a re-read. The date comes from `Intl.DateTimeFormat` with
`timeZone: "Asia/Manila"`, not from the browser's zone, and the page still never parses
`spoilage_days`. `liveShelfLifeLabel` in `lib/inventoryRisk.ts` uses the window when it is
present, then the older aged number (payloads saved before the field existed), then nothing.

Wording for a `1-3` estimate: `1–3 days left` on the scan day, then `0–2 days left`,
`0–1 days left`, `Final day` on day 3 and `Overdue` from day 4.

Where the countdown shows, for In Stock records:

- **Scan Detail and public QR:** the countdown is the main value with
  `Est. 1–3 days from scan` beneath. The public page shows it for every status, as before.
- **Scan Logs:** the countdown is now the main cell text and the estimate sits beneath as
  `Est. … from scan`. The user chose this on 2026-11-13; it replaces the estimate-first
  cell and the earlier revert of a countdown-first cell. Sorting, snapshot membership, the
  at-risk icon and exports are unchanged: they still use the stored estimate and the
  server's risk decision.
- **Kiosk Recent Scans:** the countdown replaces the stored estimate.
- **Quality Control dialog:** the countdown is the main value with `Est. … from scan`
  beneath, so the estimate under review stays visible. The dialog re-reads the clock every
  minute like the other pages.
- **Inventory is unchanged.** Its labels still come from the aged number, the same number
  its two-day rule uses, so a card under "≤2 days left" never shows a label above two days.

Sold, Spoiled and For Processing records have no countdown on staff pages. Since
2026-11-17 Scan Logs, Scan Detail and the Quality Control dialog give them the same
two-line shape as In Stock rows: the outcome where the countdown would be (`Sold · no
countdown`, `Spoiled · no countdown`, `For processing · no countdown`, from
`closedStockSpoilageLabel` in `lib/spoilageDisplay.ts`) and `Est. … from scan` beneath.
The beneath line is hidden when the estimate is Unknown; a record with no status keeps the
plain estimate. The public QR page counts down for every status, as it did before, and the
Kiosk Recent Scans list is unchanged. The Kiosk result card of the scan just taken, correction inputs, change
previews, Scan History entries, printed labels, the label preview and CSV/XLSX exports
keep the stored estimate.

Known difference: the at-risk icon, the counts and every Inventory label use the continuous
midpoint number (two days or less), while the countdown on the other pages counts calendar
days over the whole range. A fresh `1-3` scan is at risk from the start (midpoint 2.0)
while Scan Logs reads `1–3 days left`, and two days later Inventory reads `Overdue` while
Scan Detail reads `0–1 days left`. The Scan Logs at-risk tooltip says that it uses the
estimate midpoint. The Scan Logs column still sorts by the stored estimate, which is now
the small line of the cell.

## Uncertain cultivar presentation (2026-11-12)

When cameras disagree on the cultivar, the Kiosk and Scan Detail disclose the split,
and public QR tracking discloses the pending review state. The stored fused prediction
remains the labelled AI candidate.

- Kiosk keeps `Uncertain` with blank confidence/spoilage and the per-camera breakdown,
  raises a one-time warning toast for the completed scan, and disables **Accept** so a
  conflicted result is flagged for review instead of acknowledged. A human cultivar
  correction still restores the normal presentation.
- Scan Detail shows a **Cameras disagree on the cultivar** notice with the breakdown and
  **Stored AI candidate: X**, and its header badge stays **Needs Review** instead of
  **Verified**. Count-only overrides do not resolve the warning; a recorded cultivar
  correction does.
- Public QR tracking (`GET /api/v1/scans/{id}/track`) now returns `flagged`. A flagged
  scan shows **Pending quality review** above the classification card and states that the
  classification and estimates are preliminary. Per-camera detections stay
  authenticated-only; the public page never exposes the camera breakdown.

The per-image YOLO box labels are intentionally preserved as evidence: each label
describes that camera's view, not the authoritative scan result.

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
historical range midpoint minus elapsed days since the stored scan timestamp. The static
estimate labels used by Kiosk, Quality Control, correction inputs and the primary
Logs/Details value describe the estimate at capture, not an aged range; the separate
countdown labels are the aged view (since 2026-11-13 the countdown is the calendar-day
window above, and it leads those views for In Stock records). `1-4` at capture is 2.5 days and is not at risk, while
`3-6` after three days is 1.5 days and is at risk if stock eligible.
No model calculations, historical predictions or Manila date rules changed.
See [[Testing and Validation]] for boundary and seed/Kiosk parity coverage.

## Rejected scan presentation (2026-11-13)

A scan with no supported banana cultivar is refused by the backend gate described in
[[AI Models]]. Nothing is saved, so there is no result to show.

- `lib/api.ts` copies `code` and `reason` from the error body onto the thrown error by
  name. The body's text `status` is never copied, because `error.status` is the numeric
  HTTP status that `AuthContext` and `scanWrites` read.
- `ScanProvider` keeps `scanState.rejection` (`{ message, code, reason }`) for any coded
  refusal, from either the HTTP response or the `scan:failed` WebSocket event. Starting
  or completing a scan clears it.
- Notices: a coded refusal reports the same text on both paths, so they share one toast
  whose id is scoped to that scan (`scan-refused-<attempt>`); a later scan always gets its
  own. It is a warning for `ood_rejected` and an error for a fault. A failure without a
  code keeps one toast per report, as before, so the operator wording sent over the
  WebSocket is not replaced by the HTTP wording.
- Kiosk replaces the empty result card:
  - `ood_rejected`: a `role="status"` card, **No Lakatan, Latundan, or Cardaba detected**,
    the instruction to place a supported banana hand on the tray, and **Nothing was
    saved.** No cultivar, confidence or spoilage value is shown.
  - any other code (`ood_gate_unavailable`, `capture_unavailable`): a `role="alert"` card,
    **Scan could not run**, with the server message. It stays until the next scan, because
    a fault that needs an administrator must not vanish with a 4-second toast.
  - Card text uses `text-muted-foreground` at full opacity for AA contrast. The layout,
    spacing and the Recent Scans list are unchanged.
- A failure without a code (for example an unexpected server error) keeps the ordinary
  empty card and shows only the error toast.
- Activity Log: amber badge for `scan_rejected`, and the Details cell carries the full text
  as its title because rejection rows end with the per-view banana scores. Profile's
  recent activity shows "Scan rejected: no supported banana detected" instead of the raw
  audit string.

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

### Bounded history container and count badge

Scan Detail wraps historical records in `div.space-y-2.max-h-48.overflow-y-auto`, matching
the Quality Control Review Notes panel layout. When accumulated events exceed the 12rem
limit, vertical scrolling is contained internally without expanding the page. A record
count badge (`Badge variant="secondary"`) is rendered beside the Scan History heading
when records exist, and text wraps naturally (`break-words`) without horizontal clipping.

## Excel and PDF exports (2026-11-25)

Supersedes the CSV path in *CSV and XLSX exports (2026-10-22)* below. Decision: [[Development Decisions]].

- All five export surfaces offer **Export Excel (.xlsx)** (primary button) and **Export PDF (.pdf)** through `ExportDropdown`. CSV controls, `downloadCsv`, and server `?format=csv` routes were removed (`422` on server routes).
- `frontend/src/lib/pdfExport.ts` and `backend/app/core/pdf.py` generate dependency-free tabular PDF 1.4 reports (landscape for wide tables, title, Asia/Manila timestamp with seconds, record count, active filter summary, wrapped cells, repeated headers, `Page X of Y` footers). Compact single-token identifiers (`SCAN-XXXXXXXX`, `INT-XXXXXXXX`) reserve enough column width to stay on one line.
- **Parity:** Excel and PDF share one canonical row builder per surface so columns, row order, and displayed values match identically. Scan exports (Scan Logs, System Configuration summary, Quality Control) use the 14 business-friendly columns starting with `Scan Ref` (`SCAN-XXXXXXXX`) and readable `Asia/Manila` `Date & Time` with seconds (`Nov 25, 2026, 1:45:11 PM`), keeping `Confidence (%)`, `Temperature (°C)`, and `Humidity (%)` numeric (`0.0` OpenXML number format, style `3`) in Excel while rendering identically in PDF.
- Delivery Intakes exports start with `Intake Ref` (`INT-XXXXXXXX`) plus readable Manila `Date`, `Supplier / Source`, `Batch / PO`, `Items Scanned`, `Intake Status`, and `Inventory Status`. Activity Log exports format `Date & Time` in Asia/Manila and map `Action` through `activityLabel`.
- Search boxes on Scan Logs, Quality Control, and Delivery Intakes accept pasted `SCAN-XXXXXXXX` / `INT-XXXXXXXX` codes, bare 8-character hex prefixes (case-insensitive), and full UUIDs without changing on-screen table layouts.
- `frontend/src/lib/manilaTime.ts` exposes `formatManilaDateTime`, `formatManilaDate`, and `manilaPdfTimestamp` so every export date and PDF metadata timestamp stays inside `Asia/Manila`.

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

## Activity Log labels and paging (2026-11-17)

- `src/lib/activityActions.ts` gives every audit action a label, a category (sign-in,
  security, credential, record, export, system) and a badge colour. Security failures and
  system failures are red. Legacy or unknown actions fall back to the title-cased name
  and a grey badge.
- A Node test reads `AuditAction` from `backend/app/services/audit.py` and fails if the two
  lists differ.
- "Critical Actions" counts security failures, credential resets, role and status
  changes, exports, backup downloads, restores, recovery, configuration and power events.
- Search also matches the friendly label. Exports keep the raw action string. Profile's
  recent activity uses the same map.
- Rows with no account show "Unauthenticated" (security events) or "System".
- `AdminContext` passes page 1's `as_of` to later pages, so new rows arriving during the
  load do not break it. A row stamped before `as_of` but committed later can still change
  the count; the page then asks for a reload, as before.

## Inventory status changes (2026-11-17)

- **Scan Detail** (admin only): the "Update status" menu next to the Inventory Status badge
  offers every status except the current one, including correcting Sold or Spoiled. The
  Scan Logs row "Actions" menu already used this rule.
- **Dialog note:** `inventoryStatusChangeNote(current, target)` in
  `src/lib/inventoryStatusChange.ts`, used by Scan Detail and Scan Logs:
  - from Sold or Spoiled: "This corrects the {status} status.";
  - to In Stock: "The scan returns to stock. If its delivery intake is depleted, the intake
    reopens.";
  - from In Stock to anything else: "The scan leaves stock.";
  - always ending "This change will be recorded in the scan history."
- **Reopened intake:** the server publishes `intake:changed` (kind `scan-status`) after
  commit. The existing `InventoryContext.applyIntakeEvent` handler (ordered by
  `updated_at`) turns the Delivery Intake row Active without a reload. The `/status` response
  and `scan:changed` carry `inventory_eligible: true` for the restored scan.
- **Delivery Intake bulk is unchanged:** "Mark all …" follows its own transition table and
  the server skips Sold and Spoiled scans. See [[Development Decisions]] (2026-11-17).

## Scan Logs date default and review queue (2026-11-16, revised 2026-11-17)

- **Scan Logs opens on All dates.** A plain `/logs` (the sidebar Logs link), **Reset** and
  the Total Scans card show every date. The date box (`AppDateFilter` `emptyText`) reads
  **All dates** until a day is picked; clearing the day returns to all dates.
  `selectedScanLogDay` in `src/lib/scanLogFilters.ts` reads the URL: no `date`, `date=all` or
  an invalid value means all dates.
- **Links that choose a day:** the Dashboard "Scans Today" card and the source and operator
  rows send `?date=<day>`. Dashboard "View All Logs" and Recent Scans rows send
  `?date=all`. The chips send no date.
- The 2026-11-16 "today" default (redirect of plain `/logs`, midnight roll) was removed by
  user request on 2026-11-17, because an empty table showed whenever nothing had been
  scanned that day.
- **Labels:** Quality Control and Scan Detail show **Low confidence** (neutral) for an unflagged
  scan below the threshold. Only a flag means pending review; only an admin removes a flag.
- **Review queue = Status: Flagged.** The Dashboard "Pending quality reviews" chip opens
  `?status=Flagged`. The Pending Quality Reviews banner shows for Status Flagged, and "Clear
  review filter" removes it. A legacy `attention=review` link is rewritten to `status=Flagged`.
  See [[Development Decisions]] (2026-11-16).
