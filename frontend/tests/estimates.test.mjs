import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'

const { outputFiles: [{ text: code }] } = await build({
  entryPoints: [new URL('../src/lib/estimates.ts', import.meta.url).pathname],
  bundle: true, format: 'esm', write: false, logLevel: 'silent',
})
const { estimateText, fingerCountIsEstimate, fingerCountText, fingersLabel, ESTIMATE_PREFIX } =
  await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('the estimate prefix is "Est."', () => {
  assert.equal(ESTIMATE_PREFIX, 'Est.')
})

test('finger counts read as estimates with singular and plural, and corrected counts read plainly', () => {
  assert.equal(fingerCountText(13), 'Est. 13 fingers')
  assert.equal(fingerCountText(1), 'Est. 1 finger')
  assert.equal(fingerCountText(0), 'Est. 0 fingers')
  assert.equal(fingerCountText(13, false), '13 fingers')
  assert.equal(fingerCountText(1, false), '1 finger')
  for (const missing of [null, undefined, Number.NaN, -1, 2.5]) {
    assert.equal(fingerCountText(missing), 'Fingers unknown')
  }
})

test('finger labels say Est. unless the count was corrected', () => {
  assert.equal(fingersLabel(), 'Est. Fingers')
  assert.equal(fingersLabel(true), 'Est. Fingers')
  assert.equal(fingersLabel(false), 'Fingers')
})

test('a finger count is an estimate unless a person changed it from the AI value', () => {
  assert.equal(fingerCountIsEstimate({ fingerCount: 7 }), true)
  assert.equal(fingerCountIsEstimate({ fingerCount: 7, isOverridden: false, originalAiResult: { fingerCount: 5 } }), true)
  // Another field was corrected; the count is still the AI value.
  assert.equal(fingerCountIsEstimate({ fingerCount: 7, isOverridden: true, originalAiResult: { fingerCount: 7 } }), true)
  assert.equal(fingerCountIsEstimate({ fingerCount: 9, isOverridden: true, originalAiResult: { fingerCount: 7 } }), false)
  // Overridden without a recorded AI baseline: the count cannot be told apart, so it stays marked.
  assert.equal(fingerCountIsEstimate({ fingerCount: 9, isOverridden: true }), true)
  assert.equal(fingerCountIsEstimate({ fingerCount: 9, isOverridden: true, originalAiResult: {} }), true)
})

test('other estimates gain the prefix except when there is nothing to estimate', () => {
  assert.equal(estimateText('0–2 days left'), 'Est. 0–2 days left')
  assert.equal(estimateText('Overdue'), 'Est. Overdue')
  assert.equal(estimateText('1–3 days'), 'Est. 1–3 days')
  for (const blank of ['Unknown', '—', '', null, undefined]) assert.equal(estimateText(blank), blank ?? '')
  // Never doubled.
  assert.equal(estimateText('Est. 1–3 days'), 'Est. 1–3 days')
})
