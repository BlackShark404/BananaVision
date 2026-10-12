import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const tableSource = await readFile(new URL('../src/components/ui/table.tsx', import.meta.url), 'utf8')
const logsSource = await readFile(new URL('../src/pages/Logs.tsx', import.meta.url), 'utf8')

test('TableBody in table.tsx uses border-b-0 on last-child to preserve row border-left', () => {
  assert.ok(
    tableSource.includes('[&_tr:last-child]:border-b-0'),
    'TableBody must use [&_tr:last-child]:border-b-0 so row-level border-left is not wiped out on the last row'
  )
  assert.ok(
    !tableSource.includes('[&_tr:last-child]:border-0'),
    'TableBody must not use [&_tr:last-child]:border-0 because border-0 resets border-left to 0px'
  )
})

test('Logs.tsx rowClassName consistently assigns red indicator to all flagged scans', () => {
  // Extract rowClassName function logic from Logs.tsx
  // rowClassName={(scan) => scan.flagged ? 'border-l-3 border-l-red-500 bg-red-500/[0.03]' : ''}
  const rowClassNameMatch = logsSource.match(/rowClassName=\{.*?=>\s*(.*?)\}/)
  assert.ok(rowClassNameMatch, 'Logs.tsx must specify rowClassName on AppDataTable')

  const flagRowClass = (scan) => scan.flagged ? 'border-l-3 border-l-red-500 bg-red-500/[0.03]' : ''

  // 1. Flagged scans with various inventory statuses all get the red left indicator
  const flaggedInStock = { flagged: true, inventoryStatus: 'In Stock', confidence: 94.62 }
  const flaggedSold = { flagged: true, inventoryStatus: 'Sold', confidence: 89.64 }
  const flaggedSpoiled = { flagged: true, inventoryStatus: 'Spoiled', confidence: 91.0 }
  const flaggedForProcessing = { flagged: true, inventoryStatus: 'For Processing', confidence: 88.0 }

  assert.equal(flagRowClass(flaggedInStock), 'border-l-3 border-l-red-500 bg-red-500/[0.03]')
  assert.equal(flagRowClass(flaggedSold), 'border-l-3 border-l-red-500 bg-red-500/[0.03]')
  assert.equal(flagRowClass(flaggedSpoiled), 'border-l-3 border-l-red-500 bg-red-500/[0.03]')
  assert.equal(flagRowClass(flaggedForProcessing), 'border-l-3 border-l-red-500 bg-red-500/[0.03]')

  // 2. Unflagged scans (even if low confidence and under review) do NOT get the red left indicator
  const unflaggedLowConfidence = { flagged: false, inventoryStatus: 'In Stock', confidence: 60.0 }
  const unflaggedNormal = { flagged: false, inventoryStatus: 'In Stock', confidence: 96.0 }
  const unflaggedSold = { flagged: false, inventoryStatus: 'Sold', confidence: 92.0 }

  assert.equal(flagRowClass(unflaggedLowConfidence), '')
  assert.equal(flagRowClass(unflaggedNormal), '')
  assert.equal(flagRowClass(unflaggedSold), '')
})
