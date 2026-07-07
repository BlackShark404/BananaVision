import { useApp } from "@/context/AppContext"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Monitor, Camera, Wifi, WifiOff, Cpu, HardDrive, Clock, MemoryStick, Thermometer, Activity, RefreshCw, Droplets } from "lucide-react"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { useWebSocket } from "@/hooks/useWebSocket"
export default function DeviceStatus() {
  const { devices } = useApp()
  const online = devices.filter((d) => d.status === "Online").length
  const total = devices.length
  const [lastUpdate, setLastUpdate] = useState(new Date())

  const [sensorData, setSensorData] = useState({ temperature: 0, humidity: 0 })

  // Listen for live sensor readings via WebSocket
  useWebSocket({
    rooms: ["sensor_readings"],
    onEvent: (event, data) => {
      if (event === "sensor_update") {
        setSensorData({
          temperature: data.temperature,
          humidity: data.humidity
        })
      }
    }
  })

  // Fetch initial sensor data on mount
  useEffect(() => {
    api.sensors.latest().then((res) => {
      if (res) {
        setSensorData({
          temperature: res.temperature,
          humidity: res.humidity
        })
      }
    }).catch(console.error)
  }, [])

  // Simulate fetching system metrics every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      // In production: fetch('/api/system/metrics')
      setLastUpdate(new Date())
    }, 5000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
          <Monitor className="w-7 h-7" /> Device Status
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          {online} of {total} cameras online · IoT Sensors Active
        </p>
      </div>

      {/* Camera Cards */}
      {devices.length === 0 ? (
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
                <p className="text-sm font-medium">AMD Ryzen 5 5600G</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50">
              <HardDrive className="w-5 h-5 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Storage</p>
                <p className="text-sm font-medium">256 GB / 512 GB</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50">
              <Clock className="w-5 h-5 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Uptime</p>
                <p className="text-sm font-medium">12h 34m</p>
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
              <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ animationDuration: '3s' }} />
              <span>Updated {lastUpdate.toLocaleTimeString()}</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-blue-600" />
                <span className="font-medium">CPU Usage</span>
              </div>
              <span className="text-muted-foreground">45%</span>
            </div>
            <Progress value={45} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <MemoryStick className="w-4 h-4 text-purple-600" />
                <span className="font-medium">Memory Usage</span>
              </div>
              <span className="text-muted-foreground">8.2 GB / 16 GB (51%)</span>
            </div>
            <Progress value={51} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-emerald-600" />
                <span className="font-medium">Disk Usage</span>
              </div>
              <span className="text-muted-foreground">256 GB / 512 GB (50%)</span>
            </div>
            <Progress value={50} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Thermometer className="w-4 h-4 text-orange-600" />
                <span className="font-medium">CPU Temperature</span>
              </div>
              <span className="font-medium text-emerald-600">
                58°C
              </span>
            </div>
            <Progress value={(58 / 100) * 100} className="h-2" />
          </div>
        </CardContent>
      </Card>

      {/* Environmental Sensors */}
      <Card className="rounded-2xl">
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Thermometer className="w-5 h-5" /> AI Prediction Environmental Sensors
          </CardTitle>
          <p className="text-sm text-muted-foreground mt-1">IoT sensor suite for random forest regression input</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-center gap-3 p-4 rounded-xl bg-muted/50 border border-border">
              <div className="h-10 w-10 rounded-full bg-orange-100 flex items-center justify-center text-orange-600">
                <Thermometer className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Ambient Temperature</p>
                <div className="flex items-baseline gap-2">
                  <p className="text-2xl font-bold">{sensorData.temperature.toFixed(1)}<span className="text-base font-medium text-muted-foreground">°C</span></p>
                  <span className="text-[10px] text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded-full">Optimal</span>
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
                  <p className="text-2xl font-bold">{sensorData.humidity.toFixed(1)}<span className="text-base font-medium text-muted-foreground">%</span></p>
                  <span className="text-[10px] text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded-full">Optimal</span>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
