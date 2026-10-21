import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/isoDay.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { parseIsoDay, formatIsoDay } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('formatIsoDay renders the local calendar day as YYYY-MM-DD without UTC shifting', () => {
  // Local midnights are independent of the time zone the test runs in.
  assert.equal(formatIsoDay(new Date(2026, 9, 21)), '2026-10-21')
  assert.equal(formatIsoDay(parseIsoDay('2026-10-21')), '2026-10-21', 'parse/format must roundtrip exactly')
  assert.equal(formatIsoDay(new Date(2024, 1, 29)), '2024-02-29')
})

test('parseIsoDay accepts valid calendar days as local dates', () => {
  const parsed = parseIsoDay('2024-02-29')
  assert.ok(parsed instanceof Date)
  assert.equal(parsed.getFullYear(), 2024)
  assert.equal(parsed.getMonth(), 1)
  assert.equal(parsed.getDate(), 29)
})

test('parseIsoDay rejects impossible, malformed and missing values', () => {
  assert.equal(parseIsoDay('2026-02-30'), undefined)
  assert.equal(parseIsoDay('2023-02-29'), undefined)
  assert.equal(parseIsoDay('2026-13-01'), undefined)
  assert.equal(parseIsoDay('2026-00-01'), undefined)
  assert.equal(parseIsoDay('not-a-date'), undefined)
  assert.equal(parseIsoDay('2026-10'), undefined)
  assert.equal(parseIsoDay(''), undefined)
  assert.equal(parseIsoDay(undefined), undefined)
})
