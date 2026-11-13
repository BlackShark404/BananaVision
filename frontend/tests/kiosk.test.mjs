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

async function setup(t, { offline = false, empty = false, flagged = false, scanOverrides = {}, timezoneId, intakes = [], history } = {}) {
  const context = await runtime.browser.newContext({ viewport: { width: 1600, height: 1000 }, timezoneId })
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
  const state = { writes: [], jobs: new Map(), scans: empty ? [] : history ?? [saved] }
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
        if (state.triggerHold) await state.triggerHold
        if (state.triggerFailure) return route.fulfill({ status: state.triggerStatus ?? 422, headers, json: state.triggerFailure })
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
    if (path === '/api/v1/intakes') return reply(intakes)
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

for (const [raw, displayed] of [['0.9938128387987426', '1 day'], ['3.487', '3–4 days'], ['1-2', '1–2 days']]) {
  test(`kiosk formats stored ${raw} consistently in result and recent scans`, async t => {
    const { page, state } = await setup(t, { scanOverrides: { spoilage_days: raw } })
    await page.getByRole('button', { name: 'Select Source', exact: false }).click()
    await page.getByText('Fixture Supplier', { exact: true }).click()
    await page.getByRole('button', { name: /Start.*Intake/i }).click()
    await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
    await page.getByText('Scan Complete', { exact: true }).waitFor()
    const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
    assert.match(await metric.innerText(), new RegExp(displayed))
    assert.equal(state.scans[0].spoilage_days, raw)
    assert.equal(await page.getByText(displayed, { exact: true }).count(), 2)
  })
}

test('kiosk header clock shows Asia/Manila time in a Los Angeles browser', async t => {
  // 04:00 UTC is noon in Manila and 21:00 the evening before in Los Angeles.
  const { page } = await setup(t, { timezoneId: 'America/Los_Angeles' })
  await page.getByText(/^12:0\d:\d\d PM$/).waitFor()
  assert.equal(await page.getByText(/^09:0\d:\d\d PM$/).count(), 0)
})

test('kiosk recent scans count an old estimate down instead of repeating it', async t => {
  const aged = (suffix, extra) => ({ ...saved, id: scanId.replace(/1$/, suffix), spoilage_days: '1-3', ...extra })
  const week = { min_days: 1, max_days: 3, elapsed_days: 7, remaining_min_days: 0, remaining_max_days: 0,
    days_past: 4, state: 'expired', scan_date: '2026-09-25', as_of_date: '2026-10-02' }
  const history = [
    aged('1', { remaining_days: -5, risk_as_of: '2026-10-02T12:00:00+08:00', shelf_life_window: week }),
    aged('2', { remaining_days: 1, risk_as_of: '2026-10-02T12:00:00+08:00', shelf_life_window: {
      ...week, elapsed_days: 1, remaining_max_days: 2, days_past: 0, state: 'active', scan_date: '2026-10-01' } }),
    aged('3', { inventory_status: 'Sold', shelf_life_window: week }),
  ]
  const { page } = await setup(t, { history })
  await page.getByText('Overdue', { exact: true }).waitFor()
  assert.equal(await page.getByText('Overdue', { exact: true }).count(), 1)
  assert.equal(await page.getByText('0–2 days left', { exact: true }).count(), 1)
  assert.equal(await page.getByText('1–3 days', { exact: true }).count(), 1)  // the sold scan keeps its estimate
  await page.screenshot({ path: 'node_modules/.tmp/bv-shelf-life-kiosk.png', fullPage: true })
  assert.equal(history[0].spoilage_days, '1-3')
})

for (const vpd of [0, 1.2, null]) {
  test(`stored kiosk result keeps Manila time and VPD ${vpd} without live-reading fallback`, async t => {
    const { page } = await setup(t, { timezoneId: 'America/Los_Angeles', scanOverrides: {
      temperature: 0, humidity: 100, vpd, confidence: 0,
    } })
    await page.getByRole('button', { name: 'Select Source', exact: false }).click()
    await page.getByText('Fixture Supplier', { exact: true }).click()
    await page.getByRole('button', { name: /Start.*Intake/i }).click()
    await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
    const header = page.getByText('Scan Complete', { exact: true }).locator('..')
    await header.waitFor()
    assert.match(await header.textContent(), /3:00:00 PM/)
    await page.getByText('0°C', { exact: true }).waitFor()
    assert.match(await page.getByText('Confidence', { exact: true }).locator('..').textContent(), /0%/)
    if (vpd === null) assert.equal(await page.getByText('VPD', { exact: true }).count(), 0)
    else await page.getByText(`${vpd.toFixed(3)} kPa`, { exact: true }).waitFor()
  })
}

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
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent.trim() === 'Scan Now' && !button.disabled))
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

test('kiosk resumes the open active intake instead of creating a duplicate', async t => {
  const { page, state } = await setup(t, { intakes: [{
    id: 'restored-intake', supplier_id: 'supplier-1', supplier_name: 'Fixture Supplier',
    batch_number: 'BCH-OPEN', status: 'Active', intake_date: '2026-10-14', scan_count: 0,
  }] })
  await page.getByText(/Fixture Supplier \(BCH-OPEN\)/).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isEnabled(), true)
  assert.equal(state.writes.length, 0)
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
  const counts = [7, 9, 10, 13]
  const detections = ['Top', 'Left', 'Right', 'Rear'].map((camera_label, index) => ({
    camera_id: `CAM-00${index + 1}`, camera_label, detected_cultivar: 'Lakatan',
    detected_ripeness: 'Ripe', confidence: 95, finger_count: counts[index],
    bounding_boxes: [], inference_time_ms: 1,
  }))
  const { page, state } = await setup(t, { flagged: true,
    scanOverrides: { finger_count: 13, detections },
  })
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('Scan Complete - Review Needed', { exact: true }).waitFor()
  assert.equal(await page.getByText('Estimated Fingers', { exact: true }).locator('..').locator('p').last().innerText(), '13')
  await page.getByText('13 fingers', { exact: true }).waitFor()
  assert.deepEqual(state.scans[0].detections.map(view => view.finger_count), counts)
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
    assert.match(await spoilage.textContent(), corrected ? /3–5.*days/ : /—/)
    assert.equal(await page.getByText(/Cameras disagree/).count(), corrected ? 0 : 1)
    if (!corrected) {
      assert.match(await page.getByRole('status').filter({ hasText: /Cameras disagree/ }).textContent(), /Top \+ Right: Lakatan; Left \+ Rear: Latundan/)
      await page.getByText('Cultivar uncertain', { exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Review required', exact: true }).isDisabled(), true)
      assert.equal(await page.getByText('Uncertain', { exact: true }).count(), 2)
      assert.equal(await page.getByText(/Review needed/).count(), 1)
    } else {
      assert.equal(await page.getByText('Cultivar uncertain', { exact: true }).count(), 0)
      assert.equal(await page.getByRole('button', { name: 'Accept', exact: true }).isEnabled(), true)
      assert.equal(await page.getByText('Uncertain', { exact: true }).count(), 0)
      assert.equal(await page.getByText(/Review needed/).count(), 0)
    }
    assert.equal(state.scans[0].cultivar, corrected ? 'Lakatan' : 'Latundan')
    assert.equal(state.scans[0].confidence, 77.9)
    assert.equal(writesTo(state, '/trigger').length, 1)
  })
}

test('kiosk detection lightbox modal separates the Hide Boxes button from the close icon without overlap', async t => {
  const images = [{ camera_id: 'CAM-001', file_path: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"></svg>' }]
  const detections = [{
    camera_id: 'CAM-001', camera_label: 'Top',
    bounding_boxes: [{ x: 10, y: 10, w: 50, h: 50, cls: 'lakatan', conf: 0.9 }],
    finger_count: 1,
  }]
  const { page } = await setup(t, { scanOverrides: { images, detections } })
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('Scan Complete', { exact: true }).waitFor()

  const thumbnail = page.getByRole('button', { name: /CAM-001 detection/i })
  await thumbnail.click()

  const dialog = page.getByRole('dialog')
  await dialog.waitFor({ state: 'visible' })

  const hideBoxesBtn = dialog.getByRole('button', { name: /Hide.*Boxes/i })
  const closeBtn = dialog.getByRole('button', { name: 'Close', exact: true })

  await hideBoxesBtn.waitFor({ state: 'visible' })
  await closeBtn.waitFor({ state: 'visible' })

  const hideBoxesBox = await hideBoxesBtn.boundingBox()
  const closeBox = await closeBtn.boundingBox()

  assert.ok(hideBoxesBox, 'Hide Boxes button must have a bounding box')
  assert.ok(closeBox, 'Close button must have a bounding box')

  assert.ok(
    hideBoxesBox.x + hideBoxesBox.width <= closeBox.x - 10,
    `Hide Boxes right edge (${hideBoxesBox.x + hideBoxesBox.width}) must be at least 10px to the left of close icon (${closeBox.x})`
  )

  await hideBoxesBtn.click()
  const showBoxesBtn = dialog.getByRole('button', { name: /Show.*Boxes/i })
  await showBoxesBtn.waitFor({ state: 'visible' })

  await closeBtn.click()
  await dialog.waitFor({ state: 'hidden' })
})

const rejection = {
  detail: 'No Lakatan, Latundan, or Cardaba detected. Place a supported banana hand on the tray and scan again.',
  code: 'ood_rejected', status: 'rejected', is_ood: true, reason: 'no_banana',
}
const rejectionHeading = 'No Lakatan, Latundan, or Cardaba detected'

async function scanFromNewIntake(page) {
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
}

test('rejected scan shows the no-cultivar state once, saves nothing and clears on the next scan', async t => {
  const { page, state } = await setup(t)
  state.triggerFailure = rejection
  await scanFromNewIntake(page)
  const card = page.getByRole('status').filter({ hasText: 'Nothing was saved.' })
  await card.waitFor()
  assert.equal(await card.getByText(rejectionHeading, { exact: true }).count(), 1)
  assert.match(await card.innerText(), /Place a supported banana hand on the tray and scan again\./)
  // The same refusal also arrives over the WebSocket; the operator sees one notice.
  await page.evaluate(data => window.dashboardSocket.emit('scan:failed', data), {
    scan_id: 'rejected-scan', error: rejection.detail, stage: 'pipeline',
    code: rejection.code, status: rejection.status, is_ood: true, reason: rejection.reason,
  })
  const notices = page.locator('[data-sonner-toast]').filter({ hasText: rejection.detail })
  await notices.first().waitFor()
  assert.equal(await notices.count(), 1)
  assert.equal(await card.count(), 1)
  // No cultivar, confidence or spoilage estimate is presented for a rejected scan.
  assert.equal(await page.getByText('Scan Complete', { exact: false }).count(), 0)
  assert.equal(await page.getByText('Est. Spoilage', { exact: true }).count(), 0)
  assert.deepEqual(JSON.parse(await page.getByTestId('persisted-scans').textContent()), { ids: [scanId] })
  assert.equal(state.scans.length, 1)
  // The station is ready again. Starting the next scan clears the rejected state
  // while that scan is still running, before any result exists.
  state.triggerFailure = null
  let release
  state.triggerHold = new Promise(resolve => { release = resolve })
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByRole('button', { name: /Scanning/ }).waitFor()
  assert.equal(await page.getByText(rejectionHeading, { exact: true }).count(), 0)
  assert.equal(await page.getByText('Scan Complete', { exact: false }).count(), 0)
  release()
  await page.getByText('Scan Complete', { exact: true }).waitFor()
  assert.equal(await page.getByText(rejectionHeading, { exact: true }).count(), 0)
  assert.equal(writesTo(state, '/trigger').length, 2)
})

test('each rejected scan gets its own notice', async t => {
  const { page, state } = await setup(t)
  state.triggerFailure = rejection
  await scanFromNewIntake(page)
  const notices = page.locator('[data-sonner-toast]').filter({ hasText: rejection.detail })
  await notices.first().waitFor()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  // The second refusal is not merged into the first scan's notice.
  await page.waitForFunction(text => [...document.querySelectorAll('[data-sonner-toast]')]
    .filter(toast => toast.textContent.includes(text)).length === 2, rejection.detail)
  assert.equal(writesTo(state, '/trigger').length, 2)
})

test('a station fault stays on screen as an alert, not as a banana rejection', async t => {
  const { page, state } = await setup(t)
  const fault = {
    detail: 'Banana verification is unavailable, so the scan was not classified. Ask an administrator to check the detection models.',
    code: 'ood_gate_unavailable', status: 'unavailable', is_ood: false, reason: 'ood_gate_unavailable',
  }
  state.triggerStatus = 503
  state.triggerFailure = fault
  await scanFromNewIntake(page)
  const card = page.getByRole('alert').filter({ hasText: 'Scan could not run' })
  await card.waitFor()
  assert.match(await card.innerText(), /Banana verification is unavailable/)
  assert.match(await card.innerText(), /Nothing was saved\./)
  assert.equal(await page.getByText(rejectionHeading, { exact: true }).count(), 0)
  assert.equal(await page.getByText('No scans yet', { exact: true }).count(), 0)
  // The WebSocket report of the same fault does not add a second notice.
  await page.evaluate(data => window.dashboardSocket.emit('scan:failed', data), {
    scan_id: 'refused-scan', error: fault.detail, stage: 'pipeline', code: fault.code, reason: fault.reason,
  })
  assert.equal(await page.locator('[data-sonner-toast]').filter({ hasText: fault.detail }).count(), 1)
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isEnabled(), true)
})

test('rejection delivered only over the WebSocket shows the same state', async t => {
  const { page } = await setup(t)
  await page.getByText('No scans yet', { exact: true }).waitFor()
  await page.evaluate(data => window.dashboardSocket.emit('scan:failed', data), {
    scan_id: 'rejected-scan', error: rejection.detail, stage: 'pipeline',
    code: rejection.code, reason: 'no_target_cultivar',
  })
  await page.getByText(rejectionHeading, { exact: true }).waitFor()
  assert.equal(await page.getByText('No scans yet', { exact: true }).count(), 0)
})

test('ordinary scan failure keeps the empty state and reports only the error', async t => {
  const { page, state } = await setup(t)
  // A legacy or unrelated failure has no rejection code, and a text `status` in the
  // body must not turn it into one.
  state.triggerFailure = { detail: 'BananaClassifier: Model not loaded.', status: 'rejected' }
  await scanFromNewIntake(page)
  await page.locator('[data-sonner-toast]').filter({ hasText: 'BananaClassifier: Model not loaded.' }).waitFor()
  // The operator wording sent over the WebSocket is not replaced by the HTTP wording.
  await page.evaluate(() => window.dashboardSocket.emit('scan:failed', {
    scan_id: 'failed-scan', error: 'Model not loaded. Ask an administrator.', stage: 'pipeline',
  }))
  await page.locator('[data-sonner-toast]').filter({ hasText: 'Model not loaded. Ask an administrator.' }).waitFor()
  assert.equal(await page.locator('[data-sonner-toast]').filter({ hasText: 'BananaClassifier: Model not loaded.' }).count(), 1)
  assert.equal(await page.getByText(rejectionHeading, { exact: true }).count(), 0)
  assert.equal(await page.getByRole('alert').filter({ hasText: 'Scan could not run' }).count(), 0)
  assert.equal(await page.getByText('No scans yet', { exact: true }).count(), 1)
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isEnabled(), true)
})
