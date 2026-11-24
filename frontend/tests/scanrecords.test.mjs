import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'scanrecords.fixture.tsx', auth: 'persistence.auth.tsx', port: 5197 }) })
after(async () => { await runtime?.close() })
const id = '10000000-0000-4000-8000-000000000001'
const scan = () => ({
  id, revision: 1, date_time: '2024-05-05T08:10:00+08:00', cultivar: 'Lakatan', ripeness: 'Ripe',
  confidence: 92, spoilage_days: '3', finger_count: 7, operator_name: 'Historical Operator',
  source_text: 'Original source', inventory_status: 'In Stock', flagged: false, has_notes: true,
  images: [{ camera_id: 'OLD-CAMERA', file_path: `/captures/${id}/old.jpg` }],
  detections: [{ camera_id: 'OLD-CAMERA', camera_label: 'Original Top Camera', bounding_boxes: [], captured_at: '2024-05-05T08:10:00+08:00' }],
  notes: [{ id: 'old-note', scan_id: id, text: 'Recorded review note', author_name: 'Former Admin', timestamp: '2024-05-05T08:10:00+08:00' }],
  history: [{ id: 'event-1', kind: 'status', timestamp: '2024-05-05T08:10:00+08:00', actor_name: 'Former Admin', actor_id: null, reason: 'Received delivery', previous_values: null, new_values: { inventory_status: 'In Stock' }, revision: 1, legacy: false }],
})

async function setup(t, status = 200, options = {}) {
  const context = await runtime.browser.newContext({ timezoneId: 'America/Los_Angeles' })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.setDefaultNavigationTimeout(30000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const state = { record: scan(), writes: [], requests: [], imageHeaders: null, ...options }
  await page.route('**/captures/**', async route => {
    state.imageHeaders = route.request().headers()
    const image = state.imageFixtures?.[new URL(route.request().url()).pathname]
    if (image) return route.fulfill({ contentType: 'image/svg+xml', body: image,
      headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' } })
    await route.fulfill({ status: 404, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' } })
  })
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), method = request.method()
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }
    const reply = (json, code = 200) => route.fulfill({ status: code, json, headers }).catch(() => {})
    if (method === 'OPTIONS') return reply({}, 204)
    state.requests.push({ path: url.pathname, method, query: Object.fromEntries(url.searchParams) })
    if (url.pathname === `/api/v1/scans/${id}` && method === 'GET') {
      const snapshot = structuredClone(state.record)
      const hold = state.holdReadOnce; state.holdReadOnce = null
      if (hold) await hold()
      const code = state.readStatus ?? status
      return reply(code === 200 ? snapshot : { detail: 'Unavailable' }, code)
    }
    if (url.pathname === '/api/v1/scan-logs/export') return route.fulfill({ status: 200, body: 'id,name\n1,Frozen\n', headers: { ...headers, 'content-type': 'text/csv' } })
    if (url.pathname === '/api/v1/scan-logs/pending') {
      if (state.pendingStatus) return reply({ detail: 'Live scan count unavailable' }, state.pendingStatus)
      if (state.pendingResponse) return reply(state.pendingResponse(Object.fromEntries(url.searchParams)))
      return reply({ snapshot_id: url.searchParams.get('snapshot_id'), new_count: state.pendingCount ?? 0,
        generated_at: state.record.date_time })
    }
    if (['/api/v1/scan-logs', '/api/v1/scan-logs/reconcile'].includes(url.pathname)) {
      const replyPage = data => reply(url.pathname.endsWith('/reconcile') ? {
        ...data, at_risk_ids: data.at_risk_ids ?? (data.at_risk_count ? data.items.slice(0, data.at_risk_count).map(row => row.id) : []),
      } : data)
      if (state.logResponse) return replyPage(state.logResponse(Object.fromEntries(url.searchParams)))
      if (state.logStatus) return reply({ detail: 'Too many records for a browse snapshot. Narrow filters or export.' }, state.logStatus)
      if (state.expire && url.searchParams.get('snapshot_id')) return reply({ detail: 'Browse snapshot expired. Refresh.' }, 410)
      const search = url.searchParams.get('search') || 'Initial'
      if (search === 'Slow' && state.holdSearch) await state.holdSearch()
      const isRisk = url.searchParams.get('attention') === 'at-risk'
      const pageSize = Number(url.searchParams.get('page_size') || 10)
      const total = isRisk ? 1 : 201
      return replyPage({ items: [{ ...state.record, source_name: search, remaining_days: 1, temperature: null, humidity: null }], total,
        snapshot_id: url.searchParams.get('snapshot_id') || state.snapshotToken || 'snapshot-one', page: Number(url.searchParams.get('page') || 1), page_size: pageSize, avg_confidence: 92, at_risk_count: state.atRiskCount ?? (isRisk ? 1 : 0), review_count: 0,
        options: { sources: [], operators: [] }, generated_at: state.record.date_time })
    }
    if (url.pathname === '/api/v1/intakes/intake-1/scan-revisions') return reply({ revisions: { [id]: state.record.revision } })
    if (url.pathname === '/api/v1/intakes' && options.screen === 'intakes') return reply([{ id: 'intake-1', source: 'Supplier', intake_date: '2026-10-02', status: 'Active', scan_count: 1 }])
    if (url.pathname === '/api/v1/scans') return reply({ items: options.screen === 'quality' ? [state.listRecord ?? state.record] : options.screen === 'intakes' ? [{ ...state.record, intake_id: 'intake-1' }] : [], page: 1, page_size: 100, total: ['intakes', 'quality'].includes(options.screen) ? 1 : 0 })
    if (url.pathname === '/api/v1/config') return reply({ camera_ids: 'NEW-CAMERA', confidence_threshold: 85, revision: 1 })
    if (url.pathname === '/api/v1/activity') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (url.pathname === '/api/v1/users') return reply({ items: [], total: 0 })
    if (url.pathname === '/api/v1/scans/trigger' && state.triggerResponse) return reply(await state.triggerResponse())
    if (method === 'GET') return reply([])
    state.writes.push({ ...request.postDataJSON(), path: url.pathname })
    if (state.writeStatus) return reply({ detail: 'This retry was rejected. Review your access and input.' }, state.writeStatus)
    if (state.onWrite) {
      const result = await state.onWrite(request.postDataJSON(), url.pathname)
      if (state.loseResponseOnce) { state.loseResponseOnce = false; return route.abort('failed') }
      return reply(result)
    }
    return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
  })
  await page.goto(`${runtime.url}${options.path ?? (options.screen === 'quality' ? '/scans/quality' : options.screen === 'logs' ? '/logs' : options.screen === 'intakes' ? '/scans/intakes' : `/scans/${id}`)}`)
  return { page, state }
}

test('Logs keep readable ranges and risk snapshot membership while showing a live days-left label for in-stock rows', async t => {
  const records = [
    { ...scan(), id, spoilage_days: '3-6', remaining_days: 1.5, at_risk: true },
    { ...scan(), id: id.replace(/1$/, '2'), spoilage_days: '2.00001', remaining_days: 2, at_risk: false },
    { ...scan(), id: id.replace(/1$/, '3'), spoilage_days: '1-2', remaining_days: -1, inventory_status: 'Sold', at_risk: false },
    { ...scan(), id: id.replace(/1$/, '4'), spoilage_days: null, remaining_days: null, at_risk: false },
  ]
  const queries = []
  let snapshotId = 'snapshot-one'
  const logResponse = params => {
    queries.push(params)
    if (!params.snapshot_id && params.attention !== 'at-risk') snapshotId = `snapshot-${queries.length}`
    const selected = params.attention === 'at-risk' ? records.filter(row => row.at_risk) : records
    return {
      items: selected.map(({ at_risk: _fixtureRisk, ...row }) => ({ ...row, source_name: 'Stored source' })),
      total: params.attention === 'at-risk' ? 1 : 24, page: Number(params.page), page_size: Number(params.page_size || 10),
      at_risk_count: 1, avg_confidence: 92, review_count: 0, flagged_count: 0,
      at_risk_ids: records.filter(row => row.at_risk).map(row => row.id),
      generated_at: '2026-10-02T04:00:00Z', snapshot_id: params.snapshot_id || snapshotId,
      options: { sources: [], operators: [] },
    }
  }
  const { page } = await setup(t, 200, { screen: 'logs', logResponse })
  const table = page.getByRole('table')
  await table.getByText('Est. 3–6 days from scan', { exact: true }).waitFor()
  await table.getByText('Est. 2–3 days from scan', { exact: true }).waitFor()
  assert.equal(await table.getByText('1–2 days left', { exact: true }).count(), 1)
  assert.equal(await table.getByText('2 days left', { exact: true }).count(), 1)
  assert.equal(await table.getByText(/days left/).count(), 2)  // Sold and unknown rows do not count down.
  // The Sold row names its outcome and keeps the scan-time estimate in the same "Est. … from scan" line.
  await table.getByText('Sold · no countdown', { exact: true }).waitFor()
  await table.getByText('Est. 1–2 days from scan', { exact: true }).waitFor()
  assert.equal(await table.getByText('1–2 days', { exact: true }).count(), 0)
  assert.equal(await table.getByText(/from scan/).count(), 3)
  assert.equal(await table.getByRole('img', { name: 'At-risk scan', exact: true }).count(), 1)
  assert.equal(await table.getByText('Unknown days', { exact: true }).count(), 0)
  await table.getByText('Unknown', { exact: true }).waitFor()
  await page.screenshot({ path: 'node_modules/.tmp/bv-spoilage-logs.png', fullPage: true })
  await page.getByLabel('Go to next page').click()
  await until(() => queries.at(-1).page === '2')
  await page.getByText('At-Risk Scans', { exact: true }).click()
  await until(() => queries.at(-1).attention === 'at-risk' && queries.at(-1).page === '1')
  await until(async () => await table.getByRole('row').count() === 2)
  await table.getByRole('columnheader', { name: 'Est. Spoilage' }).click()
  await until(() => queries.at(-1).sort === 'spoilage_days')
  assert.equal(queries.at(-1).attention, 'at-risk')
  await until(async () => await page.getByRole('button', { name: 'Export CSV' }).isEnabled())
  assert.equal(await page.getByRole('button', { name: 'Refresh', exact: true }).count(), 0)
  const retainedSnapshot = snapshotId
  const before = queries.length
  await page.clock.runFor(31_000)
  await until(() => queries.length > before)
  assert.equal(queries.at(-1).snapshot_id, retainedSnapshot)
  assert.equal(queries.at(-1).attention, 'at-risk')
  await table.getByText('Est. 3–6 days from scan', { exact: true }).waitFor()
  assert.equal(await table.getByRole('img', { name: 'At-risk scan', exact: true }).count(), 1)
})

test('Logs ages the live days-left label from the snapshot time without changing the static estimate', async t => {
  const record = { ...scan(), spoilage_days: '5-7', remaining_days: 4 }
  const logResponse = params => ({
    items: [{ ...record, source_name: 'Stored source' }], total: 1,
    page: Number(params.page), page_size: Number(params.page_size || 10),
    at_risk_count: 0, avg_confidence: 92, review_count: 0, flagged_count: 0, at_risk_ids: [],
    generated_at: '2026-10-01T04:00:00Z', snapshot_id: 'snapshot-aging',
    options: { sources: [], operators: [] },
  })
  const { page } = await setup(t, 200, { screen: 'logs', logResponse })
  const table = page.getByRole('table')
  await table.getByText('3 days left', { exact: true }).waitFor()
  await table.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
})

const shelfWindow = (min, max, elapsed, asOf = '2026-10-02') => ({
  min_days: min, max_days: max, elapsed_days: elapsed,
  remaining_min_days: Math.max(0, min - elapsed), remaining_max_days: Math.max(0, max - elapsed),
  days_past: Math.max(0, elapsed - max),
  state: elapsed > max ? 'expired' : elapsed === max ? 'final_day' : 'active',
  scan_date: new Date(Date.parse(`${asOf}T00:00:00Z`) - elapsed * 86_400_000).toISOString().slice(0, 10),
  as_of_date: asOf,
})

test('Logs leads with the countdown in Manila calendar days and keeps the scan-time estimate beneath', async t => {
  const records = [
    { ...scan(), id, spoilage_days: '1-3', remaining_days: -5, shelf_life_window: shelfWindow(1, 3, 7) },
    { ...scan(), id: id.replace(/1$/, '2'), spoilage_days: '1-3', remaining_days: 1, shelf_life_window: shelfWindow(1, 3, 1) },
    { ...scan(), id: id.replace(/1$/, '3'), spoilage_days: '2', remaining_days: -3, inventory_status: 'Sold', shelf_life_window: shelfWindow(2, 2, 5) },
    // A row frozen before the window existed still shows the older aged number.
    { ...scan(), id: id.replace(/1$/, '4'), spoilage_days: '5-7', remaining_days: 4 },
    { ...scan(), id: id.replace(/1$/, '5'), spoilage_days: '4', remaining_days: 0, shelf_life_window: shelfWindow(4, 4, 4) },
  ]
  const logResponse = params => ({
    items: records.map(row => ({ ...row, source_name: 'Stored source' })), total: records.length,
    page: Number(params.page), page_size: Number(params.page_size || 10),
    at_risk_count: 0, avg_confidence: 92, review_count: 0, flagged_count: 0, at_risk_ids: [],
    generated_at: '2026-10-02T04:00:00Z', snapshot_id: 'snapshot-window',
    options: { sources: [], operators: [] },
  })
  const { page } = await setup(t, 200, { screen: 'logs', logResponse })
  const table = page.getByRole('table')
  await table.getByText('Overdue', { exact: true }).waitFor()
  assert.equal(await table.getByText('Overdue', { exact: true }).count(), 1)  // not the Sold row
  assert.equal(await table.getByText('0–2 days left', { exact: true }).count(), 1)
  assert.equal(await table.getByText('Final day', { exact: true }).count(), 1)
  assert.equal(await table.getByText('4 days left', { exact: true }).count(), 1)
  assert.equal(await table.getByText('Est. 1–3 days from scan', { exact: true }).count(), 2)
  assert.equal(await table.getByText('1–3 days', { exact: true }).count(), 0)  // never shown as today's value
  await table.getByText('Sold · no countdown', { exact: true }).waitFor()
  assert.equal(await table.getByText('Est. 2 days from scan', { exact: true }).count(), 1)  // the Sold row's estimate
  assert.equal(await table.getByText('2 days', { exact: true }).count(), 0)
  await page.screenshot({ path: 'node_modules/.tmp/bv-shelf-life-logs.png', fullPage: true })
  // Past Manila midnight the open list rolls over without waiting for new values.
  await page.clock.fastForward('12:01:00')
  await table.getByText('0–1 days left', { exact: true }).waitFor()
  assert.equal(await table.getByText('Overdue', { exact: true }).count(), 2)  // the 4-day estimate too
  assert.equal(await table.getByText('Est. 1–3 days from scan', { exact: true }).count(), 2)
})

for (const [elapsed, label] of [[0, '1–3 days left'], [1, '0–2 days left'], [2, '0–1 days left'], [3, 'Final day'], [4, 'Overdue'], [7, 'Overdue']]) {
  test(`ScanDetail shows ${label} for a 1-3 day estimate on day +${elapsed}`, async t => {
    const record = { ...scan(), spoilage_days: '1-3', remaining_days: 2 - elapsed,
      risk_as_of: '2026-10-02T04:00:00Z', inventory_eligible: true, shelf_life_window: shelfWindow(1, 3, elapsed) }
    const { page, state } = await setup(t, 200, { record })
    const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
    await metric.getByText(label, { exact: true }).waitFor()
    await metric.getByText('Est. 1–3 days from scan', { exact: true }).waitFor()
    assert.equal(await metric.getByText('1–3 days', { exact: true }).count(), 0)
    assert.equal(state.record.spoilage_days, '1-3')
    assert.deepEqual(state.writes, [])
  })
}

test('ScanDetail names the outcome and keeps the scan-time estimate for sold stock even when a window is sent', async t => {
  const record = { ...scan(), spoilage_days: '1-3', remaining_days: -5, inventory_status: 'Sold',
    risk_as_of: '2026-10-02T04:00:00Z', shelf_life_window: shelfWindow(1, 3, 7) }
  const { page } = await setup(t, 200, { record })
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('Sold · no countdown', { exact: true }).waitFor()
  await metric.getByText('Est. 1–3 days from scan', { exact: true }).waitFor()
  assert.equal(await metric.getByText(/days left|Final day|Overdue/).count(), 0)
})

for (const [status, outcome] of [['Spoiled', 'Spoiled · no countdown'], ['For Processing', 'For processing · no countdown']]) {
  test(`Quality Control shows ${outcome} with the estimate line`, async t => {
    const record = { ...scan(), spoilage_days: '4-5', remaining_days: -2, inventory_status: status,
      risk_as_of: '2026-10-02T04:00:00Z', shelf_life_window: shelfWindow(4, 5, 7) }
    const { page } = await setup(t, 200, { screen: 'quality', record })
    await page.locator('tbody tr').first().click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText(outcome, { exact: true }).waitFor()
    await dialog.getByText('Est. 4–5 days from scan', { exact: true }).waitFor()
    assert.equal(await dialog.getByText(/days left|Final day|Overdue/).count(), 0)
  })
}

test('QC shows the live countdown for in-stock scans', async t => {
  const record = { ...scan(), spoilage_days: '1-3', remaining_days: -5, shelf_life_window: shelfWindow(1, 3, 7) }
  const { page, state } = await setup(t, 200, { screen: 'quality', record })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('Overdue', { exact: true }).waitFor()
  await dialog.getByText('Est. 1–3 days from scan', { exact: true }).waitFor()
  assert.equal(await dialog.getByText('1–3 days', { exact: true }).count(), 0)
  assert.equal(state.record.spoilage_days, '1-3')
})

test('Scan Detail and Quality Control show Asia/Manila dates and times in a Los Angeles browser', async t => {
  // The scan is 08:10 on 5 May in Manila: 17:10 on 4 May in this browser's zone.
  const detail = await setup(t, 200)
  await detail.page.getByText('May 5, 2024', { exact: true }).waitFor()
  await detail.page.getByText('08:10 AM', { exact: true }).waitFor()
  await detail.page.getByText(/Former Admin • 5\/5\/2024, 8:10:00 AM/).waitFor()
  assert.equal(await detail.page.getByText('May 4, 2024', { exact: true }).count(), 0)
  const quality = await setup(t, 200, { screen: 'quality' })
  const row = quality.page.locator('tbody tr').first()
  await row.getByText('8:10:00 AM', { exact: true }).waitFor()
  assert.match(await row.innerText(), /\bMay 5\b/)
  assert.doesNotMatch(await row.innerText(), /\bMay 4\b/)
})

test('finger counts read "Est." on Scan Detail, Quality Control and Scan Logs; corrected counts and correction inputs do not', async t => {
  const detail = await setup(t, 200)
  const metric = detail.page.getByText('Est. Fingers', { exact: true }).locator('..')
  await metric.waitFor()
  assert.equal(await metric.locator('p').last().innerText(), '7')
  assert.equal(await detail.page.getByText('Finger Count', { exact: true }).count(), 0)
  await detail.page.getByRole('button', { name: 'Edit', exact: true }).first().click()
  // A person types the real count here, so the input is not labelled as an estimate.
  assert.equal(await detail.page.locator('label[for="edit-fingers"]').innerText(), 'Fingers')

  const corrected = { ...scan(), finger_count: 9, is_overridden: true,
    original_ai_result: { cultivar: 'Lakatan', ripeness: 'Ripe', confidence: 92, finger_count: 7, spoilage_days: '3' } }
  const fixed = await setup(t, 200, { record: corrected })
  const plain = fixed.page.getByText('Fingers', { exact: true }).first().locator('..')
  await plain.waitFor()
  assert.equal(await plain.locator('p').last().innerText(), '9')
  assert.equal(await fixed.page.getByText('Est. Fingers', { exact: true }).count(), 0)

  const quality = await setup(t, 200, { screen: 'quality' })
  await quality.page.locator('tbody tr').first().click()
  const dialog = quality.page.getByRole('dialog')
  await dialog.getByText('Est. Fingers', { exact: true }).waitFor()
  assert.equal(await dialog.getByText('Estimated Fingers', { exact: true }).count(), 0)
  await quality.page.getByRole('button', { name: 'Edit Data', exact: true }).click()
  assert.equal(await dialog.locator('label[for="fingers"]').innerText(), 'Fingers')

  const logs = await setup(t, 200, { screen: 'logs' })
  await logs.page.getByRole('columnheader', { name: 'Est. Fingers' }).waitFor()
  assert.equal(await logs.page.getByRole('columnheader', { name: 'Estimated Fingers' }).count(), 0)
})

test('Logs date picker marks today by the Asia/Manila calendar in a Los Angeles browser', async t => {
  // 04:00 UTC on 2 October is noon on 2 October in Manila and 21:00 on 1 October here.
  const { page } = await setup(t, 200, { screen: 'logs' })
  await page.getByRole('button', { name: 'Scan date', exact: true }).click()
  const today = page.locator('[role="gridcell"][data-today]')
  await today.waitFor()
  assert.equal(await today.getAttribute('data-day'), '2026-10-02')
})

const listRequests = state => state.requests.filter(r => r.path === '/api/v1/scan-logs')
const urlQuery = page => Object.fromEntries(new URL(page.url()).searchParams)

test('plain Scan Logs opens on all dates; a picked day can be cleared back to all dates', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.getByRole('button', { name: 'Scan date', exact: true }).getByText('All dates', { exact: true }).waitFor()
  await until(() => listRequests(state).length > 0)
  assert.equal(new URL(page.url()).search, '', 'the plain URL is kept')
  assert.ok(listRequests(state).every(r => r.query.business_date === undefined), JSON.stringify(listRequests(state)))
  assert.equal(await page.getByRole('button', { name: 'Reset', exact: true }).isDisabled(), true, 'all dates is the default view')
  // Pick 2 October (the Manila day), then clear it again.
  await page.getByRole('button', { name: 'Scan date', exact: true }).click()
  await page.locator('[role="gridcell"][data-day="2026-10-02"] button').click()
  await page.waitForURL('**/logs?date=2026-10-02')
  await until(() => listRequests(state).at(-1).query.business_date === '2026-10-02')
  assert.equal(await page.getByRole('button', { name: 'Reset', exact: true }).isDisabled(), false)
  await page.getByRole('button', { name: 'Clear scan date', exact: true }).click()
  await page.getByRole('button', { name: 'Scan date', exact: true }).getByText('All dates', { exact: true }).waitFor()
  await until(() => listRequests(state).at(-1).query.business_date === undefined)
  assert.equal(urlQuery(page).date, undefined)
})

test('Expiring stock opens every date, and Reset returns to plain Scan Logs', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs', path: '/logs?attention=at-risk' })
  await page.getByText('At-Risk Scans', { exact: true }).first().waitFor()
  await page.getByRole('button', { name: 'Scan date', exact: true }).getByText('All dates', { exact: true }).waitFor()
  await until(() => listRequests(state).length > 0)
  assert.ok(listRequests(state).every(r => r.query.business_date === undefined && r.query.attention === 'at-risk'))
  assert.deepEqual(urlQuery(page), { attention: 'at-risk' })
  await page.getByRole('button', { name: 'Reset', exact: true }).click()
  await until(() => new URL(page.url()).search === '')
  await until(() => listRequests(state).at(-1).query.attention === 'all')
  assert.equal(listRequests(state).at(-1).query.business_date, undefined)
  await page.getByRole('button', { name: 'Scan date', exact: true }).getByText('All dates', { exact: true }).waitFor()
})

test('the review queue shows Status Flagged and its banner; clearing it shows all dates', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs', path: '/logs?status=Flagged' })
  await page.getByText('Pending Quality Reviews', { exact: true }).waitFor()
  await page.getByRole('combobox').filter({ hasText: 'Flagged' }).waitFor()
  assert.equal(await page.getByRole('combobox').filter({ hasText: 'All Statuses' }).count(), 0)
  await until(() => listRequests(state).length > 0)
  assert.ok(listRequests(state).every(r => r.query.flagged_only === 'true' && r.query.business_date === undefined))
  await page.getByRole('button', { name: 'Clear review filter', exact: true }).click()
  await page.getByRole('combobox').filter({ hasText: 'All Statuses' }).waitFor()
  assert.equal(await page.getByText('Pending Quality Reviews', { exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Scan date', exact: true }).getByText('All dates', { exact: true }).waitFor()
  await until(() => listRequests(state).at(-1).query.flagged_only !== 'true')
  assert.equal(listRequests(state).at(-1).query.business_date, undefined)
})

test('legacy review links become Status Flagged before the first request', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs', path: '/logs?attention=review' })
  await page.waitForURL('**/logs?status=Flagged')
  await page.getByRole('combobox').filter({ hasText: 'Flagged' }).waitFor()
  await until(() => listRequests(state).length > 0)
  assert.ok(listRequests(state).every(r => r.query.attention !== 'review' && r.query.flagged_only === 'true'), JSON.stringify(listRequests(state)))
})

test('an unflagged low-confidence scan reads Low confidence, not pending review, in Details and Quality Control', async t => {
  // A person removed the flag after checking it; the threshold is 85 (mocked /config).
  const record = { ...scan(), confidence: 60, flagged: false }
  const detail = await setup(t, 200, { record })
  await detail.page.getByText('Low confidence', { exact: true }).first().waitFor()
  assert.equal(await detail.page.getByText('Needs Review', { exact: true }).count(), 0)
  assert.equal(await detail.page.getByText('Verified', { exact: true }).count(), 0)

  const quality = await setup(t, 200, { screen: 'quality', listRecord: record, record })
  const table = quality.page.getByRole('table')
  await table.getByText('Low confidence', { exact: true }).waitFor()
  assert.equal(await table.getByText('Review', { exact: true }).count(), 0)
})

test('decimal spoilage displays a readable range in Logs and Details without changing stored values', async t => {
  const raw = '4.861489519142744'
  const record = { ...scan(), spoilage_days: raw,
    history: [{ ...scan().history[0], kind: 'correction', previous_values: { spoilage_days: '3.487' }, new_values: { spoilage_days: raw } }] }
  const { page, state } = await setup(t, 200, { record })
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.waitFor()
  assert.match(await metric.innerText(), /4–5 days/)
  await page.getByText('spoilage days: 3–4 days → 4–5 days', { exact: true }).waitFor()
  assert.doesNotMatch(await page.locator('main').innerText(), /4\.861489519142744/)
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click()
  assert.equal(await page.locator('#edit-spoilage').inputValue(), '4–5')
  await page.locator('#edit-fingers').fill('9')
  await page.getByLabel('Reason for change').fill('Count verified')
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await until(() => state.writes.length === 1)
  assert.equal(state.writes[0].spoilage_days, undefined)
  assert.equal(state.record.spoilage_days, raw)
  await page.getByRole('link', { name: 'Test logs link' }).click()
  await page.getByRole('table').getByText('Est. 4–5 days from scan', { exact: true }).waitFor()
  assert.doesNotMatch(await page.getByRole('table').innerText(), /4\.861489519142744/)
})

test('ScanDetail shows a live countdown for in-stock scans beside the scan-time estimate', async t => {
  const record = { ...scan(), spoilage_days: '5-7', remaining_days: 4,
    risk_as_of: '2026-10-01T04:00:00Z', inventory_eligible: true }
  const { page } = await setup(t, 200, { record })
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('3 days left', { exact: true }).waitFor()
  await metric.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
})

test('ScanDetail shows the outcome and the estimate line for scans that are no longer in stock', async t => {
  const record = { ...scan(), spoilage_days: '5-7', remaining_days: 4,
    risk_as_of: '2026-10-01T04:00:00Z', inventory_status: 'Sold' }
  const { page } = await setup(t, 200, { record })
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('Sold · no countdown', { exact: true }).waitFor()
  await metric.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
  assert.equal(await metric.getByText('5–7 days', { exact: true }).count(), 0)
  assert.equal(await metric.getByText(/days left|Overdue/).count(), 0)
})

const splitViews = ['Top', 'Left', 'Right', 'Rear'].map((camera_label, index) => ({
  camera_id: `CAM-00${index + 1}`, camera_label,
  detected_cultivar: index % 2 === 0 ? 'Lakatan' : 'Latundan',
  detected_ripeness: 'Ripe', confidence: index % 2 === 0 ? 65 : 90,
  finger_count: 5, bounding_boxes: [], inference_time_ms: 1,
}))

test('ScanDetail explains split camera cultivars without hiding the stored AI candidate', async t => {
  const { page } = await setup(t, 200, { record: { ...scan(), confidence: 92, detections: splitViews } })
  await page.getByText('Cameras disagree on the cultivar', { exact: true }).waitFor()
  await page.getByText('Top + Right: Lakatan; Left + Rear: Latundan.', { exact: true }).waitFor()
  await page.getByText(/Stored AI candidate:/).waitFor()
  await page.getByText('Needs Review', { exact: true }).waitFor()
  assert.equal(await page.getByText('Verified', { exact: true }).count(), 0)
  // A confident scan is not flagged for a camera disagreement, so there is no flag to clear.
  await page.getByText(/Correct the cultivar if it is wrong\./).waitFor()
  assert.equal(await page.getByText(/clear the flag/).count(), 0)
})

test('ScanDetail mentions clearing the flag only when the split-view scan is flagged', async t => {
  const { page } = await setup(t, 200, { record: { ...scan(), confidence: 60, flagged: true, detections: splitViews } })
  await page.getByText('Cameras disagree on the cultivar', { exact: true }).waitFor()
  await page.getByText(/Correct the cultivar or clear the flag after review\./).waitFor()
})

test('ScanDetail keeps a human cultivar correction without repeating the split-view warning', async t => {
  const record = { ...scan(), cultivar: 'Lakatan', is_overridden: true,
    original_ai_result: { cultivar: 'Latundan', ripeness: 'Ripe', confidence: 77.9, finger_count: 5 },
    detections: splitViews }
  const { page } = await setup(t, 200, { record })
  await page.getByRole('heading', { name: /Scan Details/ }).waitFor()
  assert.equal(await page.getByText('Cameras disagree on the cultivar').count(), 0)
  assert.equal(await page.getByText('Verified', { exact: true }).count(), 1)
})

test('QC formats numeric predictions and preserves their precision when correcting another field', async t => {
  const raw = '0.9938128387987426'
  const { page, state } = await setup(t, 200, { screen: 'quality', record: { ...scan(), spoilage_days: raw } })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('1 day', { exact: true }).waitFor()
  assert.doesNotMatch(await dialog.innerText(), /0\.9938128387987426/)
  await dialog.getByRole('button', { name: 'Edit Data', exact: true }).click()
  assert.equal(await page.locator('#spoilageDays').inputValue(), '1')
  assert.equal(await page.locator('#spoilageDays').getAttribute('readonly'), '')
  await page.locator('#fingers').fill('9')
  await page.getByLabel('Reason for change', { exact: true }).fill('Count verified')
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await until(() => state.writes.length === 1)
  assert.equal(state.writes[0].spoilage_days, undefined)
  assert.equal(state.record.spoilage_days, raw)
})

test('historical direct link loads complete notes, stored camera and history with unavailable evidence', async t => {
  const { page, state } = await setup(t)
  await page.getByText('Recorded review note', { exact: true }).waitFor()
  await page.getByText('Original Top Camera', { exact: true }).first().waitFor()
  await page.getByText('Received delivery', { exact: true }).waitFor()
  await page.getByText('Image unavailable', { exact: true }).first().waitFor()
  assert.equal(state.imageHeaders?.authorization, 'Bearer admin-1')
})

test('history shows the recorded creation actor and does not invent a legacy status actor', async t => {
  const record = scan()
  record.operator_name = 'Renamed Operator'
  record.history = [
    { ...record.history[0], id: 'created', kind: 'created', actor_id: 'operator-1', actor_name: 'Recorded Operator' },
    { ...record.history[0], id: 'legacy-status', actor_id: null, actor_name: null, legacy: true },
  ]
  const { page } = await setup(t, 200, { record })
  const created = page.getByText('Scan created', { exact: true }).locator('..')
  await created.waitFor()
  assert.match(await created.innerText(), /Recorded Operator/)
  assert.doesNotMatch(await created.innerText(), /Renamed Operator|Actor not recorded|Admin User/)
  const legacy = page.getByText('Inventory status', { exact: true }).locator('..')
  assert.match(await legacy.innerText(), /Actor not recorded/)
  assert.match(await legacy.innerText(), /Historical record; additional change details were not recorded/)
  assert.doesNotMatch(await legacy.innerText(), /Recorded Operator|Renamed Operator|Admin User/)
})

test('ScanDetail history renders in a bounded scrollable container with record count badge and preserves all entries', async t => {
  const record = scan()
  record.history = Array.from({ length: 15 }, (_, i) => ({
    id: `event-${i + 1}`,
    kind: i === 0 ? 'created' : 'status',
    timestamp: '2024-05-05T08:10:00+08:00',
    actor_name: `Admin ${i + 1}`,
    actor_id: null,
    reason: `Reason entry ${i + 1} with very long descriptive text that wraps naturally without expanding or overflowing`,
    previous_values: i > 0 ? { inventory_status: 'In Stock' } : null,
    new_values: { inventory_status: i % 2 === 0 ? 'For Processing' : 'In Stock' },
    revision: i + 1,
    legacy: false,
  }))
  const { page } = await setup(t, 200, { record })
  const card = page.locator('[data-slot="card"]').filter({ hasText: 'Scan History' })
  const title = card.locator('[data-slot="card-title"]')
  await title.waitFor()
  assert.equal(await title.getByText('15', { exact: true }).count(), 1)

  const container = card.locator('div.space-y-2.max-h-48.overflow-y-auto')
  await container.waitFor()
  assert.equal(await container.locator('> div').count(), 15)

  const { scrollHeight, clientHeight } = await container.evaluate(el => ({
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
  }))
  assert.ok(scrollHeight > clientHeight, `Expected scrollHeight (${scrollHeight}) > clientHeight (${clientHeight})`)
})

test('ScanDetail history shows empty state and no count badge when history is empty', async t => {
  const record = scan()
  record.history = []
  const { page } = await setup(t, 200, { record })
  const card = page.locator('[data-slot="card"]').filter({ hasText: 'Scan History' })
  const title = card.locator('[data-slot="card-title"]')
  await title.waitFor()
  assert.equal(await title.locator('.rounded-full').count(), 0)
  await card.getByText('No recorded history is available.', { exact: true }).waitFor()
})

test('ScanDetail history with one or two entries displays naturally without scrolling', async t => {
  const record = scan()
  record.history = [
    {
      id: 'event-1',
      kind: 'created',
      timestamp: '2024-05-05T08:10:00+08:00',
      actor_name: 'Original Operator',
      actor_id: null,
      reason: 'Initial intake scan',
      previous_values: null,
      new_values: { inventory_status: 'In Stock' },
      revision: 1,
      legacy: false,
    },
  ]
  const { page } = await setup(t, 200, { record })
  const card = page.locator('[data-slot="card"]').filter({ hasText: 'Scan History' })
  const title = card.locator('[data-slot="card-title"]')
  await title.waitFor()
  assert.equal(await title.getByText('1', { exact: true }).count(), 1)

  const container = card.locator('div.space-y-2.max-h-48.overflow-y-auto')
  await container.waitFor()
  assert.equal(await container.locator('> div').count(), 1)

  const { scrollHeight, clientHeight } = await container.evaluate(el => ({
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
  }))
  assert.equal(scrollHeight, clientHeight, `Expected scrollHeight (${scrollHeight}) == clientHeight (${clientHeight})`)
})

test('ScanDetail history remains bounded and wraps long text on mobile viewport', async t => {
  const record = scan()
  record.history = Array.from({ length: 8 }, (_, i) => ({
    id: `event-${i + 1}`,
    kind: 'status',
    timestamp: '2024-05-05T08:10:00+08:00',
    actor_name: `Admin User ${i + 1}`,
    actor_id: null,
    reason: `SuperLongWordWithoutSpacesReasonTextEntryNumber${i + 1}ThatMustWrapCleanlyInsideContainer`,
    previous_values: { inventory_status: 'In Stock' },
    new_values: { inventory_status: 'Sold' },
    revision: i + 1,
    legacy: false,
  }))
  const { page } = await setup(t, 200, { record })
  await page.setViewportSize({ width: 390, height: 844 })
  const card = page.locator('[data-slot="card"]').filter({ hasText: 'Scan History' })
  const title = card.locator('[data-slot="card-title"]')
  await title.waitFor()
  assert.equal(await title.getByText('8', { exact: true }).count(), 1)

  const container = card.locator('div.space-y-2.max-h-48.overflow-y-auto')
  await container.waitFor()
  assert.equal(await container.locator('> div').count(), 8)

  const { scrollHeight, clientHeight, scrollWidth, clientWidth } = await container.evaluate(el => ({
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }))
  assert.ok(scrollHeight > clientHeight, 'Vertical scroll active')
  assert.ok(scrollWidth <= clientWidth + 2, 'No unexpected horizontal overflow')
})

for (const screen of ['logs', 'detail']) {
  for (const [value, label] of [[1.555, '1.555 kPa'], [1.25, '1.250 kPa'], [0, '0.000 kPa'], [null, '—'], [undefined, '—']]) {
    test(`${screen} VPD preserves stored ${value} with consistent units and missing-data feedback`, async t => {
      const record = { ...scan(), temperature: 22.29, humidity: 53.37, vpd: value }
      const { page, state } = await setup(t, 200, { screen, record })
      const metric = page.getByRole('group', { name: 'Vapor pressure deficit' })
      await metric.waitFor()
      assert.match(await metric.innerText(), new RegExp(label.replace('.', '\\.')))
      if (value == null) {
        await metric.getByLabel('VPD unavailable').waitFor()
        assert.equal(await metric.getByText(/kPa/).count(), 0)
      }
      await page.evaluate(() => window.dashboardSocket.emit('sensor_update', { temperature: 39, humidity: 15, vpd: 6.789 }))
      await page.clock.runFor(100)
      assert.match(await metric.innerText(), new RegExp(label.replace('.', '\\.')))
      assert.equal(state.requests.some(r => r.path.includes('/sensors')), false)
      if (screen === 'logs') assert.equal(await page.getByRole('columnheader', { name: 'VPD', exact: true }).count(), 0)
    })
  }
}

for (const [status, label] of [[403, 'Scan access denied'], [404, 'Scan not found'], [410, 'Scan deleted']]) {
  test(`direct detail distinguishes ${status}`, async t => {
    const { page } = await setup(t, status)
    await page.getByText(label, { exact: true }).waitFor()
    assert.equal(await page.getByText('Recorded review note').count(), 0)
  })
}


test('conflict preserves the correction draft and reloads before retrying', async t => {
  const { page, state } = await setup(t)
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.locator('#edit-fingers').fill('9')
  await page.getByLabel('Reason for change').fill('Count verified')
  const rejected = page.waitForResponse(response => response.status() === 409)
  await page.getByRole('button', { name: 'Save Changes' }).click()
  await rejected
  await page.clock.runFor(200)
  await page.getByRole('button', { name: 'Reload latest' }).click()
  await page.getByLabel('Reason for change').waitFor()
  assert.equal(await page.getByLabel('Reason for change').inputValue(), 'Count verified')
  assert.equal(await page.locator('#edit-fingers').inputValue(), '9')
  assert.equal(state.writes.length, 1)
})


async function until(predicate) {
  for (let i = 0; i < 250; i++) { if (await predicate()) return; await new Promise(r => setTimeout(r, 20)) }
  assert.fail('Expected request/state did not arrive')
}

test('late notes response cannot erase a successful new note', async t => {
  const { page, state } = await setup(t)
  await page.getByText('Recorded review note', { exact: true }).waitFor()
  let release, entered
  const held = new Promise(resolve => { release = resolve })
  const started = new Promise(resolve => { entered = resolve })
  state.holdReadOnce = () => { entered(); return held }
  await page.getByRole('button', { name: 'Test reload notes' }).click()
  await started
  state.onWrite = async body => {
    const note = { id: 'new-note', scan_id: id, text: body.note, author_name: 'Admin', timestamp: state.record.date_time }
    state.record = { ...state.record, revision: 2, notes: [...state.record.notes, note] }
    return { ...note, revision: 2 }
  }
  await page.getByPlaceholder('Add a review note...').fill('Persisted new note')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Confirm', exact: true }).click()
  await page.getByText('Persisted new note', { exact: true }).waitFor()
  release()
  await page.clock.runFor(200)
  const notes = JSON.parse(await page.getByTestId('notes-state').textContent())
  assert(notes.some(note => note.note === 'Persisted new note'))
})

test('Logs latest search wins; status writes use dedicated operation with reason and revision', async t => {
  let release
  const held = new Promise(resolve => { release = resolve })
  const { page, state } = await setup(t, 200, { screen: 'logs', holdSearch: () => held })
  await page.locator('tbody tr').first().waitFor()
  const search = page.getByPlaceholder(/search by cultivar/i)
  await search.fill('Slow')
  await until(() => state.requests.some(r => r.query.search === 'Slow'))
  await search.fill('Latest')
  await page.locator('tbody').getByText('Latest', { exact: true }).waitFor()
  release(); await page.clock.runFor(100)
  assert.equal(await page.locator('tbody').getByText('Slow', { exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Open menu' }).first().click()
  await page.getByRole('menuitem', { name: /Mark Sold/i }).click()
  await page.getByRole('dialog').getByText('The scan leaves stock. This change will be recorded in the scan history.', { exact: true }).waitFor()
  await page.getByLabel('Reason for change').fill('Dispatched')
  state.onWrite = async body => ({ ...state.record, revision: 2, inventory_status: body.inventory_status })
  await page.getByRole('button', { name: 'Save Changes' }).click()
  await until(() => state.writes.length === 1)
  const body = state.writes[0]
  assert.equal(body.path, `/api/v1/scans/${id}/status`)
  assert.equal(body.expected_revision, 1); assert.equal(body.inventory_status, 'Sold')
  assert.equal(body.reason, 'Dispatched'); assert.match(body.request_id, /^[0-9a-f-]{36}$/)
  assert.equal(body.is_overridden, undefined)
})

test('intake confirmation collects reason and complete membership snapshot', async t => {
  const { page, state } = await setup(t, 200, { screen: 'intakes' })
  await page.getByRole('button', { name: 'Open menu' }).first().click()
  await page.getByRole('menuitem', { name: 'Mark all Sold', exact: true }).click()
  const dialog = page.getByRole('alertdialog')
  assert(await dialog.getByRole('button', { name: 'Confirm', exact: true }).isDisabled())
  await dialog.getByLabel('Reason for change').fill('All dispatched')
  state.onWrite = async () => ({ updated_scan_ids: [id], revisions: { [id]: 2 }, intake_status: 'Depleted', status_updated_at: state.record.date_time })
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click()
  await until(() => state.writes.length === 1)
  assert.deepEqual(state.writes[0].expected_revisions, { [id]: 1 })
  assert.equal(state.writes[0].reason, 'All dispatched')
  assert.equal(state.writes[0].inventory_status, 'Sold')
})


test('older bulk receipt cannot replace a newer accepted scan; unknown/range evidence is preserved', async t => {
  const { page } = await setup(t, 200, { screen: 'intakes' })
  await until(async () => JSON.parse(await page.getByTestId('scans-state').textContent()).length === 1)
  await page.getByRole('button', { name: 'Test newer scan' }).click()
  await page.getByRole('button', { name: 'Test older bulk' }).click()
  await page.clock.runFor(100)
  const record = JSON.parse(await page.getByTestId('scans-state').textContent())[0]
  assert.equal(record.revision, 3); assert.equal(record.inventoryStatus, 'Spoiled')
  assert.match(await page.getByTestId('unknown-preview').textContent(), /Not recorded.*3 days/)
  assert.match(await page.getByTestId('range-preview').textContent(), /4–6 days.*3 days/)
})


test('lost flag acknowledgement is reachable through Retry previous after reopening a refreshed detail', async t => {
  const { page, state } = await setup(t)
  state.onWrite = async body => {
    state.record = { ...state.record, revision: 2, flagged: body.flagged }
    return state.record
  }
  state.loseResponseOnce = true
  await page.getByRole('button', { name: 'Flag for Review', exact: true }).click()
  await until(() => state.writes.length === 1)
  await page.clock.runFor(200)
  await page.getByRole('link', { name: 'Test logs link' }).click()
  await page.getByRole('link', { name: 'Test detail link' }).click()
  await page.getByRole('button', { name: 'Remove Flag', exact: true }).click()
  await page.clock.runFor(200)
  await page.locator('[data-sonner-toast][data-front="true"] button[data-action]').click()
  await until(() => state.writes.length === 2)
  assert.deepEqual(state.writes[0], state.writes[1])
  await page.getByRole('button', { name: 'Remove Flag', exact: true }).waitFor()
  assert.equal(state.record.flagged, true)
})


test('confirmed note replay clears only its submitted draft', async t => {
  const { page, state } = await setup(t)
  const note = { id: 'retried-note', scan_id: id, text: 'Once only', author_name: 'Admin', timestamp: state.record.date_time }
  state.onWrite = async () => { state.record = { ...state.record, revision: 2, notes: [...scan().notes, note] }; return { ...note, revision: 2 } }
  state.loseResponseOnce = true
  // Add with empty text opens no confirmation and writes nothing (a toast asks for text);
  // Cancel writes nothing.
  await page.getByPlaceholder('Add a review note...').waitFor()
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  assert.equal(await page.getByRole('alertdialog').count(), 0)
  await page.getByPlaceholder('Add a review note...').fill('Once only')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  assert.equal(state.writes.length, 0)
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Confirm', exact: true }).click()
  await until(() => state.writes.length === 1)
  await page.clock.runFor(200)
  await page.getByRole('button', { name: 'Retry previous', exact: true }).click()
  await until(() => state.writes.length === 2)
  await until(async () => await page.getByPlaceholder('Add a review note...').inputValue() === '')
  assert.deepEqual(state.writes[0], state.writes[1])
  assert.equal(state.record.notes.filter(n => n.id === 'retried-note').length, 1)
})


test('definitively rejected explicit retry preserves the note draft and shows no success action', async t => {
  const { page, state } = await setup(t)
  state.onWrite = async () => ({})
  state.loseResponseOnce = true
  await page.getByPlaceholder('Add a review note...').fill('Keep this draft')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Confirm', exact: true }).click()
  await until(() => state.writes.length === 1)
  await page.clock.runFor(200)
  state.onWrite = null // fixture now rejects with 409
  const response = page.waitForResponse(r => r.status() === 409)
  await page.getByRole('button', { name: 'Retry previous', exact: true }).click()
  await response; await page.clock.runFor(200)
  assert.equal(await page.getByPlaceholder('Add a review note...').inputValue(), 'Keep this draft')
  assert.equal(await page.getByText(/Previous change confirmed/).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Reload latest', exact: true }).count(), 0)
})


test('provenance conflict preserves review evidence and retries with the refreshed revision', async t => {
  const { page, state } = await setup(t, 200, { record: { ...scan(), intake_provenance: 'unverified' } })
  await page.getByLabel('Evidence and reason for provenance review').fill('Verified against original register')
  state.record.revision = 2
  const rejected = page.waitForResponse(r => r.status() === 409)
  await page.getByRole('button', { name: 'Verify genuinely unlinked' }).click()
  await rejected
  await page.getByLabel('Evidence and reason for provenance review').waitFor()
  await until(() => state.requests.filter(r => r.path === `/api/v1/scans/${id}` && r.method === 'GET').length >= 2)
  assert.equal(await page.getByLabel('Evidence and reason for provenance review').inputValue(), 'Verified against original register')
  state.onWrite = async body => ({ ...state.record, revision: 3, intake_provenance: body.intake_provenance, inventory_eligible: true })
  await page.getByRole('button', { name: 'Verify genuinely unlinked' }).click()
  await until(() => state.writes.length === 2)
  assert.equal(state.writes[1].expected_revision, 2)
  assert.equal(state.writes[1].reason, 'Verified against original register')
})

test('Logs retains a snapshot across pages and export, resets on filters and recovers from expiry', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  await page.getByLabel('Go to next page').click()
  await until(() => state.requests.some(r => r.query.page === '2' && r.query.snapshot_id === 'snapshot-one'))
  await page.getByRole('button', { name: 'Export CSV' }).click()
  await until(() => state.requests.some(r => r.path.endsWith('/export')))
  assert.equal(state.requests.find(r => r.path.endsWith('/export')).query.snapshot_id, 'snapshot-one')
  state.snapshotToken = 'snapshot-two'
  await page.getByPlaceholder(/search by cultivar/i).fill('New cohort')
  await page.locator('tbody').getByText('New cohort', { exact: true }).waitFor()
  assert.equal(state.requests.find(r => r.query.search === 'New cohort').query.snapshot_id, undefined)
  state.expire = true
  await page.getByLabel('Go to next page').click()
  await until(() => state.requests.some(r => r.query.page === '2' && !r.query.snapshot_id))
  assert.equal(await page.getByRole('alert').filter({ hasText: 'Browse snapshot expired. Refresh.' }).count(), 0)
  state.expire = false
})

test('Logs page 2 offers new Kiosk scans without replacing its frozen snapshot', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  await page.getByPlaceholder(/search by cultivar/i).fill('Filtered')
  await page.locator('tbody').getByText('Filtered', { exact: true }).waitFor()
  await page.getByRole('columnheader', { name: 'Est. Spoilage' }).click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.sort === 'spoilage_days'))
  await page.getByText(/Showing results for the previous selection/).waitFor({ state: 'detached' })
  await page.getByLabel('Go to next page').click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.page === '2' && r.query.snapshot_id === 'snapshot-one'))
  state.snapshotToken = 'snapshot-two'
  state.pendingResponse = params => ({ snapshot_id: params.snapshot_id,
    new_count: params.snapshot_id === 'snapshot-one' ? 2 : 0, generated_at: state.record.date_time })
  const listCount = state.requests.filter(r => r.path === '/api/v1/scan-logs').length
  await page.evaluate(() => window.dispatchEvent(new Event('bananavision:scans-added')))
  await page.getByText(/2 new Kiosk scans available/).waitFor()
  assert.equal(state.requests.filter(r => r.path === '/api/v1/scan-logs').length, listCount)
  assert.equal(state.requests.at(-1).path, '/api/v1/scan-logs/pending')
  await page.getByRole('button', { name: 'Later', exact: true }).click()
  await page.getByText('2 new Kiosk scans available.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'View Latest Scans', exact: true }).count(), 0)
  assert.equal(await page.getByLabel('Go to next page').isVisible(), true)
  assert.equal(state.requests.filter(r => r.path === '/api/v1/scan-logs').length, listCount)
  await page.getByRole('button', { name: 'Show latest scans', exact: true }).click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.page === '1' && !r.query.snapshot_id))
  const latest = state.requests.filter(r => r.path === '/api/v1/scan-logs' && r.query.page === '1' && !r.query.snapshot_id).at(-1)
  assert.equal(latest.query.search, 'Filtered')
  assert.equal(latest.query.sort, 'spoilage_days')
  assert.equal(await page.getByText(/new Kiosk scans available/).count(), 0)
})

test('Logs page 1 automatically shows new Kiosk scans and preserves filters', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  await page.getByPlaceholder(/search by cultivar/i).fill('Filtered')
  await page.locator('tbody').getByText('Filtered', { exact: true }).waitFor()
  await page.getByRole('columnheader', { name: 'Est. Spoilage' }).click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.sort === 'spoilage_days'))
  await page.getByText(/Showing results for the previous selection/).waitFor({ state: 'detached' })
  state.snapshotToken = 'snapshot-two'
  state.pendingResponse = params => ({ snapshot_id: params.snapshot_id,
    new_count: params.snapshot_id === 'snapshot-one' ? 1 : 0, generated_at: state.record.date_time })
  const before = state.requests.length
  await page.evaluate(() => window.dispatchEvent(new Event('bananavision:scans-added')))
  await until(() => state.requests.slice(before).some(r => r.path === '/api/v1/scan-logs' && r.query.page === '1' && !r.query.snapshot_id))
  const fresh = state.requests.slice(before).filter(r => r.path === '/api/v1/scan-logs').at(-1)
  assert.equal(fresh.query.search, 'Filtered')
  assert.equal(fresh.query.sort, 'spoilage_days')
  assert.equal(fresh.query.snapshot_id, undefined)
  assert.equal(await page.getByRole('button', { name: 'Later', exact: true }).count(), 0)
  assert.equal(await page.getByText(/new Kiosk scans available/).count(), 0)
})

test('Logs page 1 defers new Kiosk scans while the search field is active', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  const search = page.getByPlaceholder(/search by cultivar/i)
  await search.fill('Filtered')
  await page.locator('tbody').getByText('Filtered', { exact: true }).waitFor()
  await search.click()
  state.snapshotToken = 'snapshot-two'
  state.pendingResponse = params => ({ snapshot_id: params.snapshot_id,
    new_count: params.snapshot_id === 'snapshot-one' ? 1 : 0, generated_at: state.record.date_time })
  const listCount = state.requests.filter(r => r.path === '/api/v1/scan-logs').length
  await page.evaluate(() => window.dispatchEvent(new Event('bananavision:scans-added')))
  await page.getByText(/1 new Kiosk scan available/).waitFor()
  assert.equal(state.requests.filter(r => r.path === '/api/v1/scan-logs').length, listCount)
  await page.getByRole('button', { name: 'View Latest Scans', exact: true }).click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.search === 'Filtered' && !r.query.snapshot_id && r.query.page === '1'))
})

test('Logs page 1 defers auto-refresh while the tab is hidden', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  state.snapshotToken = 'snapshot-two'
  state.pendingResponse = params => ({ snapshot_id: params.snapshot_id,
    new_count: params.snapshot_id === 'snapshot-one' ? 1 : 0, generated_at: state.record.date_time })
  const listCount = state.requests.filter(r => r.path === '/api/v1/scan-logs').length
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    window.dispatchEvent(new Event('bananavision:scans-added'))
  })
  await page.getByText(/1 new Kiosk scan available/).waitFor()
  assert.equal(state.requests.filter(r => r.path === '/api/v1/scan-logs').length, listCount)
  assert.equal(await page.getByLabel('Go to next page').isVisible(), true)
  // Returning to a safe page 1 lets the resume refresh open the fresh snapshot.
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && !r.query.snapshot_id && r.query.page === '1'))
  await page.getByText(/new Kiosk scans available/).waitFor({ state: 'detached' })
})

test('Logs keeps its frozen page when the live count request fails', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  await page.getByLabel('Go to next page').click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.page === '2' && r.query.snapshot_id === 'snapshot-one'))
  state.pendingStatus = 500
  const before = state.requests.length
  await page.evaluate(() => window.dispatchEvent(new Event('bananavision:scans-added')))
  await until(() => state.requests.slice(before).some(r => r.path === '/api/v1/scan-logs/pending'))
  await page.waitForTimeout(100)
  assert.equal(await page.getByText(/new Kiosk scans available/).count(), 0)
  assert.equal(await page.getByRole('alert').count(), 0)
  assert.equal(await page.getByLabel('Go to next page').isVisible(), true)
  assert.equal(state.requests.slice(before).filter(r => r.path === '/api/v1/scan-logs').length, 0)
  // A later successful check still offers the latest scans.
  state.pendingStatus = undefined
  state.pendingCount = 2
  await page.evaluate(() => window.dispatchEvent(new Event('bananavision:scans-added')))
  await page.getByText(/2 new Kiosk scans available/).waitFor()
})

test('Logs rechecks new Kiosk scans after the websocket resumes', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  await page.getByLabel('Go to next page').click()
  await until(() => state.requests.some(r => r.path === '/api/v1/scan-logs' && r.query.page === '2' && r.query.snapshot_id === 'snapshot-one'))
  state.pendingCount = 3
  const before = state.requests.length
  await page.evaluate(() => window.dashboardSocket.disconnect())
  await page.clock.runFor(1500)
  await until(() => state.requests.slice(before).some(r => r.path === '/api/v1/scan-logs/pending'))
  await page.getByText(/3 new Kiosk scans available/).waitFor()
  assert.ok(state.requests.slice(before).some(r => r.path === '/api/v1/scans'))
  assert.equal(await page.getByLabel('Go to next page').isVisible(), true)
})

test('expired Logs snapshots rebuild risk membership for fresh rows and filters', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs' })
  await page.locator('tbody tr').first().waitFor()
  assert.equal(await page.getByRole('img', { name: 'At-risk scan', exact: true }).count(), 0)
  state.expire = true
  state.atRiskCount = 1
  state.snapshotToken = 'fresh-risk-snapshot'
  state.expire = false
  let expiredOnce = false
  await page.route('**/api/v1/scan-logs?*', async route => {
    const url = new URL(route.request().url())
    if (!expiredOnce && url.searchParams.get('snapshot_id') === 'snapshot-one') {
      expiredOnce = true
      return route.fulfill({ status: 410, json: { detail: 'Expired' }, headers: { 'access-control-allow-origin': '*' } })
    }
    return route.fallback()
  })
  await page.getByLabel('Go to next page').click()
  await page.getByRole('img', { name: 'At-risk scan', exact: true }).waitFor()
  assert.ok(state.requests.some(r => r.query.attention === 'at-risk' && r.query.snapshot_id === 'fresh-risk-snapshot'))
  state.expire = false
  const riskLists = state.requests.filter(r => r.path === '/api/v1/scan-logs' && r.query.attention === 'at-risk').length
  await page.getByText('At-Risk Scans', { exact: true }).click()
  await until(() => state.requests.filter(r => r.path === '/api/v1/scan-logs' && r.query.attention === 'at-risk').length > riskLists)
  await page.getByRole('img', { name: 'At-risk scan', exact: true }).waitFor()
})

test('ordinary websocket completion refreshes notifications once across duplicate rooms and HTTP', async t => {
  const { page, state } = await setup(t, 200)
  await page.getByText('Original source', { exact: true }).waitFor()
  await page.evaluate(() => {
    window.scanNotificationEvents = 0
    window.addEventListener('bananavision:notifications-changed', () => window.scanNotificationEvents++)
  })
  let release
  state.triggerResponse = () => new Promise(resolve => { release = resolve })
  await page.getByRole('button', { name: 'Test start scan', exact: true }).click()
  await until(() => Boolean(release))
  await page.evaluate(record => {
    window.dashboardSocket.emit('scan:completed', record)
    window.dashboardSocket.emit('scan:completed', record)
  }, state.record)
  await until(async () => await page.evaluate(() => window.scanNotificationEvents) === 1)
  release({ ...state.record, revision: 2, source_text: 'HTTP enriched source' })
  await until(async () => JSON.parse(await page.getByTestId('last-result').textContent())?.source === 'HTTP enriched source')
  assert.equal(await page.evaluate(() => window.scanNotificationEvents), 1)
})

test('an oversized snapshot still permits a complete filtered CSV export', async t => {
  const { page, state } = await setup(t, 200, { screen: 'logs', logStatus: 413 })
  await page.getByRole('alert').filter({ hasText: 'Too many records for a browse snapshot.' }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Export CSV' }).isEnabled(), true)
  await page.getByRole('button', { name: 'Export CSV' }).click()
  await until(() => state.requests.some(r => r.path.endsWith('/export')))
  assert.equal(state.requests.find(r => r.path.endsWith('/export')).query.snapshot_id, undefined)
})

for (const screen of ['detail', 'quality']) {
  test(`${screen} allows unrelated correction on a stored zero-count scan without inventing a count`, async t => {
    const record = { ...scan(), finger_count: 0 }
    const { page, state } = await setup(t, 200, { screen, record,
      onWrite: body => ({ ...record, ...body, revision: 2 }) })
    if (screen === 'quality') await page.locator('tbody tr').first().click()
    await page.getByRole('button', { name: screen === 'quality' ? 'Edit Data' : 'Edit', exact: true }).click()
    await page.getByLabel('Reason for change', { exact: true }).fill('Correct classification only')
    await page.locator(screen === 'quality' ? '#cultivar' : '#edit-cultivar').click()
    await page.getByRole('option', { name: 'Latundan', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Save Changes', exact: true }).isEnabled(), true)
    await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
    await until(() => state.writes.length === 1)
    assert.equal(state.writes[0].cultivar, 'Latundan')
    assert.equal(Object.hasOwn(state.writes[0], 'finger_count'), false)
  })

  test(`${screen} rejects explicit empty, zero and fractional finger counts without clamping`, async t => {
    const { page, state } = await setup(t, 200, { screen })
    if (screen === 'quality') await page.locator('tbody tr').first().click()
    await page.getByRole('button', { name: screen === 'quality' ? 'Edit Data' : 'Edit', exact: true }).click()
    await page.getByLabel('Reason for change', { exact: true }).fill('Verify count')
    const count = page.locator(screen === 'quality' ? '#fingers' : '#edit-fingers')
    for (const invalid of ['', '0', '1.5']) {
      await count.fill(invalid)
      await count.blur()
      assert.equal(await count.inputValue(), invalid)
      assert.equal(await page.getByRole('button', { name: 'Save Changes', exact: true }).isDisabled(), true)
    }
    assert.equal(state.writes.length, 0)
    await count.fill('8')
    assert.equal(await page.getByRole('button', { name: 'Save Changes', exact: true }).isEnabled(), true)
  })
}

test('QC detail refresh supplies the latest revision for a new note and displays Manila time', async t => {
  const record = { ...scan(), revision: 2, notes: [{ ...scan().notes[0], text: 'Latest review' }] }
  const { page, state } = await setup(t, 200, { screen: 'quality', listRecord: scan(), record,
    onWrite: body => ({ id: 'new-note', scan_id: id, text: body.note, author_name: 'Admin', timestamp: record.date_time, revision: 3 }) })
  await page.locator('tbody tr').first().click()
  await page.getByText('Latest review', { exact: true }).waitFor()
  assert.match(await page.getByRole('dialog').innerText(), /8:10:00/)
  await page.getByPlaceholder('Add a note...').fill('Verified current record')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await until(() => state.writes.length === 1)
  assert.equal(state.writes[0].expected_revision, 2)
  await page.getByText('Verified current record', { exact: true }).waitFor()
})

function cameraEvidence() {
  const record = scan()
  const positions = ['Top', 'Left', 'Right', 'Rear']
  record.images = positions.map((position, index) => ({
    camera_id: `RECORDED-${index}`, file_path: `/captures/${id}/${position}.svg`,
  }))
  // Deliberately different order: images and detections must be joined by camera ID.
  record.thumbnail_url = record.images[0].file_path
  record.detections = positions.map((position, index) => ({
    camera_id: `RECORDED-${index}`, camera_label: position, confidence: 81 + index,
    bounding_boxes: [{ x: 300 + index * 50, y: 120, w: 80, h: 160, cls: 'lakatan_ripe', conf: 0.81 + index / 100 }],
  })).reverse()
  const imageFixtures = Object.fromEntries(record.images.map((image, index) => [
    image.file_path,
    `<svg xmlns="http://www.w3.org/2000/svg" width="${index === 0 ? 1200 : 800}" height="600"><rect width="100%" height="100%" fill="${['red', 'green', 'blue', 'yellow'][index]}"/></svg>`,
  ]))
  const listRecord = { ...record }
  delete listRecord.detections
  delete listRecord.notes
  delete listRecord.history
  return { record, listRecord, imageFixtures }
}

for (const width of [1280, 390]) {
  test(`ScanDetail enlarges the selected image in a keyboard-accessible dialog at ${width}px`, async t => {
    const evidence = cameraEvidence()
    const { page, state } = await setup(t, 200, evidence)
    await page.setViewportSize({ width, height: 900 })
    await page.getByRole('button', { name: 'Left RECORDED-1', exact: true }).click()
    const trigger = page.getByRole('button', { name: 'Enlarge Left camera image', exact: true })
    await trigger.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Left camera image' })
    await dialog.waitFor()
    const image = dialog.getByRole('img', { name: 'Left', exact: true })
    await image.waitFor()
    const svg = dialog.locator('svg[preserveAspectRatio]')
    await svg.waitFor()
    await page.clock.runFor(250)
    assert.equal(await image.evaluate(async img => (await fetch(img.src)).text()),
      evidence.imageFixtures[`/captures/${id}/Left.svg`])
    assert.equal(await svg.getAttribute('viewBox'), '0 0 800 600')
    assert.equal(await svg.locator('g > rect').first().getAttribute('x'), '350')
    const bounds = await dialog.boundingBox()
    assert(bounds.x >= 0 && bounds.x + bounds.width <= width + 1)
    assert(bounds.y >= 0 && bounds.y + bounds.height <= 901)
    const imageBounds = await image.boundingBox()
    assert(Math.abs(imageBounds.width / imageBounds.height - 800 / 600) < 0.01)
    if (width === 1280) assert(imageBounds.width > 800)
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.clock.runFor(250)
    assert.equal(await trigger.evaluate(button => document.activeElement === button), true)
    // The independent Boxes control never opens the dialog.
    await page.getByTitle('Hide bounding boxes', { exact: true }).click()
    assert.equal(await page.getByRole('dialog').count(), 0)
    await trigger.click()
    await dialog.getByRole('img', { name: 'Left', exact: true }).waitFor()
    assert.equal(await dialog.locator('svg[preserveAspectRatio]').count(), 0)
    await dialog.getByRole('button', { name: 'Close', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(state.writes.length, 0)
  })
}

test('ScanDetail refreshes in place and keeps the record visible while the read is pending', async t => {
  let release
  const { page, state } = await setup(t, 200)
  await page.getByText('Original source', { exact: true }).waitFor()
  state.holdReadOnce = () => new Promise(resolve => { release = resolve })
  state.record = { ...state.record, revision: 2, source_text: 'Focused source' }
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.clock.runFor(200)
  await until(() => state.requests.filter(r => r.path === `/api/v1/scans/${id}` && r.method === 'GET').length === 2)
  await page.getByText('Original source', { exact: true }).waitFor()
  assert.equal(await page.getByRole('status', { name: 'Loading scan.' }).count(), 0)
  release()
  await page.getByText('Focused source', { exact: true }).waitFor()
})

test('ScanDetail has no enlarge action when the selected camera has no image', async t => {
  const record = { ...scan(), images: [] }
  const { page } = await setup(t, 200, { record })
  await page.getByText('No image available', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: /Enlarge .* camera image/ }).count(), 0)
})

test('QC hydrates same-revision camera positions and real boxes using ScanDetail geometry', async t => {
  const evidence = cameraEvidence()
  const { page, state } = await setup(t, 200, { screen: 'quality', ...evidence })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  for (const [index, position] of ['Top', 'Left', 'Right', 'Rear'].entries()) {
    const image = dialog.getByRole('img', { name: position, exact: true })
    await image.waitFor()
    const overlay = image.locator('..')
    const svg = overlay.locator('svg[preserveAspectRatio]')
    await svg.waitFor()
    await page.clock.runFor(250)
    assert.equal(await image.evaluate(async img => {
      const response = await fetch(img.src)
      return response.text()
    }), evidence.imageFixtures[evidence.record.images[index].file_path])
    assert.equal(await svg.getAttribute('viewBox'), `0 0 ${index === 0 ? 1200 : 800} 600`)
    assert.equal(await svg.getAttribute('preserveAspectRatio'), 'xMidYMid slice')
    const box = svg.locator('g > rect').first()
    assert.deepEqual(await box.evaluate(el => ['x', 'y', 'width', 'height'].map(name => Number(el.getAttribute(name)))),
      [300 + index * 50, 120, 80, 160])
    assert.equal(await svg.locator('text').textContent(), `Lakatan Ripe · ${81 + index}%`)
    assert.equal(await image.evaluate(img => getComputedStyle(img).objectFit), 'cover')
    // The box and image share the same viewport even when the source is not 4:3.
    const imageBounds = await image.boundingBox()
    const boxBounds = await box.boundingBox()
    const scale = Math.max(imageBounds.width / (index === 0 ? 1200 : 800), imageBounds.height / 600)
    const strokeWidth = Number(await box.getAttribute('stroke-width'))
    assert(Math.abs(boxBounds.x - (imageBounds.x + (imageBounds.width - (index === 0 ? 1200 : 800) * scale) / 2 + (300 + index * 50 - strokeWidth / 2) * scale)) < 1)
    assert(Math.abs(boxBounds.y - (imageBounds.y + (imageBounds.height - 600 * scale) / 2 + (120 - strokeWidth / 2) * scale)) < 1)
    assert(Math.abs(boxBounds.width - (80 + strokeWidth) * scale) < 1)
    assert(Math.abs(boxBounds.height - (160 + strokeWidth) * scale) < 1)
  }
  assert.equal(await dialog.locator('img').count(), 4)
  assert.doesNotMatch(await dialog.innerText(), /NEW-CAMERA|Main Detection|Finger Detection/)
  assert.equal(state.imageHeaders.authorization, 'Bearer admin-1')
  assert.equal(state.requests.filter(request => request.path === `/api/v1/scans/${id}`).length, 1)
})

test('QC missing or unavailable camera images never reuse the thumbnail or draw boxes', async t => {
  const evidence = cameraEvidence()
  evidence.record.images = evidence.record.images.filter(image => image.camera_id !== 'RECORDED-1')
  evidence.listRecord.images = evidence.record.images
  delete evidence.imageFixtures[`/captures/${id}/Rear.svg`]
  const { page } = await setup(t, 200, { screen: 'quality', ...evidence })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('Left', { exact: true }).waitFor()
  const missing = dialog.getByText('Left', { exact: true }).locator('..')
  await missing.getByText('No image available', { exact: true }).waitFor()
  assert.equal(await missing.locator('img, svg[preserveAspectRatio]').count(), 0)
  const unavailable = dialog.getByText('Rear', { exact: true }).locator('..')
  await unavailable.getByText('Image unavailable', { exact: true }).waitFor()
  assert.equal(await unavailable.locator('img, svg[preserveAspectRatio]').count(), 0)
  await until(async () => await dialog.locator('svg[preserveAspectRatio]').count() === 2)
})

test('QC images without detections do not invent boxes or positions', async t => {
  const evidence = cameraEvidence()
  evidence.record.detections = []
  const { page } = await setup(t, 200, { screen: 'quality', ...evidence })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('Recorded review note', { exact: true }).waitFor()
  await until(async () => await dialog.locator('img').count() === 4)
  assert.equal(await dialog.locator('svg[preserveAspectRatio]').count(), 0)
  for (let index = 0; index < 4; index++) await dialog.getByText(`RECORDED-${index}`, { exact: true }).waitFor()
})

test('QC scan without camera evidence shows an empty state instead of configured camera tiles', async t => {
  const record = { ...scan(), images: [], detections: [] }
  const { page } = await setup(t, 200, { screen: 'quality', record })
  await page.locator('tbody tr').first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('No camera evidence recorded', { exact: true }).waitFor()
  assert.equal(await dialog.locator('img, svg[preserveAspectRatio]').count(), 0)
  assert.doesNotMatch(await dialog.innerText(), /NEW-CAMERA/)
})

test('QC late detail preserves correction draft and requires explicit revision reload', async t => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const record = { ...scan(), revision: 2, notes: [{ ...scan().notes[0], text: 'Newer record arrived' }] }
  const { page, state } = await setup(t, 200, { screen: 'quality', listRecord: scan(), record, holdReadOnce: () => gate })
  await page.locator('tbody tr').first().click()
  await page.getByRole('button', { name: 'Edit Data', exact: true }).click()
  await page.locator('#fingers').fill('9')
  await page.getByLabel('Reason for change').fill('Draft started before detail refreshed')
  release()
  await until(async () => JSON.parse(await page.getByTestId('scans-state').textContent())[0].revision === 2)
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await until(() => state.writes.length === 1)
  assert.equal(state.writes[0].expected_revision, 1)
  assert.equal(await page.locator('#fingers').inputValue(), '9')
  await page.clock.runFor(200)
  await page.getByRole('dialog').getByRole('button', { name: 'Reload latest', exact: true }).click()
  state.onWrite = body => ({ ...record, ...body, revision: 3 })
  await until(() => state.requests.filter(r => r.path === `/api/v1/scans/${id}` && r.method === 'GET').length === 2)
  await page.getByRole('dialog').getByRole('alert').waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await until(() => state.writes.length === 2)
  assert.equal(state.writes[1].expected_revision, 2)
})

test('QC confirmed replay with failed refresh offers read recovery without replaying the write again', async t => {
  const { page, state } = await setup(t, 200, { screen: 'quality', loseResponseOnce: true })
  state.onWrite = body => {
    const note = { id: 'confirmed-note', scan_id: id, text: body.note, author_name: 'Admin', timestamp: state.record.date_time }
    state.record = { ...state.record, revision: 2, notes: [note] }
    return { ...note, revision: 2 }
  }
  await page.locator('tbody tr').first().click()
  await page.getByText('Recorded review note', { exact: true }).waitFor()
  const dialog = page.getByRole('dialog')
  await dialog.getByPlaceholder('Add a note...').fill('Retained request')
  await dialog.getByRole('button', { name: 'Add', exact: true }).click()
  await dialog.getByRole('button', { name: 'Retry previous', exact: true }).waitFor()
  state.readStatus = 503
  await dialog.getByRole('button', { name: 'Retry previous', exact: true }).click()
  await dialog.getByRole('button', { name: 'Reload latest', exact: true }).waitFor()
  assert.equal(state.writes.length, 2)
  assert.equal(await dialog.getByPlaceholder('Add a note...').inputValue(), '')
  state.readStatus = 200
  await dialog.getByRole('button', { name: 'Reload latest', exact: true }).click()
  await dialog.getByRole('alert').waitFor({ state: 'hidden' })
  assert.equal(state.writes.length, 2)
  await dialog.getByText('Retained request', { exact: true }).waitFor()
})

for (const status of [403, 422]) {
  test(`QC definitive ${status} replay rejection preserves the draft and removes the consumed retry`, async t => {
    const { page, state } = await setup(t, 200, { screen: 'quality', loseResponseOnce: true,
      onWrite: body => ({ id: 'new-note', scan_id: id, text: body.note, author_name: 'Admin', timestamp: scan().date_time, revision: 2 }) })
    await page.locator('tbody tr').first().click()
    await page.getByText('Recorded review note', { exact: true }).waitFor()
    const dialog = page.getByRole('dialog')
    await dialog.getByPlaceholder('Add a note...').fill('Keep this draft')
    await dialog.getByRole('button', { name: 'Add', exact: true }).click()
    await dialog.getByRole('button', { name: 'Retry previous', exact: true }).waitFor()
    state.writeStatus = status
    await dialog.getByRole('button', { name: 'Retry previous', exact: true }).click()
    await dialog.getByRole('alert').getByText(/This retry was rejected/).waitFor()
    assert.equal(await dialog.getByRole('button', { name: 'Retry previous', exact: true }).count(), 0)
    assert.equal(await dialog.getByPlaceholder('Add a note...').inputValue(), 'Keep this draft')
    assert.equal(await page.locator('[data-sonner-toast][data-type="success"]').count(), 0)
    assert.equal(state.writes.length, 2)
  })
}

const STATUSES = ['In Stock', 'For Processing', 'Sold', 'Spoiled']

for (const current of STATUSES) {
  test(`ScanDetail offers an admin every status except ${current}`, async t => {
    const { page } = await setup(t, 200, { record: { ...scan(), inventory_status: current } })
    await page.getByRole('button', { name: 'Update status' }).click()
    for (const target of STATUSES) {
      const item = page.getByRole('menuitem', { name: `Mark ${target}`, exact: true })
      await item.waitFor()
      assert.equal(await item.isDisabled(), target === current, `${current} -> ${target}`)
    }
  })
}

async function changeStatus(t, current, target, reason) {
  const { page, state } = await setup(t, 200, { record: { ...scan(), inventory_status: current } })
  await page.getByRole('button', { name: 'Update status' }).click()
  await page.getByRole('menuitem', { name: `Mark ${target}`, exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText(`Mark scan as ${target}?`, { exact: true }).waitFor()
  const note = await dialog.locator('p').first().textContent()
  assert.doesNotMatch(note, /terminal status|cannot be easily undone/)
  await dialog.getByLabel('Reason for change').fill(reason)
  state.onWrite = async body => {
    state.record = { ...state.record, revision: 2, inventory_status: body.inventory_status }
    return state.record
  }
  await dialog.getByRole('button', { name: 'Save Changes' }).click()
  await until(() => state.writes.length === 1)
  const body = state.writes[0]
  assert.equal(body.path, `/api/v1/scans/${id}/status`)
  assert.equal(body.expected_revision, 1)
  assert.equal(body.inventory_status, target)
  assert.equal(body.reason, reason)
  assert.match(body.request_id, /^[0-9a-f-]{36}$/)
  await dialog.waitFor({ state: 'hidden' })
  return { page, note }
}

test('ScanDetail lets an admin correct a Spoiled scan to For Processing', async t => {
  const { page, note } = await changeStatus(t, 'Spoiled', 'For Processing', 'Marked spoiled by mistake')
  assert.equal(note, 'This corrects the Spoiled status. This change will be recorded in the scan history.')
  const metric = page.getByText('Est. Spoilage', { exact: true }).locator('..')
  await metric.getByText('For processing · no countdown', { exact: true }).waitFor()
  // The menu stays available, so a second mistake can be corrected too.
  await page.getByRole('button', { name: 'Update status' }).click()
  assert.equal(await page.getByRole('menuitem', { name: 'Mark For Processing', exact: true }).isDisabled(), true)
  assert.equal(await page.getByRole('menuitem', { name: 'Mark Spoiled', exact: true }).isDisabled(), false)
})

test('ScanDetail lets an admin return a Sold scan to stock and says a depleted intake reopens', async t => {
  const { note } = await changeStatus(t, 'Sold', 'In Stock', 'Sale was cancelled')
  assert.equal(note, 'This corrects the Sold status. The scan returns to stock. If its delivery intake is depleted, the intake reopens. This change will be recorded in the scan history.')
})

test('ScanDetail moving stock to Sold says the scan leaves stock', async t => {
  const { note } = await changeStatus(t, 'In Stock', 'Sold', 'Dispatched')
  assert.equal(note, 'The scan leaves stock. This change will be recorded in the scan history.')
})
