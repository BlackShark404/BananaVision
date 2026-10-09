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
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const state = { record: scan(), writes: [], requests: [], imageHeaders: null, ...options }
  await page.route('**/captures/**', async route => {
    state.imageHeaders = route.request().headers()
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
      return reply(status === 200 ? snapshot : { detail: 'Unavailable' }, status)
    }
    if (url.pathname === '/api/v1/scan-logs') {
      const search = url.searchParams.get('search') || 'Initial'
      if (search === 'Slow' && state.holdSearch) await state.holdSearch()
      return reply({ items: [{ ...state.record, source_name: search, remaining_days: 1, temperature: null, humidity: null }], total: 201,
        page: 1, page_size: 10, avg_confidence: 92, at_risk_count: 1, review_count: 0,
        options: { sources: [], operators: [] }, generated_at: state.record.date_time })
    }
    if (url.pathname === '/api/v1/intakes/intake-1/scan-revisions') return reply({ revisions: { [id]: state.record.revision } })
    if (url.pathname === '/api/v1/intakes' && options.screen === 'intakes') return reply([{ id: 'intake-1', source: 'Supplier', intake_date: '2026-10-02', status: 'Active', scan_count: 1 }])
    if (url.pathname === '/api/v1/scans') return reply({ items: options.screen === 'intakes' ? [{ ...state.record, intake_id: 'intake-1' }] : [], page: 1, page_size: 100, total: options.screen === 'intakes' ? 1 : 0 })
    if (url.pathname === '/api/v1/config') return reply({ camera_ids: 'NEW-CAMERA', confidence_threshold: 85, revision: 1 })
    if (url.pathname === '/api/v1/activity') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (url.pathname === '/api/v1/users') return reply({ items: [], total: 0 })
    if (method === 'GET') return reply([])
    state.writes.push({ ...request.postDataJSON(), path: url.pathname })
    if (state.onWrite) return reply(await state.onWrite(request.postDataJSON(), url.pathname))
    return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
  })
  await page.goto(`${runtime.url}${options.screen === 'logs' ? '/logs' : options.screen === 'intakes' ? '/scans/intakes' : `/scans/${id}`}`)
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
  assert(notes.some(note => note.text === 'Persisted new note'))
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
  await page.getByRole('menuitem', { name: /Mark as Sold/i }).click()
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
