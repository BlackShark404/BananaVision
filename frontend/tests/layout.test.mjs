import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'layout.fixture.tsx', port: 5220 }) })
after(async () => { await runtime?.close() })

for (const screen of ['logs', 'activity']) {
  for (const [width, height] of [[1280, 650], [1024, 600], [390, 700]]) {
    test(`${screen} confines scrolling to the app at ${width}x${height}`, async t => {
      const context = await runtime.browser.newContext({ viewport: { width, height } })
      t.after(() => context.close())
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await installEnvironment(page)
      await page.route('**/api/v1/**', async route => {
        const url = new URL(route.request().url())
        const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }
        const reply = json => route.fulfill({ headers, json })
        if (route.request().method() === 'OPTIONS') return route.fulfill({ headers, status: 204 })
        if (url.pathname === '/api/v1/scan-logs') return reply({
          items: Array.from({ length: 10 }, (_, i) => ({
            id: `scan-${i}`, revision: 1, date_time: '2026-10-02T08:10:00+08:00',
            cultivar: 'Lakatan', ripeness: 'Ripe', confidence: 92, spoilage_days: '3',
            finger_count: 7, operator_name: 'Fixture Operator', source_name: 'Fixture Supplier',
            inventory_status: 'In Stock', temperature: 25, humidity: 70, vpd: 1.2,
          })),
          total: 78, page: 1, page_size: 10, snapshot_id: 'fixture-snapshot',
          avg_confidence: 92, at_risk_count: 0, review_count: 0,
          options: { sources: [], operators: [] }, generated_at: '2026-10-02T08:10:00+08:00',
        })
        if (url.pathname === '/api/v1/activity') return reply({
          items: Array.from({ length: 154 }, (_, i) => ({
            id: `activity-${i}`, user_name: 'Fixture Admin', action: 'login',
            details: 'User logged in from a fixture workstation', ip_address: '127.0.0.1',
            created_at: '2026-10-02T08:10:00+08:00',
          })), total: 154, page: 1, page_size: 200,
        })
        if (url.pathname === '/api/v1/config') return reply({ camera_ids: '', confidence_threshold: 85, revision: 1 })
        if (['/api/v1/scans', '/api/v1/users', '/api/v1/notifications'].includes(url.pathname)) {
          return reply({ items: [], total: 0, page: 1, page_size: 100 })
        }
        return reply([])
      })
      await page.goto(`${runtime.url}${screen === 'logs' ? '/logs' : '/dashboard/activity'}`)
      await page.locator('tbody tr').first().waitFor()
      await page.getByText(screen === 'logs' ? 'Showing 1–10 of 78' : 'Showing 1–15 of 154', { exact: true }).waitFor()
      await page.clock.runFor(500)
      const dimensions = await page.evaluate(() => ({
        height: document.documentElement.scrollHeight, width: document.documentElement.scrollWidth,
        viewportHeight: innerHeight, viewportWidth: innerWidth,
        escapedLabels: [...document.querySelectorAll('.sr-only')].map(el => ({
          text: el.textContent, y: el.getBoundingClientRect().y,
        })).filter(el => el.y > innerHeight),
      }))
      assert(dimensions.height <= height + 1, JSON.stringify(dimensions))
      assert(dimensions.width <= width + 1, JSON.stringify(dimensions))
      const main = page.locator('main')
      await main.evaluate(el => { el.scrollTop = el.scrollHeight })
      await page.clock.runFor(200)
      assert(await main.evaluate(el => el.scrollTop > 0))
      await page.evaluate(() => window.scrollTo({ top: 10000, behavior: 'instant' }))
      assert.equal(await page.evaluate(() => window.scrollY), 0)
      await page.getByRole('navigation', { name: 'pagination' }).waitFor()
      const pagination = await page.getByRole('navigation', { name: 'pagination' }).boundingBox()
      assert(pagination.y >= 0 && pagination.y + pagination.height <= height)
      if (width >= 1024) {
        const sidebar = await page.locator('aside').boundingBox()
        assert.equal(sidebar.y, 0)
        assert.equal(sidebar.height, height)
      }
      const table = page.locator('[data-slot="table-container"]')
      await table.evaluate(el => { el.scrollLeft = el.scrollWidth })
      assert(await table.evaluate(el => el.scrollWidth <= el.clientWidth || el.scrollLeft > 0))
      assert.equal(await main.evaluate(el => el.scrollLeft), 0)
      assert.deepEqual(errors, [])
    })
  }
}
