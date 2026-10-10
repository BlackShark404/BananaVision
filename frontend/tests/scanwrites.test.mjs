import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

async function moduleUnderTest() {
  const source = await readFile(new URL('../src/lib/scanWrites.ts', import.meta.url), 'utf8')
  const { code } = await transform(source, { loader: 'ts', format: 'esm' })
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}#${crypto.randomUUID()}`)
}

test('lost acknowledgement retries preserve exact identity and payload; changed draft is rejected', async () => {
  const { scanWrite } = await moduleUnderTest()
  const sent = []
  const payload = { expected_revision: 3, flagged: true }
  await assert.rejects(scanWrite('user:scan:flag', payload, async body => {
    sent.push(body); throw new TypeError('Failed to fetch')
  }))
  await assert.rejects(scanWrite('user:scan:flag', { ...payload, flagged: false }, async () => {}), /Retry the previous/)
  const result = await scanWrite('user:scan:flag', payload, async body => { sent.push(body); return { revision: 4 } })
  assert.equal(result.revision, 4)
  assert.deepEqual(sent[0], sent[1])
  await scanWrite('user:scan:flag', payload, async body => { sent.push(body); return {} })
  assert.notEqual(sent[1].request_id, sent[2].request_id)
})

test('concurrent identical clicks coalesce; definitive conflict and auth cleanup release retry state', async () => {
  const { scanWrite, clearScanWrites } = await moduleUnderTest()
  let release, calls = 0
  const send = () => { calls++; return new Promise(resolve => { release = resolve }) }
  const a = scanWrite('user:scan', { expected_revision: 1 }, send)
  const b = scanWrite('user:scan', { expected_revision: 1 }, send)
  await Promise.resolve()
  release('saved')
  assert.deepEqual(await Promise.all([a, b]), ['saved', 'saved'])
  assert.equal(calls, 1)
  await assert.rejects(scanWrite('user:scan', { expected_revision: 1 }, async () => { throw Object.assign(new Error('Conflict'), { status: 409 }) }))
  await scanWrite('user:scan', { expected_revision: 2 }, async () => 'okay')
  await assert.rejects(scanWrite('user:scan', {}, async () => { throw new Error('Network') }))
  clearScanWrites()
  assert.equal(await scanWrite('user:scan', { changed: true }, async () => 'new session'), 'new session')
})

test('retry after a background refresh keeps the original expected revision', async () => {
  const { scanWrite } = await moduleUnderTest()
  let original
  await assert.rejects(scanWrite('user:scan:flag', { expected_revision: 1, flagged: true }, async body => {
    original = body; throw new Error('Lost response')
  }))
  await scanWrite('user:scan:flag', { expected_revision: 2, flagged: true }, async body => {
    assert.deepEqual(body, original)
  })
})


test('changed flag or reopened bulk can explicitly replay the original uncertain operation', async () => {
  for (const [original, changed] of [
    [{ expected_revision: 1, flagged: true }, { expected_revision: 2, flagged: false }],
    [{ expected_revisions: { a: 1 }, reason: 'Sold', inventory_status: 'Sold' }, { expected_revisions: { a: 2 }, reason: 'Sold', inventory_status: 'Sold' }],
  ]) {
    const { scanWrite, clearScanWrites } = await moduleUnderTest()
    const sent = []
    const send = async body => { sent.push(body); if (sent.length === 1) throw new TypeError('Lost response'); return { revision: 2 } }
    await assert.rejects(scanWrite('scope', original, send))
    let uncertain
    try { await scanWrite('scope', changed, send) } catch (e) { uncertain = e }
    assert.equal(typeof uncertain.retry, 'function')
    assert.deepEqual(await uncertain.retry(), { revision: 2 })
    assert.deepEqual(sent[0], sent[1])
    await assert.rejects(uncertain.retry(), /no longer pending/)
    await assert.rejects(scanWrite('other', original, async () => { throw new TypeError('offline') })).catch(() => {})
    let expired
    try { await scanWrite('other', changed, send) } catch (e) { expired = e }
    clearScanWrites()
    await assert.rejects(expired.retry(), /no longer pending/)
  }
})
