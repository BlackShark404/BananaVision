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
