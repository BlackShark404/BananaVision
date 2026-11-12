import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'public-scan.fixture.tsx', auth: 'kiosk.auth.tsx' }) })
after(async () => { await runtime?.close() })

for (const [raw, label] of [['0.9938128387987426', '1 day'], ['6.07123208429123', '6–7 days'], ['3-4', '3–4 days'], [null, 'Unknown']]) {
  test(`public QR tracking formats ${raw} without changing its prediction`, async t => {
    const context = await runtime.browser.newContext()
    const page = await context.newPage()
    const errors = [], requests = []
    page.on('pageerror', error => errors.push(error.message))
    t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
    await installEnvironment(page)
    const record = Object.freeze({ id: 'fixture-scan', date_time: '2026-10-21T02:00:00+08:00',
      cultivar: 'Lakatan', ripeness: 'Ripe', spoilage_days: raw, confidence: 90, finger_count: 7,
      temperature: null, humidity: null, vpd: null, treatment: 'Natural', source_text: 'Demo source',
      inventory_status: 'In Stock', images: [] })
    await page.route('**/api/v1/**', route => {
      requests.push(route.request())
      return route.fulfill({ json: record, headers: { 'access-control-allow-origin': '*' } })
    })
    await page.goto(`${runtime.url}/scans/fixture-scan/track`)
    const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
    await metric.getByText(label, { exact: true }).waitFor()
    assert.equal(record.spoilage_days, raw)
    assert.equal(requests.length, 1)
    assert.equal(requests[0].method(), 'GET')
    assert.equal(requests[0].headers().authorization, undefined)
    if (raw?.includes('.')) assert.doesNotMatch(await metric.innerText(), new RegExp(raw.replaceAll('.', '\\.')))
  })
}

test('public QR tracking shows a live countdown beside the original estimate', async t => {
  const context = await runtime.browser.newContext()
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const record = {
    id: 'fixture-scan', date_time: '2026-09-30T12:00:00+08:00', cultivar: 'Lakatan',
    ripeness: 'Ripe', spoilage_days: '5-7', remaining_days: 4, risk_as_of: '2026-10-02T12:00:00+08:00',
    confidence: 90, finger_count: 7, temperature: null, humidity: null, vpd: null,
    treatment: 'Natural', source_text: 'Demo source', inventory_status: 'In Stock', images: [],
  }
  await page.route('**/api/v1/**', route => route.fulfill({
    json: record, headers: { 'access-control-allow-origin': '*' },
  }))
  await page.goto(`${runtime.url}/scans/fixture-scan/track`)
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('4 days left', { exact: true }).waitFor()
  await metric.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
  assert.equal(await page.getByText('Pending quality review', { exact: true }).count(), 0)
  await page.clock.fastForward('24:00:00')
  await metric.getByText('3 days left', { exact: true }).waitFor()
})

test('public QR tracking marks a flagged scan as pending quality review', async t => {
  const context = await runtime.browser.newContext()
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const record = {
    id: 'fixture-scan', date_time: '2026-09-30T12:00:00+08:00', cultivar: 'Lakatan',
    ripeness: 'Ripe', spoilage_days: '5-7', confidence: 90, finger_count: 7,
    temperature: null, humidity: null, vpd: null, treatment: 'Natural', source_text: 'Demo source',
    inventory_status: 'In Stock', flagged: true, images: [],
  }
  await page.route('**/api/v1/**', route => route.fulfill({
    json: record, headers: { 'access-control-allow-origin': '*' },
  }))
  await page.goto(`${runtime.url}/scans/fixture-scan/track`)
  await page.getByText('Pending quality review', { exact: true }).waitFor()
  await page.getByText(/classification and estimates shown are preliminary/i).waitFor()
})
