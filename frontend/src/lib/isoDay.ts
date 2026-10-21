/** Validates and parses a YYYY-MM-DD calendar-day string as a local calendar date. */
export function parseIsoDay(value: string | undefined): Date | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined
  const [year, month, day] = value.split("-").map(Number)
  const date = new Date(year, month - 1, day)
  // Strict field roundtrip rejects overflowed days such as "2026-02-30" or "2026-13-01".
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : undefined
}

// en-CA renders a date as YYYY-MM-DD without UTC shifting.
const isoDayFormatter = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" })

/** Formats a date as the YYYY-MM-DD calendar day in the viewer's local time zone. */
export function formatIsoDay(date: Date): string {
  return isoDayFormatter.format(date)
}
