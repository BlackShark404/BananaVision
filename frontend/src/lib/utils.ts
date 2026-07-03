import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { Cultivar, Ripeness, ScanResult } from "@/types"
import { CULTIVARS, RIPENESS_LEVELS, CultivarEnum, RipenessEnum } from "@/types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Calculates estimated days until spoilage based on cultivar, ripeness, and environmental factors.
 * Uses a heuristic lookup table derived from domain research on banana shelf-life data.
 */
export function getSpoilageDays(
  cultivar: Cultivar, 
  ripeness: Ripeness,
  temperature?: number,
  humidity?: number
): string {
  if (ripeness === RipenessEnum.SEMI_RIPE) {
    // Semi-ripe bananas are transitioning; estimate based on cultivar
    let srMin = 0
    let srMax = 0
    if (cultivar === CultivarEnum.LAKATAN) { srMin = 3; srMax = 5 }
    else if (cultivar === CultivarEnum.LATUNDAN) { srMin = 2; srMax = 4 }
    else if (cultivar === CultivarEnum.SABA) { srMin = 5; srMax = 7 }

    if (temperature !== undefined && humidity !== undefined) {
      let multiplier = 1.0
      if (temperature > 28) multiplier -= 0.3
      else if (temperature < 22) multiplier += 0.2
      if (humidity > 75) multiplier -= 0.2
      else if (humidity < 60) multiplier += 0.1
      multiplier = Math.max(0.2, Math.min(2.0, multiplier))
      srMin = Math.max(1, Math.round(srMin * multiplier))
      srMax = Math.max(srMin, Math.round(srMax * multiplier))
    }
    return srMin === srMax ? `${srMin}` : `${srMin}-${srMax}`
  }
  
  let baseMin = 0
  let baseMax = 0

  if (cultivar === CultivarEnum.LAKATAN) {
    if (ripeness === RipenessEnum.UNRIPE) { baseMin = 4; baseMax = 6 }
    else if (ripeness === RipenessEnum.RIPE) { baseMin = 2; baseMax = 3 }
    else if (ripeness === RipenessEnum.OVERRIPE) { baseMin = 1; baseMax = 2 }
  } else if (cultivar === CultivarEnum.LATUNDAN) {
    if (ripeness === RipenessEnum.UNRIPE) { baseMin = 3; baseMax = 5 }
    else if (ripeness === RipenessEnum.RIPE) { baseMin = 1; baseMax = 2 }
    else if (ripeness === RipenessEnum.OVERRIPE) { baseMin = 1; baseMax = 1 }
  } else if (cultivar === CultivarEnum.SABA) {
    if (ripeness === RipenessEnum.UNRIPE) { baseMin = 6; baseMax = 8 }
    else if (ripeness === RipenessEnum.RIPE) { baseMin = 3; baseMax = 4 }
    else if (ripeness === RipenessEnum.OVERRIPE) { baseMin = 2; baseMax = 3 }
  }

  // Adjust shelf-life estimate based on environmental conditions
  if (temperature !== undefined && humidity !== undefined) {
    // High heat (>28°C) accelerates spoilage by ~30%
    // High humidity (>75%) accelerates spoilage by ~20%
    // Cold (<22°C) slows spoilage
    
    let multiplier = 1.0

    if (temperature > 28) multiplier -= 0.3
    else if (temperature < 22) multiplier += 0.2

    if (humidity > 75) multiplier -= 0.2
    else if (humidity < 60) multiplier += 0.1

    // Ensure we don't go below 0 or above double the baseline
    multiplier = Math.max(0.2, Math.min(2.0, multiplier))

    baseMin = Math.max(1, Math.round(baseMin * multiplier))
    baseMax = Math.max(baseMin, Math.round(baseMax * multiplier))
  }
  
  // Return the range to represent natural variance in shelf-life estimates
  return baseMin === baseMax ? `${baseMin}` : `${baseMin}-${baseMax}`
}

/**
 * Parses spoilage string ranges (e.g. "4-6") or exact strings (e.g. "5") into numeric averages.
 * For exact numeric strings, it behaves identically.
 */
export function parseSpoilageAvg(val: string): number {
  if (!val) return 0;
  if (val.includes("-")) {
    const [min, max] = val.split("-").map(Number);
    return (min + max) / 2;
  }
  return Number(val) || 0;
}

const BANANA_IMAGES: Record<string, string[]> = {
  [RipenessEnum.UNRIPE]: [
    "https://the-veggie-table.com/cdn/shop/products/saba_300x.png?v=1586490675", // Green bananas
    "https://www.gulayatbp.com/cdn/shop/files/banana_saba1.png?v=1729220360"  // Greenish bunch
  ],
  [RipenessEnum.RIPE]: [
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTQwik_uYQV3m9z-tF0NiOJuQIR-lxNqSzSWPZAvHUrZQ&s", // Yellow
    "https://www.eatright.org/-/media/images/eatright-articles/bananas.jpg?as=0&w=967&rev=c5a21c5b5daf455baa28092d199f7ea9&hash=0DB86DF1DDEDF4F1003A3BF726BF4ABC", // Bright yellow
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ9EYaQHTYBuaCBi0Dmb2ijsHJaAp3LoxZqFQ&s"  // Yellow bundle
  ],
  [RipenessEnum.OVERRIPE]: [
    "https://chefjulieyoon.com/wp-content/uploads/2012/08/RipeBananas-1.jpg", // Spotted
    "https://delightfuladventures.com/wp-content/uploads/2019/02/what-to-do-with-overripe-bananas-info.jpg"  // Spotted yellow
  ],
  [RipenessEnum.SEMI_RIPE]: [
    "https://the-veggie-table.com/cdn/shop/products/saba_300x.png?v=1586490675", // Greenish-yellow
    "https://www.gulayatbp.com/cdn/shop/files/banana_saba1.png?v=1729220360"  // Transitioning
  ]
};

/**
 * Returns an actual photo URL based on the banana's cultivar and ripeness.
 */
export function getBananaImageUrl(cultivar: Cultivar, ripeness: Ripeness): string {
  const images = BANANA_IMAGES[ripeness] || BANANA_IMAGES[RipenessEnum.RIPE];
  // Use cultivar string length to pseudo-randomly pick an image from the array consistently
  const index = (cultivar.length + ripeness.length) % images.length;
  return images[index];
}

export function getAnalyticsData(scans: ScanResult[]) {
  const ripenessDistribution = RIPENESS_LEVELS.map((r) => ({
    name: r,
    value: scans.filter((s) => s.ripeness === r).length,
  }))

  const cultivarCounts = CULTIVARS.map((c) => ({
    name: c,
    count: scans.filter((s) => s.cultivar === c).length,
  }))

  const scansByDay: Record<string, number> = {}
  scans.forEach((s) => {
    const day = new Date(s.dateTime).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    })
    scansByDay[day] = (scansByDay[day] || 0) + 1
  })
  const scanTrend = Object.entries(scansByDay)
    .map(([date, count]) => ({ date, count }))
    .reverse()
    .slice(-14)

  const avgConfidence = scans.length
    ? parseFloat(
        (scans.reduce((a, s) => a + s.confidence, 0) / scans.length).toFixed(1)
      )
    : 0
  const cultivarCountMap: Record<string, number> = {}
  scans.forEach((s) => {
    cultivarCountMap[s.cultivar] = (cultivarCountMap[s.cultivar] || 0) + 1
  })
  const mostCommonCultivar =
    Object.entries(cultivarCountMap).sort((a, b) => b[1] - a[1])[0]?.[0] ||
    "N/A"

  return {
    ripenessDistribution,
    cultivarCounts,
    scanTrend,
    totalScans: scans.length,
    avgConfidence,
    mostCommonCultivar,
  }
}

