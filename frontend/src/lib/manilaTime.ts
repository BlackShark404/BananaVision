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
