import { manilaDayKey } from "./manilaTime"

/**
 * Live shelf-life window. The server derives it from the stored estimate and the scan
 * time in whole Asia/Manila calendar days; the page never parses a prediction itself.
 */
export interface ShelfLifeWindow {
  /** Whole-day bounds of the stored estimate. They never change. */
  min_days: number
  max_days: number
  /** Manila calendar days from `scan_date` to `as_of_date`, counted by the server, never negative. */
  elapsed_days: number
  remaining_min_days: number
  remaining_max_days: number
  days_past: number
  state: ShelfLifeState
  /** Manila calendar date (YYYY-MM-DD) of the scan. */
  scan_date: string
  /** The server's Manila calendar date (YYYY-MM-DD) for the values above. */
  as_of_date: string
}

export type ShelfLifeState = "active" | "final_day" | "expired"

export interface LiveShelfLife {
  elapsedDays: number
  remainingMin: number
  remainingMax: number
  daysPast: number
  state: ShelfLifeState
}

const DAY = 86_400_000

/** Day number of the Asia/Manila calendar date of an instant, whatever the browser's zone. */
export function manilaDayNumber(time: number): number {
  return Date.parse(`${manilaDayKey(time)}T00:00:00Z`) / DAY
}

const dayOf = (value: unknown): number =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? Date.parse(`${value}T00:00:00Z`) / DAY : NaN

/**
 * The window as of `now`: what the server would answer on the later of its own date and
 * the page's Manila date. An open tab, a frozen list or a replayed response therefore
 * rolls over at Manila midnight without a new read, and a slow clock never moves it back.
 * The count starts at the scan date, so a scan dated after the server's date stays at zero.
 */
export function liveShelfLife(window: ShelfLifeWindow | null | undefined, now: number): LiveShelfLife | null {
  if (!window) return null
  const { min_days: low, max_days: high } = window
  const scanDay = dayOf(window.scan_date), asOf = dayOf(window.as_of_date)
  if (![low, high].every(Number.isSafeInteger) || low < 0 || high < low
    || !Number.isFinite(scanDay) || !Number.isFinite(asOf) || !Number.isFinite(now)) return null
  const serverCalendar = Math.max(0, asOf - scanDay)
  const exposureOffset = Number.isSafeInteger(window.elapsed_days) && window.elapsed_days >= 0
    ? window.elapsed_days - serverCalendar
    : 0
  const calendarElapsed = Math.max(0, Math.max(manilaDayNumber(now), asOf) - scanDay)
  const elapsedDays = Math.max(0, calendarElapsed + exposureOffset)
  return {
    elapsedDays,
    remainingMin: Math.max(0, low - elapsedDays),
    remainingMax: Math.max(0, high - elapsedDays),
    daysPast: Math.max(0, elapsedDays - high),
    state: elapsedDays > high ? "expired" : elapsedDays === high ? "final_day" : "active",
  }
}

/** Countdown wording shared by every page: a range while it runs, then the last day, then overdue. */
export function shelfLifeWindowLabel(live: LiveShelfLife): string {
  if (live.state === "expired") return "Overdue"
  if (live.state === "final_day") return "Final day"
  const { remainingMin: low, remainingMax: high } = live
  return low === high ? `${high} ${high === 1 ? "day" : "days"} left` : `${low}–${high} days left`
}

/** One plain sentence for a tooltip. */
export function shelfLifeWindowDetail(live: LiveShelfLife): string {
  if (live.state === "expired") {
    return `The estimated window ended ${live.daysPast} ${live.daysPast === 1 ? "day" : "days"} ago`
  }
  if (live.state === "final_day") return "Last day of the estimated window"
  return `${live.elapsedDays} ${live.elapsedDays === 1 ? "day" : "days"} since the scan, by Asia/Manila calendar date`
}
