import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'kiosk.fixture.tsx', auth: 'kiosk.auth.tsx', port: 5205 }) })
after(async () => { await runtime?.close() })
const scanId = '10000000-0000-4000-8000-000000000001'
const saved = {
  id: scanId, revision: 1, date_time: '2026-10-12T15:00:00+08:00', cultivar: 'Lakatan', ripeness: 'Ripe',
  confidence: 95, spoilage_days: '3-5', finger_count: 7, operator_name: 'Fixture Operator',
  inventory_status: 'In Stock', images: [], detections: [],
}

async function setup(t, { offline = false, empty = false, flagged = false, scanOverrides = {} } = {}) {
  const context = await runtime.browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.setDefaultNavigationTimeout(45000)
  t.after(() => context.close())
  await installEnvironment(page)
  await page.route('https://fonts.googleapis.com/**', route => route.abort())
  await page.route('https://fonts.gstatic.com/**', route => route.abort())
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  t.after(() => assert.deepEqual(errors, []))
  const state = { writes: [], jobs: new Map(), scans: empty ? [] : [saved] }
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname, method = req.method()
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }
    const reply = json => route.fulfill({ headers, json })
    if (method === 'OPTIONS') return route.fulfill({ status: 204, headers })
    if (path.includes('/cameras/preview/')) return route.abort()
    if (method === 'POST') {
      const body = req.postDataJSON()
      state.writes.push({ path, body })
      if (path.endsWith('/retry')) {
        const job = state.jobs.get(path.split('/').at(-2))
        job.status = 'SUBMITTED'; job.error = null; job.attempt_count++
        return reply({ ...job, status: 'QUEUED' })
      }
      if (path === '/api/v1/intakes') return reply({ id: 'fixture-intake', supplier_id: 'supplier-1', supplier_name: 'Fixture Supplier', batch_number: 'BCH-FIXTURE', status: 'Active', intake_date: '2026-10-14' })
      if (path === '/api/v1/scans/trigger') {
        const job = { id: 'live-job', quantity: 1, printer_name: 'TP870 S', attempt_count: 1,
          status: offline ? 'FAILED' : 'SUBMITTED', windows_job_id: 713,
          error: offline ? 'TP870 S is OFFLINE' : null }
        state.jobs.set(job.id, job)
        const result = { ...saved, ...scanOverrides, id: '20000000-0000-4000-8000-000000000002', flagged, intake_id: body.intake_id, print_job: { ...job, status: 'QUEUED' } }
        state.scans = [result, saved]
        return reply(result)
      }
      throw new Error(`Unexpected write: ${path}`)
    }
    if (method === 'PATCH' && path.endsWith('/flag')) {
      const body = req.postDataJSON()
      state.writes.push({ path, body })
      const result = state.scans.find(scan => path.includes(scan.id))
      result.flagged = body.flagged
      result.revision++
      return reply(result)
    }
    if (path.includes('/print-jobs/')) return reply(state.jobs.get(path.split('/').at(-1)))
    if (path === '/api/v1/auth/operators') return reply([{ id: 'operator-1', username: 'fixture', full_name: 'Fixture Operator', role: 'Operator', status: 'Active' }])
    if (path === '/api/v1/scans') return reply({ items: state.scans, total: state.scans.length, page: 1, page_size: 100 })
    if (path === '/api/v1/cameras') return reply([{ device_id: 1, camera_id: 'CAM-001', label: 'Top', online: true }])
    if (path === '/api/v1/config') return reply({ camera_ids: '', confidence_threshold: 85, revision: 1 })
    if (path === '/api/v1/suppliers') return reply([{ id: 'supplier-1', name: 'Fixture Supplier', status: 'Active' }])
    if (path === '/api/v1/activity' || path === '/api/v1/users') return reply({ items: [], total: 0, page: 1, page_size: 100 })
    return reply([])
  })
  await page.goto(`${runtime.url}/logs`, { waitUntil: 'domcontentloaded' })
  await page.clock.resume()
  await page.getByText('Fixture Operator', { exact: true }).last().click()
  for (const digit of ['1', '3', '5', '7']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  return { page, state }
}

const writesTo = (state, suffix) => state.writes.filter(item => item.path.endsWith(suffix))

for (const [change, user] of [
  ['account switch', { id: 'different-operator', username: 'other', fullName: 'Other Operator', role: 'Operator' }],
  ['role change', { id: 'operator-1', username: 'fixture', fullName: 'Fixture Operator', role: 'Admin' }],
  ['logout', null],
]) {
  test(`kiosk resets operator selection after ${change}`, async t => {
    const { page, state } = await setup(t)
    await page.getByRole('button', { name: 'Select Source', exact: false }).click()
    await page.getByRole('button', { name: /Fixture Supplier/ }).click()
    await page.getByRole('button', { name: 'Start Intake Session', exact: true }).click()
    const scanButton = page.getByRole('button', { name: 'Scan Now', exact: true, includeHidden: true })
    await scanButton.waitFor()
    assert.equal(await scanButton.isEnabled(), true)
    await page.evaluate(value => window.kioskAuthTest.setUser(value), user)
    await page.getByRole('dialog').waitFor()
    assert.equal(await scanButton.isDisabled(), true)
    await page.getByText('No Operator', { exact: true }).waitFor()
    assert.equal(writesTo(state, '/scans/trigger').length, 0)
  })
}

test('kiosk offers real scans only and requires an intake before scanning', async t => {
  const { page, state } = await setup(t)
  assert.equal(state.writes.length, 0)
  assert.equal(await page.getByRole('button', { name: /demo/i }).count(), 0)
  assert.equal(await page.getByRole('combobox', { name: 'Demo prediction' }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isDisabled(), true)
  assert.equal(await page.getByAltText('Live Camera Feed - Top').evaluate(image => getComputedStyle(image).objectFit), 'contain')
  assert.deepEqual(JSON.parse(await page.getByTestId('persisted-scans').textContent()), { ids: [scanId] })
  const empty = await setup(t, { empty: true })
  assert.equal(await empty.page.getByRole('button', { name: /demo/i }).count(), 0)
  assert.equal(await empty.page.getByRole('button', { name: 'Scan Now', exact: true }).isDisabled(), true)
  assert.equal(writesTo(state, '/kiosk-demo').length, 0)
  assert.equal(empty.state.writes.length, 0)
})

test('normal kiosk scans its intake once, polls the existing print job and accepts the result', async t => {
  const { page, state } = await setup(t)
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isDisabled(), true)
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('Scan Complete', { exact: true }).waitFor()
  await page.getByText('Sent to TP870 S. Check the printed label.', { exact: true }).waitFor()
  assert.equal(writesTo(state, '/trigger').length, 1)
  assert.deepEqual(writesTo(state, '/trigger')[0].body, { intake_id: 'fixture-intake' })
  await page.getByRole('button', { name: 'Accept', exact: true }).click()
  await page.getByRole('button', { name: 'Accepted', exact: true }).waitFor()
  assert.equal(writesTo(state, '/kiosk-demo').length, 0)
  assert.equal(writesTo(state, '/print').length, 0)
  assert.equal(state.jobs.size, 1)
  assert.deepEqual(JSON.parse(await page.getByTestId('persisted-scans').textContent()), {
    ids: ['20000000-0000-4000-8000-000000000002', scanId], lastResult: '20000000-0000-4000-8000-000000000002',
  })
})

test('normal scan can retry its existing offline print job and flag the persisted result', async t => {
  const { page, state } = await setup(t, { offline: true })
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('TP870 S is OFFLINE', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'RETRY PRINT', exact: true }).dblclick()
  await page.getByText('Sent to TP870 S. Check the printed label.', { exact: true }).waitFor()
  assert.equal(writesTo(state, '/retry').length, 1)
  assert.equal(state.jobs.size, 1)
  await page.getByRole('button', { name: 'Flag for Review', exact: true }).click()
  await page.getByRole('button', { name: 'Flagged', exact: true }).waitFor()
  assert.equal(writesTo(state, '/flag').length, 1)
  assert.equal(state.scans[0].flagged, true)
  assert.equal(writesTo(state, '/kiosk-demo').length, 0)
})

test('a live scan requiring review makes the flag visible to the operator', async t => {
  const { page, state } = await setup(t, { flagged: true })
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('Scan Complete - Review Needed', { exact: true }).waitFor()
  assert.equal(writesTo(state, '/trigger').length, 1)
})

const opposingViews = ['Top', 'Left', 'Right', 'Rear'].map((camera_label, index) => ({
  camera_id: `CAM-00${index + 1}`, camera_label,
  detected_cultivar: index % 2 === 0 ? 'Lakatan' : 'Latundan',
  detected_ripeness: 'Ripe', confidence: index % 2 === 0 ? 65 : 90,
  finger_count: 5, bounding_boxes: [], inference_time_ms: 1,
}))

for (const mode of ['ai', 'cultivar_override', 'count_override']) {
  const corrected = mode === 'cultivar_override'
  test(`a split-view cultivar ${mode}: ${corrected ? 'preserves a human cultivar correction' : 'displays uncertainty and withholds dependent estimates'}`, async t => {
    const { page, state } = await setup(t, { scanOverrides: {
      cultivar: corrected ? 'Lakatan' : 'Latundan', confidence: 77.9,
      detections: opposingViews, is_overridden: mode !== 'ai',
      original_ai_result: mode !== 'ai' ? { cultivar: 'Latundan', confidence: 77.9, finger_count: 16 } : null,
      finger_count: mode === 'count_override' ? 17 : 16,
    } })
    await page.getByRole('button', { name: 'Select Source', exact: false }).click()
    await page.getByText('Fixture Supplier', { exact: true }).click()
    await page.getByRole('button', { name: /Start.*Intake/i }).click()
    await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
    await page.getByText(corrected ? 'Scan Complete' : 'Scan Complete - Review Needed', { exact: true }).waitFor()
    const cultivar = page.getByText('Cultivar', { exact: true }).locator('..')
    const confidence = page.getByText('Confidence', { exact: true }).locator('..')
    const spoilage = page.getByText('Est. Spoilage', { exact: true }).locator('..')
    assert.match(await cultivar.textContent(), corrected ? /Lakatan/ : /Uncertain/)
    assert.match(await confidence.textContent(), corrected ? /77\.9%/ : /—/)
    assert.match(await spoilage.textContent(), corrected ? /3-5.*days/ : /—/)
    assert.equal(await page.getByText(/Cameras disagree/).count(), corrected ? 0 : 1)
    if (!corrected) {
      assert.match(await page.getByRole('status').filter({ hasText: /Cameras disagree/ }).textContent(), /Top \+ Right: Lakatan; Left \+ Rear: Latundan/)
    }
    assert.equal(state.scans[0].cultivar, corrected ? 'Lakatan' : 'Latundan')
    assert.equal(state.scans[0].confidence, 77.9)
    assert.equal(writesTo(state, '/trigger').length, 1)
  })
}
