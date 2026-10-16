# Resolved Bugs

Documented log of confirmed bug root causes, verified solutions, and test coverage in BananaVision.

## 2026-10-16: Loading States & Frontend Robustness Audit

### 1. Analytics KPI Refresh Failure Stale Values
- **Issue**: When an Analytics refresh failed, previous summary cards remained visible without clearly signalling the failed refresh state.
- **Root Cause**: `Analytics.tsx` computed summary cards even when `resource.error` was populated, bypassing the error alert.
- **Fix**: Nullified `summary` when `resource.error` is present so the `<Alert variant="destructive">` with `<Button onClick={resource.reload}>Retry</Button>` is rendered directly.
- **Verification**: `tests/analytics.test.mjs` ("failed Analytics refresh shows an error with retry instead of stale values").

### 2. Dashboard Review Link Predicate Truncation
- **Issue**: Dashboard review links navigated to `/logs?attention=review&status=Flagged`, accidentally excluding unreviewed low-confidence scans from the review queue.
- **Root Cause**: `Dashboard.tsx` added `status: "Flagged"` to review query links.
- **Fix**: Removed `status: view === "review" ? "Flagged" : undefined` from `legacyScanLogsUrl` and `openRecords` to ensure the complete review predicate (`attention=review`) is used.
- **Verification**: `tests/dashboard.test.mjs` ("legacy review links use the complete review predicate").

### 3. Oversized 413 Snapshot CSV Export
- **Issue**: In `Logs.tsx`, if a scan log snapshot was too large (HTTP 413 Payload Too Large), the CSV export button was disabled because `response` was null.
- **Root Cause**: The export trigger was guarded by `response !== null`.
- **Fix**: Allowed export when active query filters exist (`canExport = response !== null || hasActiveFilters`), allowing direct server-side filtered export.
- **Verification**: `tests/scanrecords.test.mjs` ("an oversized snapshot still permits a complete filtered CSV export").

### 4. SystemConfig Button Accessible Labels & Error Alert
- **Issue**: In `SystemConfig.tsx`, when shutdown or restart were requested, the button labels were replaced with status strings ("Shutting Down..."), breaking accessible tests expecting "Shutdown Now" and "Restart Now". Additionally, application errors like "Camera 0 failed" were not rendered in a role="alert" container.
- **Root Cause**: In-button text replacement and missing alert container for `config.applicationError`.
- **Fix**: Preserved button text ("Shutdown Now", "Restart Now") with `disabled={powerPending}`, and added an `<Alert variant="destructive" role="alert">` displaying the specific application error.
- **Verification**: `tests/maintenance.test.mjs` (14/14 passed).

### 5. Windows CP1252 / UTF-8 Mojibake in Frontend Files
- **Issue**: Several frontend components had corrupted characters (`0x85` horizontal ellipsis, `\u00e2\u20ac\u2014` em dash, `\u00c2\u00b7` middle dot) caused by inconsistent Windows encoding during prior edits, causing decode errors and Playwright regex failures.
- **Root Cause**: Double-encoded UTF-8 strings or raw CP1252 bytes written into files.
- **Fix**: Systematically normalized all corrupted characters across 11 frontend files to clean UTF-8 literals (`…`, `—`, `·`).
- **Verification**: Successful AST parsing in `graphify update .`, clean `npm run typecheck`, and 100% test pass rate across 101 tests.
