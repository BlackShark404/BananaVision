import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "assigned.fixture.tsx", auth: "assigned.auth.tsx", port: 5193 }) })
after(async () => { await runtime?.close() })

async function setup(t, screen, role = "Admin") {
  const context = await runtime.browser.newContext({ viewport: { width: 1280, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  const errors = [], requests = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  const user = { id: "owner", username: "owner", fullName: "Same Name", role }
  await page.addInitScript(({ user, screen }) => {
    if (screen !== "auth") {
      localStorage.setItem("bananavision_user", JSON.stringify(user))
      localStorage.setItem("bananavision_token", "access")
    }
  }, { user, screen })
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    const body = request.postDataJSON()
    requests.push({ path, method: request.method(), body })
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
    const reply = (json, status = 200) => route.fulfill({ headers, json, status })
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 })
    if (path === "/api/v1/auth/login") return reply({ status: "requires_password_change", reason: "new_account", setup_token: "password-proof" })
    if (path === "/api/v1/auth/swap") return reply({ status: "requires_pin_change", reason: "pin_reset", setup_token: "pin-proof" })
    if (path.startsWith("/api/v1/auth/setup-")) return reply({ status: "success", token: { access_token: "new-access" }, user: { id: "owner", username: "owner", full_name: "Same Name", role } })
    if (path === "/api/v1/users" && request.method() === "POST") return reply({ id: "created", username: body.username, full_name: body.full_name, role: body.role, status: body.status, temporary_password: "generated-private-password", temporary_pin: "9087" }, 201)
    if (path === "/api/v1/users") return reply({ items: [{ id: "owner", username: "owner", full_name: "Same Name", role, status: "Active" }], total: 1 })
    if (path === "/api/v1/users/me/summary") return reply({ total_scans: 131, avg_confidence: 82.3, last_7_days: 130, total_users: role === "Admin" ? 9 : null, activity: [{ id: "log", action: "login", details: "Own activity", timestamp: "2026-10-05T10:00:00+08:00" }] })
    if (path === "/api/v1/activity") return reply({ items: [], total: 0, page: 1, page_size: 100 })
    if (path === "/api/v1/config") return reply({ camera_ids: "CAM-001", confidence_threshold: 85, data_retention_enabled: true })
    if (path === "/api/v1/devices") return reply([])
    return reply({ detail: "Unexpected fixture request" }, 404)
  })
  await page.goto(`${runtime.url}/dashboard?screen=${screen}`)
  return { page, requests }
}

test("account creation shows unique credentials once and excludes them from browser storage", async t => {
  const { page, requests } = await setup(t, "users")
  await page.getByRole("button", { name: "Add User", exact: true }).click()
  await page.getByLabel("Full Name", { exact: true }).fill("New Owner")
  await page.getByLabel("Username", { exact: true }).fill("new-owner")
  await page.getByRole("button", { name: "Create User", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByText("generated-private-password", { exact: true }).waitFor()
  assert.equal(await dialog.getByText("9087", { exact: true }).count(), 1)
  const create = requests.find(r => r.path === "/api/v1/users" && r.method === "POST")
  assert.equal(create.body.password, undefined)
  assert.equal(create.body.pin, undefined)
  assert.ok(!(await page.evaluate(() => JSON.stringify(localStorage))).includes("generated-private-password"))
  await dialog.getByRole("button", { name: "Done" }).click()
  assert.equal(await page.getByText("generated-private-password", { exact: true }).count(), 0)
})

test("operator profile uses full backend totals without requesting admin-only resources", async t => {
  const { page, requests } = await setup(t, "profile", "Operator")
  await page.getByText("131", { exact: true }).waitFor()
  await page.getByText("82.3%", { exact: true }).waitFor()
  assert.equal(await page.getByText("Average model confidence on your scans", { exact: true }).count(), 1)
  assert.ok(requests.some(r => r.path === "/api/v1/users/me/summary"))
  assert.ok(!requests.some(r => ["/api/v1/users", "/api/v1/activity", "/api/v1/scans"].includes(r.path)))
})

test("password and PIN setup carry limited proofs and do not persist setup tokens", async t => {
  const { page, requests } = await setup(t, "auth")
  await page.getByRole("button", { name: "Set password", exact: true }).click()
  await page.getByText("false", { exact: true }).waitFor()
  assert.ok(!requests.some(r => r.path === "/api/v1/auth/setup-password"))
  await page.getByRole("button", { name: "Authenticate password" }).click()
  await page.getByText("requires_password_change_new_account", { exact: true }).waitFor()
  assert.equal(await page.evaluate(() => localStorage.getItem("bananavision_token")), null)
  await page.getByRole("button", { name: "Set password", exact: true }).click()
  await page.getByText("true", { exact: true }).waitFor()
  assert.deepEqual(requests.find(r => r.path === "/api/v1/auth/setup-password").body, { setup_token: "password-proof", new_password: "replacement-password" })
  await page.getByRole("button", { name: "Authenticate PIN" }).click()
  await page.getByText("requires_pin_change_reset", { exact: true }).waitFor()
  await page.getByRole("button", { name: "Set PIN", exact: true }).click()
  await page.getByText("true", { exact: true }).waitFor()
  assert.deepEqual(requests.find(r => r.path === "/api/v1/auth/setup-pin").body, { setup_token: "pin-proof", new_pin: "2468" })
  assert.ok(!(await page.evaluate(() => JSON.stringify(localStorage))).includes("-proof"))
})
