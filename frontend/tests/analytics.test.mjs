import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "analytics.fixture.tsx", port: 5194 }) })
after(async () => { await runtime?.close() })

const definitionKeys = ["throughput", "classifications", "model_confidence", "low_confidence", "inventory_risk", "confidence_by_ripeness", "trend", "sources", "operators", "hourly", "human_verified_accuracy"]
const definitions = Object.fromEntries(definitionKeys.map(key => [key, `Server definition: ${key}`]))
const sources = [{ key: "supplier:source-a", name: "Renamed Supplier" }, { key: "supplier:source-b", name: "Other Supplier" }]
const payload = (overrides = {}) => ({
  total_scans: 12, avg_confidence: 90, most_common_cultivar: "Lakatan", low_confidence_count: 2, low_confidence_rate: 16.7,
  at_risk_count: 2, classification_count: 12, incomplete_count: 0, confidence_sample_count: 12, confidence_threshold: 85,
  current_stock_count: 10, risk_unknown_count: 0, human_verified_accuracy: null, verified_scan_count: 0,
  source_options: sources, generated_at: "2026-10-05T10:00:00+08:00", business_date: "2026-10-05",
  next_refresh_at: "2026-10-06T00:00:00+08:00", timezone: "Asia/Manila", range_start: "2026-09-29T00:00:00+08:00",
  range_end: "2026-10-05T10:00:00+08:00", trend_start: "2026-09-22", trend_end: "2026-10-05",
  metric_definitions: definitions, ripeness_distribution: [{ name: "Ripe", value: 12 }], cultivar_counts: [{ name: "Lakatan", count: 12 }],
  cultivar_ripeness: [{ name: "Lakatan", Unripe: 0, "Semi Ripe": 0, Ripe: 12, Overripe: 0 }],
  ripeness_confidence: [{ ripeness: "Ripe", count: 12, avgConfidence: 90 }],
  scans_by_source: [{ ...sources[0], count: 12 }], scan_trend: [{ date: "Oct 05", count: 12 }],
  hourly_distribution: [{ hour: "10 AM", count: 12 }],
  operator_performance: [{ operator_id: "operator-a", name: "Kiosk Operator", total_scans: 12, avg_confidence: 90, confidence_sample_count: 12 }],
  ...overrides,
})

async function setup(t, response = payload()) {
  const context = await runtime.browser.newContext({ timezoneId: "America/Los_Angeles" })
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.setDefaultNavigationTimeout(45000)
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, [], "No uncaught browser errors") })
  await page.clock.install({ time: new Date("2026-10-05T02:00:00Z") })
  await page.clock.pauseAt(new Date("2026-10-05T02:00:00Z"))
  const state = { response, fail: false, hold: null, requests: [] }
  await page.route("**/api/v1/analytics/summary**", async route => {
    const query = new URL(route.request().url()).searchParams
    state.requests.push(query)
    const value = typeof state.response === "function" ? state.response(query) : state.response
    const fail = state.fail
    if (state.hold) await state.hold(query)
    await route.fulfill({ status: fail ? 503 : 200, headers: { "access-control-allow-origin": "*" }, json: fail ? { detail: "Analytics unavailable" } : value }).catch(() => {})
  })
  await page.goto(`${runtime.url}/dashboard`, { waitUntil: "domcontentloaded" })
  return { page, state }
}

const card = (page, label) => page.locator('[data-slot="card"]').filter({ has: page.getByText(label, { exact: true }) }).first()
async function expectCount(page, count) {
  await card(page, "Total Scans").locator("h3").filter({ hasText: new RegExp(`^${count}$`) }).waitFor()
}

test("all Analytics KPI and chart definitions use the server contract", async t => {
  const { page } = await setup(t)
  await expectCount(page, 12)
  for (const [label, key] of [["Total Scans", "throughput"], ["Avg Confidence", "model_confidence"], ["Low Confidence", "low_confidence"], ["At-Risk Scans", "inventory_risk"]]) {
    assert.equal(await card(page, label).getAttribute("title"), definitions[key])
    assert.equal(await card(page, label).getAttribute("aria-description"), definitions[key])
  }
  for (const [label, key] of [["Ripeness Distribution", "classifications"], ["Cultivar Counts", "classifications"], ["Ripeness by Cultivar", "classifications"], ["Confidence by Ripeness", "confidence_by_ripeness"], ["Scans by Source", "sources"], ["Scan Trend (Last 14 Days)", "trend"], ["Operator Performance Table", "operators"], ["Peak Scanning Hours", "hourly"]]) {
    assert.equal(await page.getByText(label, { exact: true }).getAttribute("title"), definitions[key])
  }
})

test("empty and incomplete data have no fabricated confidence or accuracy", async t => {
  const { page } = await setup(t, payload({ total_scans: 0, classification_count: 0, confidence_sample_count: 0, avg_confidence: null, low_confidence_rate: null, at_risk_count: 0, scans_by_source: [], operator_performance: [] }))
  await expectCount(page, 0)
  assert.equal(await card(page, "Avg Confidence").locator("h3").innerText(), "—")
  assert.equal(await card(page, "Low Confidence").locator("h3").innerText(), "—")
  await page.getByText(/No scans match this source/).waitFor()
  assert.equal(await page.getByText("No classified scans in this selection.", { exact: true }).count(), 3)
  await page.getByText("Metric definitions", { exact: true }).click()
  await page.getByText(/Human-verified model accuracy: unavailable/).waitFor()
  assert.doesNotMatch(await page.locator("body").innerText(), /NaN|undefined|null%/)
})

test("source choices survive filtering and a delayed older response cannot replace the selected range", async t => {
  const { page, state } = await setup(t)
  await expectCount(page, 12)
  await page.getByRole("combobox", { name: "Analytics source" }).click()
  await page.getByRole("option", { name: "Renamed Supplier", exact: true }).click()
  await expectCount(page, 12)
  await page.getByRole("combobox", { name: "Analytics source" }).click()
  await page.getByRole("option", { name: "Other Supplier", exact: true }).waitFor()
  await page.keyboard.press("Escape")
  assert.ok(state.requests.some(query => query.get("source_key") === "supplier:source-a"))
  let release
  const delayed = new Promise(resolve => { release = resolve })
  state.hold = query => query.get("range") === "today" ? delayed : undefined
  state.response = query => payload({ total_scans: query.get("range") === "today" ? 999 : 37 })
  await page.getByRole("combobox", { name: "Analytics date range" }).click()
  await page.getByRole("option", { name: "Today", exact: true }).click()
  await page.getByRole("combobox", { name: "Analytics date range" }).click()
  await page.getByRole("option", { name: "Last 30 Days", exact: true }).click()
  await expectCount(page, 37)
  release()
  await page.clock.runFor(100)
  await expectCount(page, 37)
  assert.equal(await page.getByText("999", { exact: true }).count(), 0)
})

test("failed Analytics refresh shows an error with retry instead of stale values", async t => {
  const { page, state } = await setup(t)
  await expectCount(page, 12)
  state.fail = true
  await page.evaluate(() => window.dispatchEvent(new Event("online")))
  await page.getByRole("alert").getByText("Analytics unavailable", { exact: true }).waitFor()
  assert.equal(await card(page, "Total Scans").count(), 0)
  state.fail = false
  state.response = payload({ total_scans: 19 })
  await page.getByRole("button", { name: "Retry" }).click()
  await expectCount(page, 19)
})
