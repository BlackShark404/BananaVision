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

async function setup(t, status = 200) {
  const context = await runtime.browser.newContext({ timezoneId: 'America/Los_Angeles' })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const state = { record: scan(), writes: [], imageHeaders: null }
  await page.route('**/captures/**', async route => {
    state.imageHeaders = route.request().headers()
    await route.fulfill({ status: 404, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' } })
  })
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), method = request.method()
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }
    const reply = (json, code = 200) => route.fulfill({ status: code, json, headers }).catch(() => {})
    if (method === 'OPTIONS') return reply({}, 204)
    if (url.pathname === `/api/v1/scans/${id}` && method === 'GET') return reply(status === 200 ? state.record : { detail: 'Unavailable' }, status)
    if (url.pathname === '/api/v1/scans') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (url.pathname === '/api/v1/config') return reply({ camera_ids: 'NEW-CAMERA', confidence_threshold: 85, revision: 1 })
    if (url.pathname === '/api/v1/activity') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (url.pathname === '/api/v1/users') return reply({ items: [], total: 0 })
    if (method === 'GET') return reply([])
    state.writes.push(request.postDataJSON())
    return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
  })
  await page.goto(`${runtime.url}/scans/${id}`)
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
