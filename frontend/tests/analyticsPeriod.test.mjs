import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/analyticsPeriod.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { analyticsPeriodParams, analyticsPeriodLabel, hasCustomDates, rangeChoice } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('a preset sends only the range, as the backend contract defines it', () => {
  for (const range of ['today', 'week', 'month', 'all']) {
    assert.deepEqual(analyticsPeriodParams({ range, from: '', to: '' }), { range })
  }
})

test('dates replace the preset and are sent as inclusive Manila days', () => {
  assert.deepEqual(analyticsPeriodParams({ range: 'week', from: '2026-11-20', to: '2026-11-24' }),
    { date_from: '2026-11-20', date_to: '2026-11-24' })
  assert.deepEqual(analyticsPeriodParams({ range: 'month', from: '2026-11-20', to: '' }), { date_from: '2026-11-20' })
  assert.deepEqual(analyticsPeriodParams({ range: 'today', from: '', to: '2026-11-24' }), { date_to: '2026-11-24' })
  assert.equal(hasCustomDates({ range: 'week', from: '', to: '' }), false)
  assert.equal(hasCustomDates({ range: 'week', from: '', to: '2026-11-24' }), true)
})

test('"Custom" is derived from the dates, never stored', () => {
  assert.equal(rangeChoice({ range: 'month', from: '', to: '' }), 'month')
  assert.equal(rangeChoice({ range: 'month', from: '2026-11-20', to: '' }), 'custom')
})

test('labels name the period in words', () => {
  assert.equal(analyticsPeriodLabel({ range: 'today', from: '', to: '' }), 'Today')
  assert.equal(analyticsPeriodLabel({ range: 'week', from: '', to: '' }), 'Last 7 Days')
  assert.equal(analyticsPeriodLabel({ range: 'month', from: '', to: '' }), 'Last 30 Days')
  assert.equal(analyticsPeriodLabel({ range: 'all', from: '', to: '' }), 'All Time')
  assert.equal(analyticsPeriodLabel({ range: 'week', from: '2026-11-20', to: '2026-11-24' }), 'Nov 20, 2026 – Nov 24, 2026')
  assert.equal(analyticsPeriodLabel({ range: 'week', from: '2026-11-24', to: '2026-11-24' }), 'Nov 24, 2026')
  assert.equal(analyticsPeriodLabel({ range: 'week', from: '2026-01-05', to: '' }), 'From Jan 5, 2026')
  assert.equal(analyticsPeriodLabel({ range: 'week', from: '', to: '2026-12-31' }), 'Up to Dec 31, 2026')
})
