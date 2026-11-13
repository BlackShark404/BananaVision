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
  await page.getByText('Scan details', { exact: true }).click()
  // The public page cannot tell a corrected count apart, so every count is an estimate here.
  const fingers = page.getByText('Est. Fingers', { exact: true }).locator('..')
  assert.equal(await fingers.locator('p').last().innerText(), '7')
  assert.equal(await page.getByText('Finger Count', { exact: true }).count(), 0)
  await page.clock.fastForward('24:00:00')
  await metric.getByText('3 days left', { exact: true }).waitFor()
})

test('public QR tracking counts a 1-3 day estimate down by Manila calendar date until it is overdue', async t => {
  // A browser outside UTC+8: the day must still change at Manila midnight.
  const context = await runtime.browser.newContext({ timezoneId: 'America/Los_Angeles' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)  // 2026-10-02 12:00 in Manila
  const record = Object.freeze({
    id: 'fixture-scan', date_time: '2026-10-01T23:50:00+08:00', cultivar: 'Lakatan',
    ripeness: 'Ripe', spoilage_days: '1-3', remaining_days: 1.49, risk_as_of: '2026-10-02T12:00:00+08:00',
    shelf_life_window: Object.freeze({ min_days: 1, max_days: 3, elapsed_days: 1, remaining_min_days: 0,
      remaining_max_days: 2, days_past: 0, state: 'active', scan_date: '2026-10-01', as_of_date: '2026-10-02' }),
    confidence: 90, finger_count: 7, temperature: null, humidity: null, vpd: null,
    treatment: 'Natural', source_text: 'Demo source', inventory_status: 'In Stock', images: [],
  })
  let requests = 0
  await page.route('**/api/v1/**', route => {
    requests++
    return route.fulfill({ json: record, headers: { 'access-control-allow-origin': '*' } })
  })
  await page.goto(`${runtime.url}/scans/fixture-scan/track`)
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('0–2 days left', { exact: true }).waitFor()
  await metric.getByText('Est. 1–3 days from scan', { exact: true }).waitFor()
  // The estimate is shown as what it was at the scan, never as today's value.
  assert.equal(await metric.getByText('1–3 days', { exact: true }).count(), 0)
  await page.clock.fastForward('11:58:00')  // 23:58 in Manila, still 2 October
  await metric.getByText('0–2 days left', { exact: true }).waitFor()
  await page.clock.fastForward('00:04:00')  // 00:02 in Manila on 3 October
  await metric.getByText('0–1 days left', { exact: true }).waitFor()
  await page.clock.fastForward('24:00:00')
  await metric.getByText('Final day', { exact: true }).waitFor()
  await page.clock.fastForward('24:00:00')
  await metric.getByText('Overdue', { exact: true }).waitFor()
  await page.clock.fastForward(72 * 3_600_000)  // a week after the scan
  await metric.getByText('Overdue', { exact: true }).waitFor()
  await metric.getByText('Est. 1–3 days from scan', { exact: true }).waitFor()
  assert.equal(requests, 1)  // the page rolled over by itself; nothing was re-read or rewritten
  assert.equal(record.spoilage_days, '1-3')
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

// A phone scanning the printed QR code: the page must show only the scanned data.
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
const STAFF = { id: 'operator-1', username: 'fixture', fullName: 'Fixture Operator', role: 'Operator' }
const CORS = { 'access-control-allow-origin': '*' }
const scanned = () => ({
  id: 'fixture-scan', date_time: '2026-09-30T12:00:00+08:00', cultivar: 'Lakatan',
  ripeness: 'Ripe', spoilage_days: '5-7', remaining_days: 4, risk_as_of: '2026-10-02T12:00:00+08:00',
  confidence: 90, finger_count: 7, temperature: 24, humidity: 80, vpd: 0.6,
  treatment: 'Natural', source_text: 'Demo source', inventory_status: 'In Stock', images: [],
})

async function openOnPhone(t, path, { viewer = null, respond } = {}) {
  const context = await runtime.browser.newContext(PHONE)
  const page = await context.newPage()
  const errors = [], requests = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  await page.addInitScript(viewer => { window.publicScanViewer = viewer }, viewer)
  await page.route('**/api/v1/**', route => {
    requests.push(route.request())
    return route.fulfill(respond ? respond(requests.length) : { json: scanned(), headers: CORS })
  })
  await page.goto(`${runtime.url}${path}`)
  return { page, requests }
}

async function assertNoWayOut(page) {
  assert.equal(await page.locator('a, button, [role="button"], [role="link"], [onclick]').count(), 0)
  assert.doesNotMatch(await page.locator('body').innerText(), /log\s*in|login|sign\s*in|website|dashboard/i)
}

async function assertScannedData(page) {
  await page.getByText('Lakatan', { exact: true }).waitFor()
  await page.getByText('Ripe', { exact: true }).waitFor()
  const spoilage = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await spoilage.getByText('4 days left', { exact: true }).waitFor()
  await spoilage.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
  await page.getByText('Sep 30, 2026', { exact: true }).waitFor()
  await page.getByText(/Scan tracked at .*2026.*12:00:00/).waitFor()
  // Secondary values are present but collapsed until asked for.
  assert.equal(await page.getByText('24°C', { exact: true }).isVisible(), false)
  await page.getByText('Scan details', { exact: true }).click()
  await page.getByText('fixture-scan', { exact: true }).waitFor()
  const fingers = page.getByText('Est. Fingers', { exact: true }).locator('..')
  assert.equal(await fingers.locator('p').last().innerText(), '7')
  await page.getByText('24°C', { exact: true }).waitFor()
  assert.equal(await page.getByText('In Stock', { exact: true }).count(), 0)
}

test('a phone scanning the QR code sees only the scanned data, with no login or website buttons', async t => {
  const { page, requests } = await openOnPhone(t, '/scans/fixture-scan/track')
  await assertScannedData(page)
  await assertNoWayOut(page)
  assert.equal(new URL(page.url()).pathname, '/scans/fixture-scan/track')
  assert.equal(requests.length, 1)
  assert.equal(requests[0].headers().authorization, undefined)
  // Fits the phone: no sideways scrolling. Mobile emulation widens window.innerWidth to fit
  // wide content, so compare with the 390 px initial containing block instead.
  assert.deepEqual(await page.evaluate(() => {
    const root = document.documentElement
    return { width: root.clientWidth, overflow: root.scrollWidth > root.clientWidth }
  }), { width: 390, overflow: false })
})

test('a signed-in staff member scanning the QR code stays on the same data-only page', async t => {
  const { page, requests } = await openOnPhone(t, '/scans/fixture-scan/track', { viewer: STAFF })
  await assertScannedData(page)
  await assertNoWayOut(page)
  await page.clock.fastForward('00:05:00')
  assert.equal(new URL(page.url()).pathname, '/scans/fixture-scan/track')
  assert.equal(requests.length, 1)
  assert.equal(requests[0].headers().authorization, undefined)
})

test('an unknown QR code shows a message and no buttons', async t => {
  const { page } = await openOnPhone(t, '/scans/fixture-scan/track', {
    respond: () => ({ status: 404, json: { detail: 'Scan not found' }, headers: CORS }),
  })
  await page.getByRole('alert').getByText('Scan not found', { exact: true }).waitFor()
  await page.getByText('No scan record was found for this QR code.', { exact: true }).waitFor()
  await assertNoWayOut(page)
})

test('a failed load offers only Retry, which then shows the data', async t => {
  const { page, requests } = await openOnPhone(t, '/scans/fixture-scan/track', {
    respond: count => count === 1
      ? { status: 503, json: { detail: 'Service unavailable' }, headers: CORS }
      : { json: scanned(), headers: CORS },
  })
  await page.getByRole('alert').getByText('Could not load scan', { exact: true }).waitFor()
  const buttons = page.getByRole('button')
  assert.deepEqual(await buttons.allInnerTexts(), ['Retry'])
  assert.equal(await page.getByRole('link').count(), 0)
  assert.doesNotMatch(await page.locator('body').innerText(), /log\s*in|login|sign\s*in|website|dashboard/i)
  await buttons.click()
  await assertScannedData(page)
  await assertNoWayOut(page)
  assert.equal(requests.length, 2)
})

test('the normal landing page keeps its login buttons', async t => {
  const { page } = await openOnPhone(t, '/scans/landing-check')
  const access = page.getByRole('button', { name: 'Access Dashboard' })
  await access.waitFor()
  await access.click()
  assert.equal(new URL(page.url()).pathname, '/login')
})
