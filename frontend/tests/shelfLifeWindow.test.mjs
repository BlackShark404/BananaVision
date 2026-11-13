import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'

// Asia/Manila must come from the code, never from the machine that renders the page.
process.env.TZ = 'America/Los_Angeles'

// Bundled so the module's own import of lib/manilaTime.ts is included.
const { outputFiles: [{ text: code }] } = await build({
  entryPoints: [new URL('../src/lib/shelfLifeWindow.ts', import.meta.url).pathname],
  bundle: true, format: 'esm', write: false, logLevel: 'silent',
})
const { liveShelfLife, manilaDayNumber, shelfLifeWindowDetail, shelfLifeWindowLabel } =
  await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
// The same rule table drives backend/tests/test_shelf_life_window.py.
const cases = JSON.parse(await readFile(
  new URL('../../backend/tests/data/shelf_life_window_cases.json', import.meta.url), 'utf8',
))

const DAY = 86_400_000
const at = iso => Date.parse(iso)
const isoDay = time => new Date(time).toISOString().slice(0, 10)
// What the server sends for a scan `elapsed` Manila days before its date `asOf`.
const serverWindow = (min, max, elapsed, asOf) => Object.freeze({
  min_days: min, max_days: max, elapsed_days: elapsed,
  remaining_min_days: Math.max(0, min - elapsed), remaining_max_days: Math.max(0, max - elapsed),
  days_past: Math.max(0, elapsed - max),
  state: elapsed > max ? 'expired' : elapsed === max ? 'final_day' : 'active',
  scan_date: isoDay(Date.parse(`${asOf}T00:00:00Z`) - elapsed * DAY), as_of_date: asOf,
})
// What the server sends on `servedDate` for a scan dated `scanDate` (its count is clamped at zero).
const servedOn = (min, max, scanDate, servedDate) => {
  const elapsed = Math.max(0, (Date.parse(`${servedDate}T00:00:00Z`) - Date.parse(`${scanDate}T00:00:00Z`)) / DAY)
  return Object.freeze({ ...serverWindow(min, max, elapsed, servedDate), scan_date: scanDate })
}

for (const item of cases.roll_forward) {
  test(`roll forward: ${item.name}`, () => {
    const served = servedOn(item.min, item.max, item.scan_date, item.served_date)
    // Noon in Manila on the page's date.
    const live = liveShelfLife(served, Date.parse(`${item.page_date}T04:00:00Z`))
    assert.equal(live.elapsedDays, item.elapsed)
    assert.equal(live.state, item.state)
    assert.equal(shelfLifeWindowLabel(live), item.label)
  })
}

for (const item of cases.progression) {
  test(`${item.min}-${item.max} on day +${item.elapsed} reads "${item.label}"`, () => {
    const expected = {
      elapsedDays: item.elapsed, remainingMin: item.remaining_min, remainingMax: item.remaining_max,
      daysPast: item.days_past, state: item.state,
    }
    // Served today: the page shows exactly what the server counted.
    const today = serverWindow(item.min, item.max, item.elapsed, '2026-11-13')
    assert.deepEqual(liveShelfLife(today, at('2026-11-13T04:00:00Z')), expected)
    assert.deepEqual(
      [today.remaining_min_days, today.remaining_max_days, today.days_past, today.state],
      [item.remaining_min, item.remaining_max, item.days_past, item.state],
    )
    // Served on the scan day and left open: the page reaches the same answer by itself.
    const scanDay = serverWindow(item.min, item.max, 0, '2026-11-06')
    const later = liveShelfLife(scanDay, at('2026-11-06T04:00:00Z') + item.elapsed * DAY)
    assert.deepEqual(later, expected)
    assert.equal(shelfLifeWindowLabel(later), item.label)
  })
}

test('a week-old 1-3 day estimate is overdue, not still 1-3 days', () => {
  const live = liveShelfLife(serverWindow(1, 3, 7, '2026-11-13'), at('2026-11-13T04:00:00Z'))
  assert.equal(shelfLifeWindowLabel(live), 'Overdue')
  assert.equal(shelfLifeWindowDetail(live), 'The estimated window ended 4 days ago')
  assert.equal(shelfLifeWindowDetail({ ...live, daysPast: 1 }), 'The estimated window ended 1 day ago')
})

test('the day rolls over at Manila midnight, not at UTC midnight or the browser midnight', () => {
  const scanDay = serverWindow(1, 3, 0, '2026-11-06')
  // 23:59 in Manila on the 6th is 15:59 UTC and still the morning of the 6th in Los Angeles.
  assert.equal(liveShelfLife(scanDay, at('2026-11-06T15:59:59Z')).elapsedDays, 0)
  assert.equal(shelfLifeWindowLabel(liveShelfLife(scanDay, at('2026-11-06T15:59:59Z'))), '1–3 days left')
  // 00:00 in Manila on the 7th is 16:00 UTC on the 6th.
  const rolled = liveShelfLife(scanDay, at('2026-11-06T16:00:00Z'))
  assert.equal(rolled.elapsedDays, 1)
  assert.equal(shelfLifeWindowLabel(rolled), '0–2 days left')
  // UTC midnight is 08:00 in Manila: the same Manila day as the server's date.
  const morning = serverWindow(1, 3, 1, '2026-11-07')
  assert.equal(liveShelfLife(morning, at('2026-11-07T00:05:00Z')).elapsedDays, 1)
  assert.equal(manilaDayNumber(at('2026-11-06T16:00:00Z')) - manilaDayNumber(at('2026-11-06T15:59:59Z')), 1)
  assert.equal(manilaDayNumber(at('2026-11-07T00:05:00Z')), manilaDayNumber(at('2026-11-06T16:00:00Z')))
})

test('a clock behind the server never counts backwards', () => {
  const served = serverWindow(1, 3, 2, '2026-11-08')
  const live = liveShelfLife(served, at('2026-11-01T00:00:00Z'))
  assert.equal(live.elapsedDays, 2)
  assert.equal(shelfLifeWindowLabel(live), '0–1 days left')
})

test('a missing or damaged window is unknown and the input is never changed', () => {
  const now = at('2026-11-13T04:00:00Z')
  for (const value of [
    null, undefined, {}, { ...serverWindow(1, 3, 0, '2026-11-13'), as_of_date: '13/11/2026' },
    { ...serverWindow(1, 3, 0, '2026-11-13'), as_of_date: null },
    { ...serverWindow(1, 3, 0, '2026-11-13'), min_days: 1.5 },
    { ...serverWindow(1, 3, 0, '2026-11-13'), min_days: -1 },
    { ...serverWindow(3, 1, 0, '2026-11-13') },
    { ...serverWindow(1, 3, 0, '2026-11-13'), scan_date: undefined },
    { ...serverWindow(1, 3, 0, '2026-11-13'), scan_date: '2026-11-13T00:00:00+08:00' },
    { ...serverWindow(1, 3, 0, '2026-11-13'), max_days: '3' },
    { ...serverWindow(1, 3, 0, '2026-11-13'), max_days: Infinity },
  ]) assert.equal(liveShelfLife(value, now), null)
  assert.equal(liveShelfLife(serverWindow(1, 3, 0, '2026-11-13'), NaN), null)
  const frozen = serverWindow(1, 3, 1, '2026-11-12')
  liveShelfLife(frozen, now)
  assert.deepEqual(frozen, serverWindow(1, 3, 1, '2026-11-12'))
})

test('tooltips say which day of the window it is', () => {
  const now = at('2026-11-13T04:00:00Z')
  assert.equal(shelfLifeWindowDetail(liveShelfLife(serverWindow(1, 3, 3, '2026-11-13'), now)), 'Last day of the estimated window')
  assert.equal(shelfLifeWindowDetail(liveShelfLife(serverWindow(1, 3, 1, '2026-11-13'), now)), '1 day since the scan, by Asia/Manila calendar date')
  assert.equal(shelfLifeWindowDetail(liveShelfLife(serverWindow(1, 3, 0, '2026-11-13'), now)), '0 days since the scan, by Asia/Manila calendar date')
})
