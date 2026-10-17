import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/scanData.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { collectScanPages, cultivarCameraConflict } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

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

const camera = (camera_id, camera_label, detected_cultivar, confidence = 90) => ({
  camera_id, camera_label, detected_cultivar, detected_ripeness: 'Ripe', confidence,
})
const splitViews = () => [
  camera('CAM-001', 'Top', 'Lakatan', 65), camera('CAM-002', 'Left', 'Latundan', 90),
  camera('CAM-003', 'Right', 'Lakatan', 70), camera('CAM-004', 'Rear', 'Latundan', 65.8),
]

test('two versus two cultivar views disclose uncertainty without changing saved prediction', () => {
  const scan = { cultivar: 'Latundan', confidence: 77.9, detections: splitViews() }
  const before = structuredClone(scan)
  assert.equal(cultivarCameraConflict(scan), 'Top + Right: Lakatan; Left + Rear: Latundan')
  assert.deepEqual(scan, before)
})

test('manual cultivar corrections remain visible despite original split views', () => {
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', isOverridden: true,
    originalAiResult: { cultivar: 'Latundan' }, detections: splitViews() }), null)
})

test('a count-only or unverifiable override cannot conceal cultivar disagreement', () => {
  for (const originalAiResult of [undefined, { cultivar: 'Latundan', fingerCount: 16 }]) {
    assert.equal(cultivarCameraConflict({ cultivar: 'Latundan', isOverridden: true,
      originalAiResult, detections: splitViews() }), 'Top + Right: Lakatan; Left + Rear: Latundan')
  }
})

test('recorded cultivar correction history preserves a reviewed return to the original cultivar', () => {
  assert.equal(cultivarCameraConflict({ cultivar: 'Latundan', isOverridden: true,
    originalAiResult: { cultivar: 'Latundan' }, detections: splitViews(), history: [{
      previous_values: { cultivar: 'Lakatan' }, new_values: { cultivar: 'Latundan' },
    }] }), null)
})

test('unanimous views, supported majority and absent view evidence keep existing display', () => {
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan' }), null)
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', detections: [] }), null)
  const detections = splitViews()
  detections[1].detected_cultivar = 'Lakatan'
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', detections }), null)
  detections[3].detected_cultivar = 'Lakatan'
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', detections }), null)
})

test('a repeated camera cannot create cultivar majority', () => {
  const detections = splitViews()
  detections.push({ ...detections[1] })
  assert.equal(cultivarCameraConflict({ cultivar: 'Latundan', detections }), 'Top + Right: Lakatan; Left + Rear: Latundan')
})

test('incomplete and invalid camera classifications do not establish opposing evidence', () => {
  for (const confidence of [null, 0, -1, 101, NaN, Infinity]) {
    const detections = [camera('1', 'Top', 'Lakatan'), camera('2', 'Left', 'Latundan', confidence)]
    assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', detections }), null)
  }
  const detections = [camera('1', 'Top', 'Lakatan'), { ...camera('2', 'Left', 'Latundan'), detected_ripeness: null }]
  assert.equal(cultivarCameraConflict({ cultivar: 'Lakatan', detections }), null)
})

test('a weighted candidate without camera majority is uncertain even if another cultivar has one', () => {
  const detections = splitViews()
  detections[3].detected_cultivar = 'Lakatan'
  assert.equal(cultivarCameraConflict({ cultivar: 'Latundan', detections }), 'Top + Right + Rear: Lakatan; Left: Latundan')
})
