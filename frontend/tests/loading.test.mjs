import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "loading.fixture.tsx", port: 5215 }) })
after(async () => { await runtime?.close() })

async function setup(t, handler) {
  const context = await runtime.browser.newContext()
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page)
  await page.route("**/api/v1/**", async route => {
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    await handler(route, headers)
  })
  await page.goto(runtime.url + "/dashboard")
  return page
}

test("stalled GET settles with retryable timeout without clearing authentication", async t => {
  let requested
  const requestSeen = new Promise(resolve => { requested = resolve })
  const page = await setup(t, (route, headers) => {
    if (route.request().url().endsWith("/deadline")) { requested(); return }
    return route.fulfill({ headers, json: { items: [], total: 0 } })
  })
  await page.getByRole("button", { name: "Read data" }).click()
  await requestSeen
  await page.clock.runFor(15_100)
  await page.getByTestId("message").getByText("Request timed out. Please try again.", { exact: true }).waitFor({ timeout: 2000 })
  assert.equal(await page.evaluate(() => localStorage.getItem("bananavision_token")), "admin-1")
})

test("notification failure is not an empty inbox and retry can load true empty state", async t => {
  let failed = true, release
  let gate = new Promise(resolve => { release = resolve })
  const page = await setup(t, async (route, headers) => {
    const wait = gate, fail = failed
    if (wait) await wait
    await route.fulfill({ headers, status: fail ? 503 : 200, json: fail ? { detail: "Fixture unavailable" } : { items: [], total: 0 } }).catch(() => {})
  })
  await page.locator("#notification-trigger").click()
  await page.getByRole("status", { name: "Loading notifications" }).waitFor({ timeout: 2000 })
  assert.equal(await page.getByText("No notifications yet").count(), 0)
  release(); gate = null
  await page.getByRole("alert").waitFor()
  assert.equal(await page.getByText("No notifications yet").count(), 0)
  failed = false
  await page.getByRole("button", { name: "Retry notifications" }).click()
  await page.getByText("No notifications yet").waitFor()
})

test("notification refresh cannot undo marking read and account changes discard snapshots", async t => {
  let gate = null, release, requested
  let read = false
  const item = { id: "n1", type: "scan_complete", title: "Saved scan", message: "Fixture notification", timestamp: "2026-10-02T04:00:00Z", read: false }
  const page = await setup(t, async (route, headers) => {
    if (route.request().method() === "POST") { read = true; return route.fulfill({ headers, json: { message: "OK" } }) }
    const wait = gate, payload = { ...item, read }
    if (wait) { requested?.(); await wait }
    return route.fulfill({ headers, json: { items: [payload], total: 1 } }).catch(() => {})
  })
  await page.locator("#notification-trigger span").waitFor()
  gate = new Promise(resolve => { release = resolve })
  const requestSeen = new Promise(resolve => { requested = resolve })
  await page.locator("#notification-trigger").click()
  await requestSeen
  await page.getByRole("button", { name: "Mark all read" }).click()
  await page.getByRole("button", { name: "Mark all read" }).waitFor({ state: "hidden" })
  release(); gate = null
  await page.clock.runFor(100)
  assert.equal(await page.locator("#notification-trigger span").count(), 0)
  gate = new Promise(resolve => { release = resolve })
  await page.evaluate(() => window.dashboardTest.setUser({ id: "other", username: "other", fullName: "Other", role: "Admin" }))
  await page.locator("#notification-trigger").click()
  await page.getByRole("status", { name: "Loading notifications" }).waitFor()
  assert.equal(await page.getByText("Saved scan", { exact: true }).count(), 0)
  release()
})

for (const action of ["all", "single"]) {
  test(`stalled ${action} notification mark-read restores navigation`, async t => {
    let requested
    const seen = new Promise(resolve => { requested = resolve })
    const page = await setup(t, (route, headers) => {
      if (route.request().method() !== "GET") { requested(); return }
      return route.fulfill({ headers, json: { items: [{ id: "n1", type: "scan_complete", title: "Saved scan", message: "Fixture notification", timestamp: "2026-10-02T04:00:00Z", read: false }], total: 1 } })
    })
    await page.locator("#notification-trigger").click()
    const row = page.getByRole("button", { name: /Saved scan/ })
    await row.waitFor()
    await (action === "all" ? page.getByRole("button", { name: "Mark all read" }) : row).click()
    await seen
    assert.equal(await row.isDisabled(), true)
    await page.clock.runFor(15_100)
    await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(button => button.textContent.includes('Fixture notification') && !button.disabled), null, { timeout: 2000 })
    assert.equal(await page.getByRole("button", { name: "Mark all read" }).isEnabled(), true)
  })
}
