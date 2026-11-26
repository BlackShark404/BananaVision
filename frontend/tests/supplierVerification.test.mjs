import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'

const { outputFiles: [{ text: code }] } = await build({
  entryPoints: [fileURLToPath(new URL('../src/lib/supplierVerification.ts', import.meta.url))],
  bundle: true, format: 'esm', write: false, logLevel: 'silent',
})
const { bunchCountText, verificationVerdict, verifySupplier } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const intake = (id, expectedStock, extra = {}) => ({
  id, supplierName: 'Demo Supplier', batchNumber: id, date: '2026-11-25',
  status: 'Active', expectedStock, ...extra,
})
const scan = (cultivar, intakeId, source = 'Demo Supplier') => ({ cultivar, source, intakeId })

test('records complete, partial, incomplete and discrepancy verdicts per delivery', () => {
  const verification = verifySupplier('Demo Supplier', [
    intake('complete', [{ cultivar: 'Lakatan', expectedBunches: 2 }]),
    intake('partial', [{ cultivar: 'Latundan', expectedBunches: 3 }]),
    intake('incomplete', [{ cultivar: 'Cardaba', expectedBunches: 2 }]),
    intake('discrepancy', [{ cultivar: 'Lakatan', expectedBunches: 2 }]),
  ], [
    scan('Lakatan', 'complete'), scan('Lakatan', 'complete'),
    scan('Latundan', 'partial'), scan('Latundan', 'partial'),
    scan('Lakatan', 'discrepancy'), scan('Lakatan', 'discrepancy'), scan('Cardaba', 'discrepancy'),
  ])
  const byId = Object.fromEntries(verification.intakes.map(row => [row.id, row]))
  assert.equal(byId.complete.verdict, 'Complete')
  assert.equal(byId.partial.verdict, 'Partial')
  assert.equal(byId.incomplete.verdict, 'Incomplete')
  assert.equal(byId.discrepancy.verdict, 'Discrepancy')
  assert.equal(verification.expectedTotal, 9)
  assert.equal(verification.scannedTotal, 7)
  assert.equal(verification.verdict, 'Discrepancy')
  assert.deepEqual(
    verification.intakes.map(row => row.id).sort(),
    ['complete', 'discrepancy', 'incomplete', 'partial'],
  )
})

test('unexpected scanned varieties and over-counts are discrepancies', () => {
  const unexpected = verifySupplier('Demo Supplier', [
    intake('one', [{ cultivar: 'Lakatan', expectedBunches: 2 }]),
  ], [scan('Lakatan', 'one'), scan('Latundan', 'one')])
  assert.equal(unexpected.intakes[0].verdict, 'Discrepancy')
  assert.deepEqual(unexpected.intakes[0].varieties, [
    { cultivar: 'Lakatan', expected: 2, scanned: 1 },
    { cultivar: 'Latundan', expected: 0, scanned: 1 },
  ])

  const over = verifySupplier('Demo Supplier', [
    intake('one', [{ cultivar: 'Lakatan', expectedBunches: 1 }]),
  ], [scan('Lakatan', 'one'), scan('Lakatan', 'one')])
  assert.equal(over.intakes[0].verdict, 'Discrepancy')
})

test('missing expected stock is not reported as a false discrepancy', () => {
  const verification = verifySupplier('Demo Supplier', [intake('legacy', [])], [scan('Lakatan', 'legacy')])
  assert.equal(verification.intakes[0].verdict, 'Not recorded')
  assert.equal(verification.verdict, 'Not recorded')
  assert.equal(verification.expectedTotal, 0)
  assert.equal(verification.scannedTotal, 1)
})

test('unlinked scans stay in the supplier total and are reported separately', () => {
  const verification = verifySupplier('Demo Supplier', [
    intake('linked', [{ cultivar: 'Lakatan', expectedBunches: 2 }]),
  ], [
    scan('Lakatan', 'linked'), scan('Lakatan', 'linked'),
    scan('Latundan', undefined),
  ])
  assert.equal(verification.intakes[0].scannedTotal, 2)
  assert.equal(verification.unlinkedScans, 1)
  assert.deepEqual(verification.unlinkedVarieties, [{ cultivar: 'Latundan', expected: 0, scanned: 1 }])
  assert.equal(verification.scannedTotal, 3)
  assert.equal(verification.verdict, 'Discrepancy')
})

test('aggregate verdict is partial while any recorded delivery is still short', () => {
  const verification = verifySupplier('Demo Supplier', [
    intake('done', [{ cultivar: 'Lakatan', expectedBunches: 2 }]),
    intake('short', [{ cultivar: 'Latundan', expectedBunches: 2 }]),
  ], [
    scan('Lakatan', 'done'), scan('Lakatan', 'done'), scan('Latundan', 'short'),
  ])
  assert.equal(verification.verdict, 'Partial')
  assert.equal(verification.expectedTotal, 4)
  assert.equal(verification.scannedTotal, 3)
})

test('a supplier with no recorded expected stock and no scans reports no data', () => {
  const verification = verifySupplier('Empty Supplier', [], [])
  assert.equal(verification.verdict, 'Not recorded')
  assert.equal(verification.expectedTotal, 0)
  assert.equal(verification.scannedTotal, 0)
})

test('verdict rules handle quantity and variety mismatches explicitly', () => {
  assert.equal(verificationVerdict(0, 3, [{ cultivar: 'Lakatan', expected: 0, scanned: 3 }]), 'Not recorded')
  assert.equal(verificationVerdict(3, 0, [{ cultivar: 'Lakatan', expected: 3, scanned: 0 }]), 'Incomplete')
  assert.equal(verificationVerdict(3, 2, [{ cultivar: 'Lakatan', expected: 3, scanned: 2 }]), 'Partial')
  assert.equal(verificationVerdict(3, 3, [{ cultivar: 'Lakatan', expected: 3, scanned: 3 }]), 'Complete')
  assert.equal(verificationVerdict(3, 4, [{ cultivar: 'Lakatan', expected: 3, scanned: 4 }]), 'Discrepancy')
  assert.equal(verificationVerdict(3, 3, [{ cultivar: 'Cardaba', expected: 0, scanned: 1 }, { cultivar: 'Lakatan', expected: 3, scanned: 2 }]), 'Discrepancy')
  assert.equal(bunchCountText(0), '0 bunches')
  assert.equal(bunchCountText(1), '1 bunch')
  assert.equal(bunchCountText(12), '12 bunches')
})