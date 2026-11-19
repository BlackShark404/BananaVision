import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'scanimages.fixture.tsx', auth: 'dashboard.auth.tsx', port: 5199 }) })
after(async () => { await runtime?.close() })

const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }

async function setup(t, mode) {
  const context = await runtime.browser.newContext()
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, []) })
  await installEnvironment(page)
  const state = { requests: 0 }
  await page.route('**/captures/**', route => {
    state.requests += 1
    return route.fulfill({ contentType: 'image/svg+xml', headers: cors,
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#7a9e3a"/></svg>' })
  })
  await page.goto(`${runtime.url}/logs?mode=${mode}`)
  return { page, state }
}

test('deferred evidence waits until the placeholder nears the viewport', async t => {
  const { page, state } = await setup(t, 'offscreen')
  await page.waitForTimeout(300)
  assert.equal(state.requests, 0)
  await page.locator('#deferred').scrollIntoViewIfNeeded()
  await page.getByRole('img', { name: 'Deferred evidence' }).waitFor()
  assert.equal(state.requests, 1)
})

test('thumbnail blobs survive remounts and are cleared with the session', async t => {
  const { page, state } = await setup(t, 'cache')
  await page.getByRole('img', { name: 'Cached evidence' }).waitFor()
  assert.equal(state.requests, 1)
  await page.getByRole('button', { name: 'Toggle image' }).click()
  await page.getByRole('button', { name: 'Toggle image' }).click()
  await page.getByRole('img', { name: 'Cached evidence' }).waitFor()
  assert.equal(state.requests, 1)
  await page.getByRole('button', { name: 'Clear session' }).click()
  await page.getByRole('button', { name: 'Toggle image' }).click()
  await page.getByRole('button', { name: 'Toggle image' }).click()
  await page.getByRole('img', { name: 'Cached evidence' }).waitFor()
  assert.equal(state.requests, 2)
})
