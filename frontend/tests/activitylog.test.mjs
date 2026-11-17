import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "activitylog.fixture.tsx", port: 5243 }) })
after(async () => { await runtime?.close() })

const AS_OF = "2026-10-02T12:00:00.123456+08:00"
const at = minutes => new Date(Date.parse("2026-10-02T11:59:00+08:00") - minutes * 60_000).toISOString()

// Newest first, as the backend orders them. Page 1 holds the first 100 rows.
const featured = [
  { id: "a-failed", user_name: null, action: "login_failed", details: "Sign-in failed for an unrecognized username" },
  { id: "a-reset", user_name: "Admin User", action: "password_reset", details: "Password reset for user 'op1'" },
  { id: "a-export", user_name: "Admin User", action: "data_exported", details: "Exported 12 scan records as CSV" },
  { id: "a-applied", user_name: null, action: "config_applied", details: "Configuration revision 4 applied" },
  { id: "a-flag", user_name: "Operator One", action: "scan_flag", details: "Scan 7: flagged False → True" },
  { id: "a-legacy", user_name: "Admin User", action: "made_up_action", details: "Legacy stored row" },
  { id: "a-started", user_name: null, action: "system_started", details: "Station started" },
  { id: "a-denied", user_name: "Operator One", action: "access_denied", details: "GET /api/v1/users denied (403): Admin only" },
]
const fillers = Array.from({ length: 111 }, (_, index) => ({
  id: `filler-${String(index).padStart(3, "0")}`, user_name: "Filler User", action: "login", details: `Filler sign-in ${index}`,
}))
const onSecondPage = { id: "a-restore", user_name: "Admin User", action: "restore_completed", details: "Restore from backup completed" }
const original = [...featured, ...fillers, onSecondPage].map((row, index) => ({ ...row, created_at: at(index), ip_address: null }))
const arrived = { id: "a-arrived", user_name: "Admin User", action: "logout", details: "Signed out mid-load", created_at: at(-0.5), ip_address: null }

async function openActivity(t, { echoAsOf = true } = {}) {
  const context = await runtime.browser.newContext({ timezoneId: "America/New_York" })
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page)
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  const requests = []
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url())
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" }
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    if (url.pathname === "/api/v1/activity") {
      requests.push(url)
      const number = Number(url.searchParams.get("page")), size = Number(url.searchParams.get("page_size"))
      const asOf = url.searchParams.get("as_of")
      // A new row lands right after the first page; only an unpinned read can see it.
      const rows = asOf === AS_OF || requests.length === 1 ? original : [arrived, ...original]
      return route.fulfill({ headers, json: {
        items: rows.slice((number - 1) * size, number * size), total: rows.length, page: number, page_size: size,
        as_of: echoAsOf ? (asOf ?? AS_OF) : "2026-10-02T12:00:05+08:00",
      } })
    }
    const responses = {
      users: { items: [], total: 0 }, devices: [],
      config: { camera_ids: "CAM-001", confidence_threshold: 85, revision: 1 },
    }
    return route.fulfill({ headers, json: responses[url.pathname.split("/").at(-1)] ?? [] })
  })
  await page.goto(`${runtime.url}/dashboard/activity`)
  return { page, requests }
}

async function loaded(page) {
  await page.getByRole("button", { name: "Export CSV", exact: true }).waitFor()
  await page.waitForFunction(() => !document.querySelector('table [data-slot="skeleton"]'))
  await page.getByText("Sign-in failed for an unrecognized username", { exact: true }).waitFor()
}

function row(page, details) {
  return page.getByRole("row").filter({ has: page.getByText(details, { exact: true }) })
}

async function statValue(page, title) {
  const card = page.locator('[data-slot="card"]').filter({ has: page.getByText(title, { exact: true }) })
  return (await card.locator("h3").innerText()).trim()
}

test("later pages carry the first page's as_of, so rows arriving mid-load do not break the log", async t => {
  const { page, requests } = await openActivity(t)
  await loaded(page)
  assert.equal(requests.length, 2)
  assert.equal(requests[0].searchParams.get("as_of"), null)
  assert.equal(requests[1].searchParams.get("page"), "2")
  assert.equal(requests[1].searchParams.get("as_of"), AS_OF)
  assert.equal(await page.getByRole("alert").count(), 0)
  assert.equal(await page.getByText("Signed out mid-load", { exact: true }).count(), 0)
})

test("a page read at a different boundary is rejected instead of mixing snapshots", async t => {
  const { page } = await openActivity(t, { echoAsOf: false })
  await page.getByRole("alert").waitFor()
  assert.match(await page.getByRole("alert").innerText(), /could not be loaded completely/)
})

test("actions show friendly badges, actorless names and the critical count; headers are unchanged", async t => {
  const { page } = await openActivity(t)
  await loaded(page)
  assert.deepEqual(
    (await page.getByRole("columnheader").allInnerTexts()).map(text => text.trim()),
    ["Timestamp", "User", "Action", "Details", "IP Address"],
  )
  for (const [details, user, label, tone] of [
    ["Sign-in failed for an unrecognized username", "Unauthenticated", "Sign-in failed", "bg-red-50"],
    ["Password reset for user 'op1'", "Admin User", "Password reset", "bg-indigo-50"],
    ["Exported 12 scan records as CSV", "Admin User", "Data exported", "bg-cyan-50"],
    ["Configuration revision 4 applied", "System", "Configuration applied", "bg-orange-50"],
    ["Legacy stored row", "Admin User", "Made Up Action", "bg-muted"],
    ["Station started", "System", "System started", "bg-orange-50"],
  ]) {
    const line = row(page, details)
    const badge = line.locator('[data-slot="badge"]')
    assert.equal((await badge.innerText()).trim(), label, details)
    assert.ok((await badge.getAttribute("class")).split(/\s+/).includes(tone), `${details}: ${await badge.getAttribute("class")}`)
    assert.equal(await line.getByText(user, { exact: true }).count(), 1, details)
  }
  // login_failed, password_reset, data_exported, config_applied, access_denied, restore_completed (page 2).
  assert.equal(await statValue(page, "Critical Actions"), "6")

  // Search also finds the friendly label, not only the stored action name or details.
  await page.getByPlaceholder("Search activities...").fill("data exported")
  await page.waitForFunction(() => document.querySelectorAll("tbody tr").length === 1)
  assert.equal(await page.getByText("Exported 12 scan records as CSV", { exact: true }).count(), 1)
})
