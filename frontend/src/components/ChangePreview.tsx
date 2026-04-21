import { Badge } from "@/components/ui/badge"

interface ChangePreviewProps {
  originalData: {
    cultivar?: string
    ripeness?: string
    spoilageDays?: number | string
    fingerCount?: number | string
  }
  editData: {
    cultivar?: string
    ripeness?: string
    spoilageDays?: number | string
    fingerCount?: number | string
  }
  className?: string
  badgeClassName?: string
  textClassName?: string
}

export function ChangePreview({ originalData, editData, className = "", badgeClassName = "bg-background border-border text-[10px]", textClassName = "text-muted-foreground text-[10px]" }: ChangePreviewProps) {
  if (!originalData || !editData) return null

  const safeOriginalFingers = originalData.fingerCount === '' || originalData.fingerCount === undefined ? 0 : Math.max(0, Number(originalData.fingerCount) || 0)
  const safeOriginalSpoilage = originalData.spoilageDays === '' || originalData.spoilageDays === undefined ? 0 : Math.max(0, Number(originalData.spoilageDays) || 0)
  
  const safeEditFingers = editData.fingerCount === '' || editData.fingerCount === undefined ? 0 : Math.max(0, Number(editData.fingerCount) || 0)
  const safeEditSpoilage = editData.spoilageDays === '' || editData.spoilageDays === undefined ? 0 : Math.max(0, Number(editData.spoilageDays) || 0)

  const hasCultivarChange = !!editData.cultivar && !!originalData.cultivar && editData.cultivar !== originalData.cultivar
  const hasRipenessChange = !!editData.ripeness && !!originalData.ripeness && editData.ripeness !== originalData.ripeness
  const hasSpoilageChange = editData.spoilageDays !== undefined && safeEditSpoilage !== safeOriginalSpoilage
  const hasFingerChange = editData.fingerCount !== undefined && safeEditFingers !== safeOriginalFingers

  const hasChanges = hasCultivarChange || hasRipenessChange || hasSpoilageChange || hasFingerChange

  return (
    <div className={`p-3 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl space-y-1 ${className}`}>
      <p className="text-[10px] text-yellow-700 dark:text-yellow-400 uppercase tracking-wider font-semibold">Changes from AI result</p>
      <div className="flex flex-wrap gap-2 text-xs">
        {hasCultivarChange && (
          <Badge variant="outline" className={badgeClassName}>
            Cultivar: {originalData.cultivar} → {editData.cultivar}
          </Badge>
        )}
        {hasRipenessChange && (
          <Badge variant="outline" className={badgeClassName}>
            Ripeness: {originalData.ripeness} → {editData.ripeness}
          </Badge>
        )}
        {hasSpoilageChange && (
          <Badge variant="outline" className={badgeClassName}>
            Spoilage: {safeOriginalSpoilage}d → {safeEditSpoilage}d
          </Badge>
        )}
        {hasFingerChange && (
          <Badge variant="outline" className={badgeClassName}>
            Fingers: {safeOriginalFingers} → {safeEditFingers}
          </Badge>
        )}
        {!hasChanges && (
          <span className={textClassName}>No changes made yet</span>
        )}
      </div>
    </div>
  )
}