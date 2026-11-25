import { manilaDayNumber } from "./shelfLifeWindow"
import { closedStockSpoilageLabel } from "./spoilageDisplay"

export const RIPENESS_STAGES = ["Unripe", "Semi Ripe", "Ripe", "Overripe"] as const
export type RipenessStage = (typeof RIPENESS_STAGES)[number]

/**
 * Live ripeness projection derived by the server from the scan-time classification,
 * stored shelf-life estimate, and RFR stage thresholds. Nothing in it is persisted.
 */
export interface RipenessProjection {
  base_ripeness: RipenessStage
  current_ripeness: RipenessStage
  progressed: boolean
  elapsed_days: number
  /** Whole Asia/Manila days after `scan_date` when each later stage starts. */
  transitions: Partial<Record<RipenessStage, number>>
  /** Manila calendar date (YYYY-MM-DD) of the scan. */
  scan_date: string
  /** The server's Manila calendar date (YYYY-MM-DD) for the values above. */
  as_of_date: string
}

export interface LiveRipeness {
  base: RipenessStage
  current: RipenessStage
  progressed: boolean
  elapsedDays: number
  /** `"Est. <Stage>"` once progressed past the scan-time observation; plain stage otherwise. */
  badgeLabel: string
}

const DAY = 86_400_000

const dayOf = (value: unknown): number =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? Date.parse(`${value}T00:00:00Z`) / DAY : NaN

function isRipenessStage(value: unknown): value is RipenessStage {
  return typeof value === "string" && (RIPENESS_STAGES as readonly string[]).includes(value)
}

/**
 * Evaluate the projected ripeness as of `now` (Asia/Manila calendar date), mirroring
 * `liveShelfLife`: advances monotonically at Manila midnight without extra requests,
 * never moves backward, and freezes at `base_ripeness` for closed inventory statuses
 * unless `ignoreClosedStatus` is set (Public QR view).
 */
export function liveRipeness(
  projection: RipenessProjection | null | undefined,
  now: number,
  inventoryStatus?: string | null,
  options?: { ignoreClosedStatus?: boolean },
): LiveRipeness | null {
  if (!projection || !isRipenessStage(projection.base_ripeness)) return null
  const base = projection.base_ripeness
  if (!options?.ignoreClosedStatus && closedStockSpoilageLabel(inventoryStatus) !== null) {
    return { base, current: base, progressed: false, elapsedDays: 0, badgeLabel: base }
  }
  const scanDay = dayOf(projection.scan_date)
  const asOf = dayOf(projection.as_of_date)
  if (!Number.isFinite(scanDay) || !Number.isFinite(asOf) || !Number.isFinite(now)) return null

  const elapsedDays = Math.max(0, Math.max(manilaDayNumber(now), asOf) - scanDay)
  const baseIdx = RIPENESS_STAGES.indexOf(base)
  let current: RipenessStage = base
  const transitions = projection.transitions ?? {}
  for (let idx = baseIdx + 1; idx < RIPENESS_STAGES.length; idx++) {
    const stage = RIPENESS_STAGES[idx]
    const threshold = transitions[stage]
    if (typeof threshold === "number" && Number.isSafeInteger(threshold) && threshold >= 1 && elapsedDays >= threshold) {
      current = stage
    }
  }
  const progressed = current !== base
  return {
    base,
    current,
    progressed,
    elapsedDays,
    badgeLabel: progressed ? `Est. ${current}` : current,
  }
}

/** Effective ripeness stage for grouping/filtering, falling back to the scanned stage if absent. */
export function effectiveRipeness(
  scan: { ripeness?: string | null; ripenessProjection?: RipenessProjection | null; inventoryStatus?: string | null },
  now: number,
  options?: { ignoreClosedStatus?: boolean },
): string {
  const live = liveRipeness(scan.ripenessProjection, now, scan.inventoryStatus, options)
  return live?.current ?? scan.ripeness ?? "Unknown"
}
