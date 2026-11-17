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
  page.setDefaultNavigationTimeout(45000)
  const errors = [], requests = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  const user = { id: "owner", username: "owner", fullName: "Same Name", role }
  await page.addInitScript(({ user, screen }) => {
    if (screen !== "auth" && location.pathname !== "/login") {
      localStorage.setItem("bananavision_user", JSON.stringify(user))
      localStorage.setItem("bananavision_token", "access")
    }
    if (screen === "socket") {
      window.fixtureSockets = []
      const NativeWebSocket = window.WebSocket
      window.WebSocket = class {
        constructor(url, protocols) {
          if (!url.includes("/api/v1/ws")) return new NativeWebSocket(url, protocols)
          this.url = url
          window.fixtureSockets.push(this)
          queueMicrotask(() => this.onopen?.({}))
        }
        close(code = 1000) { this.onclose?.({ code }) }
      }
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
    if (path === "/api/v1/users/me/summary") return reply({ total_scans: 131, avg_confidence: 82.3, last_7_days: 130, recent_actions_7d: role === "Admin" ? 6 : 2, total_users: role === "Admin" ? 9 : null, activity: [{ id: "log", action: "login", details: "Own activity", timestamp: "2026-10-05T10:00:00+08:00" }] })
    if (path === "/api/v1/activity") return reply({ items: [], total: 0, page: 1, page_size: 100 })
    if (path === "/api/v1/config") return reply({ camera_ids: "CAM-001", confidence_threshold: 85, data_retention_enabled: true })
    if (path === "/api/v1/devices") return reply([])
    return reply({ detail: "Unexpected fixture request" }, 404)
  })
  await page.goto(`${runtime.url}/dashboard?screen=${screen}`, { waitUntil: "domcontentloaded" })
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

test("admin profile replaces system avg confidence with personal recent actions count", async t => {
  const { page } = await setup(t, "profile", "Admin")
  await page.getByText("131", { exact: true }).waitFor()
  await page.getByText("6", { exact: true }).waitFor()
  assert.equal(await page.getByText("Your Actions (7d)", { exact: true }).count(), 1)
  assert.equal(await page.getByText("System Avg Confidence", { exact: true }).count(), 0)
  assert.equal(await page.getByText("82.3%", { exact: true }).count(), 0)
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

test("role changes clear admin data and reject late responses while preserving child state", async t => {
  const { page } = await setup(t, "scope")
  const state = () => page.getByTestId("scope-state").textContent().then(JSON.parse)
  await page.waitForFunction(() => JSON.parse(document.querySelector('[data-testid="scope-state"]').textContent).users.length === 1)
  await page.getByRole("button", { name: "Keep child state" }).click()
  let release
  const held = new Promise(resolve => { release = resolve })
  await page.route("**/api/v1/users", async route => {
    if (route.request().method() !== "POST") return route.fallback()
    await held
    return route.fulfill({ status: 201, headers: { "access-control-allow-origin": "*" }, json: {
      id: "late", username: "late-owner", full_name: "Late private owner", role: "Operator", status: "Active",
      temporary_password: "temporary-handoff", temporary_pin: "5678",
    } })
  })
  t.after(() => release())
  const started = page.waitForRequest(request => request.url().endsWith("/api/v1/users") && request.method() === "POST")
  await page.getByRole("button", { name: "Create pending user" }).click()
  await started
  await page.getByRole("button", { name: "Become operator" }).click()
  assert.equal((await state()).role, "Operator")
  assert.equal((await state()).count, 1)
  assert.deepEqual((await state()).users, [])
  release()
  await page.waitForFunction(() => JSON.parse(document.querySelector('[data-testid="scope-state"]').textContent).result === "complete")
  assert.deepEqual((await state()).users, [])
})

test("WebSocket revocation clears current auth but an old socket cannot clear a rotated token", async t => {
  const { page } = await setup(t, "socket")
  await page.waitForFunction(() => document.querySelector('[data-testid="socket-state"]').textContent === "connected")
  await page.evaluate(() => {
    localStorage.setItem("bananavision_token", "rotated-access")
    window.fixtureSockets[0].close(4001)
  })
  await page.waitForFunction(() => window.fixtureSockets.length === 2)
  await page.evaluate(() => window.fixtureSockets[0].close(4001))
  assert.equal(await page.evaluate(() => localStorage.getItem("bananavision_token")), "rotated-access")
  await page.route(`${runtime.url}/login`, route => route.fulfill({ contentType: "text/html", body: "<p>Sign in again</p>" }))
  await page.evaluate(() => window.fixtureSockets[1].close(4001))
  await page.waitForURL(`${runtime.url}/login`)
  assert.equal(await page.evaluate(() => localStorage.getItem("bananavision_token")), null)
  assert.equal(await page.evaluate(() => localStorage.getItem("bananavision_user")), null)
})

test("a delayed profile response cannot overwrite auth metadata after a role change", async t => {
  const { page } = await setup(t, "scope")
  let release
  const held = new Promise(resolve => { release = resolve })
  await page.route("**/api/v1/users/me/profile", async route => {
    if (route.request().method() !== "PATCH") return route.fallback()
    await held
    return route.fulfill({ headers: { "access-control-allow-origin": "*" }, json: {
      id: "owner", username: "owner", full_name: "Same Name", role: "Admin", status: "Active", avatar_url: "private-avatar.png",
    } })
  })
  t.after(() => release())
  const started = page.waitForRequest(request => request.url().endsWith("/me/profile") && request.method() === "PATCH")
  await page.getByRole("button", { name: "Update pending profile" }).click()
  await started
  await page.getByRole("button", { name: "Become operator" }).click()
  release()
  await page.waitForFunction(() => JSON.parse(document.querySelector('[data-testid="scope-state"]').textContent).result === "complete")
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("bananavision_user")))
  assert.equal(stored.role, "Operator")
  assert.equal(stored.avatar, undefined)
})
