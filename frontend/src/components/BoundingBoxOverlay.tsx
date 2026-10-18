/**
 * BoundingBoxOverlay — renders an image with YOLO detection bounding boxes.
 *
 * Each bounding box is drawn as an absolutely-positioned element scaled
 * relative to the image's natural dimensions. Labels show the class
 * (cultivar_ripeness) and confidence percentage.
 */

import { useState, useRef, useCallback } from "react"
import { ScanImage } from "@/components/ScanImage"
import type { BoundingBox } from "@/types"

// ── Class label color mapping ───────────────────────────────────────────────
// Colors are chosen to be visually distinct and match the cultivar/ripeness
// categories used in the YOLO training dataset.

const CLASS_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  // Cardaba
  cardaba_overripe:   { border: "#ef4444", bg: "rgba(239,68,68,0.18)",   text: "#fca5a5" },
  cardaba_ripe:       { border: "#eab308", bg: "rgba(234,179,8,0.18)",   text: "#fde047" },
  cardaba_semi_ripe:  { border: "#f97316", bg: "rgba(249,115,22,0.18)",  text: "#fdba74" },
  cardaba_unripe:     { border: "#22c55e", bg: "rgba(34,197,94,0.18)",   text: "#86efac" },
  // Lakatan
  lakatan_overripe:   { border: "#dc2626", bg: "rgba(220,38,38,0.18)",   text: "#fca5a5" },
  lakatan_ripe:       { border: "#facc15", bg: "rgba(250,204,21,0.18)",  text: "#fef08a" },
  lakatan_semi_ripe:  { border: "#fb923c", bg: "rgba(251,146,60,0.18)", text: "#fed7aa" },
  lakatan_unripe:     { border: "#4ade80", bg: "rgba(74,222,128,0.18)",  text: "#bbf7d0" },
  // Latundan
  latundan_overripe:  { border: "#f43f5e", bg: "rgba(244,63,94,0.18)",  text: "#fda4af" },
  latundan_ripe:      { border: "#a3e635", bg: "rgba(163,230,53,0.18)", text: "#d9f99d" },
  latundan_semi_ripe: { border: "#e879f9", bg: "rgba(232,121,249,0.18)", text: "#f0abfc" },
  latundan_unripe:    { border: "#34d399", bg: "rgba(52,211,153,0.18)",  text: "#a7f3d0" },
}

const DEFAULT_COLOR = { border: "#d946ef", bg: "rgba(217,70,239,0.18)", text: "#f0abfc" }

function getClassColor(cls: string) {
  return CLASS_COLORS[cls.toLowerCase()] || DEFAULT_COLOR
}

/** Format a raw class name for display: "lakatan_semi_ripe" → "Lakatan Semi Ripe" */
function formatClassName(cls: string): string {
  return cls
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

// ── Props ───────────────────────────────────────────────────────────────────

interface BoundingBoxOverlayProps {
  /** URL of the image to display */
  src: string
  /** Alt text for the image */
  alt?: string
  /** Array of bounding boxes to render on the image */
  boxes: BoundingBox[]
  /** Optional CSS class for the container */
  className?: string
  /** Whether to show labels on the boxes (default: true) */
  showLabels?: boolean
  /** Whether to show confidence on the boxes (default: true) */
  showConfidence?: boolean
  /** Optional aspect ratio override for the container */
  aspectRatio?: number
}

export default function BoundingBoxOverlay(props: BoundingBoxOverlayProps) {
  return <BoundingBoxImage key={props.src} {...props} />
}

function deduplicateDisplayBoxes(boxes: BoundingBox[]): BoundingBox[] {
  if (boxes.length <= 1) return boxes
  const sorted = [...boxes].sort((a, b) => b.conf - a.conf)
  const result: BoundingBox[] = []

  for (const box of sorted) {
    const isDuplicate = result.some((existing) => {
      const ax2 = box.x + box.w
      const ay2 = box.y + box.h
      const bx2 = existing.x + existing.w
      const by2 = existing.y + existing.h

      const interW = Math.max(0, Math.min(ax2, bx2) - Math.max(box.x, existing.x))
      const interH = Math.max(0, Math.min(ay2, by2) - Math.max(box.y, existing.y))
      const interArea = interW * interH
      if (interArea <= 0) return false

      const boxArea = box.w * box.h
      const existArea = existing.w * existing.h
      const union = boxArea + existArea - interArea
      const iou = union > 0 ? interArea / union : 0
      const containment = Math.min(boxArea, existArea) > 0
        ? interArea / Math.min(boxArea, existArea)
        : 0

      // Only suppress genuine ghost/coincident duplicate boxes on the same finger,
      // preserving distinct adjacent or overlapping fingers in a dense banana bunch.
      return iou >= 0.80 || containment >= 0.88
    })

    if (!isDuplicate) {
      result.push(box)
    }
  }

  return result
}

function BoundingBoxImage({
  src,
  alt = "Detection result",
  boxes,
  className = "",
  showLabels = true,
  showConfidence = true,
  aspectRatio,
}: BoundingBoxOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [imgNaturalSize, setImgNaturalSize] = useState<{ w: number; h: number } | null>(null)
  const [imgLoaded, setImgLoaded] = useState(false)

  const onImgLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget
    setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
    setImgLoaded(true)
  }, [])

  const onImageUnavailable = useCallback(() => { setImgLoaded(false); setImgNaturalSize(null) }, [])

  const displayBoxes = deduplicateDisplayBoxes(boxes)

  const computedAspect = aspectRatio
    ? `${aspectRatio}`
    : imgNaturalSize
      ? `${imgNaturalSize.w} / ${imgNaturalSize.h}`
      : undefined

  return (
    <div
      ref={containerRef}
      className={`relative overflow-hidden ${className}`}
      style={{
        position: "relative",
        aspectRatio: computedAspect,
      }}
    >
      {/* Base image */}
      <ScanImage
        src={src}
        alt={alt}
        className="w-full h-full object-cover"
        onLoad={onImgLoad}
        onUnavailable={onImageUnavailable}
        draggable={false}
      />

      {/* Bounding box overlay layer */}
      {imgLoaded && imgNaturalSize && displayBoxes.length > 0 && (
        <svg
          viewBox={`0 0 ${imgNaturalSize.w} ${imgNaturalSize.h}`}
          className="absolute inset-0 w-full h-full pointer-events-none"
          preserveAspectRatio="xMidYMid slice"
          xmlns="http://www.w3.org/2000/svg"
        >
          {displayBoxes.map((box, idx) => {
            const color = getClassColor(box.cls)
            const label = showLabels ? formatClassName(box.cls) : ""
            const conf = showConfidence ? `${Math.round(box.conf * 100)}%` : ""
            const labelText = [label, conf].filter(Boolean).join(" · ")

            // Font size relative to image — scales with image resolution
            const fontSize = Math.max(10, Math.min(16, imgNaturalSize.w * 0.018))
            const labelPadX = fontSize * 0.4
            const labelPadY = fontSize * 0.25
            const labelHeight = fontSize + labelPadY * 2

            return (
              <g key={idx}>
                {/* Box rectangle */}
                <rect
                  x={box.x}
                  y={box.y}
                  width={box.w}
                  height={box.h}
                  fill={color.bg}
                  stroke={color.border}
                  strokeWidth={Math.max(1.5, imgNaturalSize.w * 0.003)}
                  rx={2}
                />
                {/* Label background */}
                {labelText && (
                  <>
                    <rect
                      x={box.x}
                      y={Math.max(0, box.y - labelHeight)}
                      width={labelText.length * fontSize * 0.58 + labelPadX * 2}
                      height={labelHeight}
                      fill={color.border}
                      rx={2}
                    />
                    <text
                      x={box.x + labelPadX}
                      y={Math.max(0, box.y - labelHeight) + labelPadY + fontSize * 0.82}
                      fontSize={fontSize}
                      fill="#fff"
                      fontFamily="Inter, system-ui, sans-serif"
                      fontWeight="600"
                    >
                      {labelText}
                    </text>
                  </>
                )}
              </g>
            )
          })}
        </svg>
      )}

      {/* Box count badge */}
      {displayBoxes.length > 0 && (
        <div className="absolute bottom-2 right-2 bg-black/70 backdrop-blur-sm text-white text-[10px] font-bold px-2 py-1 rounded-md flex items-center gap-1 z-10">
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
          {displayBoxes.length} detection{displayBoxes.length !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  )
}
