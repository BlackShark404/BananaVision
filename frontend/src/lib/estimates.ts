/**
 * Display wording for AI-estimated numbers (finger counts, shelf-life estimates).
 * Presentation only: stored and API values, sorting, filters and thresholds keep using
 * the raw numbers. Cultivar, ripeness and confidence keep their own labels.
 */
export const ESTIMATE_PREFIX = "Est."

interface FingerCountSource {
  fingerCount?: number | null
  isOverridden?: boolean
  originalAiResult?: { fingerCount?: number | null } | null
}

/**
 * True unless a person changed this scan's finger count away from the AI value. The
 * scan-level override flag alone is not enough: it is also set when only the cultivar,
 * ripeness or spoilage changed.
 */
export function fingerCountIsEstimate(scan: FingerCountSource): boolean {
  const original = scan.originalAiResult?.fingerCount
  if (!scan.isOverridden || typeof original !== "number") return true
  return scan.fingerCount === original
}

/** Field label: "Est. Fingers" for an AI count, "Fingers" for a counted one. */
export function fingersLabel(estimated = true): string {
  return estimated ? `${ESTIMATE_PREFIX} Fingers` : "Fingers"
}

/** Inline value: "Est. 13 fingers", "Est. 1 finger", "13 fingers" when counted. */
export function fingerCountText(count: number | null | undefined, estimated = true): string {
  if (typeof count !== "number" || !Number.isInteger(count) || count < 0) return "Fingers unknown"
  const text = `${count} ${count === 1 ? "finger" : "fingers"}`
  return estimated ? `${ESTIMATE_PREFIX} ${text}` : text
}

const NOT_AN_ESTIMATE = new Set(["", "—", "Unknown"])

/** Marks a standalone estimate ("0–2 days left" → "Est. 0–2 days left"); never doubles it. */
export function estimateText(text: string | null | undefined): string {
  if (!text || NOT_AN_ESTIMATE.has(text) || text.startsWith(`${ESTIMATE_PREFIX} `)) return text ?? ""
  return `${ESTIMATE_PREFIX} ${text}`
}
