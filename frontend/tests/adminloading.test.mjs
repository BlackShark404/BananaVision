import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "adminloading.fixture.tsx", port: 5201 }) })
after(async () => { await runtime?.close() })

for (const [screen, endpoint, empty, item, payload] of [
  ["users", "users", "No users found", "Fixture User", {items:[{id:"fixture",username:"fixture",full_name:"Fixture User",role:"Operator",status:"Active"}],total:1}],
  ["suppliers", "suppliers", "No suppliers found", "Fixture Supplier", [{id:"fixture",name:"Fixture Supplier",status:"Active"}]],
  ["activity", "activity", "No activities found", "Fixture activity", {items:[{id:"fixture",user_name:"Fixture User",action:"login",details:"Fixture activity",created_at:"2026-10-02T04:00:00Z"}],total:1,page:1,page_size:100}],
]) {
  test(screen + " has cold skeletons, preserves refresh snapshot and reports failure", async t => {
    const context = await runtime.browser.newContext()
    t.after(() => context.close())
    const page = await context.newPage()
    await installEnvironment(page)
    let release
    let gate = new Promise(resolve => { release = resolve })
    let failed = false
    const errors = []
    page.on("pageerror", error => errors.push(error.message))
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname
      const headers = {"access-control-allow-origin":"*","access-control-allow-headers":"*"}
      if (route.request().method() === "OPTIONS") return route.fulfill({status:204,headers})
      if (path === "/api/v1/" + endpoint) {
        const wait = gate, fail = failed
        if (wait) await wait
        return route.fulfill({headers,status:fail ? 503 : 200,json:fail ? {detail:"Fixture failure"} : payload}).catch(() => {})
      }
      const responses = {
        users:{items:[],total:0},activity:{items:[],total:0,page:1,page_size:100},
        config:{camera_ids:"CAM-001",confidence_threshold:85,data_retention_enabled:true,revision:1},
        devices:[],suppliers:[],intakes:[],scans:{items:[],total:0,page:1,page_size:100},
      }
      return route.fulfill({headers,json:responses[path.split("/").at(-1)] ?? {items:[],total:0}})
    })
    await page.goto(runtime.url + "/dashboard/" + screen)
    await page.getByRole("status").first().waitFor()
    assert.equal(await page.getByText(empty,{exact:true}).count(),0)
    assert.ok(await page.locator('[data-slot="skeleton"]').count() > 0)
    release(); gate = null
    await page.getByText(item,{exact:true}).first().waitFor()
    gate = new Promise(resolve => { release = resolve })
    failed = true
    await page.getByRole("link",{name:screen === "users" ? "Suppliers page" : "Users page"}).click()
    await page.getByRole("link",{name:screen[0].toUpperCase()+screen.slice(1)+" page"}).click()
    await page.getByText(item,{exact:true}).first().waitFor()
    assert.equal(await page.locator('table [data-slot="skeleton"]').count(),0)
    release(); gate = null
    await page.getByRole("alert").waitFor()
    assert.equal(await page.getByText(empty,{exact:true}).count(),0)
    assert.equal(await page.getByText(item,{exact:true}).first().isVisible(),true)
    assert.deepEqual(errors,[])
  })
}


for (const resource of ["users", "suppliers"]) {
  test(resource + " writes survive older GET and permit later authoritative refresh", async t => {
    const context = await runtime.browser.newContext()
    t.after(() => context.close())
    const page = await context.newPage()
    await installEnvironment(page)
    const original = resource === "users"
      ? { id:"fixture",username:"fixture",full_name:"Original User",role:"Operator",status:"Active" }
      : { id:"fixture",name:"Original Supplier",status:"Active" }
    const saved = { ...original, ...(resource === "users" ? {full_name:"Saved User"} : {name:"Saved Supplier"}) }
    const latest = { ...saved, ...(resource === "users" ? {full_name:"Latest User"} : {name:"Latest Supplier"}) }
    let payload = original, gate = null, release, heldRequests = 0
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname
      const headers = {"access-control-allow-origin":"*","access-control-allow-headers":"*","access-control-allow-methods":"*"}
      if (route.request().method() === "OPTIONS") return route.fulfill({status:204,headers})
      if (path === "/api/v1/" + resource + "/fixture") return route.fulfill({headers,json:saved})
      if (path === "/api/v1/" + resource) {
        const snapshot = payload, wait = gate
        if (wait) { heldRequests++; await wait }
        return route.fulfill({headers,json:resource === "users" ? {items:[snapshot],total:1} : [snapshot]}).catch(() => {})
      }
      const responses = {users:{items:[],total:0},suppliers:[],intakes:[],devices:[],
        config:{camera_ids:"CAM-001",confidence_threshold:85,revision:1},
        activity:{items:[],total:0,page:1,page_size:100},scans:{items:[],total:0,page:1,page_size:100}}
      return route.fulfill({headers,json:responses[path.split("/").at(-1)] ?? {items:[],total:0}})
    })
    await page.goto(runtime.url + "/dashboard/" + resource)
    await page.getByText(resource === "users" ? "Original User" : "Original Supplier",{exact:true}).waitFor()
    gate = new Promise(resolve => { release = resolve })
    await page.getByRole("link",{name:"Activity page"}).click()
    await page.getByRole("link",{name:resource === "users" ? "Users page" : "Suppliers page"}).click()
    await page.getByText("Refreshing " + resource + "…",{exact:true}).waitFor()
    assert.ok(heldRequests > 0)
    await page.getByRole("button",{name:resource === "users" ? "Write user" : "Write supplier",exact:true}).click()
    await page.getByText(resource === "users" ? "Saved User" : "Saved Supplier",{exact:true}).waitFor()
    const received = page.waitForResponse(r => new URL(r.url()).pathname === "/api/v1/" + resource && r.request().method() === "GET")
    release(); gate = null
    await received
    await page.waitForFunction(resource => {
      const state = JSON.parse(document.querySelector('[data-testid="provider-state"]').textContent)
      return !state[resource + "Loading"] && !state.intakesLoading
    }, resource)
    assert.equal(await page.getByText(resource === "users" ? "Saved User" : "Saved Supplier",{exact:true}).count(),1)
    payload = latest
    await page.getByRole("link",{name:"Activity page"}).click()
    await page.getByRole("link",{name:resource === "users" ? "Users page" : "Suppliers page"}).click()
    await page.getByText(resource === "users" ? "Latest User" : "Latest Supplier",{exact:true}).waitFor()
  })
}

test("intake-only failure reports recovery instead of indefinite loading", async t => {
  const context = await runtime.browser.newContext()
  t.after(() => context.close())
  const page = await context.newPage()
  await installEnvironment(page)
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname
    const headers = {"access-control-allow-origin":"*","access-control-allow-headers":"*"}
    if (route.request().method() === "OPTIONS") return route.fulfill({status:204,headers})
    if (path === "/api/v1/intakes") return route.fulfill({status:503,headers,json:{detail:"Fixture intake failure"}})
    const responses = {users:{items:[],total:0},suppliers:[],devices:[],
      config:{camera_ids:"CAM-001",confidence_threshold:85,revision:1},
      activity:{items:[],total:0,page:1,page_size:100},scans:{items:[],total:0,page:1,page_size:100}}
    return route.fulfill({headers,json:responses[path.split("/").at(-1)] ?? {items:[],total:0}})
  })
  await page.goto(runtime.url + "/dashboard/intakes")
  await page.getByRole("alert").waitFor()
  assert.match(await page.getByRole("alert").innerText(), /Intake data unavailable.*Reload/)
  assert.equal(await page.getByText("Loading complete scan history…",{exact:true}).count(),0)
})

for (const resource of ["users", "suppliers"]) {
  test(resource + " write during first load triggers a complete fresh snapshot", async t => {
    const context = await runtime.browser.newContext()
    t.after(() => context.close())
    const page = await context.newPage()
    await installEnvironment(page)
    let release, reads = 0, written = false
    const gate = new Promise(resolve => { release = resolve })
    const record = (id, name) => resource === "users"
      ? { id, username: id, full_name: name, role: "Operator", status: "Active" }
      : { id, name, status: "Active" }
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }
      const reply = json => route.fulfill({ headers, json }).catch(() => {})
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers })
      if (path === `/api/v1/${resource}/fixture`) { written = true; return reply(record("fixture", "Saved record")) }
      if (path === `/api/v1/${resource}`) {
        const items = [record("fixture", written ? "Saved record" : "Old record"), record("other", "Other record")]
        if (++reads === 1) await gate
        return reply(resource === "users" ? { items, total: 2 } : items)
      }
      const responses = { users: { items: [], total: 0 }, suppliers: [], intakes: [], devices: [],
        config: { camera_ids: "CAM-001", confidence_threshold: 85, revision: 1 },
        activity: { items: [], total: 0, page: 1, page_size: 100 }, scans: { items: [], total: 0, page: 1, page_size: 100 } }
      return reply(responses[path.split("/").at(-1)] ?? [])
    })
    try {
      await page.goto(runtime.url + "/dashboard/" + resource)
      await page.locator('table [data-slot="skeleton"]').first().waitFor()
      await page.getByRole("button", { name: resource === "users" ? "Write user" : "Write supplier", exact: true }).click()
      await page.getByText("Saved record", { exact: true }).waitFor()
      await page.getByText("Other record", { exact: true }).waitFor()
      assert.ok(reads >= 2)
      release()
      await page.clock.runFor(100)
      assert.equal(await page.getByText("Old record", { exact: true }).count(), 0)
    } finally { release() }
  })
}
