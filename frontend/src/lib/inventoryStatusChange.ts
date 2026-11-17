import type { InventoryStatus } from "@/types"

const CLOSED_STATUSES: readonly string[] = ["Sold", "Spoiled"]

/**
 * Dialog note for a single-scan inventory status change. An admin can correct any status,
 * including Sold and Spoiled; restoring stock reopens a depleted intake on the server.
 */
export function inventoryStatusChangeNote(current: InventoryStatus | string, target: InventoryStatus | string): string {
  // "Reload latest" after a conflict can leave the dialog open on the status the scan now has.
  if (current === target) return `The scan is already ${target}. Saving changes nothing.`
  const sentences: string[] = []
  if (CLOSED_STATUSES.includes(current)) sentences.push(`This corrects the ${current} status.`)
  if (target === "In Stock") {
    sentences.push("The scan returns to stock. If its delivery intake is depleted, the intake reopens.")
  } else if (current === "In Stock") {
    sentences.push("The scan leaves stock.")
  }
  sentences.push("This change will be recorded in the scan history.")
  return sentences.join(" ")
}
