import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/scanLogFilters.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { buildScanLogsUrl, scanLogParams, normalizeScanLogSearch, selectedScanLogDay, isDefaultScanLogView } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const TODAY = '2026-10-02'
const normalized = query => {
  const next = normalizeScanLogSearch(new URLSearchParams(query), TODAY)
  return next === null ? null : Object.fromEntries(next)
}

test('buildScanLogsUrl builds the quality review link as Status: Flagged', () => {
  assert.equal(buildScanLogsUrl({ status: 'Flagged' }), '/logs?status=Flagged')
})

test('buildScanLogsUrl omits empty and undefined filters', () => {
  assert.equal(buildScanLogsUrl({}), '/logs')
  assert.equal(buildScanLogsUrl({ attention: 'at-risk' }), '/logs?attention=at-risk')
  assert.equal(buildScanLogsUrl({ status: undefined }), '/logs')
  assert.equal(buildScanLogsUrl({ date: 'all' }), '/logs?date=all')
})

test('Status Flagged is the review queue: flagged_only with or without the legacy attention', () => {
  for (const query of ['status=Flagged', 'attention=review&status=Flagged']) {
    const params = scanLogParams(new URLSearchParams(query))
    assert.equal(params.flagged_only, true, query)
    assert.equal(params.inventory_status, undefined, query)
  }
  assert.equal(scanLogParams(new URLSearchParams('status=Flagged')).attention, 'all')
})

test('scanLogParams parses inventory statuses separately from the flag', () => {
  const inStockReview = scanLogParams(new URLSearchParams('attention=review&status=In+Stock'))
  assert.equal(inStockReview.attention, 'review')
  assert.equal(inStockReview.inventory_status, 'In Stock')
  assert.equal(inStockReview.flagged_only, false)

  const sold = scanLogParams(new URLSearchParams('status=Sold'))
  assert.equal(sold.attention, 'all')
  assert.equal(sold.inventory_status, 'Sold')
  assert.equal(sold.flagged_only, false)
})

test('only a real calendar day becomes business_date; all and invalid dates mean all history', () => {
  assert.equal(scanLogParams(new URLSearchParams('date=2026-10-02')).business_date, '2026-10-02')
  for (const query of ['date=all', '', 'date=', 'date=yesterday', 'date=2026-02-30', 'date=2026-1-2']) {
    assert.equal(scanLogParams(new URLSearchParams(query)).business_date, undefined, query)
  }
  assert.equal(selectedScanLogDay(new URLSearchParams('date=2026-10-01&attention=at-risk')), '2026-10-01')
  assert.equal(selectedScanLogDay(new URLSearchParams('date=all')), '')
  assert.equal(selectedScanLogDay(new URLSearchParams('attention=at-risk')), '')
})

test('plain Scan Logs opens on the Manila day; page and sort are kept and are not filters', () => {
  assert.deepEqual(normalized(''), { date: TODAY })
  assert.deepEqual(normalized('page=3'), { page: '3', date: TODAY })
  assert.deepEqual(normalized('sort=confidence&direction=asc&limit=25'), { sort: 'confidence', direction: 'asc', limit: '25', date: TODAY })
})

test('filtered links keep all dates, and explicit dates are left alone', () => {
  for (const query of ['attention=at-risk', 'status=Flagged', 'date=all', 'date=2026-10-01', 'source_key=supplier:1', 'stock=eligible&status=In+Stock', 'intake=intake-1', 'search=alex']) {
    assert.equal(normalized(query), null, query)
  }
})

test('the default view is a date with only paging or sorting', () => {
  for (const query of ['date=2026-10-02', 'date=2026-10-02&page=2&sort=confidence&direction=asc', '']) {
    assert.equal(isDefaultScanLogView(new URLSearchParams(query)), true, query)
  }
  for (const query of ['date=2026-10-02&status=Sold', 'date=2026-10-02&attention=at-risk', 'date=all&search=x']) {
    assert.equal(isDefaultScanLogView(new URLSearchParams(query)), false, query)
  }
})

test('legacy review links become Status: Flagged without adding a date', () => {
  assert.deepEqual(normalized('attention=review'), { status: 'Flagged' })
  assert.deepEqual(normalized('attention=review&status=Flagged&page=2'), { status: 'Flagged', page: '2' })
  assert.deepEqual(normalized('attention=review&date=2026-10-01'), { date: '2026-10-01', status: 'Flagged' })
  // Another status cannot share the single Status menu with Flagged; keep the server rule.
  assert.equal(normalized('attention=review&status=In+Stock'), null)
})

test('scanLogParams parses limit or page_size for supported sizes (10, 25, 50, 100) and defaults to 10', () => {
  assert.equal(scanLogParams(new URLSearchParams('limit=25')).page_size, 25)
  assert.equal(scanLogParams(new URLSearchParams('page_size=50')).page_size, 50)
  assert.equal(scanLogParams(new URLSearchParams('limit=100')).page_size, 100)
  assert.equal(scanLogParams(new URLSearchParams('limit=999')).page_size, 10, 'unsupported size defaults to 10')
  assert.equal(scanLogParams(new URLSearchParams('limit=-5')).page_size, 10, 'negative size defaults to 10')
  assert.equal(scanLogParams(new URLSearchParams('limit=invalid')).page_size, 10, 'invalid string defaults to 10')
  assert.equal(scanLogParams(new URLSearchParams('')).page_size, 10, 'omitted size defaults to 10')
})

test('buildScanLogsUrl includes limit or page_size when specified', () => {
  assert.equal(buildScanLogsUrl({ limit: 25 }), '/logs?limit=25')
  assert.equal(buildScanLogsUrl({ page_size: 50 }), '/logs?page_size=50')
})
