import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/detectionBoxes.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { deduplicateDisplayBoxes } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const box = (x, y, w = 100, h = 140, cls = 'latundan_ripe', conf = 0.9) => ({ x, y, w, h, cls, conf })

test('fourteen fingers remain fourteen when three neighboring pairs have different ripeness labels', () => {
  // Same numeric regression as backend/test_rotation_consensus.py: IoU 0.739,
  // containment 0.85, equal areas. Each pair is two fingers, not two class guesses.
  const boxes = Array.from({ length: 8 }, (_, index) => box(index * 200, 0))
  for (let index = 0; index < 3; index++) {
    boxes.push(box(index * 300, 400))
    boxes.push(box(index * 300 + 15, 400, 100, 140, 'latundan_semi_ripe'))
  }
  const before = structuredClone(boxes)
  assert.equal(deduplicateDisplayBoxes(boxes).length, 14)
  assert.deepEqual(boxes, before)
})

test('similar-sized overlapping neighboring fingers survive containment without being mistaken for fragments', () => {
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(8, 5)]).length, 2)
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(8, 5, 100, 140, 'latundan_unripe')]).length, 2)
})

test('coincident hypotheses and aligned nested fragments count once across ripeness labels', () => {
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(0, 0, 100, 140, 'latundan_semi_ripe')]).length, 1)
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(20, 10, 60, 110, 'Latundan_Ripe')]).length, 1)
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(80, 20, 50, 50)]).length, 2)
})

test('competing cultivar hypotheses retain the backend counting safeguard', () => {
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(15, 0, 100, 140, 'lakatan_ripe')]).length, 1)
  assert.equal(deduplicateDisplayBoxes([box(0, 0), box(100, 0, 100, 140, 'lakatan_ripe')]).length, 2)
})

test('deduplication preserves source order rather than introducing another confidence-based decision', () => {
  const boxes = [box(0, 0, 100, 140, 'latundan_ripe', 0.6), box(0, 0, 100, 140, 'lakatan_ripe', 0.95)]
  assert.deepEqual(deduplicateDisplayBoxes(boxes), [boxes[0]])
})

test('stored counting decisions survive cultivar harmonization without losing raw hypotheses', () => {
  // Competing cultivar hypotheses counted once before fusion rewrote both labels.
  const boxes = [
    { ...box(0, 0), counts_as_finger: true },
    { ...box(15, 0), counts_as_finger: false },
  ]
  const before = structuredClone(boxes)
  assert.deepEqual(deduplicateDisplayBoxes(boxes), [boxes[0]])
  assert.deepEqual(boxes, before)
})

test('legacy or incomplete counting markers use geometric fallback', () => {
  const boxes = [{ ...box(0, 0), counts_as_finger: false }, box(15, 0)]
  assert.deepEqual(deduplicateDisplayBoxes(boxes), boxes)
})

test('stacked horizontal flank fingers inside a diagonal neighbor box remain distinct', () => {
  const upperDiagonal = box(839, 276, 423, 417, 'latundan_ripe', 0.92)
  const lowerHorizontal = box(853, 499, 415, 201, 'latundan_ripe', 0.63)
  assert.equal(deduplicateDisplayBoxes([upperDiagonal, lowerHorizontal]).length, 2)
})

test('centered square or portrait tip inside wide horizontal parent deduplicates cleanly', () => {
  const wideParent = box(40, 200, 400, 210, 'cardaba_unripe', 0.85)
  const centeredSub = box(185, 235, 110, 140, 'cardaba_unripe', 0.67)
  assert.equal(deduplicateDisplayBoxes([wideParent, centeredSub]).length, 1)

  const stackedChild = box(185, 205, 110, 95, 'cardaba_unripe', 0.62)
  assert.equal(deduplicateDisplayBoxes([wideParent, stackedChild]).length, 2)
})
