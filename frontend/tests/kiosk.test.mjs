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

async function setup(t, { offline = false, loseResponse = false, empty = false } = {}) {
  const context = await runtime.browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
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
      if (path.endsWith('/kiosk-demo')) {
        const job = state.jobs.get(body.request_id) ?? { id: body.request_id, quantity: 1,
          printer_name: 'TP870 S', attempt_count: 1, windows_job_id: 712,
          status: offline ? 'FAILED' : 'SUBMITTED', error: offline ? 'TP870 S is OFFLINE' : null }
        state.jobs.set(job.id, job)
        if (loseResponse) { loseResponse = false; return route.abort('failed') }
        return reply({ scan: saved, print_job: { ...job, status: 'QUEUED' }, label: {
          payload: `BANANAVISION\nID=${scanId}\nRIPENESS=Ripe\nTEST=DEMO`,
          panel: ['BANANAVISION', scanId.slice(0, 8), 'Ripe', '3-5 days', '95%', 'DEMO'],
          printer_name: 'TP870 S', width_mm: 40, height_mm: 30, max_quantity: 10,
        } })
      }
      if (path.endsWith('/retry')) {
        const job = state.jobs.get(path.split('/').at(-2))
        job.status = 'SUBMITTED'; job.error = null; job.attempt_count++
        return reply({ ...job, status: 'QUEUED' })
      }
      if (path === '/api/v1/intakes') return reply({ id: 'fixture-intake', supplier_id: 'supplier-1', supplier_name: 'Fixture Supplier', batch_number: 'BCH-DEMO', status: 'Active', intake_date: '2026-10-14' })
      if (path === '/api/v1/scans/trigger') {
        const job = { id: 'live-job', quantity: 1, printer_name: 'TP870 S', attempt_count: 1, status: 'SUBMITTED', windows_job_id: 713, error: null }
        state.jobs.set(job.id, job)
        const result = { ...saved, id: '20000000-0000-4000-8000-000000000002', intake_id: body.intake_id, print_job: { ...job, status: 'QUEUED' } }
        state.scans = [result, saved]
        return reply(result)
      }
      throw new Error(`Unexpected write: ${path}`)
    }
    if (path.includes('/print-jobs/')) return reply(state.jobs.get(path.split('/').at(-1)))
    if (path === '/api/v1/auth/operators') return reply([{ id: 'operator-1', username: 'fixture', full_name: 'Fixture Operator', role: 'Operator', status: 'Active' }])
    if (path === '/api/v1/scans') return reply({ items: state.scans, total: state.scans.length, page: 1, page_size: 100 })
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

test('kiosk demo prints once, keeps real history untouched and simulates review locally', async t => {
  const { page, state } = await setup(t)
  assert.equal(state.writes.length, 0)
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByRole('button', { name: 'Run Demo & Print', exact: true }).dblclick()
  await page.getByText('Demo Complete', { exact: true }).waitFor()
  await page.getByText('Sent to TP870 S. Check the printed label.', { exact: true }).waitFor()
  if (process.env.KIOSK_SCREENSHOT_PATH) await page.screenshot({ path: process.env.KIOSK_SCREENSHOT_PATH })
  assert.equal(writesTo(state, '/kiosk-demo').length, 1)
  assert.equal(writesTo(state, '/trigger').length, 0)
  assert.equal(state.jobs.size, 1)
  assert.deepEqual(JSON.parse(await page.getByTestId('persisted-scans').textContent()), { ids: [scanId] })
  await page.getByRole('button', { name: 'Flag demo', exact: true }).click()
  assert.equal(state.writes.length, 1)
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByText('No scans yet', { exact: true }).waitFor()
  assert.equal(state.writes.length, 1)
})

test('demo offline status retries its existing job and Accept demo does not save stock', async t => {
  const { page, state } = await setup(t, { offline: true })
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByRole('button', { name: 'Run Demo & Print', exact: true }).click()
  await page.getByText('TP870 S is OFFLINE', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'RETRY PRINT', exact: true }).dblclick()
  await page.getByText('Sent to TP870 S. Check the printed label.', { exact: true }).waitFor()
  assert.equal(writesTo(state, '/retry').length, 1)
  assert.equal(state.jobs.size, 1)
  await page.getByRole('button', { name: 'Accept demo', exact: true }).click()
  assert.equal(state.writes.length, 2)
})

test('lost demo acknowledgement reuses its request ID; empty history cannot demo', async t => {
  const { page, state } = await setup(t, { loseResponse: true })
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByRole('button', { name: 'Run Demo & Print', exact: true }).click()
  await page.getByRole('button', { name: 'Retry demo request', exact: true }).click()
  await page.getByText('Demo Complete', { exact: true }).waitFor()
  const requests = writesTo(state, '/kiosk-demo')
  assert.deepEqual(requests[0].body, requests[1].body)
  assert.equal(state.jobs.size, 1)
  const empty = await setup(t, { empty: true })
  await empty.page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  assert.equal(await empty.page.getByRole('button', { name: 'Run Demo & Print', exact: true }).isDisabled(), true)
})

test('normal kiosk still requires an intake and calls the real trigger after demo is disabled', async t => {
  const { page, state } = await setup(t)
  assert.equal(await page.getByRole('button', { name: 'Scan Now', exact: true }).isDisabled(), true)
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByRole('button', { name: 'Run Demo & Print', exact: true }).click()
  await page.getByText('Demo Complete', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Demo mode', exact: true }).click()
  await page.getByRole('button', { name: 'Select Source', exact: false }).click()
  await page.getByText('Fixture Supplier', { exact: true }).click()
  await page.getByRole('button', { name: /Start.*Intake/i }).click()
  await page.getByRole('button', { name: 'Scan Now', exact: true }).click()
  await page.getByText('Scan Complete', { exact: true }).waitFor()
  await page.getByText('Sent to TP870 S. Check the printed label.', { exact: true }).waitFor()
  assert.equal(writesTo(state, '/trigger').length, 1)
  assert.deepEqual(writesTo(state, '/trigger')[0].body, { intake_id: 'fixture-intake' })
  assert.equal(writesTo(state, '/kiosk-demo').length, 1)
  assert.equal(writesTo(state, '/print').length, 0)
})
