# Persistence and historical-data browser regressions

Run from `frontend` with an installed Playwright and Chrome:

```text
node --test tests/persistence.test.mjs
```

The existing dashboard harness supports `PLAYWRIGHT_MODULE` (an installed
`playwright/index.mjs`), `PLAYWRIGHT_CHANNEL`, and `PLAYWRIGHT_EXECUTABLE_PATH`.
This suite uses port 5191. It does not download browsers or dependencies.

The real Scan, Admin, and Inventory providers and the real Quality Control
screen run against intercepted HTTP responses. Authentication and WebSockets
are isolated; no database, credentials, or hardware are required. Coverage
includes complete paginated scan/activity history, original offset timestamps,
failed/partial refreshes, duplicate final pages, all provider writes, delayed
confirmation, canonical persisted values, quality-review errors, and CSV export.
