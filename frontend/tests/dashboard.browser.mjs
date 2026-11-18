import { createServer } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { pathToFileURL, fileURLToPath } from "node:url"
import path from "node:path"

export async function startBrowser({ fixture = "dashboard.fixture.tsx", auth = "dashboard.auth.tsx", port, showScrollbars = false } = {}) {
  const modulePath = process.env.PLAYWRIGHT_MODULE
  let playwright
  try {
    playwright = await import(modulePath ? pathToFileURL(path.resolve(modulePath)).href : "playwright")
  } catch (cause) {
    throw new Error("Set PLAYWRIGHT_MODULE to an existing playwright/index.mjs, or use an installed playwright package. See tests/dashboard.README.md.", { cause })
  }
  const root = fileURLToPath(new URL("../", import.meta.url))
  const server = await createServer({
    root, configFile: false, envFile: false, logLevel: "error",
    define: { "import.meta.env.VITE_API_URL": JSON.stringify("http://127.0.0.1:8000") },
    cacheDir: path.join(root, "node_modules", `.vite-tests-${fixture.replace(/\W/g, "-")}`),
    plugins: [react(), tailwindcss(), {
      name: "isolated-dashboard-fixture",
      configureServer(vite) {
        vite.middlewares.use(async (req, res, next) => {
          if (!(req.url ?? "").match(/^\/(dashboard|logs|devices|scans|track)(\?|\/|$)/)) return next()
          const html = await vite.transformIndexHtml(req.url, `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1" /></head><body><div id="root"></div><script type="module" src="/tests/${fixture}"></script></body></html>`)
          res.setHeader("Content-Type", "text/html")
          res.end(html)
        })
      },
    }],
    resolve: { alias: [
      { find: "@/context/AuthContext", replacement: path.join(root, "tests", auth) },
      { find: "@", replacement: path.join(root, "src") },
    ] },
    optimizeDeps: { entries: [`tests/${fixture}`] },
    server: { host: "127.0.0.1", port: port || Number(process.env.DASHBOARD_TEST_PORT) || 5189 },
  })
  await server.listen()
  let browser
  try {
    browser = await playwright.chromium.launch({ headless: true,
      ignoreDefaultArgs: showScrollbars ? ["--hide-scrollbars"] : undefined,
      ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: process.env.PLAYWRIGHT_CHANNEL || "chrome" }),
    })
  } catch (error) { await server.close(); throw error }
  return { browser, url: `http://127.0.0.1:${server.httpServer.address().port}`,
    close: async () => { await browser.close(); await server.close() },
  }
}

export const summary = (overrides = {}) => ({
  generated_at: "2026-10-02T04:00:00Z", business_date: "2026-10-02", timezone: "Asia/Manila",
  total_scans: 12, avg_confidence: 92.5, active_operator_count: 2,
  sources: [{ key: "supplier:source-1", name: "Fixture Supplier", count: 12 }],
  operators: [{ operator_id: "operator-1", name: "Alex Santos", username: "alex1", scan_count: 12, avg_confidence: 92.5 }],
  recent_scans: [], fifo_recommendations: [], pending_review_count: 3, expiring_stock_count: 4, confidence_threshold: 85, ...overrides,
})

export async function installEnvironment(page, { user, now = "2026-10-02T04:00:00Z" } = {}) {
  // Freeze before mounting: module loading must not accidentally cross midnight.
  await page.clock.install({ time: new Date(new Date(now).getTime() - 60_000) })
  await page.clock.pauseAt(new Date(now))
  await page.addInitScript(({ user }) => {
    localStorage.setItem("bananavision_token", user?.id ?? "admin-1")
    if (user) window.dashboardUser = user
    const sockets = []
    class TestWebSocket {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3
      readyState = 0
      constructor(url) { this.url = url; sockets.push(this); queueMicrotask(() => this.open()) }
      open() { this.readyState = 1; this.onopen?.({}) }
      close(code = 1000) { this.readyState = 3; this.onclose?.({ code }) }
      send() {}
    }
    window.WebSocket = TestWebSocket
    window.dashboardSocket = {
      disconnect: () => sockets.filter(s => s.readyState === 1).forEach(s => s.close(1006)),
      emit: (event, data = {}) => sockets.filter(s => s.readyState === 1).forEach(s => s.onmessage?.({ data: JSON.stringify({ event, data }) })),
    }
  }, { user })
}

export async function interceptApi(page, options = {}) {
  const state = { summary: summary(), cameras: [], byAccount: {}, failSummary: false, failCameras: false, hold: null, requests: [], ...options }
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url())
    const account = (route.request().headers().authorization ?? "").replace("Bearer ", "")
    state.requests.push({ url, account })
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" }
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    if (url.pathname === "/api/v1/dashboard") {
      const payload = state.byAccount[account] ?? state.summary
      const failed = state.failSummary
      if (state.hold) await state.hold(account)
      return route.fulfill({ status: failed ? 503 : 200, headers, json: failed ? { detail: "Fixture service unavailable" } : payload }).catch(() => {})
    }
    if (url.pathname === "/api/v1/dashboard/scans") return route.fulfill({ headers, json: {
      items: [], total: 0, page: 1, page_size: 15, generated_at: state.summary.generated_at, business_date: state.summary.business_date, timezone: "Asia/Manila",
    } })
    if (url.pathname === "/api/v1/cameras") return route.fulfill({ status: state.failCameras ? 503 : 200, headers, json: state.failCameras ? { detail: "Camera metadata unavailable" } : state.cameras })
    if (url.pathname.includes("/cameras/preview/")) return route.abort("failed")
    return route.fulfill({ status: 404, headers, json: { detail: `Unexpected test API: ${url.pathname}` } })
  })
  return state
}
