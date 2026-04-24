import { useState, useMemo, useRef } from "react"
import { useApp } from "@/context/AppContext"
import { useTheme } from "@/components/theme-provider"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { StatsCard } from "@/components/shared/stats-card"
import { Switch } from "@/components/ui/switch"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Separator } from "@/components/ui/separator"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp"
import { User, Shield, Calendar, Activity, TrendingUp, Target, Moon, Sun, Eye, EyeOff, Camera } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { toast } from "sonner"

export default function Profile() {
  const { user, scans, activityLogs, updateUser, users } = useApp()
  const { theme, setTheme } = useTheme()
  const [isEditingPassword, setIsEditingPassword] = useState(false)
  const [isEditingPin, setIsEditingPin] = useState(false)
  const [passwordData, setPasswordData] = useState({ current: "", new: "", confirm: "" })
  const [showPasswords, setShowPasswords] = useState({ current: false, new: false, confirm: false })
  const [pinStep, setPinStep] = useState<"current" | "new" | "confirm">("current")
  const [pinData, setPinData] = useState({ current: "", new: "", confirm: "" })
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > 2 * 1024 * 1024) {
      toast.error("Image size must be less than 2MB")
      return
    }

    const reader = new FileReader()
    reader.onload = (event) => {
      const base64 = event.target?.result as string
      if (user) {
        updateUser(user.id, { avatar: base64 })
        toast.success("Avatar updated successfully")
      }
    }
    reader.readAsDataURL(file)
  }

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark")
    toast.success(`Switched to ${theme === "dark" ? "light" : "dark"} mode`)
  }

  const userScans = useMemo(() => scans.filter(s => s.operator === user?.fullName), [scans, user])
  const userActivity = useMemo(() => activityLogs.filter(log => log.user === user?.fullName), [activityLogs, user])

  const formatActivityLabel = (action: string, details: string) => {
    switch (action) {
      case "login":
        return "Signed in to the web dashboard"
      case "logout":
        return "Signed out from the session"
      case "scan_created":
        return "Captured a new banana scan in Kiosk"
      case "scan_edited":
        return "Updated scan data in Quality Control"
      case "scan_flagged":
        return "Flagged a scan for manual review"
      case "intake_created":
        return "Recorded a new delivery intake"
      case "intake_status_changed":
        return "Updated intake status in Intake Management"
      case "config_changed":
        return "Adjusted system configuration settings"
      default:
        return details
    }
  }

  const operatorMockActivity = useMemo(() => {
    if (user?.role !== "Operator") return []

    // Use current date but kept outside loop for consistency
    const now = new Date().getTime()
    const latestScans = userScans.slice(0, 3)

    const scanEntries = latestScans.map((scan, index) => ({
      id: `mock-scan-${scan.id}`,
      details: `Completed kiosk scan: ${scan.cultivar} (${scan.ripeness}) at ${scan.confidence.toFixed(1)}% confidence`,
      timestamp: new Date(now - (index + 1) * 45 * 60 * 1000).toISOString(),
    }))

    return [
      ...scanEntries,
      {
        id: "mock-logs-status",
        details: "Updated inventory status from the Logs module",
        timestamp: new Date(now - 3 * 60 * 60 * 1000).toISOString(),
      },
      {
        id: "mock-analytics",
        details: "Reviewed personal performance in Analytics",
        timestamp: new Date(now - 5 * 60 * 60 * 1000).toISOString(),
      },
      {
        id: "mock-profile-security",
        details: "Opened Profile security settings for PIN/password",
        timestamp: new Date(now - 8 * 60 * 60 * 1000).toISOString(),
      },
    ]
  }, [user?.role, userScans])

  const recentActivityFeed = useMemo(() => {
    if (userActivity.length > 0) {
      return userActivity.slice(0, 8).map((activity) => ({
        id: activity.id,
        details: formatActivityLabel(activity.action, activity.details),
        timestamp: activity.timestamp,
      }))
    }

    if (user?.role === "Operator") {
      return operatorMockActivity.slice(0, 8)
    }

    return []
  }, [userActivity, user?.role, operatorMockActivity])

  const isUsingOperatorMockActivity = user?.role === "Operator" && userActivity.length === 0

  const stats = useMemo(() => {
    if (user?.role === "Admin") {
      const avgConfidence = scans.length
        ? (scans.reduce((sum, s) => sum + s.confidence, 0) / scans.length).toFixed(1)
        : 0
      return { 
        totalScans: scans.length,
        avgConfidence,
        totalUsers: users.length
      }
    } else {
      const avgConfidence = userScans.length
        ? (userScans.reduce((sum, s) => sum + s.confidence, 0) / userScans.length).toFixed(1)
        : 0
      const currentTime = new Date().getTime()
      const last7Days = userScans.filter(s => {
        const scanTime = new Date(s.dateTime).getTime()
        return currentTime - scanTime < 7 * 24 * 60 * 60 * 1000
      }).length

      return { avgConfidence, last7Days, totalScans: userScans.length }
    }
  }, [userScans, scans, user, users])

  const handlePasswordChange = (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (passwordData.new !== passwordData.confirm) {
      toast.error("Passwords don't match")
      return
    }
    if (passwordData.new.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }
    // In production: API call to change password
    toast.success("Password changed successfully")
    setPasswordData({ current: "", new: "", confirm: "" })
    setIsEditingPassword(false)
  }

  const handlePinOtpChange = (val: string) => {
    if (pinStep === "current") {
      setPinData(prev => ({ ...prev, current: val }))
      if (val.length === 4) {
        const fullUser = users.find(u => u.id === user?.id)
        if (fullUser && fullUser.pin && fullUser.pin !== val) {
          toast.error("Current PIN is incorrect")
          setPinData(prev => ({ ...prev, current: "" }))
          return
        }
        setPinStep("new")
      }
    } else if (pinStep === "new") {
      setPinData(prev => ({ ...prev, new: val }))
      if (val.length === 4) {
        setPinStep("confirm")
      }
    } else {
      setPinData(prev => ({ ...prev, confirm: val }))
      if (val.length === 4) {
        if (pinData.new !== val) {
          toast.error("PINs don't match. Try again.")
          setPinData(prev => ({ ...prev, new: "", confirm: "" }))
          setPinStep("new")
          return
        }
        if (user) {
          updateUser(user.id, { pin: val })
          toast.success("Kiosk PIN changed successfully")
          setPinData({ current: "", new: "", confirm: "" })
          setPinStep("current")
          setIsEditingPin(false)
        }
      }
    }
  }

  const resetPinDialog = () => {
    setPinData({ current: "", new: "", confirm: "" })
    setPinStep("current")
    setIsEditingPin(false)
  }

  if (!user) return null

  return (
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="My Profile"
        description="Manage your account and view your activity"
        icon={User}
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatsCard
          title={user.role === "Admin" ? "System Scans" : "Total Scans"}
          value={stats.totalScans}
          icon={Activity}
          delay={50}
          description={user.role === "Admin" ? "Platform lifetime scans" : "Your lifetime scans"}
          trend={{ value: 12, isPositive: true }}
        />
        {user.role === "Admin" ? (
          <StatsCard
            title="Total Users"
            value={stats.totalUsers || 0}
            icon={User}
            iconColor="text-blue-600"
            iconBgColor="bg-blue-500/10"
            delay={100}
            description="Registered accounts"
            trend={{ value: 2, isPositive: true }}
          />
        ) : (
          <StatsCard
            title="Last 7 Days"
            value={stats.last7Days || 0}
            icon={TrendingUp}
            iconColor="text-blue-600"
            iconBgColor="bg-blue-500/10"
            delay={100}
            description="Recent activity"
            trend={{ value: 8, isPositive: true }}
          />
        )}
        <StatsCard
          title={user.role === "Admin" ? "System Avg Confidence" : "Avg Confidence"}
          value={`${stats.avgConfidence}%`}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={150}
          description={user.role === "Admin" ? "Platform detection accuracy" : "Personal detection accuracy"}
          trend={{ value: 3, isPositive: true }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        {/* Profile Info */}
        <div className="lg:col-span-2 space-y-4 sm:space-y-6">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6 border-b bg-muted/20">
              <CardTitle className="text-base sm:text-lg">Personal Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6 p-4 sm:p-6">
              <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
                <div 
                  className="relative group cursor-pointer inline-block rounded-full" 
                  onClick={() => fileInputRef.current?.click()}
                  title="Upload new avatar"
                >
                  <Avatar className="w-20 h-20 sm:w-24 sm:h-24 border-[3px] border-background ring-1 ring-border shadow-sm transition-all group-hover:ring-primary/50 group-hover:shadow-md">
                    {user.avatar ? (
                      <AvatarImage src={user.avatar} className="object-cover" />
                    ) : (
                      <AvatarFallback className="text-2xl sm:text-3xl bg-primary/10 text-primary font-bold">
                        {user.fullName.split(' ').map(n => n[0]).join('').toUpperCase()}
                      </AvatarFallback>
                    )}
                  </Avatar>
                  <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Camera className="w-6 h-6 text-white" />
                  </div>
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept="image/*"
                    onChange={handleAvatarUpload}
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <h3 className="text-xl sm:text-2xl font-bold tracking-tight">{user.fullName}</h3>
                  <p className="text-sm sm:text-base text-muted-foreground font-medium">@{user.username}</p>
                  <div className="pt-2">
                    <Badge variant="outline" className={`gap-1.5 font-medium ${user.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : "bg-secondary text-secondary-foreground"}`}>
                      <Shield className="w-3 h-3" />
                      {user.role} Account
                    </Badge>
                  </div>
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
                <div className="space-y-2">
                  <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Full Name</Label>
                  <Input value={user.fullName} disabled className="bg-muted/50 font-medium" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Username</Label>
                  <Input value={user.username} disabled className="bg-muted/50 font-medium" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Preferences */}
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6 border-b bg-muted/20">
              <CardTitle className="text-base sm:text-lg">Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 p-4 sm:p-6">
              <div className="flex items-center justify-between p-4 rounded-xl border bg-card transition-colors hover:bg-muted/50">
                <div className="flex items-center gap-4">
                  <div className="p-2 rounded-lg bg-primary/10 text-primary">
                    {theme === "dark" ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">Theme Appearance</p>
                    <p className="text-xs text-muted-foreground">{theme === "dark" ? "Dark Mode is enabled" : "Light Mode is enabled"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <kbd className="hidden sm:inline-flex pointer-events-none h-5 select-none items-center gap-1 rounded border bg-background px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100 shadow-sm">
                    D
                  </kbd>
                  <Switch 
                    checked={theme === "dark"} 
                    onCheckedChange={() => toggleTheme()} 
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Security & Authentication */}
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6 pb-6 border-b bg-muted/20">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <CardTitle className="text-base sm:text-lg">Security & Authentication</CardTitle>
                  <p className="text-xs sm:text-sm text-muted-foreground">Manage your credentials and system access permissions</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6 flex flex-col sm:flex-row gap-3">
               {user.role !== "Admin" && (
                <Button variant="outline" className="flex-1" onClick={() => setIsEditingPin(true)}>
                  Change Kiosk PIN
                </Button>
              )}
              <Button variant="default" className="flex-1" onClick={() => setIsEditingPassword(true)}>
                Update Password
              </Button>
            </CardContent>
          </Card>

          {/* Change Password Dialog */}
          <Dialog open={isEditingPassword} onOpenChange={setIsEditingPassword}>
            <DialogContent className="sm:max-w-md rounded-2xl">
              <DialogHeader>
                <DialogTitle>Change Password</DialogTitle>
              </DialogHeader>
              <form onSubmit={handlePasswordChange} className="space-y-4 pt-4">
                <div className="space-y-2">
                  <Label htmlFor="current">Current Password</Label>
                  <div className="relative">
                    <Input
                      id="current"
                      type={showPasswords.current ? "text" : "password"}
                      value={passwordData.current}
                      onChange={(e) => setPasswordData({ ...passwordData, current: e.target.value })}
                      required
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords({ ...showPasswords, current: !showPasswords.current })}
                      className="absolute right-3 top-1.5 text-muted-foreground hover:text-foreground transition-none"
                      tabIndex={-1}
                    >
                      {showPasswords.current ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new">New Password</Label>
                  <div className="relative">
                    <Input
                      id="new"
                      type={showPasswords.new ? "text" : "password"}
                      value={passwordData.new}
                      onChange={(e) => setPasswordData({ ...passwordData, new: e.target.value })}
                      required
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords({ ...showPasswords, new: !showPasswords.new })}
                      className="absolute right-3 top-1.5 text-muted-foreground hover:text-foreground transition-none"
                      tabIndex={-1}
                    >
                      {showPasswords.new ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm">Confirm New Password</Label>
                  <div className="relative">
                    <Input
                      id="confirm"
                      type={showPasswords.confirm ? "text" : "password"}
                      value={passwordData.confirm}
                      onChange={(e) => setPasswordData({ ...passwordData, confirm: e.target.value })}
                      required
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })}
                      className="absolute right-3 top-1.5 text-muted-foreground hover:text-foreground transition-none"
                      tabIndex={-1}
                    >
                      {showPasswords.confirm ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                <div className="flex gap-2 pt-2">
                  <Button type="button" variant="outline" onClick={() => setIsEditingPassword(false)} className="flex-1">
                    Cancel
                  </Button>
                  <Button type="submit" className="flex-1">
                    Update Password
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>

          {/* Change PIN Dialog - only for operators */}
          {user.role !== "Admin" && (
            <Dialog open={isEditingPin} onOpenChange={(open) => { if (!open) resetPinDialog() }}>
              <DialogContent className="sm:max-w-md rounded-2xl">
                <DialogHeader>
                  <DialogTitle>Change Kiosk PIN</DialogTitle>
                </DialogHeader>
                <div className="space-y-5 pt-4">
                  {/* Step Indicators */}
                  <div className="flex items-center justify-center gap-2">
                    {(["current", "new", "confirm"] as const).map((step, i) => (
                      <div key={step} className="flex items-center gap-2">
                        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                          pinStep === step
                            ? "bg-primary text-primary-foreground"
                            : (pinStep === "new" && step === "current") || (pinStep === "confirm" && step !== "confirm")
                              ? "bg-emerald-500 text-white"
                              : "bg-muted text-muted-foreground"
                        }`}>
                          {(pinStep === "new" && step === "current") || (pinStep === "confirm" && step !== "confirm") ? "✓" : i + 1}
                        </div>
                        {i < 2 && <div className={`w-8 h-0.5 rounded-full ${
                          (pinStep === "new" && i === 0) || (pinStep === "confirm") ? "bg-emerald-500" : "bg-muted"
                        }`} />}
                      </div>
                    ))}
                  </div>

                  <p className="text-center text-sm font-semibold text-muted-foreground">
                    {pinStep === "current" ? "Enter Current PIN" : pinStep === "new" ? "Enter New PIN" : "Confirm New PIN"}
                  </p>

                  <div className="flex justify-center py-2">
                    <InputOTP
                      maxLength={4}
                      value={pinStep === "current" ? pinData.current : pinStep === "new" ? pinData.new : pinData.confirm}
                      onChange={handlePinOtpChange}
                      autoFocus
                    >
                      <InputOTPGroup className="gap-2">
                        <InputOTPSlot index={0} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                        <InputOTPSlot index={1} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                        <InputOTPSlot index={2} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                        <InputOTPSlot index={3} className="w-12 h-14 text-2xl rounded-lg border-y border-x" />
                      </InputOTPGroup>
                    </InputOTP>
                  </div>

                  <Button variant="ghost" className="w-full text-muted-foreground h-10" onClick={resetPinDialog}>
                    Cancel
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          )}
        </div>

        {/* Recent Activity */}
        <div className="space-y-4 sm:space-y-6">
          <Card className="rounded-xl sm:rounded-2xl sticky top-21">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                Recent Activity
              </CardTitle>
              {isUsingOperatorMockActivity && (
                <p className="text-xs text-muted-foreground">Showing operator mock activity data</p>
              )}
            </CardHeader>
            <CardContent className="px-4 sm:px-6 pb-4 sm:pb-6">
              <div className="space-y-3 max-h-[calc(100vh-200px)] overflow-y-auto">
                {recentActivityFeed.map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3 text-sm">
                    <div className="w-2 h-2 rounded-full bg-primary mt-2 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{activity.details}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(activity.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" })} at{" "}
                        {new Date(activity.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}
                {recentActivityFeed.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">No recent activity</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
