import { useMemo, useState, useEffect, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { useScans } from "@/context/ScanContext"
import { useAdmin } from "@/context/AdminContext"
import { useWebSocket } from "@/hooks/useWebSocket"
import { api, BASE_URL } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AppStatsCard } from "@/components/AppStatsCard"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { AppPageHeader } from "@/components/AppPageHeader"
import {
  ScanLine,
  Camera,
  AlertCircle,
  Package,
  Target,
  TrendingUp,
  Users,
  Activity,
  ArrowRight,
  LayoutDashboard
} from "lucide-react"
import { AppStatusBadge } from "@/components/AppStatusBadge"

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { scans } = useScans()
  const { devices, config } = useAdmin()

  // --- Real-time Backend Metrics State ---
  const [summary, setSummary] = useState<any>(null)
  const [operatorPerf, setOperatorPerf] = useState<any>(null)
  const [activeSourcesList, setActiveSourcesList] = useState<{name: string, count: number}[]>([])

  const fetchDashboardData = useCallback(async () => {
    try {
      const sum = await api.analytics.summary({ range: "today" })
      setSummary(sum)
      setActiveSourcesList(sum.scans_by_source || [])

      const perf = await api.analytics.operatorPerformance({ range: "today" })
      if (user?.role === "Operator") {
        const myPerf = perf.items?.find((i: any) => i.name === user.fullName)
        setOperatorPerf(myPerf || null)
      } else {
        setOperatorPerf({ activeCount: perf.items?.length || 0 })
      }
    } catch (e) {
      console.error("Failed to fetch dashboard metrics", e)
    }
  }, [user])

  useEffect(() => {
    fetchDashboardData()
  }, [fetchDashboardData])

  // Listen for websocket events to keep backend metrics real-time
  useWebSocket({
    rooms: ["dashboard"],
    onEvent: (event) => {
      if (event === "scan:completed") {
        fetchDashboardData()
      }
    },
    enabled: !!user
  })

  // --- RBAC Filtering for Recent Scans ---
  const roleFilteredScans = useMemo(() => {
    return user?.role === "Operator" ? scans.filter(s => s.operator === user?.fullName) : scans
  }, [scans, user])

  const recentScans = useMemo(() => {
    return roleFilteredScans.slice(0, 5)
  }, [roleFilteredScans])

  // --- Derived Metrics ---
  const todayScans = useMemo(() => {
    return user?.role === "Operator" ? (operatorPerf?.total_scans || 0) : (summary?.total_scans || 0)
  }, [summary, operatorPerf, user])

  const operatorMetric = useMemo(() => {
    if (user?.role === "Operator") {
      const avgConf = operatorPerf?.avg_confidence
      return { 
        value: avgConf ? `${Math.round(avgConf)}%` : "—", 
        label: "My Avg Confidence", 
        icon: Target, 
        desc: "Accuracy today" 
      }
    } else {
      return { 
        value: operatorPerf?.activeCount || 0, 
        label: "Active Operators", 
        icon: Users, 
        desc: "Staff working today" 
      }
    }
  }, [operatorPerf, user])

  const onlineCameras = useMemo(() => {
    return devices.filter(d => d.status === "Online").length
  }, [devices])

  const sortedDevices = useMemo(() => {
    const order = config.cameraIds.split(",").map(id => id.trim()).filter(Boolean)
    return [...devices].sort((a, b) => {
      const indexA = order.indexOf(a.cameraId)
      const indexB = order.indexOf(b.cameraId)
      if (indexA === -1 && indexB === -1) return 0
      if (indexA === -1) return 1
      if (indexB === -1) return -1
      return indexA - indexB
    })
  }, [devices, config.cameraIds])

  return (
    <div className="space-y-4 sm:space-y-6 pb-4 sm:pb-6">
      {/* Header */}
      <AppPageHeader
        title={user?.role === "Operator" ? "My Dashboard" : "Admin Dashboard"}
        description={user?.role === "Operator" ? "Performance overview and recent scans" : "High-level overview of system operations and daily metrics"}
        icon={LayoutDashboard}
      />

      {/* KPI StatsRow */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AppStatsCard
          title="Scans Today"
          value={todayScans}
          icon={TrendingUp}
          iconColor="text-blue-600"
          iconBgColor="bg-blue-500/10"
          delay={50}
          description="Total bananas scanned"
        />
        <AppStatsCard
          title={operatorMetric.label}
          value={operatorMetric.value}
          icon={operatorMetric.icon}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={100}
          description={operatorMetric.desc}
        />
        <AppStatsCard
          title={user?.role === "Operator" ? "My Sources Today" : "Active Sources"}
          value={activeSourcesList.length}
          icon={Package}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={150}
          description="Sources scanned today"
        />
        <AppStatsCard
          title="System Health"
          value={`${onlineCameras}/${devices.length}`}
          icon={Activity}
          iconColor={onlineCameras === devices.length && devices.length > 0 ? "text-emerald-600" : "text-amber-600"}
          iconBgColor={onlineCameras === devices.length && devices.length > 0 ? "bg-emerald-500/10" : "bg-amber-500/10"}
          delay={200}
          description="Cameras online"
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        
        {/* Recent Scans Table (Takes up 2 columns) */}
        <Card className="col-span-1 lg:col-span-2 rounded-xl sm:rounded-2xl shadow-sm overflow-hidden flex flex-col">
          <CardHeader className="pb-3 flex flex-row items-center justify-between border-b bg-muted/10">
            <div>
              <CardTitle className="text-base sm:text-lg">Recent Scans</CardTitle>
              <CardDescription className="text-xs">Live feed of the latest classification results</CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => navigate("/logs")} className="hidden sm:flex text-muted-foreground hover:text-primary">
              View All Logs <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </CardHeader>
          <div className="flex-1">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="font-semibold w-[140px]">Date/Time</TableHead>
                  <TableHead className="font-semibold">Cultivar</TableHead>
                  <TableHead className="font-semibold">Ripeness</TableHead>
                  <TableHead className="font-semibold">Confidence</TableHead>
                  <TableHead className="font-semibold">Source</TableHead>
                  {user?.role !== "Operator" && <TableHead className="font-semibold text-right">Operator</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentScans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={user?.role === "Operator" ? 5 : 6} className="h-48 text-center">
                      <Empty>
                        <EmptyHeader>
                          <EmptyMedia variant="icon" className="size-10 rounded-full bg-primary/10 text-primary [&_svg]:size-5">
                            <ScanLine className="w-4 h-4" />
                          </EmptyMedia>
                          <EmptyTitle className="text-sm font-medium mt-1">No recent scans</EmptyTitle>
                        </EmptyHeader>
                      </Empty>
                    </TableCell>
                  </TableRow>
                ) : (
                  recentScans.map((scan) => (
                    <TableRow key={scan.id} className="cursor-pointer hover:bg-muted/50" onClick={() => navigate(`/scans/${scan.id}`)}>
                      <TableCell className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(scan.dateTime).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      </TableCell>
                      <TableCell className="font-medium text-sm">{scan.cultivar}</TableCell>
                      <TableCell>
                        <AppStatusBadge type="ripeness" status={scan.ripeness} size="sm" />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium">{scan.confidence}%</span>
                          <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden hidden sm:block">
                            <div className="h-full bg-primary rounded-full" style={{ width: `${scan.confidence}%` }} />
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="font-medium text-xs text-muted-foreground whitespace-nowrap">
                        {scan.source || "—"}
                      </TableCell>
                      {user?.role !== "Operator" && (
                        <TableCell className="text-right text-xs truncate max-w-[100px]">
                          {scan.operator}
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Card>

        {/* Active Sources Side Panel */}
        <Card className="col-span-1 rounded-xl sm:rounded-2xl shadow-sm flex flex-col">
          <CardHeader className="pb-3 border-b bg-muted/10 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base sm:text-lg">Today's Sources</CardTitle>
              <CardDescription className="text-xs">Suppliers & sources with activity today</CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => navigate("/logs")} className="h-8 w-8 text-muted-foreground hover:text-primary">
              <ArrowRight className="w-4 h-4" />
            </Button>
          </CardHeader>
          <CardContent className="p-0 flex-1">
            {activeSourcesList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                <Package className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-sm">No active sources today</p>
              </div>
            ) : (
              <div className="divide-y overflow-y-auto" style={{ maxHeight: "400px" }}>
                {activeSourcesList.map((sourceItem) => (
                  <div key={sourceItem.name} className="p-4 flex items-center justify-between hover:bg-muted/30 transition-colors">
                    <div className="min-w-0 pr-4">
                      <p className="text-sm font-semibold truncate text-foreground/90">{sourceItem.name}</p>
                    </div>
                    <div className="flex flex-col items-end shrink-0">
                      <Badge variant="secondary" className="bg-primary/10 text-primary hover:bg-primary/20 border-primary/20">
                        {sourceItem.count} scans
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

      </div>

      {/* Camera Frames Section */}
      <div>
        <h2 className="text-base sm:text-lg font-semibold mb-3 flex items-center gap-2 px-1">
          <Camera className="w-4 h-4 sm:w-5 sm:h-5 text-muted-foreground" /> Hardware Monitoring
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {sortedDevices.map((device) => {
            const isOnline = device.status === "Online"
            const camIndex = parseInt(device.cameraId.replace(/[^0-9]/g, '')) - 1
            
            return (
              <Card key={device.id} className="rounded-lg sm:rounded-xl overflow-hidden group">
                <div className={`aspect-video relative flex items-center justify-center ${isOnline ? 'bg-black' : 'bg-destructive/5'}`}>
                  {isOnline ? (
                    <>
                      <img
                        src={`${BASE_URL}/api/v1/cameras/preview/${camIndex}`}
                        alt={`Live Camera Feed - ${device.cameraId}`}
                        className="inset-0 w-full h-full object-cover z-0 absolute animate-fade-in"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                          const fallback = e.currentTarget.parentElement?.querySelector('.camera-fallback');
                          if (fallback) (fallback as HTMLElement).style.display = 'block';
                        }}
                      />
                      <div className="absolute inset-0 bg-linear-to-b from-transparent to-black/40 z-0 pointer-events-none" />
                      
                      <div className="camera-fallback hidden text-center space-y-1.5 sm:space-y-2 z-10 relative">
                        <Camera className="w-6 h-6 sm:w-8 sm:h-8 text-white/40 mx-auto" />
                        <p className="text-[10px] sm:text-xs text-white/60">{device.cameraId} Ready</p>
                      </div>

                      <div className="absolute top-1.5 sm:top-2 right-1.5 sm:right-2 z-10">
                        <Badge variant="outline" className="bg-emerald-500/90 text-white border-0 text-[9px] sm:text-[10px] px-1 sm:px-1.5 h-4 sm:h-auto">
                          ONLINE
                        </Badge>
                      </div>
                      <div className="absolute bottom-1.5 sm:bottom-2 left-1.5 sm:left-2 z-10">
                        <span className="text-[9px] sm:text-[10px] text-white/90 bg-black/50 px-1.5 sm:px-2 py-0.5 rounded backdrop-blur-sm shadow-sm font-medium">
                          {device.cameraId}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="text-center space-y-1.5 sm:space-y-2 relative z-10">
                      <AlertCircle className="w-6 h-6 sm:w-8 sm:h-8 text-destructive/40 mx-auto" />
                      <p className="text-[10px] sm:text-xs text-destructive/60 font-medium">{device.cameraId} Offline</p>
                    </div>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
