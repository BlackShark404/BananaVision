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
    byAccount: { "account-A": summary({ total_scans: 999 }), "account-B": summary({ total_scans: 7, avg_confidence: 0 }) },
  } })
  await until(() => requests(state).some(({ account }) => account === "account-A"), "old account starts request")
  await page.evaluate(() => window.dashboardTest.setUser({ id: "account-B", username: "alex-b", fullName: "Alex Santos", role: "Operator" }))
  await expectValue(card(page), "7")
  release()
  await page.clock.runFor(100)
  await expectValue(card(page), "7")
  assert.equal(await page.getByText("999", { exact: true }).count(), 0)
  assert.equal(await card(page, /Active Operators/i).count(), 0)
  assert.match(await value(card(page, /My Avg Confidence/i)).innerText(), /^0(?:\.0)?%$/)
  assert.ok(requests(state).some(({ account }) => account === "account-B"), "new request uses account identity")
})

test("admin KPIs open matching drilldowns and System Health opens devices", async t => {
  const { page } = await setup(t)
  await expectValue(card(page), "12")
  for (const [label, view] of [[/Scans Today/i, "today"], [/Active Operators/i, "operators"], [/Active Sources/i, "sources"], [/Pending quality reviews/i, "review"], [/Expiring stock/i, "expiring"]]) {
    await card(page, label).click()
    await page.waitForURL(`**/dashboard?**view=${view}**`)
    await page.getByRole("dialog").waitFor()
    await page.keyboard.press("Escape")
    await page.getByRole("dialog").waitFor({ state: "hidden" })
  }
  await card(page, /System Health/i).click()
  await page.waitForURL("**/devices")
})

test("operator confidence and source KPIs open their matching drilldowns", async t => {
  const { page } = await setup(t, { environment: { user: { id: "operator-account", username: "operator", fullName: "Alex Santos", role: "Operator" } } })
  await expectValue(card(page), "12")
  for (const [label, view] of [[/My Avg Confidence/i, "confidence"], [/My Sources Today/i, "sources"]]) {
    await card(page, label).click()
    await page.waitForURL(`**/dashboard?**view=${view}**`)
    await page.getByRole("dialog").waitFor()
    await page.keyboard.press("Escape")
    await page.getByRole("dialog").waitFor({ state: "hidden" })
  }
})

test("Recent Scans and Today's Sources retain their logs destinations", async t => {
  const { page } = await setup(t)
  await expectValue(card(page), "12")
  await page.getByRole("button", { name: /View All Logs/i }).click()
  await page.waitForURL("**/logs")
  await page.goto(`${runtime.url}/dashboard`)
  await expectValue(card(page), "12")
  await page.getByRole("button", { name: "Open Today's Sources in Scan Logs" }).click()
  await page.waitForURL("**/logs")
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
