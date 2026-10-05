# Dashboard browser regression tests

Run from `frontend`:

```text
node --test tests/dashboard.test.mjs
```

The harness starts an isolated Vite server and installed Chrome. It uses a local
`playwright` package or `PLAYWRIGHT_MODULE`, the absolute path of an already
installed `playwright/index.mjs`. No packages or browser binaries are downloaded.
For another existing browser, set `PLAYWRIGHT_CHANNEL` or
`PLAYWRIGHT_EXECUTABLE_PATH`. Set `DASHBOARD_TEST_PORT` to change the local port.

The production Dashboard, API, data-loading and WebSocket hooks, cards, and
drilldown run unchanged. Only authentication, HTTP data, and WebSocket transport
are controlled. Tests need no database, user credentials, or camera hardware.
They check loading/error/stale states, recovery, scoped responses, race handling,
Manila midnight, KPI drilldown, `/logs` navigation, and camera failures.

Optional desktop/mobile screenshots are saved when `DASHBOARD_SCREENSHOT_DIR`
is set. These are local QA artifacts and should not be committed.

## Assigned-feature and persistence checks

```text
node --test --test-concurrency=1 tests/persistence.test.mjs tests/assigned.test.mjs
```

These suites use the same existing Chrome/Playwright setup and fixture API responses. Assigned-feature checks cover the administrator's one-time credential handoff, password/PIN setup proof propagation, browser-storage exclusions and operator profile totals/access scope. Vite caches are separated by fixture. No real account, camera, power or cleanup operation is performed.
