import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/spoilageDisplay.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { formatSpoilageDays, spoilageDayUnit } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

for (const [stored, label] of [
  ['0.9938128387987426', '1 day'], ['0.7435556840773698', '1 day'],
  ['1.012775879604427', '1–2 days'], ['1.9999', '1–2 days'],
  ['2', '2 days'], ['2.00001', '2–3 days'], ['6.07123208429123', '6–7 days'],
  ['4.861489519142744', '4–5 days'], ['11.0092880647441', '11–12 days'],
  ['1', '1 day'], ['0', '0 days'], [0, '0 days'], [0.0000001, '1 day'],
  ['1-2', '1–2 days'], ['3–4', '3–4 days'], [' 3 - 6 ', '3–6 days'],
  ['1-1', '1 day'], ['1.2-3.4', '1–4 days'],
  [null, 'Unknown'], [undefined, 'Unknown'], ['', 'Unknown'], ['Unknown', 'Unknown'],
  [NaN, 'Unknown'], [Infinity, 'Unknown'], ['-1', 'Unknown'], ['3-1', 'Unknown'],
  ['1e2', 'Unknown'], ['0x10', 'Unknown'], ['1 day', 'Unknown'],
]) {
  test(`display ${String(stored)} as ${label} without changing the source`, () => {
    const scan = Object.freeze({ spoilage_days: stored })
    assert.equal(formatSpoilageDays(scan.spoilage_days), label)
    const amount = formatSpoilageDays(scan.spoilage_days, false)
    const unit = spoilageDayUnit(scan.spoilage_days)
    assert.equal([amount, unit].filter(Boolean).join(' '), label)
    assert.equal(scan.spoilage_days, stored)
  })
}
