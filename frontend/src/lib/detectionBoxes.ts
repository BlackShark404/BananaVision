import type { BoundingBox } from "@/types"

function cultivar(cls: string): string | null {
  const prefix = cls.toLowerCase().split("_", 1)[0]
  return ["lakatan", "latundan", "cardaba"].includes(prefix) ? prefix : null
}

/** Match classification._unique_box_detections so overlays and finger counts agree. */
export function deduplicateDisplayBoxes(boxes: BoundingBox[]): BoundingBox[] {
  // New scans retain raw hypotheses with the classifier's counting decision,
  // which remains authoritative after cultivar labels are harmonized by fusion.
  if (boxes.every(box => typeof box.counts_as_finger === "boolean")) {
    return boxes.filter(box => box.counts_as_finger)
  }
  const unique: BoundingBox[] = []
  for (const box of boxes) {
    const duplicate = unique.some(existing => {
      const intersection = Math.max(0, Math.min(box.x + box.w, existing.x + existing.w) - Math.max(box.x, existing.x))
        * Math.max(0, Math.min(box.y + box.h, existing.y + existing.h) - Math.max(box.y, existing.y))
      const minArea = Math.min(box.w * box.h, existing.w * existing.h)
      const maxArea = Math.max(box.w * box.h, existing.w * existing.h)
      const union = box.w * box.h + existing.w * existing.h - intersection
      const iou = union > 0 ? intersection / union : 0
      const containment = minArea > 0 ? intersection / minArea : 0
      const minWidth = Math.min(box.w, existing.w)
      const minHeight = Math.min(box.h, existing.h)
      const relDx = minWidth > 0 ? Math.abs(box.x + box.w / 2 - existing.x - existing.w / 2) / minWidth : 0
      const relDy = minHeight > 0 ? Math.abs(box.y + box.h / 2 - existing.y - existing.h / 2) / minHeight : 0
      const [smaller, larger] = box.w * box.h <= existing.w * existing.h ? [box, existing] : [existing, box]
      let aligned = false
      if (minWidth <= 0 || minHeight <= 0 || Math.max(relDx, relDy) <= 0.08) {
        aligned = true
      } else if (Math.min(relDx, relDy) <= 0.08) {
        if (smaller.w < 0.45 * larger.w && smaller.h < 0.45 * larger.h) {
          aligned = true
        } else if (larger.w > larger.h && smaller.w > smaller.h) {
          aligned = relDy <= 0.08 && !(smaller.h < 0.50 * larger.h && smaller.w < 0.75 * larger.w)
        } else if (smaller.h > smaller.w && smaller.h >= 0.80 * larger.h && larger.w >= 1.8 * smaller.w && relDy <= 0.08) {
          aligned = true
        } else if (larger.h >= larger.w && smaller.h >= smaller.w) {
          aligned = relDx <= 0.08 && !(smaller.w < 0.50 * larger.w && smaller.h < 0.75 * larger.h)
        } else if (larger.h >= larger.w && smaller.w >= 0.80 * larger.w && relDx <= 0.08) {
          aligned = true
        } else if (larger.w > larger.h && smaller.h >= 0.80 * larger.h && relDy <= 0.08) {
          aligned = true
        }
      }
      const sameCultivar = cultivar(box.cls) !== null && cultivar(box.cls) === cultivar(existing.cls)
      if (box.cls === existing.cls || sameCultivar) {
        // Ripeness differences must not merge adjacent fingers of the same cultivar.
        return iou >= 0.80 || (maxArea > 0 && minArea / maxArea <= 0.72 && containment >= 0.80 && aligned)
      }
      return (box.x === existing.x && box.y === existing.y && box.w === existing.w && box.h === existing.h)
        || iou >= 0.70 || (containment >= 0.85 && aligned)
    })
    if (!duplicate) unique.push(box)
  }
  return unique
}
