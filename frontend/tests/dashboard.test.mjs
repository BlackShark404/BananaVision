import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { mkdir } from "node:fs/promises"
import path from "node:path"
import { startBrowser, installEnvironment, interceptApi, summary } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser() })
after(async () => { await runtime?.close() })

async function setup(t, { environment, response, viewport, timezoneId } = {}) {
  const context = await runtime.browser.newContext({ viewport: viewport ?? { width: 1365, height: 1000 }, timezoneId: timezoneId ?? "UTC" })
  const page = await context.newPage()
  page.setDefaultTimeout(8000)
  page.setDefaultNavigationTimeout(30_000)
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, [], "No uncaught browser errors") })
  await installEnvironment(page, environment)
  const state = await interceptApi(page, response)
  await page.goto(`${runtime.url}/dashboard`, { waitUntil: "domcontentloaded" })
  return { page, state }
}

const requests = state => state.requests.filter(({ url }) => url.pathname === "/api/v1/dashboard")
const card = (page, title = /Scans Today/i) => page.getByRole("button", { name: new RegExp(`^(?:${title.source})`, title.flags) })
const value = element => element.locator("h3")
async function expectValue(element, expected) {
  await value(element).filter({ hasText: new RegExp(`^${expected}$`) }).waitFor()
  assert.equal(await value(element).innerText(), expected)
}
async function until(predicate, message) {
  const deadline = Date.now() + 6000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  assert.fail(message)
}

test("loading and unavailable are not zero; retry can produce a genuine zero", async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { page, state } = await setup(t, { response: { failSummary: true, hold: () => pending } })
  await card(page).waitFor()
  assert.notEqual(await value(card(page)).innerText(), "0")
  state.hold = null
  release()
  await page.getByText(/unavailable|could not be loaded/i).first().waitFor()
  assert.notEqual(await value(card(page)).innerText(), "0")
  state.failSummary = false
  state.summary = summary({ total_scans: 0, avg_confidence: null, active_operator_count: 0, sources: [], operators: [], pending_review_count: 0, expiring_stock_count: 0 })
  await page.getByRole("button", { name: /retry|refresh/i }).first().click()
  await expectValue(card(page), "0")
})

test("failed refresh preserves last snapshot and an explicit retry recovers", async t => {
  const { page, state } = await setup(t)
  await expectValue(card(page), "12")
  state.failSummary = true
  await page.evaluate(() => window.dispatchEvent(new Event("online")))
  await page.getByText(/stale|unavailable|could not be loaded/i).first().waitFor()
  await expectValue(card(page), "12")
  state.failSummary = false
  state.summary = summary({ total_scans: 18 })
  await page.getByRole("button", { name: /retry|refresh/i }).first().click()
  await expectValue(card(page), "18")
})

test("socket disconnection is visible and reconnect refreshes the data", async t => {
  const { page, state } = await setup(t)
  await expectValue(card(page), "12")
  const count = requests(state).length
  await page.evaluate(() => window.dashboardSocket.disconnect())
  await page.getByText(/disconnected|reconnecting|stale/i).first().waitFor()
  await expectValue(card(page), "12")
  state.summary = summary({ total_scans: 23 })
  await page.clock.runFor(1500)
  await until(() => requests(state).length > count, "reconnect must refresh summary")
  await expectValue(card(page), "23")
})

test("completion events and periodic polling reconcile counts", async t => {
  const { page, state } = await setup(t)
  await expectValue(card(page), "12")
  state.summary = summary({ total_scans: 14 })
  await page.evaluate(() => window.dashboardSocket.emit("scan:completed", { scan_id: "fixture" }))
  await page.clock.runFor(1000)
  await expectValue(card(page), "14")
  state.summary = summary({ total_scans: 15 })
  await page.clock.runFor(31_000)
  await expectValue(card(page), "15")
})

test("Manila midnight refreshes the business day in a different browser timezone", async t => {
  const { page, state } = await setup(t, {
    environment: { now: "2026-10-01T15:59:59.500Z" }, timezoneId: "America/Los_Angeles",
    response: { summary: summary({ business_date: "2026-10-01", generated_at: "2026-10-01T15:59:59.500Z" }) },
  })
  await expectValue(card(page), "12")
  const count = requests(state).length
  state.summary = summary({ business_date: "2026-10-02", generated_at: "2026-10-01T16:00:01Z", total_scans: 0 })
  await page.clock.runFor(2500)
  await until(() => requests(state).length > count, "Manila midnight must refresh daily counts")
  await expectValue(card(page), "0")
})

test("same-name account and role changes discard an older in-flight response", async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const alex = { id: "account-A", username: "alex-a", fullName: "Alex Santos", role: "Admin" }
  const { page, state } = await setup(t, { environment: { user: alex }, response: {
    hold: account => account === "account-A" ? pending : undefined,
    byAccount: { "account-A": summary({ total_scans: 999 }), "account-B": summary({ total_scans: 7, success_rate: 0 }) },
  } })
  await until(() => requests(state).some(({ account }) => account === "account-A"), "old account starts request")
  await page.evaluate(() => window.dashboardTest.setUser({ id: "account-B", username: "alex-b", fullName: "Alex Santos", role: "Operator" }))
  await expectValue(card(page), "7")
  release()
  await page.clock.runFor(100)
  await expectValue(card(page), "7")
  assert.equal(await page.getByText("999", { exact: true }).count(), 0)
  assert.equal(await card(page, /Active Operators/i).count(), 0)
  assert.equal(await page.getByText("Scan Success Rate", { exact: true }).count(), 1)
  assert.equal(await page.getByRole("heading", { name: "0.0%", exact: true }).count(), 1)
  assert.ok(requests(state).some(({ account }) => account === "account-B"), "new request uses account identity")
})

test("admin scan KPIs redirect to filtered logs; group KPIs retain lists", async t => {
  const { page } = await setup(t)
  for (const [label, query] of [[/Scans Today/i, { date: "2026-10-02" }], [/Pending quality reviews/i, { status: "Flagged" }], [/Expiring stock/i, { attention: "at-risk" }]]) {
    await expectValue(card(page), "12")
    await card(page, label).click()
    await page.waitForURL("**/logs?**")
    assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams), query)
    assert.equal(await page.getByRole("dialog").count(), 0)
    await page.goto(`${runtime.url}/dashboard`, { waitUntil: "domcontentloaded" })
  }
  for (const [label, view] of [[/Active Operators/i, "operators"], [/Active Sources/i, "sources"]]) {
    await card(page, label).click()
    await page.waitForURL(`**/dashboard?**view=${view}**`)
    await page.getByRole("dialog").waitFor()
    await page.keyboard.press("Escape")
    await page.getByRole("dialog").waitFor({ state: "hidden" })
  }
  await card(page, /System Health/i).click()
  await page.waitForURL("**/devices")
})

test("operator source KPI opens its list and success rate uses the server metric", async t => {
  const { page } = await setup(t, { environment: { user: { id: "operator-account", username: "operator", fullName: "Alex Santos", role: "Operator" } }, response: { summary: summary({ success_rate: 75 }) } })
  await expectValue(card(page), "12")
  assert.equal(await page.getByText("Scan Success Rate", { exact: true }).count(), 1)
  assert.equal(await page.getByRole("heading", { name: "75.0%", exact: true }).count(), 1)
  await card(page, /My Sources/i).click()
  await page.waitForURL("**/dashboard?**view=sources**")
  await page.getByRole("dialog").waitFor()
})

test("daily group rows retain the selected date and stable identity", async t => {
  const { page } = await setup(t)
  for (const [label, row, filter] of [[/Active Sources/i, /Fixture Supplier/, { source_key: "supplier:source-1" }], [/Active Operators/i, /Alex Santos/, { operator_id: "operator-1" }]]) {
    await expectValue(card(page), "12")
    await card(page, label).click()
    await page.getByRole("dialog").getByRole("button", { name: row }).click()
    await page.waitForURL("**/logs?**")
    assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams), { date: "2026-10-02", ...filter })
    await page.goto(`${runtime.url}/dashboard`)
  }
})

test("legacy review and all-records links keep their meaning", async t => {
  const { page } = await setup(t)
  for (const [view, query] of [["review", { status: "Flagged" }], ["expiring", { attention: "at-risk" }], ["all", { date: "all" }]]) {
    await page.goto(`${runtime.url}/dashboard?view=${view}`)
    await page.waitForURL("**/logs?**")
    assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams), query, view)
  }
})

test("Recent Scans and Today's Sources retain their logs destinations", async t => {
  const olderScan = {
    id: "scan-older", date_time: "2026-09-30T08:10:00+08:00", cultivar: "Lakatan", ripeness: "Ripe",
    confidence: 91, operator_id: "operator-1", operator_name: "Alex Santos", source_key: "supplier:source-1",
    source_name: "Fixture Supplier", inventory_status: "In Stock", flagged: false, spoilage_days: "5-7", remaining_days: 3,
  }
  const { page } = await setup(t, { response: { summary: summary({ recent_scans: [olderScan] }) } })
  await expectValue(card(page), "12")
  await page.getByRole("button", { name: /View All Logs/i }).click()
  await page.waitForURL("**/logs?**")
  assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams), { date: "all" })
  await page.goto(`${runtime.url}/dashboard`)
  await expectValue(card(page), "12")
  const hrefs = await page.locator('a[href^="/logs"]').evaluateAll(links => links.map(link => link.getAttribute("href")))
  assert.ok(hrefs.includes("/logs?date=all"), "recent scan rows open every date, so older scans stay visible")
  assert.ok(!hrefs.includes("/logs"), "no dashboard link falls back to today's plain view")
  await page.goto(`${runtime.url}/dashboard`)
  await expectValue(card(page), "12")
  await page.getByRole("button", { name: "Open Today's Sources in Scan Logs" }).click()
  await page.waitForURL("**/logs?**")
  assert.equal(new URL(page.url()).searchParams.get("date"), "2026-10-02")
})

test("FIFO recommendations surface actionable batches and open their records", async t => {
  const fifo = [
    {
      key: "intake:intake-1", intake_id: "intake-1", scan_id: null, source_name: "Fifo Supplier",
      scanned_at: "2026-09-30T08:00:00+08:00", hands: 2, earliest_remaining_days: 1,
    },
    {
      key: "scan:scan-9", intake_id: null, scan_id: "scan-9", source_name: "Loose Batch",
      scanned_at: "2026-10-01T08:00:00+08:00", hands: 1, earliest_remaining_days: null,
    },
  ]
  const { page } = await setup(t, { response: { summary: summary({ fifo_recommendations: fifo }) } })
  await expectValue(card(page), "12")
  await page.getByText("Sell immediately", { exact: true }).waitFor()
  await page.getByText("Risk unknown", { exact: true }).waitFor()
  await page.getByText("Est. 1 day left", { exact: true }).waitFor()
  assert.equal(await page.getByRole("link", { name: /Fifo Supplier/ }).getAttribute("href"), "/logs?intake=intake-1")
  assert.equal(await page.getByRole("link", { name: /Loose Batch/ }).getAttribute("href"), "/scans/scan-9")
  await page.getByRole("button", { name: /View Inventory/i }).click()
  await page.waitForURL("**/inventory")
})

test("zero cameras and failed preview are explicit and use the physical device ID", async t => {
  const { page, state } = await setup(t)
  await expectValue(card(page), "12")
  await page.getByText(/No cameras configured|No cameras found/i).first().waitFor()
  assert.equal(await page.locator('img[src*="/cameras/preview/"]').count(), 0)
  state.cameras = [{ device_id: 9, label: "Top camera", online: true }]
  await page.evaluate(() => window.dispatchEvent(new Event("focus")))
  await page.getByText(/preview unavailable|preview failed|feed unavailable|feed offline/i).first().waitFor()
  await expectValue(card(page), "12")
  assert.ok(state.requests.some(({ url }) => url.pathname.endsWith("/cameras/preview/9")))
})

test("camera outage leaves metrics usable, with no mobile page overflow", async t => {
  const { page, state } = await setup(t, { viewport: { width: 390, height: 844 }, response: { failCameras: true } })
  await expectValue(card(page), "12")
  await page.getByText(/camera.*unavailable|camera.*could not|unable.*camera/i).first().waitFor()
  assert.notEqual(await value(card(page, /System Health/i)).innerText(), "0/0")
  state.failCameras = false
  await page.evaluate(() => window.dispatchEvent(new Event("focus")))
  await page.getByText(/No cameras configured|No cameras found/i).first().waitFor()
  const dimensions = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }))
  assert.ok(dimensions.content <= dimensions.viewport + 1, `mobile overflow: ${JSON.stringify(dimensions)}`)
  if (process.env.DASHBOARD_SCREENSHOT_DIR) {
    await mkdir(process.env.DASHBOARD_SCREENSHOT_DIR, { recursive: true })
    await page.screenshot({ path: path.join(process.env.DASHBOARD_SCREENSHOT_DIR, "dashboard-mobile.png"), fullPage: true })
    await page.setViewportSize({ width: 1365, height: 1000 })
    await page.screenshot({ path: path.join(process.env.DASHBOARD_SCREENSHOT_DIR, "dashboard-desktop.png"), fullPage: true })
  }
})

test('operator success KPI opens exactly the all-time successful scan population', async t => {
  const { page } = await setup(t, { environment: { user: { id: 'operator-account', username: 'operator', fullName: 'Alex Santos', role: 'Operator' } }, response: { summary: summary({ success_rate: 75 }) } })
  await expectValue(card(page), '12')
  const success = page.getByRole('button', { name: /^Scan Success Rate/ })
  assert.equal(await success.count(), 1)
  await success.click()
  await page.waitForURL('**/logs?**')
  assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams), { attention: 'success' })
})
