/**
 * The one frontend time zone. Every date or time the app shows, groups by day or puts in
 * a file name is Asia/Manila, whatever zone the viewing machine uses. The backend
 * counterpart is backend/app/core/time.py. tests/manilaTime.test.mjs rejects any other
 * date formatting in src/.
 */
export const MANILA_TIME_ZONE = "Asia/Manila"

/** The caller's format options with the Manila zone; the zone cannot be overridden. */
export function inManila<T extends Intl.DateTimeFormatOptions>(options?: T): T & { timeZone: string } {
  return { ...(options ?? ({} as T)), timeZone: MANILA_TIME_ZONE }
}

const dayParts = new Intl.DateTimeFormat("en-CA", inManila({ year: "numeric", month: "2-digit", day: "2-digit" }))

/** Manila calendar day of an instant as YYYY-MM-DD (business dates, file names). */
export function manilaDayKey(time: number | Date = Date.now()): string {
  const parts: Record<string, string> = {}
  for (const part of dayParts.formatToParts(time)) parts[part.type] = part.value
  return `${parts.year}-${parts.month}-${parts.day}`
}

/**
 * The Manila calendar day as a local Date at midnight. Date pickers work in local
 * calendar days, so this marks "today" as the day it is in Manila.
 */
export function manilaToday(time: number | Date = Date.now()): Date {
  const [year, month, day] = manilaDayKey(time).split("-").map(Number)
  return new Date(year, month - 1, day)
}

const BUSINESS_DATE = /^\d{4}-\d{2}-\d{2}$/

const dateParts = new Intl.DateTimeFormat("en-US", inManila({
  month: "short", day: "numeric", year: "numeric",
}))

const dateTimeParts = new Intl.DateTimeFormat("en-US", inManila({
  month: "short", day: "numeric", year: "numeric",
  hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true,
}))

const pdfStampParts = new Intl.DateTimeFormat("en-CA", inManila({
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
}))

/** Human-readable Asia/Manila timestamp with seconds for exports, e.g. "Nov 25, 2026, 1:45:11 PM". */
export function formatManilaDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === "") return ""
  const instant = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(instant.getTime())) return typeof value === "string" ? value : ""
  const parts: Record<string, string> = {}
  for (const part of dateTimeParts.formatToParts(instant)) parts[part.type] = part.value
  return `${parts.month} ${parts.day}, ${parts.year}, ${parts.hour}:${parts.minute}:${parts.second} ${parts.dayPeriod}`
}

/** Human-readable Asia/Manila calendar date for exports, e.g. "Oct 2, 2026". */
export function formatManilaDate(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === "") return ""
  const instant = typeof value === "string" && BUSINESS_DATE.test(value)
    ? new Date(`${value}T00:00:00+08:00`)
    : value instanceof Date ? value : new Date(value)
  if (Number.isNaN(instant.getTime())) return typeof value === "string" ? value : ""
  const parts: Record<string, string> = {}
  for (const part of dateParts.formatToParts(instant)) parts[part.type] = part.value
  return `${parts.month} ${parts.day}, ${parts.year}`
}

/** PDF CreationDate metadata string in Asia/Manila (+08'00'). */
export function manilaPdfTimestamp(time: number | Date = Date.now()): string {
  const parts: Record<string, string> = {}
  for (const part of pdfStampParts.formatToParts(time)) parts[part.type] = part.value
  const hour = parts.hour === "24" ? "00" : parts.hour
  return `D:${parts.year}${parts.month}${parts.day}${hour}${parts.minute}${parts.second}+08'00'`
}

/**
 * Whether a stored business date (YYYY-MM-DD, already a Manila day) or an instant falls on
 * today's Manila calendar day. Unreadable values are never today.
 */
export function isManilaToday(value: string | null | undefined, now: number | Date = Date.now()): boolean {
  if (!value) return false
  let day: string
  if (BUSINESS_DATE.test(value)) {
    day = value
  } else {
    const instant = Date.parse(value)
    if (Number.isNaN(instant)) return false
    day = manilaDayKey(instant)
  }
  return day === manilaDayKey(now)
}
