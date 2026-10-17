import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'printing.fixture.tsx', port: 5198 }) })
after(async () => { await runtime?.close() })

async function setup(t, { fail = false, loseResponse = false } = {}) {
  const context = await runtime.browser.newContext()
  t.after(() => context.close())
  const page = await context.newPage()
  await page.route('https://fonts.googleapis.com/**', route => route.abort())
  await page.route('https://fonts.gstatic.com/**', route => route.abort())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  const writes = []
  let job
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }
    const reply = json => route.fulfill({ headers, json })
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    if (path.endsWith('/label')) return reply({ payload: 'BANANAVISION\nID=saved-scan\nRIPENESS=Ripe\nCONFIDENCE=90%', panel: ['BANANAVISION', 'saved-sc', 'Ripe', '3 days', '90%'], printer_name: 'TP870 S', max_quantity: 10, width_mm: 40, height_mm: 30 })
    if (req.method() === 'POST') {
      const body = req.postDataJSON()
      writes.push({ path, body })
      if (path.endsWith('/retry')) { fail = false; job.attempt_count++ }
      else job = { id: body.request_id, quantity: body.quantity, attempt_count: 1, printer_name: 'TP870 S', windows_job_id: null, error: null }
      job.status = fail ? 'FAILED' : 'SUBMITTED'
      job.error = fail ? 'TP870 S is OFFLINE' : null
      if (loseResponse) { loseResponse = false; return route.abort('failed') }
      return reply({ ...job, status: 'QUEUED' })
    }
    return reply(job)
  })
  await page.goto(`${runtime.url}/logs`, { waitUntil: 'domcontentloaded' })
  await page.getByAltText('Prediction QR label').waitFor()
  return { page, writes }
}

test('StrictMode and previews never print; quantity is bounded and explicit submission works', async t => {
  const { page, writes } = await setup(t)
  assert.equal(writes.length, 0)
  for (const invalid of ['11', '0', '1.5', '']) {
    await page.getByLabel('Labels (1–10)').fill(invalid)
    await page.getByLabel('Labels (1–10)').blur()
    assert.equal(await page.getByLabel('Labels (1–10)').inputValue(), invalid)
    await page.getByRole('button', { name: 'Print labels', exact: true }).click()
    await page.getByRole('alert').waitFor()
    assert.equal(writes.length, 0)
  }
  await page.getByLabel('Labels (1–10)').fill('3')
  await page.getByRole('button', { name: 'Print labels', exact: true }).dblclick()
  await page.getByText('3 label(s) sent to TP870 S.', { exact: false }).waitFor()
  assert.equal(writes.length, 1)
  assert.equal(writes[0].body.quantity, 3)
  await page.reload()
  await page.getByAltText('Prediction QR label').waitFor()
  assert.equal(writes.length, 1)
})

test('failed submission shows the error and explicitly retries the same job', async t => {
  const { page, writes } = await setup(t, { fail: true })
  await page.getByRole('button', { name: 'Print labels', exact: true }).click()
  await page.getByText('TP870 S is OFFLINE', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'RETRY PRINT', exact: true }).click()
  await page.getByText('1 label(s) sent to TP870 S.', { exact: false }).waitFor()
  assert.equal(writes.length, 2)
  assert.match(writes[1].path, new RegExp(`${writes[0].body.request_id}/retry$`))
  assert.deepEqual(writes[1].body, { expected_attempt: 1 })
})

test('a lost HTTP response retains the same request ID and quantity', async t => {
  const { page, writes } = await setup(t, { loseResponse: true })
  await page.getByRole('button', { name: 'Print labels', exact: true }).click()
  await page.getByRole('button', { name: 'Check / retry request', exact: true }).click()
  await page.getByText('1 label(s) sent to TP870 S.', { exact: false }).waitFor()
  assert.equal(writes.length, 2)
  assert.deepEqual(writes[1].body, writes[0].body)
})
