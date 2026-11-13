import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

// The QR page through the real app: real routes, providers, auth and 401 handling.
let runtime
before(async () => { runtime = await startBrowser({ fixture: 'public-scan-app.fixture.tsx', auth: 'app.auth.tsx', port: 5196 }) })
after(async () => { await runtime?.close() })

const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
const CORS = { 'access-control-allow-origin': '*' }
const STAFF = { id: 'operator-1', username: 'operator', fullName: 'Station Operator', role: 'Operator' }
const record = {
  id: 'fixture-scan', date_time: '2026-09-30T12:00:00+08:00', cultivar: 'Lakatan',
  ripeness: 'Ripe', spoilage_days: '5-7', remaining_days: 4, risk_as_of: '2026-10-02T12:00:00+08:00',
  confidence: 90, finger_count: 7, temperature: 24, humidity: 80, vpd: 0.6,
  treatment: 'Natural', source_text: 'Demo source', inventory_status: 'In Stock', images: [],
}

// A phone that still holds a staff session whose token has expired or was revoked:
// every staff request answers 401, which the app turns into a trip to /login.
async function openWithExpiredSession(t, path) {
  const context = await runtime.browser.newContext(PHONE)
  const page = await context.newPage()
  const errors = [], publicRequests = [], staffRequests = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  // The real app lazy-loads its pages, and React reveals Suspense content on a timer, so
  // the frozen test clock must run (from 2026-10-02 12:00 in Manila).
  await page.clock.resume()
  await page.addInitScript(user => {
    // Seed the stored session once per tab, as a real phone would have it.
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('bananavision_user', JSON.stringify(user))
      sessionStorage.setItem('seeded', '1')
    }
    const TestSocket = window.WebSocket
    window.socketUrls = []
    window.WebSocket = class extends TestSocket {
      constructor(url, ...rest) { super(url, ...rest); window.socketUrls.push(String(url)) }
    }
  }, STAFF)
  await page.route('http://127.0.0.1:8000/**', route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/scans/fixture-scan/track') {
      publicRequests.push(route.request())
      return route.fulfill({ json: record, headers: CORS })
    }
    staffRequests.push(url.pathname)
    return route.fulfill({ status: 401, json: { detail: 'Could not validate credentials' }, headers: CORS })
  })
  await page.goto(`${runtime.url}${path}`)
  return { page, publicRequests, staffRequests }
}

test('a phone with an old staff session stays on the QR data page and loads no staff data', async t => {
  const { page, publicRequests, staffRequests } = await openWithExpiredSession(t, '/track/fixture-scan')
  await page.getByText('Lakatan', { exact: true }).waitFor()
  await page.getByText('Scan details', { exact: true }).click()
  await page.getByText('Est. Fingers', { exact: true }).waitFor()
  // Exact countdown wording is covered in public-scan.test.mjs with a frozen clock.
  await page.getByText('Est. 5–7 days from scan', { exact: true }).waitFor()
  await page.getByText(/^\d+(–\d+)? days? left$/).waitFor()
  // Timers, reconnects and focus reconciles get their chance to run.
  await page.clock.fastForward('00:05:00')
  await page.evaluate(() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')) })
  await page.clock.fastForward('00:01:00')
  assert.equal(new URL(page.url()).pathname, '/track/fixture-scan')
  assert.deepEqual(staffRequests, [])
  // StrictMode (as in main.tsx) mounts effects twice in development and cancels the first
  // fetch, so one or two public reads are expected; none may carry the staff token.
  assert.ok(publicRequests.length >= 1 && publicRequests.length <= 2)
  for (const request of publicRequests) {
    assert.equal(request.method(), 'GET')
    assert.equal(request.headers().authorization, undefined)
  }
  // Only the Vite dev server's own reload socket may exist; no app socket is opened.
  assert.deepEqual(await page.evaluate(() => window.socketUrls.filter(url => new URL(url).host !== location.host)), [])
  // The stored session is left alone; the phone is not logged out by viewing a QR page.
  assert.equal(JSON.parse(await page.evaluate(() => localStorage.getItem('bananavision_user'))).id, STAFF.id)
  assert.deepEqual(await page.evaluate(() => {
    const root = document.documentElement
    return { width: root.clientWidth, overflow: root.scrollWidth > root.clientWidth }
  }), { width: 390, overflow: false })
  assert.equal(await page.locator('a, button, [role="button"], [role="link"], [onclick]').count(), 0)
  assert.doesNotMatch(await page.locator('body').innerText(), /log\s*in|login|sign\s*in|website|dashboard/i)
})

test('staff pages still load staff data and still send an expired session to login', async t => {
  const { page, staffRequests } = await openWithExpiredSession(t, '/dashboard')
  await page.waitForURL(url => url.pathname === '/login')
  assert.ok(staffRequests.length > 0)
})
