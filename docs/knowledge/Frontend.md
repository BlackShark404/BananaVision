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

## Key Components

- **`AppDataTable`**: Structured table supporting skeleton placeholders, sortable headers, pagination, and multi-filter criteria.
- **`AppStatsCard`**: KPI indicator cards with support for skeleton loading and stale data indicators.
- **`useDashboardResource`**: Handles async data fetching with cancellation, request sequencing, and snapshot retention.
- **`ScanContext` / `InventoryContext` / `AdminContext`**: State management with authoritative server timestamps (Asia/Manila).

See [[Testing and Validation]] and [the loading recheck](../audits/2026-10-17-loading-recheck.md) for verified scope and remaining limitations.
