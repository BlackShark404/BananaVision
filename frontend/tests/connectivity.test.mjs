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
  await page.addInitScript(() => {
    localStorage.setItem('bananavision_token', 'fixture-secret')
    window.sockets = []
    class Socket {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3
      readyState = 0; sent = []
      constructor(url) { this.url = url; window.sockets.push(this) }
      open() { this.readyState = 1; this.onopen?.({}) }
      send(data) { this.sent.push(JSON.parse(data)) }
      close(code = 1000) { this.readyState = 3; this.onclose?.({ code }) }
      emit() { this.onmessage?.({ data: JSON.stringify({ event: 'test', data: {} }) }) }
    }
    window.WebSocket = Socket
  })
  await page.route('**/captures/**', r => r.fulfill({ status: 404 }))
  await page.goto(`${runtime.url}/devices`)
  await page.waitForFunction(() => window.sockets.length > 0)
  return page
}

test('StrictMode and overlapping subscribers share one socket without URL credentials', async t => {
  const page = await setup(t)
  const urls = await page.evaluate(() => window.sockets.map(s => s.url))
  assert.equal(urls.length, 1)
  assert.equal(new URL(urls[0]).searchParams.has('token'), false)
  assert.equal(new URL(urls[0]).hostname, '127.0.0.1')
  await page.evaluate(() => window.sockets[0].open())
  const sent = await page.evaluate(() => window.sockets[0].sent)
  assert.deepEqual(sent[0], { event: 'authenticate', token: 'fixture-secret', rooms: ['dashboard', 'devices'] })
})

test('disconnect retries once, session swap replaces socket, logout cancels retries', async t => {
  const page = await setup(t)
  await page.evaluate(() => { window.sockets.at(-1).open(); window.sockets.at(-1).close(1006) })
  await page.waitForFunction(() => window.sockets.length === 2)
  await page.getByRole('button', { name: 'Swap' }).click()
  await page.waitForFunction(() => window.sockets.length === 3)
  await page.evaluate(() => window.sockets.at(-1).open())
  assert.equal(await page.evaluate(() => window.sockets.at(-1).sent[0].token), 'replacement-fixture-token')
  await page.getByRole('button', { name: 'Logout' }).click()
  const count = await page.evaluate(() => window.sockets.length)
  await page.evaluate(() => window.sockets.forEach(s => { s.emit(); s.close(1006) }))
  await page.waitForTimeout(1200)
  assert.equal(await page.evaluate(() => window.sockets.length), count)
  await page.getByText('dashboard:disconnected:0', { exact: true }).waitFor()
})

test('unmount during handshake ignores late callbacks and does not reconnect', async t => {
  const page = await setup(t)
  await page.getByRole('button', { name: 'Unmount' }).click()
  await page.waitForTimeout(30)
  const count = await page.evaluate(() => window.sockets.length)
  await page.evaluate(() => window.sockets.forEach(s => { s.open(); s.emit(); s.close(1006) }))
  await page.waitForTimeout(1200)
  assert.equal(await page.evaluate(() => window.sockets.length), count)
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
