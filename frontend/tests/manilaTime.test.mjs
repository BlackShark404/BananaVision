import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile, readdir } from 'node:fs/promises'
import { transform } from 'esbuild'

// Asia/Manila must come from the code, never from the machine that renders the page.
process.env.TZ = 'America/Los_Angeles'

const source = await readFile(new URL('../src/lib/manilaTime.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const {
  MANILA_TIME_ZONE, inManila, manilaDayKey, manilaToday, isManilaToday,
  formatManilaDateTime, formatManilaDate, manilaPdfTimestamp,
} =
  await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const at = iso => Date.parse(iso)

test('the zone constant is Asia/Manila', () => {
  assert.equal(MANILA_TIME_ZONE, 'Asia/Manila')
})

test('inManila keeps the caller options and only adds the zone', () => {
  assert.deepEqual(inManila(), { timeZone: 'Asia/Manila' })
  assert.deepEqual(inManila({ month: 'short', day: 'numeric' }),
    { month: 'short', day: 'numeric', timeZone: 'Asia/Manila' })
  // A caller can never opt out by passing its own zone.
  assert.equal(inManila({ timeZone: 'UTC' }).timeZone, 'Asia/Manila')
})

test('times render in Manila whatever the machine zone is', () => {
  const instant = new Date('2026-10-01T16:30:00Z')  // 00:30 on 2 October in Manila
  assert.equal(instant.toLocaleDateString('en-US', inManila({ month: 'short', day: 'numeric' })), 'Oct 2')
  assert.equal(instant.toLocaleTimeString('en-US', inManila({ hour: '2-digit', minute: '2-digit' })), '12:30 AM')
  // The machine itself is still on 1 October here; the helper ignores it.
  assert.equal(instant.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), 'Oct 1')
})

test('the Manila calendar day changes at 16:00 UTC, not at local or UTC midnight', () => {
  assert.equal(manilaDayKey(at('2026-10-01T15:59:59Z')), '2026-10-01')
  assert.equal(manilaDayKey(at('2026-10-01T16:00:00Z')), '2026-10-02')
  assert.equal(manilaDayKey(at('2026-10-02T00:00:00Z')), '2026-10-02')
  assert.equal(manilaDayKey(new Date('2026-12-31T16:00:00Z')), '2027-01-01')
  assert.match(manilaDayKey(), /^\d{4}-\d{2}-\d{2}$/)
})

test('isManilaToday compares a stored business date or instant with the Manila day', () => {
  const noon = at('2026-10-02T04:00:00Z')  // 12:00 on 2026-10-02 in Manila
  assert.equal(isManilaToday('2026-10-02', noon), true)
  assert.equal(isManilaToday('2026-10-01', noon), false)
  assert.equal(isManilaToday('2026-10-03', noon), false)
  // Instants are read in Manila: 23:30 on 10-01 UTC is already 10-02 in Manila.
  assert.equal(isManilaToday('2026-10-01T23:30:00Z', noon), true)
  assert.equal(isManilaToday('2026-10-02T08:10:00+08:00', noon), true)
  assert.equal(isManilaToday('2026-10-01T15:59:59Z', noon), false)
  // Just after Manila midnight, yesterday's business date is no longer today.
  const afterMidnight = at('2026-10-02T16:05:00Z')
  assert.equal(isManilaToday('2026-10-02', afterMidnight), false)
  assert.equal(isManilaToday('2026-10-03', afterMidnight), true)
  for (const value of ['', 'not-a-date', null, undefined, '2026-13-40']) {
    assert.equal(isManilaToday(value, noon), false, String(value))
  }
})

test('manilaToday is the local calendar date of the Manila day for the date picker', () => {
  const today = manilaToday(at('2026-10-01T16:30:00Z'))
  assert.deepEqual([today.getFullYear(), today.getMonth() + 1, today.getDate()], [2026, 10, 2])
  assert.equal([today.getHours(), today.getMinutes()].join(':'), '0:0')
})

test('export date/time formatters always render Asia/Manila wall clock', () => {
  // 16:30 UTC on Oct 1 is 12:30:00 AM on Oct 2 in Asia/Manila (and Oct 1 in Los Angeles).
  assert.equal(formatManilaDateTime('2026-10-01T16:30:00Z'), 'Oct 2, 2026, 12:30:00 AM')
  assert.equal(formatManilaDateTime('2026-11-19T21:12:45.123456+08:00'), 'Nov 19, 2026, 9:12:45 PM')
  assert.equal(formatManilaDate('2026-10-02'), 'Oct 2, 2026')
  assert.equal(formatManilaDate('2026-10-01T16:30:00Z'), 'Oct 2, 2026')
  assert.equal(manilaPdfTimestamp(at('2026-10-01T16:30:00Z')), "D:20261002003000+08'00'")
  assert.equal(formatManilaDateTime(''), '')
  assert.equal(formatManilaDate(null), '')
})

// ── Source guard: every date shown, grouped or used in a file name goes through Manila. ──

const ALLOWED_FILES = new Set([
  'lib/manilaTime.ts',            // the one place that defines the zone
  'lib/isoDay.ts',                // date-picker values: local calendar days by design
  'components/ui/calendar.tsx',   // the picker grid renders local calendar days
  'components/ui/chart.tsx',      // number formatting only
])
const MANILA = /inManila\(|MANILA_TIME_ZONE|["']Asia\/Manila["']/

async function sourceFiles(dir = new URL('../src/', import.meta.url), prefix = '') {
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = `${prefix}${entry.name}`
    if (entry.isDirectory()) files.push(...await sourceFiles(new URL(`${entry.name}/`, dir), `${path}/`))
    else if (/\.(ts|tsx)$/.test(entry.name)) files.push(path)
  }
  return files
}

/** The argument text of the call whose opening parenthesis is at `open`. */
function callArguments(text, open) {
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === '(') depth++
    else if (text[i] === ')' && --depth === 0) return text.slice(open + 1, i)
  }
  return text.slice(open + 1)
}

test('no source file formats a date outside Asia/Manila', async () => {
  const problems = []
  for (const file of await sourceFiles()) {
    if (ALLOWED_FILES.has(file)) continue
    const text = await readFile(new URL(`../src/${file}`, import.meta.url), 'utf8')
    const line = index => text.slice(0, index).split('\n').length
    for (const match of text.matchAll(/\.toLocale(?:Date|Time)?String\(|new Intl\.DateTimeFormat\(/g)) {
      const args = callArguments(text, match.index + match[0].length - 1)
      if (!MANILA.test(args)) problems.push(`${file}:${line(match.index)} ${match[0]} without the Manila zone`)
    }
    for (const match of text.matchAll(/\.toISOString\(\)\s*\.(?:slice|split|substring)\(/g)) {
      problems.push(`${file}:${line(match.index)} UTC date taken from toISOString(); use manilaDayKey`)
    }
    for (const match of text.matchAll(/\.get(?:FullYear|Month|Date|Day|Hours|Minutes)\(\)/g)) {
      problems.push(`${file}:${line(match.index)} ${match[0]} reads the machine zone; use the Manila helpers`)
    }
  }
  assert.deepEqual(problems, [])
})
