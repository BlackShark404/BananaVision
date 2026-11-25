import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "clientexports.fixture.tsx", port: 5217 }) })
after(async () => { await runtime?.close() })

const longText = ('Export group: Peñafrancia, "full detail"\n' + "Unabridged value • ".repeat(15)).trim()
const timestamp = "2026-10-02T12:34:56.123456+08:00"
const readableTimestamp = "Oct 2, 2026, 12:34:56 PM"
const scanUuid = index => `deb78e${String(index).padStart(2, "0")}-0f09-4e3b-bd35-cd66690fca72`
const intakeUuid = index => `a1b2c3${String(index).padStart(2, "0")}-1111-4222-8333-444455556666`

const scans = Array.from({ length: 19 }, (_, index) => ({
  id: scanUuid(index), revision: 1,
  date_time: timestamp, operator_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  cultivar: "Lakatan", ripeness: "Ripe", confidence: index, temperature: index === 1 ? null : 26.44,
  humidity: index === 1 ? null : 72.56, spoilage_days: "3.5454545454545454", finger_count: index === 2 ? 12 : index,
  source_text: index === 1 || index === 18 ? null : longText,
  flagged: index === 0,
  is_overridden: index === 2,
  original_ai_result: index === 2 ? { cultivar: "Lakatan", ripeness: "Ripe", confidence: 2, finger_count: 10 } : null,
  inventory_status: index === 3 ? "Sold" : "In Stock",
  shelf_life_window: {
    min_days: 3, max_days: 4, elapsed_days: 0,
    remaining_min_days: 3, remaining_max_days: 4, days_past: 0,
    state: "active", scan_date: "2026-10-02", as_of_date: "2026-10-02",
  },
}))
const activities = Array.from({ length: 19 }, (_, index) => ({
  id: `activity-${index}`, created_at: timestamp, user_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  action: "login", details: index === 18 ? "Excluded" : longText, ip_address: null,
})).reverse()
const intakes = Array.from({ length: 19 }, (_, index) => ({
  id: intakeUuid(index), intake_date: "2026-10-02", status: "Active",
  batch_number: `BATCH-${String(index).padStart(2, "0")}`,
  supplier_name: index === 18 ? "Excluded" : `Export group ${String(index).padStart(2, "0")}`,
  source: index === 18 ? "Excluded" : `${longText}${String(index).padStart(2, "0")}`,
})).reverse()

async function openScreen(t, screen, fail = false, now = "2026-10-02T05:00:00Z") {
  const context = await runtime.browser.newContext({ timezoneId: "America/New_York" })
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page, { now })
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
      config: { camera_ids: "CAM-001", confidence_threshold: 80, revision: 1 },
    }
    return route.fulfill({ headers, json: responses[path.split("/").at(-1)] ?? [] })
  })
  await page.goto(`${runtime.url}/dashboard/${screen}`)
  if (fail) { await page.getByRole("alert").first().waitFor(); return page }
  await page.getByRole("button", { name: "Export Excel", exact: true }).waitFor()
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
  if (format === "xlsx") await page.getByRole("button", { name: "Export Excel", exact: true }).click()
  else {
    await page.getByRole("button", { name: "Export options", exact: true }).click()
    await page.getByRole("menuitem", { name: "Export PDF (.pdf)", exact: true }).click()
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

function decodePdfLiteral(raw) {
  const bytes = []
  for (let i = 0; i < raw.length; i++) {
    if (raw[i] === "\\" && i + 1 < raw.length) {
      const next = raw[i + 1]
      if (next === "(" || next === ")" || next === "\\") {
        bytes.push(next.charCodeAt(0))
        i++
        continue
      }
      const octal = raw.slice(i + 1, i + 4)
      if (/^[0-7]{3}$/.test(octal)) {
        bytes.push(parseInt(octal, 8))
        i += 3
        continue
      }
    }
    bytes.push(raw.charCodeAt(i))
  }
  const cp1252 = {
    0x80: "€", 0x85: "…", 0x91: "‘", 0x92: "’", 0x93: "“", 0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
  }
  return bytes.map(b => cp1252[b] ?? String.fromCharCode(b)).join("")
}

function extractPdfText(buffer) {
  const text = buffer.toString("latin1")
  assert.ok(text.startsWith("%PDF-1.4\n"), "valid PDF header")
  assert.ok(text.trimEnd().endsWith("%%EOF"), "valid PDF EOF")
  const tokens = []
  for (const match of text.matchAll(/\(((?:\\.|[^\\()])*)\)\s*Tj/g)) {
    tokens.push(decodePdfLiteral(match[1]))
  }
  return tokens.join(" ")
}

test("ExportDropdown removes CSV completely and shows only Excel and PDF options", async t => {
  const page = await openScreen(t, "quality")
  assert.equal(await page.getByRole("button", { name: /csv/i }).count(), 0)
  await page.getByRole("button", { name: "Export options", exact: true }).click()
  const items = await page.getByRole("menuitem").allInnerTexts()
  assert.deepEqual(items.map(s => s.trim()), ["Export Excel (.xlsx)", "Export PDF (.pdf)"])
})

test("Quality Control and Delivery Intakes search by exported Scan Ref and Intake Ref", async t => {
  const qualityPage = await openScreen(t, "quality")
  const qSearch = qualityPage.getByPlaceholder("Search by operator, cultivar, source, or ID...")
  for (const query of ["SCAN-DEB78E02", "scan-deb78e02", "DEB78E02", scanUuid(2)]) {
    await qSearch.fill(query)
    await qualityPage.waitForFunction(() => document.querySelectorAll("tbody tr").length === 1)
    assert.equal(await qualityPage.locator("tbody").getByText("Export group 02", { exact: true }).count(), 1, query)
  }

  const intakesPage = await openScreen(t, "intakes")
  const iSearch = intakesPage.getByPlaceholder("Search by source or intake ID...")
  for (const query of ["INT-A1B2C305", "int-a1b2c305", "A1B2C305", "BATCH-05", intakeUuid(5)]) {
    await iSearch.fill(query)
    await intakesPage.waitForFunction(() => document.querySelectorAll("tbody tr").length === 1)
    assert.equal(await intakesPage.locator("tbody").getByText("Export group 05", { exact: true }).count(), 1, query)
  }
})

for (const [screen, prefix] of [["activity", "activity-log"], ["intakes", "intakes"], ["quality", "quality-control"]]) {
  test(`${screen} export file names carry the Asia/Manila date, not the UTC or browser date`, async t => {
    // 16:30 UTC on 1 October is 00:30 on 2 October in Manila and 12:30 on 1 October in New York.
    const page = await openScreen(t, screen, false, "2026-10-01T16:30:00Z")
    for (const format of ["xlsx", "pdf"]) {
      const file = await startDownload(page, format)
      assert.equal(file.suggestedFilename(), `${prefix}-2026-10-02.${format}`)
    }
  })
}

for (const screen of ["activity", "intakes", "quality"]) {
  test(`${screen} Excel and PDF export identical human-friendly rows across all pages`, async t => {
    const page = await openScreen(t, screen)
    const xlsxBuffer = await download(page, "xlsx")
    const pdfBuffer = await download(page, "pdf")

    const { default: ExcelJS } = await import("exceljs")
    const workbook = new ExcelJS.Workbook()
    await workbook.xlsx.load(xlsxBuffer)
    const sheet = workbook.worksheets[0]
    const rows = Array.from({ length: sheet.rowCount }, (_, index) =>
      Array.from({ length: sheet.columnCount }, (_, column) => sheet.getRow(index + 1).getCell(column + 1).value ?? ""))

    const pdfText = extractPdfText(pdfBuffer)
    assert.ok(pdfText.includes("Asia/Manila"), "PDF includes Asia/Manila export timestamp")
    assert.ok(pdfText.includes("Total records: 18"), "PDF includes filtered record count")
    assert.ok(pdfText.includes("Filters:"), "PDF includes active filter summary")
    assert.equal(rows.length, 19, "header and all 18 matching records across pages")

    if (screen === "activity") {
      assert.deepEqual(rows[0], ["Date & Time", "User", "Action", "Details", "IP Address"])
      assert.deepEqual(rows[1], [readableTimestamp, "Export group 00", "Signed in", longText, ""])
      assert.equal(rows[18][1], "Export group 17")
      assert.ok(!pdfText.includes(" login "), "raw snake_case action is not shown")
      assert.ok(pdfText.includes("Signed in"))
      assert.ok(pdfText.includes(readableTimestamp))
    } else if (screen === "intakes") {
      assert.deepEqual(rows[0], ["Intake Ref", "Date", "Supplier / Source", "Batch / PO", "Items Scanned", "Intake Status", "Inventory Status"])
      assert.deepEqual(rows[1], ["INT-A1B2C300", "Oct 2, 2026", "Export group 00", "BATCH-00", 0, "Active", "In Stock"])
      assert.equal(rows[18][0], "INT-A1B2C317")
      assert.equal(rows[18][2], "Export group 17")
      assert.ok(!pdfText.includes(intakeUuid(0)), "raw 36-char intake UUID excluded")
      assert.ok(pdfText.includes("INT-A1B2C300") && pdfText.includes("INT-A1B2C317") && pdfText.includes("Oct 2, 2026") && pdfText.includes("BATCH-00"))
    } else {
      assert.deepEqual(rows[0], [
        "Scan Ref", "Date & Time", "Source / Supplier", "Cultivar", "Ripeness", "Est. Fingers",
        "Est. Shelf Life (Original)", "Est. Time Left / Freshness", "Inventory Status",
        "Review Status", "Confidence (%)", "Temperature (°C)", "Humidity (%)", "Operator",
      ])
      // Row 0: Scan Ref first, readable timestamp with seconds, numeric Confidence/Temp/Humidity.
      assert.deepEqual(rows[1], [
        "SCAN-DEB78E00", readableTimestamp, longText, "Lakatan", "Ripe", "Est. 0 fingers",
        "3–4 days", "3–4 days left", "In Stock", "Needs Review", 0, 26.4, 72.6, "Export group 00",
      ])
      assert.equal(sheet.getRow(2).getCell(11).numFmt, "0.0")
      assert.equal(sheet.getRow(2).getCell(12).numFmt, "0.0")
      assert.equal(sheet.getRow(2).getCell(13).numFmt, "0.0")
      // Row 1: missing optional temp/humidity/source stay blank.
      assert.equal(rows[2][0], "SCAN-DEB78E01")
      assert.equal(rows[2][2], "")
      assert.equal(rows[2][11], "")
      assert.equal(rows[2][12], "")
      // Row 2: human-corrected finger count drops "Est." prefix.
      assert.equal(rows[3][0], "SCAN-DEB78E02")
      assert.equal(rows[3][5], "12 fingers")
      assert.equal(rows[3][9], "Approved")
      // Row 3: closed stock shows outcome ("Sold") instead of countdown.
      assert.equal(rows[4][7], "Sold")
      assert.equal(rows[4][8], "Sold")
      assert.equal(rows[18][0], "SCAN-DEB78E17")
      assert.equal(rows[18][13], "Export group 17")
      // PDF parity: short Scan Ref included, raw UUID and 15-digit float excluded, formatted values match.
      assert.ok(!pdfText.includes(scanUuid(0)))
      assert.ok(!pdfText.includes("3.545454"))
      for (const token of ["SCAN-DEB78E00", "SCAN-DEB78E17", readableTimestamp, "Est. 0 fingers", "12 fingers", "3–4 days", "3–4 days left", "Needs Review", "Approved", "26.4", "72.6", "Export group 17"]) {
        assert.ok(pdfText.includes(token), `expected PDF to include ${token}`)
      }
    }
  })

  test(`${screen} blocks downloads when required data is unavailable`, async t => {
    const page = await openScreen(t, screen, true)
    assert.equal(await page.getByRole("button", { name: "Export Excel", exact: true }).isDisabled(), true)
    assert.equal(await page.getByRole("button", { name: "Export options", exact: true }).isDisabled(), true)
  })
}
