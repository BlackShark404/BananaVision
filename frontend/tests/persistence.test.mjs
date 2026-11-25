import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { readFile } from "node:fs/promises"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "persistence.fixture.tsx", auth: "persistence.auth.tsx", port: 5191 }) })
after(async () => { await runtime?.close() })

const storedDate = index => new Date(Date.parse("2024-05-05T08:10:00Z") - index * 86_400_000).toISOString().replace("Z", "+08:00")
const rows = (count = 205) => Array.from({ length: count }, (_, index) => ({
  id: `scan-${index}`, revision: 1, date_time: storedDate(index), cultivar: "Lakatan", ripeness: "Ripe", confidence: 92,
  spoilage_days: "2", finger_count: 7, operator_name: "Test Admin", source_text: index === count - 1 ? "Oldest source" : "Recent source",
  inventory_status: "In Stock", intake_id: index === count - 1 ? "intake-2" : "intake-1", flagged: false, has_notes: false,
  inventory_eligible: true, intake_provenance: "linked", remaining_days: 2, risk_as_of: "2026-10-02T12:00:00+08:00",
}))
const snapshot = page => page.getByTestId("state").textContent().then(JSON.parse)
async function until(predicate, message = "Condition was not met") {
  const deadline = Date.now() + 10000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  assert.fail(message)
}

async function setup(t, options = {}) {
  const context = await runtime.browser.newContext({ timezoneId: "America/Los_Angeles", viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.setDefaultNavigationTimeout(30000)
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, [], "No uncaught browser errors") })
  await installEnvironment(page)
  const state = {
    scans: rows(options.count), requests: [], failPage: 0, failWrites: true, holdWrite: null, pageOverride: null,
    users: [{ id: "admin-1", username: "admin", full_name: "Test Admin", role: "Admin", status: "Active", last_active: storedDate(0) }],
    config: { camera_ids: "CAM-001", camera_device_ids: [0], confidence_threshold: 85, data_retention_enabled: true, revision: 1, application_status: "applied" },
    suppliers: [{ id: "supplier-1", name: "Original supplier", status: "Active", date_added: storedDate(0) }],
    intakes: [1, 2].map(id => ({ id: `intake-${id}`, supplier_id: "supplier-1", supplier_name: "Original supplier", batch_number: `batch-${id}`, intake_date: storedDate(id), status: "Active", scan_count: 1 })),
    ...options,
  }
  await page.route("**/api/v1/**", async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers })
    state.requests.push({ path: url.pathname, params: Object.fromEntries(url.searchParams), method, body: request.postDataJSON() })
    const reply = (json, status = 200) => route.fulfill({ json, status, headers }).catch(() => {})
    if (method !== "GET") {
      if (state.holdWrite) await state.holdWrite()
      if (state.failWrites) return reply({ detail: "Database write rejected" }, 503)
      const body = request.postDataJSON()
      if (url.pathname === "/api/v1/suppliers") {
        const supplier = { id: "supplier-new", ...body, date_added: storedDate(0), updated_at: storedDate(0) }
        state.suppliers.push(supplier)
        return reply(supplier, 201)
      }
      if (url.pathname === "/api/v1/intakes") {
        const intake = {
          id: "intake-new", supplier_id: body.supplier_id, supplier_name: "Original supplier",
          source: body.source ?? "Kiosk", batch_number: body.batch_number,
          intake_date: storedDate(0), status: "Active", scan_count: 0,
        }
        state.intakes.unshift(intake)
        return reply(intake)
      }
      if (url.pathname === "/api/v1/suppliers/supplier-1") {
        state.suppliers[0] = { ...state.suppliers[0], ...body, name: "Canonical supplier" }
        return reply(state.suppliers[0])
      }
      if (url.pathname === "/api/v1/scans/scan-0/notes") return reply({ id: "note-1", scan_id: "scan-0", text: body.note, author_name: "Test Admin", timestamp: storedDate(0), revision: ++state.scans[0].revision })
      if (url.pathname === "/api/v1/scans/scan-0/flag") { state.scans[0].flagged = body.flagged; state.scans[0].revision++; return reply(state.scans[0]) }
      if (url.pathname === "/api/v1/intakes/intake-1/bulk-inventory") {
        state.scans[0].inventory_status = body.inventory_status
        return reply({ revisions: { "scan-0": ++state.scans[0].revision }, updated_scan_ids: ["scan-0"], updated_count: 1, status_updated_at: storedDate(0), intake_status: "Depleted" })
      }
      return reply({ detail: `Unexpected successful test write: ${url.pathname}` }, 400)
    }
    if (url.pathname === "/api/v1/scans") {
      const requestedPage = Number(url.searchParams.get("page"))
      const pageSize = Number(url.searchParams.get("page_size")) || 20
      if (requestedPage === state.failPage) return reply({ detail: "History page unavailable" }, 503)
      const payload = { items: state.scans.slice((requestedPage - 1) * pageSize, requestedPage * pageSize), page: requestedPage, page_size: pageSize, total: state.scans.length }
      return reply(state.pageOverride?.(payload) ?? payload)
    }
    if (url.pathname === "/api/v1/activity") {
      const requestedPage = Number(url.searchParams.get("page"))
      const pageSize = Number(url.searchParams.get("page_size")) || 20
      const activity = state.scans.map((scan, index) => ({ id: `activity-${scan.id}`, created_at: storedDate(index), user_name: "Test Admin", action: "scan_created", details: scan.id }))
      return reply({ items: activity.slice((requestedPage - 1) * pageSize, requestedPage * pageSize), page: requestedPage, page_size: pageSize, total: activity.length })
    }
    if (url.pathname === "/api/v1/users") return reply({ items: state.users, total: state.users.length })
    if (url.pathname === "/api/v1/config") return reply(state.config)
    if (url.pathname === "/api/v1/devices") return reply([])
    if (url.pathname === "/api/v1/suppliers") return reply(state.suppliers)
    if (url.pathname === "/api/v1/intakes") {
      const payload = structuredClone(state.intakes)
      if (state.holdIntakes) await state.holdIntakes()
      return state.failIntakes ? reply({ detail: "Intakes unavailable" }, 503) : reply(payload)
    }
    if (url.pathname === "/api/v1/scans/scan-0") return reply({ ...state.scans[0], notes: [] })
    if (url.pathname.endsWith("/notes")) return reply([])
    return reply({ detail: `Unexpected test read: ${url.pathname}` }, 404)
  })
  await page.goto(`${runtime.url}/dashboard${options.screen ? `?screen=${options.screen}` : ""}`, { waitUntil: "domcontentloaded" })
  await until(async () => {
    if (!await page.getByTestId("state").count()) return false
    const current = await snapshot(page)
    return !current.loading && !current.activityLoading && !current.intakesLoading && current.users.length > 0 && current.suppliers.length > 0 && (current.activeIntake || state.failIntakes || state.intakes.length === 0)
  }, "Providers did not finish initial loading")
  return { page, state }
}

test("shared scan and activity lists retrieve every page and preserve backend historical timestamps", async t => {
  const { page, state } = await setup(t)
  const current = await snapshot(page)
  assert.equal(current.scans.length, 205)
  assert.equal(current.activity.length, 205)
  assert.equal(current.error, null)
  assert.equal(current.activityError, null)
  assert.deepEqual(current.scans.map(scan => scan.dateTime), state.scans.map(scan => scan.date_time))
  assert.equal(current.activity[204].timestamp, storedDate(204))
  assert.equal([...current.scans].sort((a, b) => Date.parse(a.dateTime) - Date.parse(b.dateTime))[0].id, "scan-204")
  for (const path of ["/api/v1/scans", "/api/v1/activity"]) {
    const requests = state.requests.filter(request => request.path === path)
    assert.deepEqual(requests.map(request => request.params.page), ["1", "2", "3"])
    assert(requests.every(request => request.params.page_size === "100" && !("per_page" in request.params)))
  }
})

test("initial intake failure is unavailable and retry recovers instead of reporting zero", async t => {
  const { page, state } = await setup(t, { screen: "inventory", count: 1, failIntakes: true })
  await page.getByRole("alert").filter({ hasText: "Intake data is unavailable" }).waitFor()
  assert.equal(await page.getByText("Total Hands", { exact: true }).count(), 0)
  state.failIntakes = false
  await page.getByRole("button", { name: "Retry", exact: true }).click()
  await page.getByText("Total Hands", { exact: true }).waitFor()
  assert.equal((await snapshot(page)).intakesError, null)
})

test("failed intake refresh explicitly labels the retained stock snapshot stale", async t => {
  const { page, state } = await setup(t, { screen: "inventory", count: 1 })
  state.failIntakes = true
  await page.evaluate(() => { history.pushState({}, '', '/logs?screen=inventory'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await until(async () => Boolean((await snapshot(page)).intakesError))
  await page.getByRole("alert").filter({ hasText: /stale/i }).waitFor()
  assert.equal((await snapshot(page)).intakesStale, true)
  assert.equal(await page.getByText("Total Hands", { exact: true }).count(), 1)
  state.failIntakes = false
  await page.getByRole("button", { name: /Retry intake/i }).click()
  await until(async () => !(await snapshot(page)).intakesStale)
  assert.equal(await page.getByRole("alert").count(), 0)
})

test("a failed later history page never publishes a partial successful history", async t => {
  const { page } = await setup(t, { failPage: 2 })
  const current = await snapshot(page)
  assert.deepEqual(current.scans, [])
  assert.match(current.error, /unavailable/i)
})

test("empty intake snapshot remains visible and labelled stale on refresh failure", async t => {
  const { page, state } = await setup(t, { screen: "inventory", count: 0, intakes: [] })
  state.failIntakes = true
  await page.evaluate(() => { history.pushState({}, '', '/logs?screen=inventory'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await until(async () => Boolean((await snapshot(page)).intakesError))
  await page.getByRole("alert").filter({ hasText: /stale/i }).waitFor()
  assert.equal(await page.getByText("Total Hands", { exact: true }).count(), 1)
})

test("inventory uses authoritative eligibility and aged remaining life including unlinked stock", async t => {
  const records = rows(5).map((row, index) => ({ ...row, intake_id: null,
    intake_provenance: index === 4 ? "unverified" : "unlinked", inventory_eligible: index !== 4,
    remaining_days: [1.25, -2, null, null, 1][index], spoilage_days: ["8-10", "5", "Unknown", "bad", "1"][index],
    source_text: ["Aged standalone", "Expired standalone", "Unknown standalone", "Invalid standalone", "Ambiguous legacy"][index],
    risk_as_of: new Date().toISOString(),
  }))
  const { page } = await setup(t, { screen: "inventory", scans: records })
  await page.getByText("Aged standalone — Lakatan", { exact: true }).waitFor()
  await page.getByText("Expired standalone — Lakatan", { exact: true }).waitFor()
  assert.equal(await page.getByText("Ambiguous legacy — Lakatan", { exact: true }).count(), 0)
  await page.getByText(/2 hands have unknown remaining shelf life/).waitFor()
  assert.equal(await page.getByText("All stock is fresh", { exact: true }).count(), 0)
  await page.getByText("Est. Overdue", { exact: true }).first().waitFor()
  await page.getByText("Est. 1–2 days left", { exact: true }).first().waitFor()
  // Finger totals are AI estimates and say so; the hand counts are record counts.
  await page.getByText("Est. Total Fingers", { exact: true }).waitFor()
  await page.getByText(/^1 hands \(Est\. 7 fingers\)$/).first().waitFor()
  await page.getByText(/^Est\. \d+ fingers • /).first().waitFor()
  // Only non-zero totals are estimates; an empty ripeness group is an exact zero.
  assert.equal(await page.getByText(/(^|[^.] )[1-9]\d* fingers/).count(), 0)
  await page.getByText("0 fingers • Store in controlled temperature", { exact: true }).waitFor()
  // Scope to the rendered product; the fixture's provider probe retains raw state.
  assert.doesNotMatch(await page.locator('main').innerText(), /1\.25/)
})

test("inventory finger totals drop Est. only when every counted scan was corrected by a person", async t => {
  const corrected = rows(1).map(row => ({ ...row, intake_id: null, intake_provenance: "unlinked",
    inventory_eligible: true, finger_count: 9, is_overridden: true, remaining_days: 1.5,
    risk_as_of: new Date().toISOString(), source_text: "Counted standalone",
    original_ai_result: { cultivar: row.cultivar, ripeness: row.ripeness, confidence: 90, finger_count: 7, spoilage_days: "2" } }))
  const { page } = await setup(t, { screen: "inventory", scans: corrected })
  await page.getByText("Total Fingers", { exact: true }).waitFor()
  assert.equal(await page.getByText("Est. Total Fingers", { exact: true }).count(), 0)
  await page.getByText(/^1 hands \(9 fingers\)$/).first().waitFor()
  // The shelf-life badge is still a heuristic estimate.
  await page.getByText(/^Est\. /).first().waitFor()
})

test("late intake read cannot undo a confirmed bulk update", async t => {
  const { page, state } = await setup(t, { count: 2, failWrites: false })
  let release
  state.holdIntakes = () => new Promise(resolve => { release = resolve })
  await page.evaluate(() => { history.pushState({}, '', '/logs'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await until(() => Boolean(release))
  await page.getByRole("button", { name: "bulk", exact: true }).click()
  await until(async () => (await snapshot(page)).activeIntake.status === "Depleted")
  state.holdIntakes = null
  release()
  await page.waitForTimeout(150)
  assert.equal((await snapshot(page)).intakes.find(i => i.id === "intake-1").status, "Depleted")
  assert.equal((await snapshot(page)).intakesLoading, false)
})

test("failed refresh retains the previous complete snapshot with an error", async t => {
  const { page, state } = await setup(t)
  const original = (await snapshot(page)).scans
  state.scans = rows(210)
  state.failPage = 2
  await page.getByRole("button", { name: "refresh", exact: true }).click()
  await until(async () => Boolean((await snapshot(page)).error))
  assert.deepEqual((await snapshot(page)).scans, original)
})

test("duplicate or shortened final pages are rejected instead of claiming a complete history", async t => {
  for (const mode of ["duplicate", "short"]) {
    const { page } = await setup(t, { pageOverride: payload => payload.page === 3 ? {
      ...payload, items: mode === "duplicate" ? rows(5) : payload.items.slice(1),
    } : payload })
    assert.deepEqual((await snapshot(page)).scans, [])
    assert.match((await snapshot(page)).error, /incomplete/i)
  }
})

test("missing historical timestamp causes an error, never a current-time replacement", async t => {
  const records = rows(2)
  delete records[1].date_time
  const { page } = await setup(t, { scans: records })
  assert.deepEqual((await snapshot(page)).scans, [])
  assert.match((await snapshot(page)).error, /timestamp.*missing or invalid/i)
})

test("every rejected provider write preserves persisted local state and rejects its caller", async t => {
  const { page } = await setup(t, { count: 2 })
  const beforeWrite = await snapshot(page)
  for (const operation of ["flag", "note", "override", "supplierAdd", "supplierUpdate", "supplierStatus", "userAdd", "userUpdate", "password", "pin", "config", "intake", "bulk"]) {
    await page.getByRole("button", { name: operation, exact: true }).click()
    await until(async () => (await page.getByTestId("operation-result").textContent()).startsWith("error:"), operation)
    assert.match(await page.getByTestId("operation-result").textContent(), /^error: Database write rejected/)
    assert.deepEqual(await snapshot(page), beforeWrite, `${operation} must not mutate state after a failed write`)
  }
})

test("pending writes wait for server confirmation and then use server-canonical values", async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { page, state } = await setup(t, { count: 2, failWrites: false, holdWrite: () => pending })
  await page.getByRole("button", { name: "supplierUpdate", exact: true }).click()
  await until(() => state.requests.some(request => request.method === "PATCH"))
  assert.equal(await page.getByTestId("operation-result").textContent(), "pending")
  assert.equal((await snapshot(page)).suppliers[0].name, "Original supplier")
  release()
  await until(async () => (await page.getByTestId("operation-result").textContent()) === "success")
  assert.equal((await snapshot(page)).suppliers[0].name, "Canonical supplier")
  await page.getByRole("button", { name: "note", exact: true }).click()
  await until(async () => (await snapshot(page)).notes.length === 1)
  assert.equal((await snapshot(page)).notes[0].timestamp, storedDate(0))
  await page.getByRole("button", { name: "bulk", exact: true }).click()
  await until(async () => (await snapshot(page)).activeIntake.status === "Depleted")
  const current = await snapshot(page)
  assert.equal(current.scans[0].inventoryStatus, "Sold")
  assert.equal(current.scans[1].inventoryStatus, "In Stock", "Only IDs confirmed by the bulk response change")
})

test("Quality Control shows write failures without success toasts or discarding note text", async t => {
  const { page, state } = await setup(t, { count: 2, screen: "quality" })
  await page.locator("tbody tr").first().click()
  const dialog = page.getByRole("dialog")
  await dialog.waitFor()
  await dialog.getByRole("button", { name: /flag/i }).click()
  await until(() => state.requests.some(request => request.method === "PATCH"))
  await page.clock.runFor(200)
  await dialog.getByRole('alert').waitFor()
  assert.ok((await dialog.getByRole('alert').innerText()).trim().length > 0)
  assert.equal((await snapshot(page)).scans[0].flagged, false)
  const note = dialog.getByPlaceholder(/note/i)
  await note.fill("Do not lose this pending review note")
  await dialog.getByRole("button", { name: "Add", exact: true }).click()
  await until(async () => await dialog.getByRole("button", { name: "Add", exact: true }).isEnabled())
  assert.equal(await note.inputValue(), "Do not lose this pending review note")
  assert.deepEqual((await snapshot(page)).notes, [])
  assert.equal(await page.locator('[data-sonner-toast][data-type="success"]').count(), 0)
})

test("Quality Control export includes complete history with readable Asia/Manila timestamps", async t => {
  const { page } = await setup(t, { screen: "quality" })
  const downloadPromise = page.waitForEvent("download")
  await page.getByRole("button", { name: /export excel/i }).click()
  const download = await downloadPromise
  const { default: ExcelJS } = await import("exceljs")
  const workbook = new ExcelJS.Workbook()
  await workbook.xlsx.load(await readFile(await download.path()))
  const sheet = workbook.worksheets[0]
  assert.equal(sheet.rowCount, 206)
  assert.equal(sheet.getRow(206).getCell(1).value, "SCAN-SCAN204")
  assert.equal(sheet.getRow(206).getCell(2).value, "Oct 14, 2023, 8:10:00 AM")
  assert.equal(sheet.getRow(206).getCell(3).value, "Oldest source")
})

test("Quality Control disables export after incomplete history retrieval", async t => {
  const { page } = await setup(t, { screen: "quality", failPage: 2 })
  assert.equal(await page.getByRole("button", { name: /export excel/i }).isDisabled(), true)
  await page.getByRole("alert").filter({ hasText: /History page unavailable/ }).waitFor()
})

test("a supplier live event that arrives before its create response does not duplicate the row", async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { page, state } = await setup(t, { failWrites: false, holdWrite: () => pending })
  await page.getByRole("button", { name: "supplierAdd", exact: true }).click()
  await until(() => state.requests.some(request => request.method === "POST" && request.path === "/api/v1/suppliers"))
  await page.evaluate(() => window.dashboardSocket.emit("supplier:changed", {
    event_id: "supplier-event-1", supplier_id: "supplier-new", kind: "created",
    supplier: { id: "supplier-new", name: "New supplier", status: "Active", date_added: "2024-05-05T08:10:00+08:00", updated_at: "2024-05-05T08:10:00+08:00" },
  }))
  await until(async () => (await snapshot(page)).suppliers.some(supplier => supplier.id === "supplier-new"), "Live supplier event was not applied")
  release()
  await until(async () => (await page.getByTestId("operation-result").textContent()) === "success")
  const created = (await snapshot(page)).suppliers.filter(supplier => supplier.id === "supplier-new")
  assert.equal(created.length, 1, "The create response must merge into the live row, not append a copy")
  assert.equal(created[0].name, "New supplier")
})

test("an intake live event that arrives before its create response does not duplicate the row", async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { page, state } = await setup(t, { failWrites: false, holdWrite: () => pending })
  await page.getByRole("button", { name: "intake", exact: true }).click()
  await until(() => state.requests.some(request => request.method === "POST" && request.path === "/api/v1/intakes"))
  await page.evaluate(() => window.dashboardSocket.emit("intake:changed", {
    event_id: "intake-event-1", intake_id: "intake-new", kind: "created", status: "Active",
    intake: { id: "intake-new", supplier_id: "supplier-1", supplier_name: "Original supplier", source: "Kiosk", batch_number: "new-batch", intake_date: "2024-05-05T08:10:00+08:00", status: "Active", scan_count: 0 },
  }))
  await until(async () => (await snapshot(page)).intakes.some(intake => intake.id === "intake-new"), "Live intake event was not applied")
  release()
  await until(async () => (await page.getByTestId("operation-result").textContent()) === "success")
  const current = await snapshot(page)
  assert.equal(current.intakes.filter(intake => intake.id === "intake-new").length, 1, "The create response must merge into the live row, not prepend a copy")
  assert.equal(current.activeIntake.id, "intake-new")
})
