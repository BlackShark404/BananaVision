import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile, readdir } from 'node:fs/promises'
import { transform } from 'esbuild'

// Asia/Manila must come from the code, never from the machine that renders the page.
process.env.TZ = 'America/Los_Angeles'

const source = await readFile(new URL('../src/lib/manilaTime.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { MANILA_TIME_ZONE, inManila, manilaDayKey, manilaToday } =
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

test('manilaToday is the local calendar date of the Manila day for the date picker', () => {
  const today = manilaToday(at('2026-10-01T16:30:00Z'))
  assert.deepEqual([today.getFullYear(), today.getMonth() + 1, today.getDate()], [2026, 10, 2])
  assert.equal([today.getHours(), today.getMinutes()].join(':'), '0:0')
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
