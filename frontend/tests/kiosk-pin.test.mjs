import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { startBrowser } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "kiosk-pin.fixture.tsx", auth: "assigned.auth.tsx", port: 5206 }) })
after(async () => { await runtime?.close() })

const existingUser = { id: "admin-1", username: "admin-fixture", fullName: "Fixture Admin", role: "Admin" }
const authenticated = {
  status: "success", token: { access_token: "operator-access", token_type: "bearer" },
  user: { id: "operator-1", username: "fixture", full_name: "Fixture Operator", role: "Operator" },
}

async function setup(t, responses = []) {
  const context = await runtime.browser.newContext({ viewport: { width: 1280, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.setDefaultNavigationTimeout(45000)
  const errors = [], requests = []
  page.on("pageerror", error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await page.addInitScript(user => {
    if (location.pathname === "/login") return
    localStorage.setItem("bananavision_token", "existing-access")
    localStorage.setItem("bananavision_user", JSON.stringify(user))
  }, existingUser)
  // Every API request is intercepted, including unexpected requests after navigation.
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    requests.push({ path, body: request.postDataJSON() })
    const response = responses.shift() ?? { status: 404, json: { detail: "Unexpected fixture request" } }
    if (response.abort) return route.abort("failed")
    return route.fulfill({ headers, ...response })
  })
  await page.route("**/login", route => route.fulfill({ contentType: "text/html", body: "<p>Login fixture</p>" }))
  await page.goto(`${runtime.url}/dashboard`, { waitUntil: "domcontentloaded" })
  await page.getByRole("dialog").getByRole("button", { name: /Fixture Operator/ }).click()
  return { page, requests }
}

async function enterPin(page, pin = "1234") {
  for (const digit of pin) await page.getByRole("dialog").getByRole("button", { name: digit, exact: true }).click()
}

async function storedSession(page) {
  return page.evaluate(() => ({
    token: localStorage.getItem("bananavision_token"),
    user: JSON.parse(localStorage.getItem("bananavision_user")),
  }))
}

test("back cancels delayed PIN verification before it submits", async t => {
  const { page, requests } = await setup(t)
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  await enterPin(page)
  await page.getByRole("button", { name: "Back to operators" }).click()
  await page.clock.runFor(500)
  assert.equal(requests.length, 0)
  await page.getByRole("button", { name: /Fixture Operator/ }).waitFor()
})

test("PIN verification sends once and prevents navigation while pending", async t => {
  const { page, requests } = await setup(t)
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  let calls = 0, release
  const gate = new Promise(resolve => { release = resolve })
  await page.route("**/api/v1/auth/swap", async route => {
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
    calls++
    await gate
    await route.fulfill({ headers, json: authenticated })
  })
  await enterPin(page)
  // Extra digits must not cancel the pending fourth-digit submission.
  await page.getByRole("dialog").getByRole("button", { name: "5", exact: true }).click()
  await page.clock.runFor(250)
  try {
    await page.getByText("Verifying...", { exact: true }).waitFor()
    assert.equal(await page.getByRole("button", { name: "Back to operators" }).isDisabled(), true)
    await page.keyboard.press("Escape")
    assert.equal(await page.getByRole("dialog").isVisible(), true)
    assert.equal(calls, 1)
    assert.equal(requests.length, 0)
  } finally { release() }
  await page.getByRole("dialog").waitFor({ state: "hidden" })
})

for (const operation of ["swap", "setup-pin"]) {
  test(`stalled ${operation} unlocks PIN recovery and ignores a late successful response`, async t => {
    const { page } = await setup(t, [{ status: 200, json: { status: "requires_pin_change", reason: "pin_reset", setup_token: "limited-proof" } }])
    if (operation === "setup-pin") {
      await enterPin(page)
      await page.getByRole("heading", { name: "Create New Kiosk PIN", exact: true }).waitFor()
      await enterPin(page, "2468")
      await page.getByRole("heading", { name: "Confirm New PIN", exact: true }).waitFor()
    }
    await page.clock.install()
    await page.clock.pauseAt(new Date())
    let release, requested
    const gate = new Promise(resolve => { release = resolve })
    const seen = new Promise(resolve => { requested = resolve })
    await page.route(`**/api/v1/auth/${operation}`, async route => {
      const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers })
      requested()
      await gate
      await route.fulfill({ headers, json: authenticated }).catch(() => {})
    })
    try {
      await enterPin(page, operation === "swap" ? "1234" : "2468")
      await page.clock.runFor(250)
      await seen
      await page.clock.runFor(15_100)
      await page.getByText("Kiosk temporarily unavailable", { exact: true }).waitFor({ timeout: 2000 })
      assert.equal(await page.getByRole("button", { name: "Back to operators" }).isEnabled(), true)
      release()
      await page.clock.runFor(100)
      assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
      await page.getByRole("button", { name: "Back to operators" }).click()
      await page.getByRole("button", { name: /Fixture Operator/ }).waitFor()
    } finally { release() }
  })
}

test("station recovery errors explain unavailability and allow the same PIN to succeed after recovery", async t => {
  const { page, requests } = await setup(t, [
    { status: 503, json: { detail: "Station requires recovery; new work is temporarily unavailable" } },
    { status: 200, json: authenticated },
  ])
  await enterPin(page)
  await page.getByText("Kiosk temporarily unavailable", { exact: true }).waitFor()
  await page.getByText(/Station requires recovery.*retry/i).waitFor()
  assert.equal(await page.getByText("Invalid PIN code", { exact: true }).count(), 0)
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
  await enterPin(page)
  await page.getByRole("dialog").waitFor({ state: "hidden" })
  assert.deepEqual(requests.map(request => request.body), [{ username: "fixture", pin: "1234" }, { username: "fixture", pin: "1234" }])
  assert.equal((await storedSession(page)).token, "operator-access")
  assert.equal((await page.getByTestId("auth-state").textContent()).includes('"swapped":"operator-1"'), true)
})

test("connection failures request a server retry without accusing the operator of a wrong PIN", async t => {
  const { page } = await setup(t, [{ abort: true }])
  await enterPin(page)
  await page.getByText("Kiosk temporarily unavailable", { exact: true }).waitFor()
  await page.getByText(/Backend unavailable.*retry/i).waitFor()
  assert.equal(await page.getByText("Invalid PIN code", { exact: true }).count(), 0)
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
})

test("PIN lockout keeps the backend wait duration visible", async t => {
  const { page } = await setup(t, [{ status: 429, json: { detail: "Too many failed PIN attempts. Try again in 37 seconds." } }])
  await enterPin(page)
  await page.getByText("Too many PIN attempts", { exact: true }).waitFor()
  await page.getByText("Too many failed PIN attempts. Try again in 37 seconds.", { exact: true }).waitFor()
  assert.equal(await page.getByText("Invalid PIN code", { exact: true }).count(), 0)
})

test("wrong PIN 401 preserves the current session and stays on the kiosk for another attempt", async t => {
  const { page } = await setup(t, [{ status: 401, json: { detail: "Invalid PIN" } }])
  await enterPin(page)
  await page.getByText("Invalid PIN code", { exact: true }).waitFor()
  assert.equal(new URL(page.url()).pathname, "/dashboard")
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
})

test("inactive account 403 keeps its account guidance distinct from an invalid PIN", async t => {
  const { page } = await setup(t, [{ status: 403, json: { detail: "Account is inactive" } }])
  await enterPin(page)
  await page.getByText("Account Inactive", { exact: true }).waitFor()
  assert.equal(await page.getByText("Invalid PIN code", { exact: true }).count(), 0)
})

for (const [status, title] of [["failed", "Invalid PIN code"], ["inactive", "Account Inactive"]]) {
  test(`normal HTTP 200 ${status} PIN response preserves its existing guidance and session`, async t => {
    const { page } = await setup(t, [{ status: 200, json: { status } }])
    await enterPin(page)
    await page.getByText(title, { exact: true }).waitFor()
    assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
    assert.equal(await page.getByText("Kiosk temporarily unavailable", { exact: true }).count(), 0)
  })
}

test("temporary PIN verification requires matching replacement digits and sends only the limited setup proof", async t => {
  const { page, requests } = await setup(t, [
    { status: 200, json: { status: "requires_pin_change", reason: "pin_reset", setup_token: "limited-pin-proof" } },
    { status: 200, json: authenticated },
  ])
  await enterPin(page)
  await page.getByRole("heading", { name: "Create New Kiosk PIN", exact: true }).waitFor()
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
  await enterPin(page, "2468")
  await page.getByRole("heading", { name: "Confirm New PIN", exact: true }).waitFor()
  await enterPin(page, "2469")
  await page.getByText("PINs do not match. Try again.", { exact: true }).waitFor()
  await page.getByRole("heading", { name: "Create New Kiosk PIN", exact: true }).waitFor()
  assert.equal(requests.length, 1)
  await enterPin(page, "2468")
  await page.getByRole("heading", { name: "Confirm New PIN", exact: true }).waitFor()
  await enterPin(page, "2468")
  await page.getByRole("dialog").waitFor({ state: "hidden" })
  assert.deepEqual(requests, [
    { path: "/api/v1/auth/swap", body: { username: "fixture", pin: "1234" } },
    { path: "/api/v1/auth/setup-pin", body: { setup_token: "limited-pin-proof", new_pin: "2468" } },
  ])
  assert.equal((await page.evaluate(() => JSON.stringify(localStorage))).includes("limited-pin-proof"), false)
})

test("PIN setup service failure preserves the limited proof for a retry and reports unavailability", async t => {
  const { page, requests } = await setup(t, [
    { status: 200, json: { status: "requires_pin_change", reason: "new_account", setup_token: "new-account-proof" } },
    { status: 503, json: { detail: "Station is draining; new work is temporarily unavailable" } },
    { status: 200, json: authenticated },
  ])
  await enterPin(page)
  await page.getByRole("heading", { name: "Create New Kiosk PIN", exact: true }).waitFor()
  await page.getByText(/An Admin created this account/).waitFor()
  await enterPin(page, "2468")
  await page.getByRole("heading", { name: "Confirm New PIN", exact: true }).waitFor()
  await enterPin(page, "2468")
  await page.getByText("Kiosk temporarily unavailable", { exact: true }).waitFor()
  await page.getByText(/Station is draining.*retry/i).waitFor()
  await page.getByRole("heading", { name: "Create New Kiosk PIN", exact: true }).waitFor()
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
  await enterPin(page, "2468")
  await page.getByRole("heading", { name: "Confirm New PIN", exact: true }).waitFor()
  await enterPin(page, "2468")
  await page.getByRole("dialog").waitFor({ state: "hidden" })
  assert.deepEqual(requests.slice(1), [
    { path: "/api/v1/auth/setup-pin", body: { setup_token: "new-account-proof", new_pin: "2468" } },
    { path: "/api/v1/auth/setup-pin", body: { setup_token: "new-account-proof", new_pin: "2468" } },
  ])
})

test("password credential 401 also preserves an existing session", async t => {
  const { page } = await setup(t, [{ status: 401, json: { detail: "Invalid credentials" } }])
  await page.evaluate(() => document.querySelectorAll("button").forEach(button => {
    if (button.textContent === "Submit password") button.click()
  }))
  await page.waitForFunction(() => JSON.parse(document.querySelector('[data-testid="auth-state"]').textContent).loginResult === "failed")
  assert.equal(new URL(page.url()).pathname, "/dashboard")
  assert.deepEqual(await storedSession(page), { token: "existing-access", user: existingUser })
})

test("protected endpoint 401 still clears expired authentication and navigates to login", async t => {
  const { page } = await setup(t, [{ status: 401, json: { detail: "Token expired" } }])
  await page.evaluate(() => document.querySelectorAll("button").forEach(button => {
    if (button.textContent === "Check protected request") button.click()
  }))
  await page.waitForURL("**/login")
  assert.deepEqual(await storedSession(page), { token: null, user: null })
})
