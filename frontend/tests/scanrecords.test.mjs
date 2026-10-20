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
    if (url.pathname === '/api/v1/scan-logs') {
      if (state.logStatus) return reply({ detail: 'Too many records for a browse snapshot. Narrow filters or export.' }, state.logStatus)
      if (state.expire && url.searchParams.get('snapshot_id')) return reply({ detail: 'Browse snapshot expired. Refresh.' }, 410)
      const search = url.searchParams.get('search') || 'Initial'
      if (search === 'Slow' && state.holdSearch) await state.holdSearch()
      return reply({ items: [{ ...state.record, source_name: search, remaining_days: 1, temperature: null, humidity: null }], total: 201,
        snapshot_id: state.snapshotToken ?? 'snapshot-one', page: Number(url.searchParams.get('page') || 1), page_size: 10, avg_confidence: 92, at_risk_count: 1, review_count: 0,
        options: { sources: [], operators: [] }, generated_at: state.record.date_time })
    }
    if (url.pathname === '/api/v1/intakes/intake-1/scan-revisions') return reply({ revisions: { [id]: state.record.revision } })
    if (url.pathname === '/api/v1/intakes' && options.screen === 'intakes') return reply([{ id: 'intake-1', source: 'Supplier', intake_date: '2026-10-02', status: 'Active', scan_count: 1 }])
    if (url.pathname === '/api/v1/scans') return reply({ items: options.screen === 'quality' ? [state.listRecord ?? state.record] : options.screen === 'intakes' ? [{ ...state.record, intake_id: 'intake-1' }] : [], page: 1, page_size: 100, total: ['intakes', 'quality'].includes(options.screen) ? 1 : 0 })
    if (url.pathname === '/api/v1/config') return reply({ camera_ids: 'NEW-CAMERA', confidence_threshold: 85, revision: 1 })
    if (url.pathname === '/api/v1/activity') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (url.pathname === '/api/v1/users') return reply({ items: [], total: 0 })
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
  await page.goto(`${runtime.url}${options.screen === 'quality' ? '/scans/quality' : options.screen === 'logs' ? '/logs' : options.screen === 'intakes' ? '/scans/intakes' : `/scans/${id}`}`)
  return { page, state }
}

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
  assert.match(await page.getByTestId('unknown-preview').textContent(), /Not recorded.*3d/)
  assert.match(await page.getByTestId('range-preview').textContent(), /4-6d.*3d/)
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
  await page.getByPlaceholder('Add a review note...').fill('Once only')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
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

test('Logs retains a snapshot across pages and export, resets on filters and retries expiry', async t => {
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
  await page.getByRole('alert').filter({ hasText: 'Browse snapshot expired. Refresh.' }).waitFor()
  state.expire = false; state.snapshotToken = 'snapshot-three'
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.locator('tbody').getByText('New cohort', { exact: true }).waitFor()
  assert.equal(state.requests.filter(r => r.path === '/api/v1/scan-logs').at(-1).query.snapshot_id, undefined)
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
