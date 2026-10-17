import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"
let runtime
before(async () => { runtime = await startBrowser({ fixture: "operationsloading.fixture.tsx", auth: "kiosk.auth.tsx", port: 5214 }) })
after(async () => { await runtime?.close() })

async function setup(t, screen, overrides = {}) {
  const context = await runtime.browser.newContext()
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page)
  const state = { failOperators: true, sensor: null, failSensor: false, ...overrides }
  const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" }
  await page.route("**/health", route => route.fulfill({ headers, json: { sensor_connected: true } }))
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    if (path === "/api/v1/auth/operators") return route.fulfill({ headers, status: state.failOperators ? 503 : 200, json: state.failOperators ? { detail: "Unavailable" } : [{ id: "operator-1", username: "fixture", full_name: "Fixture Operator", role: "Operator", status: "Active" }] })
    if (path === "/api/v1/sensors/latest") {
      const data = state.sensor
      if (state.holdSensor) await state.holdSensor()
      return route.fulfill({ headers, status: state.failSensor ? 503 : 200, json: state.failSensor ? { detail: "Unavailable" } : data }).catch(() => {})
    }
    const payload = { users: { items: [], total: 0 }, activity: { items: [], total: 0, page: 1, page_size: 100 }, scans: { items: [], total: 0, page: 1, page_size: 100 }, config: { camera_ids: "", confidence_threshold: 85, revision: 1 }, metrics: { cpu_name: "Fixture CPU", cpu_percent: 1, memory_used_gb: 1, memory_total_gb: 4, memory_percent: 25, disk_used_gb: 1, disk_total_gb: 10, disk_percent: 10, uptime: "1 hour", cpu_temp: null } }
    return route.fulfill({ headers, json: payload[path.split("/").at(-1)] ?? [] })
  })
  await page.goto(runtime.url + screen)
  return { page, state }
}

test("kiosk operator list failure shows retry and recovers without a blank chooser", async t => {
  const { page, state } = await setup(t, "/logs")
  await page.getByRole("alert").getByText(/Operator list unavailable/).waitFor()
  state.failOperators = false
  await page.getByRole("button", { name: "Retry operator list" }).click()
  await page.getByRole("dialog").getByRole("button", { name: /Fixture Operator/ }).waitFor()
})

test("missing sensor readings remain unknown and failed reads can recover", async t => {
  const { page, state } = await setup(t, "/devices", { failSensor: true })
  await page.getByRole("alert").filter({ hasText: "Sensor readings unavailable" }).waitFor()
  assert.equal(await page.getByText("0.0", { exact: true }).count(), 0)
  assert.equal(await page.getByText("Optimal", { exact: true }).count(), 0)
  await page.getByText("No readings", { exact: true }).waitFor()
  state.failSensor = false; state.sensor = { temperature: 27.5, humidity: 70 }
  await page.getByRole("button", { name: "Retry sensor readings" }).click()
  await page.getByText("27.5", { exact: false }).waitFor()
})

test("a late initial sensor read cannot overwrite a newer live measurement", async t => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const { page } = await setup(t, "/devices", { sensor: { temperature: 20, humidity: 50 }, holdSensor: () => gate })
  await page.getByText("Loading sensor readings…").waitFor()
  await page.evaluate(() => window.dashboardSocket.emit("sensor:update", { temperature: 29.5, humidity: 75 }))
  await page.getByText("29.5", { exact: false }).waitFor()
  release()
  await page.clock.runFor(50)
  assert.equal(await page.getByText("29.5", { exact: false }).isVisible(), true)
})
