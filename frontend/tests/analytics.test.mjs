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

async function setup(t, response = payload(), user) {
  const context = await runtime.browser.newContext({ timezoneId: "America/Los_Angeles" })
  const page = await context.newPage()
  if (user) await page.addInitScript(value => { window.dashboardUser = value }, user)
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
    const fail = typeof state.fail === "function" ? state.fail(query) : state.fail
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
  await page.getByText(`Verified Accuracy: ${definitions.human_verified_accuracy}`, { exact: true }).waitFor()
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

test("cultivar and status selections combine with source and date filters", async t => {
  const { page, state } = await setup(t)
  await expectCount(page, 12)
  for (const [label, option] of [["Analytics source", "Renamed Supplier"], ["Analytics date range", "Today"], ["Analytics cultivar", "Cardaba"], ["Analytics stock status", "Sold"]]) {
    await page.getByRole("combobox", { name: label }).click()
    await page.getByRole("option", { name: option, exact: true }).click()
  }
  await expectCount(page, 12)
  const query = state.requests.at(-1)
  assert.equal(query.get("source_key"), "supplier:source-a")
  assert.equal(query.get("range"), "today")
  assert.equal(query.get("cultivar"), "Cardaba")
  assert.equal(query.get("inventory_status"), "Sold")
})

test("operator performance shows scan activity without attributing QC actions to operators", async t => {
  const { page } = await setup(t, payload({
    operator_performance: [{
      operator_id: "operator-a",
      name: "Kiosk Operator",
      total_scans: 12,
      avg_confidence: 90,
      confidence_sample_count: 12,
      flagged_scans: 3,
      flag_rate: 25.0,
      overridden_scans: 2,
    }],
  }))
  await expectCount(page, 12)
  await page.getByText("Operator Performance Table", { exact: true }).waitFor()
  assert.deepEqual(await page.getByRole("columnheader").allTextContents(), ["#", "Operator", "Total Scans", "Avg Confidence"])
  assert.equal(await page.getByRole("cell", { name: "12", exact: true }).count(), 1)
  assert.equal(await page.getByRole("cell", { name: "90%", exact: true }).count(), 1)
  assert.match(await page.getByRole("cell", { name: "90%", exact: true }).locator("[title]").getAttribute("title"), /12 valid model-confidence results/)
  assert.equal(await page.getByText("Flag Rate (%)", { exact: true }).count(), 0)
  assert.equal(await page.getByText("QC Overrides", { exact: true }).count(), 0)
})

test("operator table keeps numeric/name sorting, zero and missing confidence, and responsive scrolling", async t => {
  const { page } = await setup(t, payload({ operator_performance: [
    { operator_id: "c", name: "Casey Santos", total_scans: 12, avg_confidence: 90, confidence_sample_count: 10 },
    { operator_id: "b", name: "Blair Cruz", total_scans: 2, avg_confidence: 0, confidence_sample_count: 2 },
    { operator_id: "a", name: "Alex Reyes", total_scans: 5, avg_confidence: null, confidence_sample_count: 0 },
  ] }))
  await expectCount(page, 12)
  const table = page.getByRole("table")
  const names = () => table.locator("tbody tr").evaluateAll(rows => rows.map(row => row.cells[1].querySelector(".font-medium").textContent))
  await table.getByRole("columnheader", { name: "Total Scans", exact: true }).click()
  assert.deepEqual(await names(), ["Blair Cruz", "Alex Reyes", "Casey Santos"])
  await table.getByRole("columnheader", { name: "Total Scans", exact: true }).click()
  assert.deepEqual(await names(), ["Casey Santos", "Alex Reyes", "Blair Cruz"])
  await table.getByRole("columnheader", { name: "Operator", exact: true }).click()
  assert.deepEqual(await names(), ["Alex Reyes", "Blair Cruz", "Casey Santos"])
  await table.getByRole("columnheader", { name: "Avg Confidence", exact: true }).click()
  await table.getByRole("columnheader", { name: "Avg Confidence", exact: true }).click()
  assert.equal((await names())[0], "Casey Santos")
  assert.equal(await table.getByRole("cell", { name: "0%", exact: true }).count(), 1)
  assert.equal(await table.getByRole("cell", { name: "—", exact: true }).count(), 1)
  assert.equal(await table.getByRole("cell", { name: "—", exact: true }).locator("[title]").getAttribute("title"), "0 valid model-confidence results")
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await table.scrollIntoViewIfNeeded()
    await page.clock.runFor(1000)
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "No page-level horizontal overflow")
    const bounds = await table.locator("..").boundingBox()
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1, "Table scroll container stays inside viewport")
    await table.locator("..").evaluate(element => { element.scrollLeft = element.scrollWidth })
    await table.getByRole("columnheader", { name: "Avg Confidence", exact: true }).click()
    await page.screenshot({ path: `node_modules/.tmp/bv-operator-${width}.png` })
  }
})

test("operator metrics update with combined filters and disappear for an empty selection", async t => {
  const { page } = await setup(t, query => {
    const filtered = query.get("range") === "today" && query.get("source_key") === "supplier:source-a"
      && query.get("cultivar") === "Cardaba" && query.get("inventory_status") === "Sold"
    return payload({ total_scans: query.get("range") === "all" ? 0 : filtered ? 2 : 12, operator_performance: query.get("range") === "all" ? [] : [{
      operator_id: "operator-a", name: "Kiosk Operator", total_scans: filtered ? 2 : 12,
      avg_confidence: filtered ? 0 : 90, confidence_sample_count: filtered ? 1 : 12,
    }] })
  })
  await expectCount(page, 12)
  for (const [label, option] of [["Analytics source", "Renamed Supplier"], ["Analytics date range", "Today"], ["Analytics cultivar", "Cardaba"], ["Analytics stock status", "Sold"]]) {
    await page.getByRole("combobox", { name: label }).click()
    await page.getByRole("option", { name: option, exact: true }).click()
  }
  await expectCount(page, 2)
  assert.equal(await page.getByRole("cell", { name: "2", exact: true }).count(), 1)
  assert.equal(await page.getByRole("cell", { name: "0%", exact: true }).count(), 1)
  await page.getByRole("combobox", { name: "Analytics date range" }).click()
  await page.getByRole("option", { name: "All Time", exact: true }).click()
  await expectCount(page, 0)
  assert.equal(await page.getByRole("table").count(), 0)
})

test("Operator view uses the same activity columns without restricted QC metrics", async t => {
  const { page } = await setup(t, payload(), { id: "operator-a", username: "kiosk", fullName: "Kiosk Operator", role: "Operator" })
  await expectCount(page, 12)
  assert.deepEqual(await page.getByRole("columnheader").allTextContents(), ["#", "Operator", "Total Scans", "Avg Confidence"])
  assert.equal(await page.getByRole("table").locator("tbody tr").count(), 1)
})

test("Date From and Date To replace the preset and are sent as inclusive Manila days", async t => {
  const { page, state } = await setup(t)
  await expectCount(page, 12)
  await page.getByRole("button", { name: "Date from", exact: true }).click()
  await page.getByRole("button", { name: /October 1st, 2026/ }).click()
  await page.getByRole("button", { name: "Date to", exact: true }).click()
  // Days after today (Asia/Manila, Oct 5) cannot be picked.
  assert.equal(await page.getByRole("button", { name: /October 6th, 2026/ }).isDisabled(), true)
  await page.getByRole("button", { name: /October 3rd, 2026/ }).click()
  const query = () => state.requests.at(-1)
  assert.equal(query().get("date_from"), "2026-10-01")
  assert.equal(query().get("date_to"), "2026-10-03")
  // "custom" is a UI choice only; the backend receives no range with dates.
  assert.equal(query().get("range"), null)
  await page.getByRole("combobox", { name: "Analytics date range" }).getByText("Custom", { exact: true }).waitFor()
  await page.getByRole("button", { name: "Clear custom dates" }).click()
  await page.getByRole("combobox", { name: "Analytics date range" }).getByText("Last 7 Days", { exact: true }).waitFor()
  assert.equal(query().get("range"), "week")
  assert.equal(query().get("date_from"), null)
})

test("a chart with its own dates shows its own error, never the page data", async t => {
  const { page, state } = await setup(t)
  await expectCount(page, 12)
  const ripeness = card(page, "Ripeness Distribution")
  await ripeness.getByTitle("Page dates").getByText("Last 7 Days").waitFor()
  state.fail = query => query.get("range") === "today"
  await page.getByRole("combobox", { name: "Ripeness Distribution date range" }).click()
  await page.getByRole("option", { name: "Today", exact: true }).click()
  await ripeness.getByRole("alert").getByText(/Could not load this chart for Today/).waitFor()
  assert.equal(await ripeness.getByText(/^Ripe 100%/).count(), 0)
  await expectCount(page, 12)
  state.fail = false
  state.response = query => query.get("range") === "today" ? payload({ ripeness_distribution: [{ name: "Unripe", value: 3 }] }) : payload()
  await ripeness.getByRole("button", { name: "Retry" }).click()
  await page.clock.runFor(2000) // pie labels appear after the chart animation
  await ripeness.getByText(/Unripe 100%/).waitFor()
  assert.equal(await ripeness.getByRole("alert").count(), 0)
  await ripeness.getByTitle("This chart has its own dates").getByText("Today · this chart").waitFor()
  await page.getByRole("button", { name: "Use page dates for Ripeness Distribution" }).click()
  await page.clock.runFor(2000)
  await ripeness.getByText(/^Ripe 100%/).waitFor()
  await ripeness.getByTitle("Page dates").getByText("Last 7 Days").waitFor()
})
