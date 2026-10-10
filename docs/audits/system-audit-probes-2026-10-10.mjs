// Audit-only characterization. Passing confirms observed gaps, not corrected behavior.
// No app imports, dependencies, server, database, browser, environment or file writes.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import test from 'node:test'

const root = new URL('../../', import.meta.url)
const read = path => readFileSync(fileURLToPath(new URL(path, root)), 'utf8')
const extract = (source, pattern, label) => {
  const match = source.match(pattern)
  assert.ok(match, `${label} changed: review probe before interpreting results`)
  return match[1]
}
const utils = read('frontend/src/lib/utils.ts')
const spoilageBody = extract(utils, /export function parseSpoilageAvg\(val: string\): number \{([\s\S]*?)\n\}/, 'spoilage parser')
const parse = vm.runInNewContext(`(function(val) {${spoilageBody}\n})`)
const inventory = read('frontend/src/pages/Inventory.tsx')
const riskBody = extract(inventory, /inStock\.forEach\(s => \{\s*(const daysNum = [\s\S]*?if \(daysNum > 2\) return)/, 'Inventory alert predicate')
const inventoryAlerts = vm.runInNewContext(`(function(s, parseSpoilageAvg) {${riskBody}; return true})`)
const filters = read('frontend/src/lib/scanLogFilters.ts')
const buildBody = extract(filters, /export function buildScanLogsUrl\(filters: ScanLogNavigation = \{\}\) \{([\s\S]*?)\n\}/, 'Logs URL builder')
const paramsBody = extract(filters, /export function scanLogParams\(params: URLSearchParams\): ScanLogParams \{([\s\S]*?)\n\}/, 'Logs query parser')
const build = vm.runInNewContext(`(function(filters = {}) {${buildBody}\n})`, { URLSearchParams })
const params = vm.runInNewContext(`(function(params) {${paramsBody}\n})`)

test('characterizes Inventory ignoring elapsed age and accepting unknown estimates as urgent', () => {
  assert.equal(parse('5-7'), 6)
  const aged = { spoilageDays: '5-7', dateTime: '2026-10-06T12:00:00+08:00' }
  const now = Date.parse('2026-10-10T12:00:00+08:00')
  const remaining = parse(aged.spoilageDays) - (now - Date.parse(aged.dateTime)) / 86_400_000
  assert.equal(remaining, 2)
  assert.equal(inventoryAlerts(aged, parse), undefined, 'current UI omits an aged two-day risk')
  for (const value of ['Unknown', 'NaN', '', '3-1']) {
    assert.equal(inventoryAlerts({ spoilageDays: value }, parse), true, `current UI alerts on ${JSON.stringify(value)}`)
  }
})

test('characterizes Dashboard review URL selecting flagged-only instead of the full review predicate', () => {
  const dashboard = read('frontend/src/pages/Dashboard.tsx')
  assert.equal((dashboard.match(/status: view === "review" \? "Flagged" : undefined/g) ?? []).length, 2)
  const current = params(new URLSearchParams(build({ status: 'Flagged' }).split('?')[1]))
  const complete = params(new URLSearchParams(build({ attention: 'review' }).split('?')[1]))
  assert.equal(current.flagged_only, true)
  assert.equal(current.attention, 'all')
  assert.equal(complete.flagged_only, false)
  assert.equal(complete.attention, 'review')
  // Independent truth-table example of the SQL OR predicate; no database executed.
  const record = { flagged: false, confidence: 60 }
  assert.equal(record.flagged || record.confidence < 85, true)
  assert.equal(record.flagged, false)
})

test('characterizes daily group drilldowns dropping the selected business date', () => {
  const groups = read('frontend/src/components/DashboardRecords.tsx')
  assert.equal((groups.match(/business_date: ""/g) ?? []).length, 2)
  assert.equal(build({ date: '', source_key: 'text:Farm' }), '/logs?source_key=text%3AFarm')
  assert.equal(build({ date: '2026-10-10', source_key: 'text:Farm' }), '/logs?date=2026-10-10&source_key=text%3AFarm')
})
