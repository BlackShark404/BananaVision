import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/scanLogFilters.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { buildScanLogsUrl, scanLogParams } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('buildScanLogsUrl includes attention=review and status=Flagged for quality reviews', () => {
  const url = buildScanLogsUrl({ attention: 'review', status: 'Flagged' })
  assert.equal(url, '/logs?attention=review&status=Flagged')
})

test('buildScanLogsUrl omits empty and undefined filters', () => {
  assert.equal(buildScanLogsUrl({}), '/logs')
  assert.equal(buildScanLogsUrl({ attention: 'at-risk' }), '/logs?attention=at-risk')
  assert.equal(buildScanLogsUrl({ status: undefined }), '/logs')
})

test('scanLogParams does not set flagged_only when attention=review is active', () => {
  const params = scanLogParams(new URLSearchParams('attention=review&status=Flagged'))
  assert.equal(params.attention, 'review')
  assert.equal(params.flagged_only, false, 'flagged_only must be false so low-confidence scans are not excluded')
  assert.equal(params.inventory_status, undefined)
})

test('scanLogParams sets flagged_only when status=Flagged is manually selected without review attention', () => {
  const params = scanLogParams(new URLSearchParams('status=Flagged'))
  assert.equal(params.attention, 'all')
  assert.equal(params.flagged_only, true)
  assert.equal(params.inventory_status, undefined)
})

test('scanLogParams parses inventory status properly with and without review attention', () => {
  const inStockReview = scanLogParams(new URLSearchParams('attention=review&status=In+Stock'))
  assert.equal(inStockReview.attention, 'review')
  assert.equal(inStockReview.inventory_status, 'In Stock')
  assert.equal(inStockReview.flagged_only, false)

  const sold = scanLogParams(new URLSearchParams('status=Sold'))
  assert.equal(sold.attention, 'all')
  assert.equal(sold.inventory_status, 'Sold')
  assert.equal(sold.flagged_only, false)
})
