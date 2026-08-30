import { useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useApp } from "@/context/AppContext"
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
  const { scans, devices, user, config } = useApp()

  // --- RBAC Filtering ---
  const roleFilteredScans = useMemo(() => {
    return user?.role === "Operator" ? scans.filter(s => s.operator === user?.fullName) : scans
  }, [scans, user])

  // --- Derived Metrics ---
  const todayScans = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return roleFilteredScans.filter(s => new Date(s.dateTime) >= today).length
  }, [roleFilteredScans])

  const activeSources = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const scansToday = roleFilteredScans.filter(s => new Date(s.dateTime) >= today)
    return Array.from(new Set(scansToday.map(s => s.source).filter(Boolean)))
  }, [roleFilteredScans])

  const operatorMetric = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const scansToday = roleFilteredScans.filter(s => new Date(s.dateTime) >= today)

    if (user?.role === "Operator") {
      // Show operator's average confidence today
      const avgConf = scansToday.length 
        ? Math.round(scansToday.reduce((sum, s) => sum + s.confidence, 0) / scansToday.length)
        : 0
      return { value: avgConf ? `${avgConf}%` : "—", label: "My Avg Confidence", icon: Target, desc: "Accuracy today" }
    } else {
      // Show total active operators today
      const operatorsToday = new Set(scansToday.map(s => s.operator))
      return { value: operatorsToday.size, label: "Active Operators", icon: Users, desc: "Staff working today" }
    }
  }, [roleFilteredScans, user])

  const onlineCameras = useMemo(() => {
    return devices.filter(d => d.status === "Online").length
  }, [devices])

  const recentScans = useMemo(() => {
    return roleFilteredScans.slice(0, 5)
  }, [roleFilteredScans])

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
          value={activeSources.length}
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
          iconColor={onlineCameras === devices.length ? "text-emerald-600" : "text-amber-600"}
          iconBgColor={onlineCameras === devices.length ? "bg-emerald-500/10" : "bg-amber-500/10"}
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
            {activeSources.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                <Package className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-sm">No active sources today</p>
              </div>
            ) : (
              <div className="divide-y overflow-y-auto" style={{ maxHeight: "400px" }}>
                {activeSources.map((source) => {
                  const today = new Date()
                  today.setHours(0, 0, 0, 0)
                  const sourceScans = roleFilteredScans.filter(s => s.source === source && new Date(s.dateTime) >= today).length
                  return (
                    <div key={source as string} className="p-4 flex items-center justify-between hover:bg-muted/30 transition-colors">
                      <div className="min-w-0 pr-4">
                        <p className="text-sm font-semibold truncate text-foreground/90">{source}</p>
                      </div>
                      <div className="flex flex-col items-end shrink-0">
                        <Badge variant="secondary" className="bg-primary/10 text-primary hover:bg-primary/20 border-primary/20">
                          {sourceScans} scans
                        </Badge>
                      </div>
                    </div>
                  )
                })}
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
            return (
              <Card key={device.id} className="rounded-lg sm:rounded-xl overflow-hidden group">
                <div className={`aspect-video relative flex items-center justify-center ${isOnline ? 'bg-muted/60' : 'bg-destructive/5'}`}>
                  {isOnline ? (
                    <>
                      <div className="absolute inset-0 bg-linear-to-b from-transparent to-black/20" />
                      <div className="text-center space-y-1.5 sm:space-y-2">
                        <Camera className="w-6 h-6 sm:w-8 sm:h-8 text-muted-foreground/40 mx-auto" />
                        <p className="text-[10px] sm:text-xs text-muted-foreground">{device.cameraId} Ready</p>
                      </div>
                      <div className="absolute top-1.5 sm:top-2 right-1.5 sm:right-2">
                        <Badge variant="outline" className="bg-emerald-500/90 text-white border-0 text-[9px] sm:text-[10px] px-1 sm:px-1.5 h-4 sm:h-auto">
                          ONLINE
                        </Badge>
                      </div>
                      <div className="absolute bottom-1.5 sm:bottom-2 left-1.5 sm:left-2">
                        <span className="text-[9px] sm:text-[10px] text-white/80 bg-black/40 px-1 sm:px-1.5 py-0.5 rounded backdrop-blur-sm">
                          {new Date().toLocaleTimeString()}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="text-center space-y-1.5 sm:space-y-2">
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
