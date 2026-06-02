import { getSpoilageDays, getBananaImageUrl } from "@/lib/utils"
import type {
  ActivityLog,
  AppNotification,
  Cultivar,
  DailyIntake,
  Device,
  InventoryStatus,
  Ripeness,
  ScanResult,
  Supplier,
  User,
} from "@/types"

export const MOCK_SUPPLIERS = [
  "Local Market",
  "Farmer Joe",
  "Davao Plantations",
  "Mang Jose Farms",
]

export const generateSuppliers = (): Supplier[] => {
  return MOCK_SUPPLIERS.map((name, index) => ({
    id: `SUP-${index + 1}`.padStart(7, "0"),
    name,
    contactPerson: index % 2 === 0 ? "Juan Dela Cruz" : undefined,
    contactPhone:
      index % 2 === 0
        ? `09${Math.floor(Math.random() * 900000000) + 100000000}`
        : undefined,
    status: "Active",
    dateAdded: new Date(
      Date.now() - Math.random() * 86400000 * 30
    ).toISOString(),
  }))
}

const cultivars: Cultivar[] = ["Lakatan", "Latundan", "Saba"]
const ripenessLevels: Ripeness[] = ["Unripe", "Ripe", "Overripe", "Rotten"]
const operators = [
  "Test Operator",
  "Juan Cruz",
  "Maria Santos",
  "Pedro Reyes",
  "Ana Dizon",
  "Carlos Mendoza",
]

function randomItem<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

function randomBetween(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function generateId(): string {
  return Math.random().toString(36).substring(2, 10)
}

function generateDate(daysAgo: number): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  d.setHours(randomBetween(6, 18), randomBetween(0, 59), randomBetween(0, 59))
  return d.toISOString()
}

export function generateScanResults(count: number): ScanResult[] {
  const inventoryStatuses: InventoryStatus[] = [
    "In Stock",
    "Sold",
    "For Processing",
    "Spoiled",
  ]

  return Array.from({ length: count }, (_, i) => {
    const ripeness = randomItem(ripenessLevels)
    const cultivar = randomItem(cultivars)
    const temperature = parseFloat((Math.random() * 10 + 20).toFixed(1)) // 20.0 to 30.0 C
    const humidity = parseFloat((Math.random() * 30 + 50).toFixed(1)) // 50.0 to 80.0 %
    const spoilage = getSpoilageDays(cultivar, ripeness, temperature, humidity)
    const daysAgo = Math.floor(i / 3)
    const source = randomItem(MOCK_SUPPLIERS)

    // Older scans are more likely to be sold/shipped, recent ones in stock
    let status: InventoryStatus = "In Stock"
    if (daysAgo > 5) {
      status = randomItem(inventoryStatuses)
    } else if (daysAgo > 2) {
      status =
        Math.random() > 0.6
          ? "In Stock"
          : randomItem(["Sold", "For Processing"])
    }

    return {
      id: generateId(),
      dateTime: generateDate(daysAgo),
      cultivar,
      ripeness,
      confidence: parseFloat((Math.random() * 15 + 85).toFixed(1)),
      temperature, // 20.0 to 30.0 C
      humidity, // 50.0 to 80.0 %
      spoilageDays: spoilage,
      fingerCount: randomBetween(4, 16),
      operator: randomItem(operators),
      source,
      thumbnailUrl: getBananaImageUrl(cultivar, ripeness),
      inventoryStatus: status,
      statusUpdatedAt: generateDate(Math.max(0, daysAgo - 1)),
    }
  }).sort(
    (a, b) => new Date(b.dateTime).getTime() - new Date(a.dateTime).getTime()
  )
}

export function generateIntakes(scans: ScanResult[]): DailyIntake[] {
  const intakeMap = new Map<string, DailyIntake>()

  scans.forEach((scan) => {
    if (!scan.source) return
    const date = new Date(scan.dateTime).toISOString().split("T")[0]
    const key = `${scan.source}-${date}`

    if (!intakeMap.has(key)) {
      const daysAgo = Math.floor(
        (new Date().getTime() - new Date(scan.dateTime).getTime()) /
          (1000 * 60 * 60 * 24)
      )
      intakeMap.set(key, {
        id: `INT-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
        source: scan.source,
        date,
        status: daysAgo > 3 ? "Depleted" : "Active",
      })
    }
    scan.intakeId = intakeMap.get(key)!.id
  })

  return Array.from(intakeMap.values()).sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
  )
}

export function generateUsers(): User[] {
  return [
    {
      id: "1",
      username: "admin",
      fullName: "Admin User",
      role: "Admin",
      lastActive: generateDate(0),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
    {
      id: "2",
      username: "operator",
      fullName: "Test Operator",
      role: "Operator",
      lastActive: generateDate(0),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
    {
      id: "3",
      username: "jcruz",
      fullName: "Juan Cruz",
      role: "Operator",
      lastActive: generateDate(0),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
    {
      id: "4",
      username: "msantos",
      fullName: "Maria Santos",
      role: "Operator",
      lastActive: generateDate(1),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
    {
      id: "5",
      username: "preyes",
      fullName: "Pedro Reyes",
      role: "Operator",
      lastActive: generateDate(0),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
    {
      id: "6",
      username: "adizon",
      fullName: "Ana Dizon",
      role: "Operator",
      lastActive: generateDate(2),
      status: "Inactive",
      pin: "1234",
      password: "pass",
    },
    {
      id: "7",
      username: "cmendoza",
      fullName: "Carlos Mendoza",
      role: "Admin",
      lastActive: generateDate(0),
      status: "Active",
      pin: "1234",
      password: "pass",
    },
  ]
}

export function generateDevices(cameraIds?: string[]): Device[] {
  if (cameraIds && cameraIds.length > 0) {
    return cameraIds.map((id, index) => ({
      id: String(index + 1),
      cameraId: id,
      label: `Scanner ${index + 1}`,
      status: index % 3 === 0 ? "Offline" : "Online",
      resolution: "1920x1080",
      lastSeen: index % 3 === 0 ? generateDate(1) : new Date().toISOString(),
    }))
  }

  return [
    {
      id: "1",
      cameraId: "CAM-001",
      label: "Main Scanner",
      status: "Online",
      resolution: "1920x1080",
      lastSeen: new Date().toISOString(),
    },
    {
      id: "2",
      cameraId: "CAM-002",
      label: "Side Scanner",
      status: "Online",
      resolution: "1280x720",
      lastSeen: new Date().toISOString(),
    },
    {
      id: "3",
      cameraId: "CAM-003",
      label: "Quality Check",
      status: "Offline",
      resolution: "1920x1080",
      lastSeen: generateDate(1),
    },
    {
      id: "4",
      cameraId: "CAM-004",
      label: "Backup Camera",
      status: "Offline",
      resolution: "640x480",
      lastSeen: generateDate(3),
    },
  ]
}

export function getAnalyticsData(scans: ScanResult[]) {
  const ripenessDistribution = ripenessLevels.map((r) => ({
    name: r,
    value: scans.filter((s) => s.ripeness === r).length,
  }))

  const cultivarCounts = cultivars.map((c) => ({
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

export function generateActivityLogs(): ActivityLog[] {
  const actions: ActivityLog["action"][] = [
    "login",
    "logout",
    "scan_created",
    "scan_edited",
    "scan_deleted",
    "user_created",
    "user_updated",
    "config_changed",
    "scan_flagged",
    "supplier_created",
    "supplier_updated",
    "supplier_deleted",
    "intake_created",
    "intake_edited",
    "intake_deleted",
    "intake_status_changed",
    "system_shutdown",
    "system_restart",
  ]
  const users = [
    "Admin User",
    "Juan Cruz",
    "Maria Santos",
    "Pedro Reyes",
    "Carlos Mendoza",
  ]
  const ips = [
    "192.168.1.10",
    "192.168.1.15",
    "192.168.1.20",
    "192.168.1.25",
    "192.168.1.30",
  ]

  const details: Record<ActivityLog["action"], string[]> = {
    login: ["Successful login", "Login from new device", "Login attempt"],
    logout: ["User logged out", "Session expired", "Logged out"],
    scan_created: [
      "Created new banana scan",
      "Scanned Lakatan bunch",
      "Scanned Saba bunch",
      "Scanned Latundan bunch",
    ],
    scan_edited: [
      "Updated scan confidence",
      "Corrected ripeness classification",
      "Modified scan data",
    ],
    scan_deleted: [
      "Deleted scan record",
      "Removed duplicate scan entry",
      "Deleted invalid scan data",
    ],
    user_created: [
      "Created new operator account",
      "Added new user",
      "Registered new operator",
    ],
    user_updated: [
      "Updated user permissions",
      "Changed user role",
      "Modified user status",
    ],
    config_changed: [
      "Updated confidence threshold",
      "Modified system settings",
      "Changed camera configuration",
    ],
    scan_flagged: [
      "Flagged scan for review",
      "Marked scan as low quality",
      "Flagged for quality control",
    ],
    supplier_created: ["Added new supplier", "Registered new farm source"],
    supplier_updated: ["Updated supplier contact", "Modified supplier details"],
    supplier_deleted: ["Deactivated supplier", "Removed farm source"],
    intake_created: ["Recorded new batch delivery", "Scanned implicit intake"],
    intake_edited: ["Adjusted intake records", "Modified delivery data"],
    intake_deleted: ["Voided intake", "Deleted erroneous delivery"],
    intake_status_changed: ["Marked intake as depleted", "Re-activated intake"],
    system_shutdown: ["System shutdown initiated", "Manual shutdown completed"],
    system_restart: ["System restart initiated", "Manual reboot completed"],
  }

  return Array.from({ length: 100 }, (_, i) => {
    const action = randomItem(actions)
    return {
      id: generateId(),
      timestamp: generateDate(Math.floor(i / 5)),
      user: randomItem(users),
      action,
      details: randomItem(details[action]),
      ipAddress: randomItem(ips),
    }
  }).sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )
}

// ─── Notifications ───────────────────────────────────────────────────────────

export function getMockNotifications(): AppNotification[] {
  const now = new Date()
  return [
    {
      id: "n1",
      type: "scan_flagged",
      title: "Scan Flagged for Review",
      message:
        "Scan #a8k2m has low confidence (72%) and was flagged automatically.",
      timestamp: new Date(now.getTime() - 2 * 60 * 1000),
      read: false,
      href: "/logs",
    },
    {
      id: "n3",
      type: "quality_warning",
      title: "Quality Threshold Alert",
      message:
        "3 scans in the last hour fell below the 85% confidence threshold.",
      timestamp: new Date(now.getTime() - 32 * 60 * 1000),
      read: false,
      href: "/admin/quality",
    },
    {
      id: "n2",
      type: "intake_update",
      title: "New Delivery Intake",
      message:
        "Mang Jose Farms — 5 bananas scanned and added to today's intake.",
      timestamp: new Date(now.getTime() - 15 * 60 * 1000),
      read: false,
      href: "/admin/intakes",
    },
    {
      id: "n4",
      type: "scan_complete",
      title: "Scan Completed",
      message: "Lakatan · Ripe · 96.2% confidence · 8 fingers detected.",
      timestamp: new Date(now.getTime() - 1 * 60 * 60 * 1000),
      read: true,
      href: "/logs",
    },
    {
      id: "n5",
      type: "system_alert",
      title: "Camera Reconnected",
      message: "CAM-002 is back online after a brief disconnection.",
      timestamp: new Date(now.getTime() - 2 * 60 * 60 * 1000),
      read: true,
      href: "/devices",
    },
    {
      id: "n6",
      type: "scan_complete",
      title: "Scan Completed",
      message: "Saba · Unripe · 91.8% confidence · 12 fingers detected.",
      timestamp: new Date(now.getTime() - 3 * 60 * 60 * 1000),
      read: true,
      href: "/logs",
    },
  ]
}
