import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { startBrowser } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'connectivity.fixture.tsx', auth: 'persistence.auth.tsx', port: 5198 }) })
after(async () => { await runtime?.close() })

async function setup(t) {
  const context = await runtime.browser.newContext()
  t.after(() => context.close())
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  await page.clock.install()
  await page.addInitScript(() => {
    localStorage.setItem('bananavision_token', 'fixture-secret')
    window.sockets = []
    class Socket {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3
      readyState = 0; sent = []
      constructor(url) { this.url = url; if (new URL(url).pathname === '/api/v1/ws') window.sockets.push(this) }
      open() { this.readyState = 1; this.onopen?.({}) }
      send(data) { this.sent.push(JSON.parse(data)) }
      close(code = 1000) { this.readyState = 3; this.onclose?.({ code }) }
      emit() { this.onmessage?.({ data: JSON.stringify({ event: 'test', data: {} }) }) }
    }
    window.WebSocket = Socket
  })
  await page.route('**/captures/**', r => r.fulfill({ status: 404 }))
  await page.goto(`${runtime.url}/devices`)
  await page.getByRole('button', { name: 'Unmount', exact: true }).waitFor()
  await page.waitForFunction(() => window.sockets.filter(s => s.readyState !== 3).length === 2)
  return page
}

test('StrictMode keeps one active socket per hook with the current query-token protocol', async t => {
  const page = await setup(t)
  const urls = await page.evaluate(() => window.sockets.filter(s => s.readyState !== 3).map(s => s.url))
  assert.equal(urls.length, 2)
  assert.deepEqual(urls.map(url => new URL(url).searchParams.get('rooms')).sort(), ['dashboard', 'dashboard,devices'])
  for (const url of urls) {
    assert.equal(new URL(url).searchParams.get('token'), 'fixture-secret')
    assert.equal(new URL(url).hostname, '127.0.0.1')
  }
  await page.evaluate(() => window.sockets.filter(s => s.readyState !== 3).forEach(s => { s.open(); s.emit() }))
  await page.getByText('dashboard:connected:1', { exact: true }).waitFor()
  await page.getByText('dashboard,devices:connected:1', { exact: true }).waitFor()
  assert.deepEqual(await page.evaluate(() => window.sockets.flatMap(s => s.sent)), [])
})

test('disconnect retries once, session swap replaces socket, logout cancels retries', async t => {
  const page = await setup(t)
  const initial = await page.evaluate(() => window.sockets.length)
  await page.evaluate(() => { window.sockets.at(-1).open(); window.sockets.at(-1).close(1006) })
  await page.clock.runFor(1000)
  assert.equal(await page.evaluate(() => window.sockets.length), initial + 1)
  await page.getByRole('button', { name: 'Swap' }).click()
  await page.waitForFunction(() => window.sockets.filter(s => s.readyState !== 3).length === 2 && window.sockets.filter(s => s.readyState !== 3).every(s => new URL(s.url).searchParams.get('token') === 'replacement-fixture-token'))
  await page.evaluate(() => window.sockets.filter(s => s.readyState !== 3).forEach(s => { s.open(); s.close(1006) }))
  await page.getByRole('button', { name: 'Logout' }).click()
  const count = await page.evaluate(() => window.sockets.length)
  await page.evaluate(() => window.sockets.forEach(s => { s.emit(); s.close(1006) }))
  await page.clock.runFor(1200)
  assert.equal(await page.evaluate(() => window.sockets.length), count)
  await page.getByText('dashboard:disconnected:0', { exact: true }).waitFor()
  assert.equal(await page.getByTestId('delivered').textContent(), '0')
  await page.getByRole('button', { name: 'Login', exact: true }).click()
  await page.waitForFunction(() => window.sockets.filter(s => s.readyState !== 3).length === 2)
  assert.ok(await page.evaluate(() => window.sockets.filter(s => s.readyState !== 3).every(s => new URL(s.url).searchParams.get('token') === 'login-fixture-token')))
})

test('unmount during handshake ignores late callbacks and does not reconnect', async t => {
  const page = await setup(t)
  await page.getByRole('button', { name: 'Unmount' }).click()
  const count = await page.evaluate(() => window.sockets.length)
  await page.evaluate(() => window.sockets.forEach(s => { s.open(); s.emit(); s.close(1006) }))
  await page.clock.runFor(1200)
  assert.equal(await page.evaluate(() => window.sockets.length), count)
  assert.equal(await page.getByTestId('delivered').textContent(), '0')
})

test('unavailable API is actionable and does not erase the session', async t => {
  const page = await setup(t)
  await page.route('**/api/v1/scans/fixture', r => r.abort('connectionrefused'))
  await page.getByRole('button', { name: 'Request', exact: true }).click()
  await page.getByText(/Backend unavailable/).waitFor()
  assert.equal(await page.evaluate(() => localStorage.getItem('bananavision_token')), 'fixture-secret')
})

test('Landing background SVG is valid base64 and decodes as an image', async t => {
  const source = await readFile(new URL('../src/pages/Landing.tsx', import.meta.url), 'utf8')
  const uri = source.match(/data:image\/svg\+xml;base64,([^']+)/)[0]
  const context = await runtime.browser.newContext(); t.after(() => context.close())
  const page = await context.newPage()
  const decoded = await page.evaluate(async src => {
    try { const img = new Image(); img.src = src; await img.decode(); return true } catch { return false }
  }, uri)
  assert.equal(decoded, true)
})
