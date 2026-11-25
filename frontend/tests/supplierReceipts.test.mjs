import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'

const { outputFiles: [{ text: code }] } = await build({
  entryPoints: [fileURLToPath(new URL('../src/lib/supplierReceipts.ts', import.meta.url))],
  bundle: true, format: 'esm', write: false, logLevel: 'silent',
})
const { bunchCountText, receivedBySupplier } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const scan = (source, cultivar) => ({ source, cultivar })

test('counts every recorded bunch per supplier and variety', () => {
  const receipts = receivedBySupplier([
    scan('Alpha Farms', 'Lakatan'), scan('Alpha Farms', 'Lakatan'), scan('Alpha Farms', 'Cardaba'),
    scan('Beta Growers', 'Latundan'), scan('Beta Growers', 'Latundan'), scan('Beta Growers', 'Lakatan'),
  ])
  assert.deepEqual(receipts, [
    { supplier: 'Alpha Farms', total: 3, varieties: [{ cultivar: 'Lakatan', count: 2 }, { cultivar: 'Cardaba', count: 1 }] },
    { supplier: 'Beta Growers', total: 3, varieties: [{ cultivar: 'Lakatan', count: 1 }, { cultivar: 'Latundan', count: 2 }] },
  ])
})

test('orders suppliers by bunch count, then by name, and varieties in cultivar order', () => {
  const receipts = receivedBySupplier([
    scan('Zeta', 'Cardaba'), scan('Zeta', 'Unknown'),
    scan('Alpha', 'Latundan'),
    scan('Mike', 'Cardaba'), scan('Mike', 'Lakatan'), scan('Mike', 'Latundan'),
  ])
  assert.deepEqual(receipts.map(row => row.supplier), ['Mike', 'Zeta', 'Alpha'])
  assert.deepEqual(receipts[0].varieties.map(row => row.cultivar), ['Lakatan', 'Latundan', 'Cardaba'])
  assert.deepEqual(receipts[1].varieties.map(row => row.cultivar), ['Cardaba', 'Unknown'])
})

test('missing source and cultivar stay counted under explicit fallbacks', () => {
  const receipts = receivedBySupplier([
    scan(undefined, 'Lakatan'), scan('   ', null), scan('', '  '),
    scan('Alpha', null),
  ])
  assert.deepEqual(receipts, [
    { supplier: 'Unknown Supplier', total: 3, varieties: [{ cultivar: 'Lakatan', count: 1 }, { cultivar: 'Unknown', count: 2 }] },
    { supplier: 'Alpha', total: 1, varieties: [{ cultivar: 'Unknown', count: 1 }] },
  ])
})

test('an empty history has no supplier rows', () => {
  assert.deepEqual(receivedBySupplier([]), [])
})

test('bunch totals read singular and plural', () => {
  assert.equal(bunchCountText(0), '0 bunches')
  assert.equal(bunchCountText(1), '1 bunch')
  assert.equal(bunchCountText(12), '12 bunches')
})
