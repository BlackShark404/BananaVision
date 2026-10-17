# Loading states recheck — 2026-10-17

Scope: resume the interrupted loading audit on `main` at `77ff51c`, preserve committed fixes and UI design, validate the supplied review screenshots against source. Existing layout, typography, colors and reusable components remain in use. No backend/schema changes, deployment or live device/database operations were made.

## Pattern by system area

| Area | Pattern and reason | Result of review |
|---|---|---|
| Application/authentication | Centered status spinner only before the application can render; content skeleton within the loaded shell for lazy routes | Added accessible initialization status and route-local Suspense; navigation retains the shell. |
| Dashboard and Analytics | Structured card/table/chart skeletons initially; local refresh feedback while a snapshot exists | Retained existing implementation. Dashboard labels stale data; Analytics labels previous selections while loading and shows error/retry after a failed refresh. All-time and daily metrics keep distinct semantics. |
| Scan Logs, Inventory, Scan Detail | Structured skeletons for first data; localized filter/pagination/refresh; inline action spinners | Retained existing loading components, snapshot ordering and error/empty states. Fixed count validation to preserve raw invalid input and allow unrelated corrections on stored zero-count scans. |
| Quality Control and review notes | Initial table/card skeletons, local notes loading, disabled save actions with spinners | Late detail updates refresh displayed data without silently rebasing correction drafts. Conflict/uncertain-write recovery is reachable inside the modal, preserving drafts; note timestamps explicitly use Manila. |
| User/Supplier management, Activity Log, Delivery Intake | Initial rows/cards as skeletons; retained refresh snapshots and local write feedback | User/supplier writes invalidate stale reads; first-load writes trigger complete refreshes. Supplier/intake loading settles independently. Intake failures now show the actual error instead of permanent loading text. |
| Profile and configuration | Section-level skeleton/loading status; inline save feedback | Existing behavior retained; shared JSON reads now have a finite deadline. |
| Notifications | Skeleton list initially; local refresh status; inline mark-read busy state | Added real error/empty distinction and retry. Confirmed mark-read survives delayed refresh; account changes discard snapshots. |
| Kiosk/operator selection, scanning and inference | Skeleton operator choices; PIN/action spinner; existing scan-stage/status feedback | Added operator-list error/empty retry and cancellation/deduplication of queued PIN requests. Completion now exposes the server review flag. |
| Device Status, cameras and calibration | Local status for discovery/initialization, retained metrics during polling, explicit unknown/offline/error states | Unknown readings no longer render as zero or "Optimal". Live measurements beat delayed initial reads. Calibration initial reads use the bounded API client. |
| Backup/restore, maintenance and printing | Existing operation stages/status and action-specific spinners | Retained operation identity, busy guards and outcome recovery. Hardware mutation timeout is not treated as proof that an operation failed. Verified only with mocks. |
| Exports/downloads | Local action feedback, existing CSV deadline | Existing CSV limit is 300 seconds. Browser Blob buffering remains; large-export scalability is not proven. |

JSON reads routed through the shared API helper time out after 15 seconds, including body parsing, with caller cancellation preserved. This does not change mutation contracts or impose a blanket deadline on archive downloads. No artificial minimum loading delay was introduced. Existing skeleton sizes and retained content limit replacement/layout flicker; no comprehensive layout-shift performance benchmark was run.

## Screenshot findings checked

- **Dashboard success link:** the unfiltered success rate is all-time, so its drilldown is intentionally all-time. Explicit date filters remain in relevant links. Adding today's date unconditionally would misrepresent the metric.
- **Trend range:** the 14-day trend is intentionally independent of the summary filter; the hourly chart represents today's granularity. Retained that behavior.
- **Operator metrics, page sizes and notes spacing:** already present in the current source; preserved.
- **Search:** exact full UUID matching is optimized. Arbitrary substrings still use leading-wildcard queries; no scale/query-plan benchmark establishes that concern as solved.
- **CSV:** increasing the timeout does not remove frontend Blob buffering or server snapshot storage costs.
- **Scan corrections:** changed counts must be positive integers, without coercion/clamping. An unchanged stored zero count is omitted from unrelated corrections. Original AI results remain the source of model-confidence analytics.
- **Spoilage recalculation:** the frontend correction helper remains a heuristic; it is not proof of trained model/treatment-aware recalculation.

## Verification

Final verification is recorded in `TASK_PROGRESS.txt`; this report will be updated with final counts after the running suite completes.

- Isolated backend: **389 passed, 38 skipped** (96.26s). PostgreSQL-specific cases were skipped because no disposable PostgreSQL URL was configured; no backend code changed in this recheck.
- Focused delayed-response, loading and recovery regressions passed, including a real click on QC modal conflict recovery and writes during initial user/supplier loading.
- TypeScript and production build passed before the final kiosk text correction; final repeat is pending.
- Frontend lint: **37 existing errors, 5 warnings**. ESLint comparison against HEAD across all 13 modified source files found **no diagnostic increases**. This is a failing lint result, not a clean run.
- Known pre-existing connectivity tests expect a shared WebSocket and authentication in the first message. The unchanged frontend hook and backend handler implement per-hook sockets and query authentication. Both tests fail on this contract mismatch; they were not weakened or removed. A separate coordinated connectivity change is required before claiming the entire suite passes.

Browser fixtures mock APIs/WebSockets and exercise cold, empty, failed, delayed, stale and duplicate-action paths. They do not establish physical camera, inference, printer, backup/restore or OS power behavior. Full visual parity/performance certification and large-scale database/export benchmarks are outside this verification.
