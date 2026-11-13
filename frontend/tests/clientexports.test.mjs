import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "clientexports.fixture.tsx", port: 5217 }) })
after(async () => { await runtime?.close() })

const longText = 'Export group: Peñafrancia, "full detail"\n' + "Unabridged value • ".repeat(30)
const timestamp = "2026-10-02T12:34:56.123456+08:00"
const scans = Array.from({ length: 19 }, (_, index) => ({
  id: `full-scan-identifier-${String(index).padStart(2, "0")}`, revision: 1,
  date_time: timestamp, operator_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  cultivar: "Lakatan", ripeness: "Ripe", confidence: index, temperature: index === 1 ? null : 0,
  humidity: index === 1 ? null : 0, spoilage_days: "3.5454545454545454", finger_count: index,
  source_text: index === 1 || index === 18 ? null : longText, flagged: false, inventory_status: "In Stock",
}))
const activities = Array.from({ length: 19 }, (_, index) => ({
  id: `activity-${index}`, created_at: timestamp, user_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  action: "login", details: index === 18 ? "Excluded" : longText, ip_address: null,
})).reverse()
const intakes = Array.from({ length: 19 }, (_, index) => ({
  id: `full-intake-identifier-${String(index).padStart(2, "0")}`, intake_date: "2026-10-02", status: "Active",
  supplier_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  source: index === 18 ? "Excluded" : `${longText}${String(index).padStart(2, "0")}`,
})).reverse()

async function openScreen(t, screen, fail = false, now) {
  const context = await runtime.browser.newContext({ timezoneId: "America/New_York" })
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page, now ? { now } : {})
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" }
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    if (fail && path.endsWith(screen === "quality" ? "/scans" : `/${screen}`)) {
      return route.fulfill({ status: 503, headers, json: { detail: "Fixture unavailable" } })
    }
    const responses = {
      activity: { items: activities, total: activities.length, page: 1, page_size: 100 },
      scans: { items: scans, total: scans.length, page: 1, page_size: 100 },
      intakes, users: { items: [], total: 0 }, devices: [], suppliers: [],
      config: { camera_ids: "CAM-001", confidence_threshold: 85, revision: 1 },
    }
    return route.fulfill({ headers, json: responses[path.split("/").at(-1)] ?? [] })
  })
  await page.goto(`${runtime.url}/dashboard/${screen}`)
  if (fail) { await page.getByRole("alert").first().waitFor(); return page }
  await page.getByRole("button", { name: "Export CSV", exact: true }).waitFor()
  await page.waitForFunction(() => !document.querySelector('table [data-slot="skeleton"]'))
  await page.getByPlaceholder(
    screen === "activity"
      ? "Search activities..."
      : screen === "intakes" ? "Search by source or intake ID..." : "Search by operator, cultivar, source, or ID...",
  ).fill("Export group")
  await page.getByRole("columnheader", { name: screen === "activity" ? "User" : screen === "intakes" ? "Supplier" : "Confidence", exact: true }).click()
  await page.locator('button[title="Last page"]').click()
  return page
}

async function startDownload(page, format) {
  const pending = page.waitForEvent("download")
  if (format === "csv") await page.getByRole("button", { name: "Export CSV", exact: true }).click()
  else {
    await page.getByRole("button", { name: "Export options", exact: true }).click()
    await page.getByRole("menuitem", { name: /Excel/ }).click()
  }
  return pending
}

async function download(page, format) {
  const file = await startDownload(page, format)
  const chunks = []
  for await (const chunk of await file.createReadStream()) chunks.push(chunk)
  assert.ok(file.suggestedFilename().endsWith(`.${format}`))
  return Buffer.concat(chunks)
}

function parseCsv(buffer) {
  const text = buffer.toString("utf8").replace(/^\uFEFF/, "")
  const rows = [], row = []
  let value = "", quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { value += '"'; i++ }
      else quoted = !quoted
    } else if (!quoted && (char === "," || char === "\n")) {
      row.push(value.replace(/\r$/, "")); value = ""
      if (char === "\n") { rows.push(row.splice(0)) }
    } else value += char
  }
  if (value || row.length) { row.push(value); rows.push(row) }
  return rows
}

for (const [screen, prefix] of [["activity", "activity-log"], ["intakes", "intakes"], ["quality", "quality-control"]]) {
  test(`${screen} export file names carry the Asia/Manila date, not the UTC or browser date`, async t => {
    // 16:30 UTC on 1 October is 00:30 on 2 October in Manila and 12:30 on 1 October in New York.
    const page = await openScreen(t, screen, false, "2026-10-01T16:30:00Z")
    for (const format of ["csv", "xlsx"]) {
      const file = await startDownload(page, format)
      assert.equal(file.suggestedFilename(), `${prefix}-2026-10-02.${format}`)
    }
  })
}

for (const screen of ["activity", "intakes", "quality"]) {
  for (const format of ["csv", "xlsx"]) {
    test(`${screen} ${format} exports complete filtered sorted rows and exact values from any page`, async t => {
      const page = await openScreen(t, screen)
      const buffer = await download(page, format)
      let rows
      if (format === "csv") {
        assert.deepEqual([...buffer.subarray(0, 3)], [239, 187, 191])
        rows = parseCsv(buffer)
      } else {
        const { default: ExcelJS } = await import("exceljs")
        const workbook = new ExcelJS.Workbook()
        await workbook.xlsx.load(buffer)
        const sheet = workbook.worksheets[0]
        rows = Array.from({ length: sheet.rowCount }, (_, index) =>
          Array.from({ length: sheet.columnCount }, (_, column) => sheet.getRow(index + 1).getCell(column + 1).value ?? ""))
      }
      assert.equal(rows.length, 19, "header and all 18 matching records across pages")
      if (screen === "activity") {
        assert.deepEqual(rows[1], [timestamp, "Export group 00", "login", longText, ""])
        assert.equal(rows[18][1], "Export group 17")
      } else if (screen === "intakes") {
        assert.deepEqual(rows[1], ["full-intake-identifier-00", `${longText}00`, "2026-10-02", format === "csv" ? "0" : 0, "Active"])
        assert.equal(rows[18][0], "full-intake-identifier-17")
      } else {
        assert.deepEqual(rows[1], ["full-scan-identifier-00", timestamp, "Export group 00", "Lakatan", "Ripe",
          ...(format === "csv" ? ["0", "0", "0"] : [0, 0, 0]), "3.5454545454545454", format === "csv" ? "0" : 0,
          longText, "No", "Review"])
        assert.equal(rows[2][6], "")
        assert.equal(rows[2][7], "")
        assert.equal(rows[2][10], "")
        assert.equal(rows[18][0], "full-scan-identifier-17")
      }
    })
  }
  test(`${screen} blocks downloads when required data is unavailable`, async t => {
    const page = await openScreen(t, screen, true)
    assert.equal(await page.getByRole("button", { name: "Export CSV", exact: true }).isDisabled(), true)
    assert.equal(await page.getByRole("button", { name: "Export options", exact: true }).isDisabled(), true)
  })
}
