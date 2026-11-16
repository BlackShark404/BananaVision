import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'layout.fixture.tsx', port: 5220, showScrollbars: true }) })
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


for (const [width, height] of [[1280, 650], [1024, 600], [390, 700]]) {
  test(`configuration sections, save bar and restore dialog fit at ${width}x${height}`, async t => {
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
      if (url.pathname === '/api/v1/config') return reply({
        camera_ids: 'TOP, LEFT, RIGHT, REAR', camera_device_ids: [0, 1, 2, 3], confidence_threshold: 85,
        detection_confidence_threshold: 40, data_retention_enabled: true, revision: 1,
        application_status: 'applied', retention_days: 14,
      })
      if (url.pathname === '/api/v1/config/maintenance') return reply({ state: 'ready', active_operations: 0 })
      if (url.pathname === '/api/v1/config/restores/validate') return reply({ validation_id: 'fixture', token: 'fixture-only', manifest: {}, expires_at: '2099-01-01T00:00:00Z' })
      if (url.pathname === '/api/v1/cameras/discovery') return reply({
        backend: 'fixture', error: null, devices: ['TOP', 'LEFT', 'RIGHT', 'REAR'].map((id, index) => ({
          device_id: index, name: 'EMEET SmartCam C100 2K USB Camera With A Long Device Name',
          device_uid: `fixture-device-${index}`, configured_camera_id: id, online: true,
        })),
      })
      if (['/api/v1/scans', '/api/v1/users', '/api/v1/notifications', '/api/v1/activity'].includes(url.pathname)) return reply({ items: [], total: 0 })
      return reply([])
    })
    await page.goto(`${runtime.url}/dashboard/config`)
    await page.getByRole('button', { name: 'Rename camera 1: TOP' }).waitFor()
    await page.getByRole('combobox', { name: 'Detected device for camera 1' }).waitFor()
    const main = page.locator('main')
    // Exercise classic scrollbars even on hosts that default to overlay scrollbars.
    await page.addStyleTag({ content: 'main { scrollbar-width: auto; } main::-webkit-scrollbar { width: 16px; }' })
    const originalPanel = await page.getByRole('tabpanel', { name: 'Cameras', exact: true }).boundingBox()
    const originalTabs = await page.getByRole('tablist', { name: 'Configuration sections' }).boundingBox()
    assert(await main.evaluate(el => el.scrollHeight > el.clientHeight), 'Camera fixture must require scrolling')
    assert(await main.evaluate(el => el.offsetWidth > el.clientWidth), 'Fixture must reserve a classic scrollbar')
    const capture = async name => {
      if (!process.env.SYSTEMCONFIG_SCREENSHOT_DIR) return
      await mkdir(process.env.SYSTEMCONFIG_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ animations: 'disabled', path: `${process.env.SYSTEMCONFIG_SCREENSHOT_DIR}/${name}-${width}.png` })
    }
    const bounds = async () => {
      const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight }))
      assert(dimensions.width <= width + 1, JSON.stringify(dimensions))
      assert(dimensions.height <= height + 1, JSON.stringify(dimensions))
      assert(await main.evaluate(el => el.scrollWidth <= el.clientWidth + 1))
    }
    for (const section of ['Cameras', 'Detection', 'Data & Backups', 'Power', 'Cameras']) {
      await page.getByRole('tab', { name: section, exact: true }).click()
      assert.equal(await page.getByRole('tab', { name: section, exact: true }).getAttribute('aria-selected'), 'true')
      await main.evaluate(el => { el.scrollTop = 0 })
      await page.clock.runFor(200)
      await bounds()
      const panel = await page.getByRole('tabpanel', { name: section, exact: true }).boundingBox()
      const tabs = await page.getByRole('tablist', { name: 'Configuration sections' }).boundingBox()
      assert(Math.abs(panel.width - originalPanel.width) < 1, `${section} panel width shifted: ${originalPanel.width} → ${panel.width}`)
      assert(Math.abs(panel.x - originalPanel.x) < 1, `${section} panel moved horizontally`)
      // Mobile tabs can scroll horizontally to reveal the selected section.
      assert(Math.abs(tabs.width - originalTabs.width) < 1, `${section} tab bar width shifted`)
      await capture(section.toLowerCase().replace(/[^a-z]+/g, '-'))
    }
    await page.getByRole('tab', { name: 'Detection', exact: true }).click()
    await page.getByRole('slider').press('ArrowLeft')
    await page.getByRole('tab', { name: 'Cameras', exact: true }).click()
    await main.evaluate(el => { el.scrollTop = el.scrollHeight })
    const bar = await page.getByRole('region', { name: 'Unsaved configuration changes' }).boundingBox()
    assert(bar.y >= 0 && bar.y + bar.height <= height + 1, JSON.stringify(bar))
    await bounds()
    await capture('unsaved')
    await page.getByRole('button', { name: 'Discard', exact: true }).click()
    await page.getByRole('tab', { name: 'Data & Backups', exact: true }).click()
    await page.getByRole('button', { name: 'Restore from Backup' }).click()
    const dialog = await page.getByRole('dialog', { name: 'Restore Station Data' }).boundingBox()
    assert(dialog.x >= 0 && dialog.x + dialog.width <= width + 1, JSON.stringify(dialog))
    assert(dialog.y >= 0 && dialog.y + dialog.height <= height + 1, JSON.stringify(dialog))
    await capture('restore')
    await page.getByLabel('Backup archive').setInputFiles({ name: 'fixture.zip', mimeType: 'application/zip', buffer: Buffer.from('mock archive') })
    await page.getByRole('button', { name: 'Validate Backup', exact: true }).click()
    await page.getByLabel('Administrator password').waitFor()
    await page.getByRole('button', { name: 'Replace Station Data', exact: true }).scrollIntoViewIfNeeded()
    const confirmation = await page.getByRole('dialog', { name: 'Restore Station Data' }).boundingBox()
    assert(confirmation.y >= 0 && confirmation.y + confirmation.height <= height + 1, JSON.stringify(confirmation))
    const replace = await page.getByRole('button', { name: 'Replace Station Data', exact: true }).boundingBox()
    assert(replace.y >= confirmation.y && replace.y + replace.height <= confirmation.y + confirmation.height, JSON.stringify(replace))
    await capture('restore-confirm')
    assert.deepEqual(errors, [])
  })
}

test('sidebar Logs opens today directly and does not reload the open default view', async t => {
  const context = await runtime.browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'America/Los_Angeles' })
  t.after(() => context.close())
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await installEnvironment(page)
  const listRequests = []
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }
    if (route.request().method() === 'OPTIONS') return route.fulfill({ headers, status: 204 })
    if (url.pathname === '/api/v1/scan-logs') {
      listRequests.push(Object.fromEntries(url.searchParams))
      return route.fulfill({ headers, json: { items: [{ id: 'scan-1', revision: 1, date_time: '2026-10-02T08:10:00+08:00',
        cultivar: 'Lakatan', ripeness: 'Ripe', confidence: 92, spoilage_days: '3', finger_count: 7,
        operator_name: 'Fixture Operator', source_name: 'Fixture Supplier', inventory_status: 'In Stock' }],
        total: 1, page: 1, page_size: 10, snapshot_id: 'fixture-snapshot', avg_confidence: 92, at_risk_count: 0,
        review_count: 0, options: { sources: [], operators: [] }, generated_at: '2026-10-02T08:10:00+08:00' } })
    }
    if (url.pathname === '/api/v1/config') return route.fulfill({ headers, json: { camera_ids: '', confidence_threshold: 85, revision: 1 } })
    return route.fulfill({ headers, json: ['/api/v1/scans', '/api/v1/users', '/api/v1/notifications'].includes(url.pathname) ? { items: [], total: 0, page: 1, page_size: 100 } : [] })
  })
  await page.goto(`${runtime.url}/logs`)
  await page.waitForURL('**/logs?date=2026-10-02')
  await page.locator('tbody tr').first().waitFor()
  const logsLink = page.locator('aside').getByRole('link', { name: 'Logs', exact: true })
  // The Manila day, although this browser's clock still reads 1 October.
  assert.equal(await logsLink.getAttribute('href'), '/logs?date=2026-10-02')
  const historyLength = await page.evaluate(() => history.length)
  const requestCount = listRequests.length
  await logsLink.click()
  await page.clock.runFor(500)
  assert.equal(new URL(page.url()).search, '?date=2026-10-02')
  assert.equal(await page.evaluate(() => history.length), historyLength, 'no duplicate history entry')
  assert.equal(listRequests.length, requestCount, 'the open view is not reloaded')
  assert.equal(await page.locator('tbody tr').count(), 1)
  assert.deepEqual(errors, [])
})
