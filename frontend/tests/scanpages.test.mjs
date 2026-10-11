import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/scanData.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { collectScanPages } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('history collection propagates the original snapshot and publishes only a complete set', async () => {
  const calls = []
  const result = await collectScanPages(async (page, size, signal, token) => {
    calls.push(token)
    return { items: [{ id: String(page) }], total: 2, page, page_size: 1, snapshot_id: 'same' }
  })
  assert.deepEqual(calls, [undefined, 'same'])
  assert.deepEqual(result.map(r => r.id), ['1', '2'])
})

for (const mode of ['changed', 'expired', 'duplicate']) {
  test(`history collection rejects ${mode} pages without publishing partial state`, async () => {
    await assert.rejects(collectScanPages(async page => {
      if (page === 2 && mode === 'expired') throw Object.assign(new Error('Snapshot expired'), { status: 410 })
      return { items: [{ id: mode === 'duplicate' ? '1' : String(page) }], total: 2, page, page_size: 1,
        snapshot_id: page === 2 && mode === 'changed' ? 'new' : 'original' }
    }), /snapshot|Snapshot|incomplete/)
  })
}
