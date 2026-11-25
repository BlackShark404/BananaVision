import assert from "node:assert/strict"
import { test } from "node:test"
import { fileURLToPath } from "node:url"
import { build } from "esbuild"

// Asia/Manila must come from the code, never from the viewing machine's zone.
process.env.TZ = "America/Los_Angeles"

const { outputFiles: [{ text: code }] } = await build({
  entryPoints: [fileURLToPath(new URL("../src/lib/ripenessProjection.ts", import.meta.url))],
  bundle: true, format: "esm", write: false, logLevel: "silent",
})
const { liveRipeness, effectiveRipeness } =
  await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`)

const at = iso => Date.parse(iso)

const projection = (overrides = {}) => Object.freeze({
  base_ripeness: "Unripe",
  current_ripeness: "Unripe",
  progressed: false,
  elapsed_days: 0,
  transitions: Object.freeze({ "Semi Ripe": 3, Ripe: 6, Overripe: 9 }),
  scan_date: "2026-11-06",
  as_of_date: "2026-11-06",
  ...overrides,
})

test("stays anchored at scanned ripeness on Day 0 and rolls over strictly at Asia/Manila midnight", () => {
  const proj = projection()
  // Day 0 through Day 2 23:59:59 Asia/Manila (15:59:59Z on Nov 8).
  const day0 = liveRipeness(proj, at("2026-11-06T04:00:00Z"), "In Stock")
  assert.deepEqual(day0, { base: "Unripe", current: "Unripe", progressed: false, elapsedDays: 0, badgeLabel: "Unripe" })

  const beforeMidnight = liveRipeness(proj, at("2026-11-08T15:59:59Z"), "In Stock")
  assert.equal(beforeMidnight.elapsedDays, 2)
  assert.equal(beforeMidnight.current, "Unripe")
  assert.equal(beforeMidnight.progressed, false)
  assert.equal(beforeMidnight.badgeLabel, "Unripe")

  // 00:00:00 Asia/Manila on Nov 9 = 16:00:00Z on Nov 8 (day 3 -> Est. Semi Ripe).
  const atMidnight = liveRipeness(proj, at("2026-11-08T16:00:00Z"), "In Stock")
  assert.equal(atMidnight.elapsedDays, 3)
  assert.equal(atMidnight.current, "Semi Ripe")
  assert.equal(atMidnight.progressed, true)
  assert.equal(atMidnight.badgeLabel, "Est. Semi Ripe")

  // Day 6 -> Est. Ripe; Day 9+ -> Est. Overripe.
  const day6 = liveRipeness(proj, at("2026-11-11T16:00:00Z"), "In Stock")
  assert.equal(day6.current, "Ripe")
  assert.equal(day6.badgeLabel, "Est. Ripe")

  const day12 = liveRipeness(proj, at("2026-11-18T04:00:00Z"), "In Stock")
  assert.equal(day12.current, "Overripe")
  assert.equal(day12.badgeLabel, "Est. Overripe")
})

test("closed inventory statuses freeze at scanned ripeness while Public QR can keep progressing", () => {
  const proj = projection()
  const day10 = at("2026-11-16T04:00:00Z")
  for (const status of ["Sold", "For Processing", "Spoiled"]) {
    const frozen = liveRipeness(proj, day10, status)
    assert.deepEqual(frozen, {
      base: "Unripe", current: "Unripe", progressed: false, elapsedDays: 0, badgeLabel: "Unripe",
    })
  }
  const publicLive = liveRipeness(proj, day10, "Sold", { ignoreClosedStatus: true })
  assert.equal(publicLive.current, "Overripe")
  assert.equal(publicLive.progressed, true)
  assert.equal(publicLive.badgeLabel, "Est. Overripe")
})

test("a slow workstation clock behind as_of_date never moves ripeness backward", () => {
  const servedDay6 = projection({
    current_ripeness: "Ripe",
    progressed: true,
    elapsed_days: 6,
    as_of_date: "2026-11-12",
  })
  const live = liveRipeness(servedDay6, at("2026-11-01T00:00:00Z"), "In Stock")
  assert.equal(live.elapsedDays, 6)
  assert.equal(live.current, "Ripe")
  assert.equal(live.badgeLabel, "Est. Ripe")
})

test("missing or damaged projections return null safely and effectiveRipeness falls back to scanned ripeness", () => {
  const now = at("2026-11-12T04:00:00Z")
  for (const invalid of [
    null, undefined, {},
    { ...projection(), base_ripeness: "Unknown" },
    { ...projection(), scan_date: "11/06/2026" },
    { ...projection(), as_of_date: null },
  ]) {
    assert.equal(liveRipeness(invalid, now, "In Stock"), null)
  }
  assert.equal(liveRipeness(projection(), NaN, "In Stock"), null)
  assert.equal(effectiveRipeness({ ripeness: "Semi Ripe", ripenessProjection: null, inventoryStatus: "In Stock" }, now), "Semi Ripe")
  assert.equal(effectiveRipeness({ ripeness: "Unripe", ripenessProjection: projection(), inventoryStatus: "In Stock" }, now), "Ripe")
  assert.equal(effectiveRipeness({ ripeness: "Unripe", ripenessProjection: projection(), inventoryStatus: "Sold" }, now), "Unripe")
})
