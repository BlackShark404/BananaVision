import { Skeleton } from "@/components/ui/skeleton"
import { useAdmin } from "@/context/AdminContext"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Monitor, Camera, Wifi, WifiOff, Cpu, HardDrive, Clock, MemoryStick, Thermometer, Activity, RefreshCw, Droplets } from "lucide-react"
import { useEffect, useState, useRef } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { useWebSocket } from "@/hooks/useWebSocket"
export default function DeviceStatus() {
  const { devices, devicesLoading, devicesReady, devicesError } = useAdmin()
  const online = devices.filter((d) => d.status === "Online").length
  const total = devices.length
  const [metricsLoading, setMetricsLoading] = useState(true)
  const [metricsError, setMetricsError] = useState("")
  const [lastUpdate, setLastUpdate] = useState(new Date())

  const [systemMetrics, setSystemMetrics] = useState<{
    cpu_name: string
    cpu_percent: number
    memory_used_gb: number
    memory_total_gb: number
    memory_percent: number
    disk_used_gb: number
    disk_total_gb: number
    disk_percent: number
    uptime: string
    cpu_temp: number | null
  } | null>(null)

  const [sensorData, setSensorData] = useState<{ temperature: number; humidity: number } | null>(null)
  const [sensorConnected, setSensorConnected] = useState<boolean | null>(null)
  const [sensorLoading, setSensorLoading] = useState(true)
  const [sensorError, setSensorError] = useState("")
  const [sensorRetry, setSensorRetry] = useState(0)
  const liveSensorRevision = useRef(0)

  // Listen for live sensor readings via WebSocket
  useWebSocket({
    rooms: ["dashboard"],
    onEvent: (event, data) => {
      if (event === "sensor:update") {
        if (!Number.isFinite(data.temperature) || !Number.isFinite(data.humidity)) return
        ++liveSensorRevision.current
        setSensorLoading(false)
        setSensorError("")
        setSensorConnected(true)
        setSensorData({
          temperature: data.temperature,
          humidity: data.humidity
        })
      }
    }
  })

  // Fetch initial sensor data and health on mount
  useEffect(() => {
    let active = true
    const revision = liveSensorRevision.current
    setSensorLoading(true)
    setSensorError("")
    api.sensors.latest().then((res) => {
      if (active && revision === liveSensorRevision.current && res) setSensorData({ temperature: res.temperature, humidity: res.humidity })
    }).catch(() => { if (active && revision === liveSensorRevision.current) setSensorError("Sensor readings unavailable.") })
      .finally(() => { if (active) setSensorLoading(false) })

    api.health().then((res) => {
      if (active && revision === liveSensorRevision.current) setSensorConnected(res.sensor_connected)
    }).catch(() => { if (active && revision === liveSensorRevision.current) setSensorError("Sensor connection status unavailable.") })
    return () => { active = false }
  }, [sensorRetry])

  // Fetch live system metrics every 5 seconds
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const fetchMetrics = async () => {
      setMetricsLoading(true)
      try {
        const res = await api.system.metrics()
        if (active) { setSystemMetrics(res); setLastUpdate(new Date()); setMetricsError("") }
      } catch { if (active) setMetricsError("System metrics unavailable. Retrying automatically…") }
      finally {
        if (active) { setMetricsLoading(false); timer = setTimeout(fetchMetrics, 5000) }
      }
    }
    void fetchMetrics()
    return () => { active = false; clearTimeout(timer) }
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          <Monitor className="w-7 h-7" /> Device Status
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          {online} of {total} cameras online
        </p>
      </div>

      {/* Camera Cards */}
      {devicesError && <p role="alert" className="text-sm text-destructive">{devicesError}</p>}
      {!devicesReady && devicesLoading ? <div role="status" aria-label="Loading cameras" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-40 rounded-2xl" />)}</div> : devices.length === 0 && !devicesError ? (
        <Card className="rounded-2xl">
          <CardContent className="p-12">
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                  <Camera className="w-4 h-4" />
                </EmptyMedia>
                <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No cameras found</EmptyTitle>
                <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                  No camera devices are currently configured in the system
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {devices.map((device, i) => (
          <Card
            key={device.id}
            className={`rounded-2xl animate-fade-in overflow-hidden transition-shadow hover:shadow-lg ${
              device.status === "Online" ? "border-emerald-200" : "border-border opacity-75"
            }`}
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className={`h-1 ${device.status === "Online" ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${device.status === "Online" ? "bg-emerald-100 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                    <Camera className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-sm font-semibold">{device.label}</CardTitle>
                    <p className="text-xs text-muted-foreground">{device.cameraId}</p>
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                    device.status === "Online"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : "bg-red-50 text-red-600 border-red-200"
                  }`}
                >
                  {device.status === "Online" ? <Wifi className="w-3 h-3 mr-1" /> : <WifiOff className="w-3 h-3 mr-1" />}
                  {device.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Resolution</span>
                <span className="font-medium">{device.resolution}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Last Seen</span>
                <span className="font-medium text-xs">
                  {new Date(device.lastSeen).toLocaleDateString()}
                </span>
              </div>
            </CardContent>
          </Card>
          ))}
        </div>
      )}

      {/* System Info */}
      <Card className="rounded-2xl">
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Cpu className="w-5 h-5" /> System Information
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50">
              <Cpu className="w-5 h-5 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Processor</p>
                <p className="text-sm font-medium">{systemMetrics?.cpu_name ?? (metricsLoading ? <Skeleton className="h-5 w-24" /> : "Unavailable")}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50">
              <HardDrive className="w-5 h-5 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Storage</p>
                <p className="text-sm font-medium">{systemMetrics ? `${systemMetrics.disk_used_gb} GB / ${systemMetrics.disk_total_gb} GB` : metricsLoading ? <Skeleton className="h-5 w-24" /> : "Unavailable"}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50">
              <Clock className="w-5 h-5 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Uptime</p>
                <p className="text-sm font-medium">{systemMetrics?.uptime ?? (metricsLoading ? <Skeleton className="h-5 w-24" /> : "Unavailable")}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* System Performance */}
      <Card className="rounded-2xl">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" /> System Performance
            </CardTitle>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <RefreshCw className={`w-3.5 h-3.5 ${metricsLoading ? "animate-spin" : ""}`} />
              <span>{metricsLoading ? "Refreshing metrics…" : systemMetrics ? `Updated ${lastUpdate.toLocaleTimeString()}` : "Metrics unavailable"}</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {metricsError && <p role="alert" className="text-sm text-destructive">{metricsError}</p>}
          {!systemMetrics && metricsLoading ? <div role="status" aria-label="Loading system metrics" className="space-y-5">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div> : <>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-blue-600" />
                <span className="font-medium">CPU Usage</span>
              </div>
              <span className="text-muted-foreground">{systemMetrics ? `${systemMetrics.cpu_percent}%` : "—"}</span>
            </div>
            <Progress value={systemMetrics?.cpu_percent ?? 0} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <MemoryStick className="w-4 h-4 text-purple-600" />
                <span className="font-medium">Memory Usage</span>
              </div>
              <span className="text-muted-foreground">{systemMetrics ? `${systemMetrics.memory_used_gb} GB / ${systemMetrics.memory_total_gb} GB (${systemMetrics.memory_percent}%)` : "—"}</span>
            </div>
            <Progress value={systemMetrics?.memory_percent ?? 0} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-emerald-600" />
                <span className="font-medium">Disk Usage</span>
              </div>
              <span className="text-muted-foreground">{systemMetrics ? `${systemMetrics.disk_used_gb} GB / ${systemMetrics.disk_total_gb} GB (${systemMetrics.disk_percent}%)` : "—"}</span>
            </div>
            <Progress value={systemMetrics?.disk_percent ?? 0} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Thermometer className="w-4 h-4 text-orange-600" />
                <span className="font-medium">CPU Temperature</span>
              </div>
              <span className={`font-medium ${(systemMetrics?.cpu_temp ?? 0) > 80 ? 'text-red-600' : 'text-emerald-600'}`}>
                {systemMetrics?.cpu_temp != null ? `${systemMetrics.cpu_temp}°C` : "N/A"}
              </span>
            </div>
            <Progress value={systemMetrics?.cpu_temp != null ? (systemMetrics.cpu_temp / 100) * 100 : 0} className="h-2" />
          </div>
          </>}
        </CardContent>
      </Card>

      {/* Environmental Sensors */}
      <Card className="rounded-2xl overflow-hidden relative">
        <CardHeader>
          <div className="flex items-start sm:items-center justify-between flex-col sm:flex-row gap-4 sm:gap-2">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Thermometer className="w-5 h-5" /> AI Prediction Environmental Sensors
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">IoT sensor suite for random forest regression input</p>
            </div>
            <Badge
              variant="outline"
              className={`text-xs px-2.5 py-0.5 rounded-full font-semibold shrink-0 ${
                sensorConnected
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-red-50 text-red-600 border-red-200"
              }`}
            >
              {sensorConnected ? <Wifi className="w-3.5 h-3.5 mr-1.5" /> : <WifiOff className="w-3.5 h-3.5 mr-1.5" />}
              {sensorConnected === null ? "Status unknown" : sensorConnected ? (sensorData ? "Live" : "No readings") : "Offline"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 relative">
          {sensorError && <div role="alert" className="flex items-center gap-3 text-sm text-destructive">{sensorError}<Button variant="outline" size="sm" disabled={sensorLoading} onClick={() => setSensorRetry(value => value + 1)}>Retry sensor readings</Button></div>}
          {sensorConnected === false && (
            <div className="flex items-center gap-3 px-4 py-3 bg-red-50/50 border border-red-100/50 rounded-xl">
              <div className="w-8 h-8 shrink-0 rounded-full bg-red-100 flex items-center justify-center text-red-600">
                <WifiOff className="w-4 h-4" />
              </div>
              <div className="text-left">
                <p className="text-sm font-semibold text-red-900 leading-none mb-1">Sensor Disconnected</p>
                <p className="text-xs text-red-700/80 leading-tight">{sensorData ? "Showing last recorded historical data." : "No recorded sensor readings available."}</p>
              </div>
            </div>
          )}
          {sensorLoading && !sensorData && <p role="status" className="text-sm text-muted-foreground">Loading sensor readings…</p>}
          {!sensorLoading && !sensorData && <p className="text-sm text-muted-foreground">No sensor readings available.</p>}
          <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 ${!sensorConnected ? 'opacity-70 grayscale-[30%]' : ''}`}>
            <div className="flex items-center gap-3 p-4 rounded-xl bg-muted/50 border border-border">
              <div className="h-10 w-10 rounded-full bg-orange-100 flex items-center justify-center text-orange-600">
                <Thermometer className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Ambient Temperature</p>
                <div className="flex items-baseline gap-2">
                  <p className="text-2xl font-bold">{sensorData ? sensorData.temperature.toFixed(1) : "—"}<span className="text-base font-medium text-muted-foreground">°C</span></p>

                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-xl bg-muted/50 border border-border">
              <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600">
                <Droplets className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Ambient Humidity</p>
                <div className="flex items-baseline gap-2">
                  <p className="text-2xl font-bold">{sensorData ? sensorData.humidity.toFixed(1) : "—"}<span className="text-base font-medium text-muted-foreground">%</span></p>

                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
