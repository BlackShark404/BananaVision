import { useState, useMemo, useRef, useEffect } from "react"
import { useAuth } from "@/context/AuthContext"
import { api } from "@/lib/api"
import { useAdmin } from "@/context/AdminContext"
import { useTheme } from "@/components/theme-provider"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { AppStatsCard } from "@/components/AppStatsCard"
import { Switch } from "@/components/ui/switch"
import { AppPageHeader } from "@/components/AppPageHeader"
import { Separator } from "@/components/ui/separator"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp"
import { Loader2, User, Shield, Calendar, Activity, TrendingUp, Target, Moon, Sun, Eye, EyeOff, Camera } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "sonner"

export default function Profile() {
  const { user, changePassword, changePin } = useAuth()
  const { updateOwnProfile } = useAdmin()
  const { theme, setTheme } = useTheme()
  const [isEditingPassword, setIsEditingPassword] = useState(false)
  const [isEditingPin, setIsEditingPin] = useState(false)
  const [passwordData, setPasswordData] = useState({ current: "", new: "", confirm: "" })
  const [showPasswords, setShowPasswords] = useState({ current: false, new: false, confirm: false })
  const [pinStep, setPinStep] = useState<"current" | "new" | "confirm">("current")
  const [pinData, setPinData] = useState({ current: "", new: "", confirm: "" })
  const fileInputRef = useRef<HTMLInputElement>(null)
  const credentialFlight = useRef(false)
  const [savingCredential, setSavingCredential] = useState(false)
  const [savingAvatar, setSavingAvatar] = useState(false)

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file || !user || savingAvatar) return

    if (file.size > 2 * 1024 * 1024) {
      toast.error("Image size must be less than 2MB")
      return
    }

    setSavingAvatar(true)
    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("Could not read image"))
        reader.onerror = () => reject(new Error("Could not read image"))
        reader.readAsDataURL(file)
      })
      await updateOwnProfile({ avatar: base64 })
      toast.success("Avatar updated successfully")
    } catch (error) {
      toast.error("Could not update avatar", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSavingAvatar(false)
    }
  }

  const handleRemoveAvatar = async () => {
    if (!user || savingAvatar) return
    setSavingAvatar(true)
    try {
      await updateOwnProfile({ avatar: "" })
      toast.success("Avatar removed successfully")
    } catch (error) {
      toast.error("Could not remove avatar", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      setSavingAvatar(false)
    }
  }

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark")
    toast.success(`Switched to ${theme === "dark" ? "light" : "dark"} mode`)
  }

  const [summary, setSummary] = useState<Awaited<ReturnType<typeof api.users.summary>> | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    setSummary(null)
    setSummaryError(false)
    if (user) {
      api.users.summary(controller.signal).then(data => {
        if (!controller.signal.aborted) setSummary(data)
      }).catch(() => {
        if (!controller.signal.aborted) setSummaryError(true)
      })
    }
    return () => controller.abort()
  }, [user])

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
      case "scan_rejected":
        return "Scan rejected: no supported banana detected"
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

  const recentActivityFeed = useMemo(() => {
    const userActivity = summary?.activity ?? []
    if (userActivity.length > 0) {
      return userActivity.slice(0, 8).map((activity) => ({
        id: activity.id,
        details: formatActivityLabel(activity.action, activity.details),
        timestamp: activity.timestamp,
      }))
    }
    return []
  }, [summary])

  const stats = {
    totalScans: summary?.total_scans ?? "—",
    avgConfidence: summary?.avg_confidence?.toFixed(1) ?? null,
    totalUsers: summary?.total_users ?? "—",
    last7Days: summary?.last_7_days ?? "—",
  }

  const handlePasswordChange = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (credentialFlight.current) return
    if (passwordData.new !== passwordData.confirm) {
      toast.error("Passwords don't match")
      return
    }
    if (passwordData.new.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }
    if (!passwordData.current) {
      toast.error("Please enter your current password")
      return
    }
    
    if (user) {
      credentialFlight.current = true; setSavingCredential(true)
      try {
        const success = await changePassword(passwordData.current, passwordData.new)
        if (success) {
          toast.success("Password changed successfully")
          setPasswordData({ current: "", new: "", confirm: "" })
          setIsEditingPassword(false)
        } else {
          toast.error("Failed to change password. Please check your current password.")
        }
      } catch {
        toast.error("An error occurred while changing password.")
      } finally { credentialFlight.current = false; setSavingCredential(false) }
    }
  }

  const handlePinOtpChange = async (val: string) => {
    if (credentialFlight.current) return
    if (pinStep === "current") {
      setPinData(prev => ({ ...prev, current: val }))
      if (val.length === 4) {
        if (!user) return
        // Current PIN will be verified server-side when we submit the change
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
          credentialFlight.current = true; setSavingCredential(true)
          try {
            const success = await changePin(pinData.current, val)
            if (success) {
              toast.success("Kiosk PIN changed successfully")
              setPinData({ current: "", new: "", confirm: "" })
              setPinStep("current")
              setIsEditingPin(false)
            } else {
              toast.error("Failed to change Kiosk PIN. Please check your current PIN.")
              setPinData({ current: "", new: "", confirm: "" })
              setPinStep("current")
            }
          } catch {
            toast.error("Current PIN is incorrect")
            setPinData({ current: "", new: "", confirm: "" })
            setPinStep("current")
          } finally { credentialFlight.current = false; setSavingCredential(false) }
        }
      }
    }
  }

  const resetPinDialog = () => {
    if (credentialFlight.current) return
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

      {summaryError && <p role="alert" className="text-sm text-destructive">Profile statistics and activity could not be loaded. Reload to retry.</p>}
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <AppStatsCard
          loading={!summary && !summaryError}
          title={user.role === "Admin" ? "System Scans" : "Total Scans"}
          value={stats.totalScans}
          icon={Activity}
          delay={50}
          description={user.role === "Admin" ? "All retained platform scans" : "All your retained scans"}
        />
        {user.role === "Admin" ? (
          <AppStatsCard
          loading={!summary && !summaryError}
            title="Total Users"
            value={stats.totalUsers || 0}
            icon={User}
            iconColor="text-blue-600"
            iconBgColor="bg-blue-500/10"
            delay={100}
            description="Registered accounts"
          />
        ) : (
          <AppStatsCard
          loading={!summary && !summaryError}
            title="Last 7 Days"
            value={stats.last7Days || 0}
            icon={TrendingUp}
            iconColor="text-blue-600"
            iconBgColor="bg-blue-500/10"
            delay={100}
            description="Recent activity"
          />
        )}
        <AppStatsCard
          loading={!summary && !summaryError}
          title={user.role === "Admin" ? "System Avg Confidence" : "Avg Confidence"}
          value={stats.avgConfidence === null ? "—" : `${stats.avgConfidence}%`}
          icon={Target}
          iconColor="text-emerald-600"
          iconBgColor="bg-emerald-500/10"
          delay={150}
          description={user.role === "Admin" ? "Average platform model confidence" : "Average model confidence on your scans"}
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
                  aria-busy={savingAvatar}
                  onClick={() => !savingAvatar && fileInputRef.current?.click()}
                  title="Upload new avatar"
                >
                  <Avatar className="w-20 h-20 sm:w-24 sm:h-24 border-[3px] border-background ring-1 ring-border shadow-sm transition-all group-hover:ring-primary/50 group-hover:shadow-md">
                    <AvatarImage src={user.avatar || undefined} className="object-cover" />
                    <AvatarFallback className="text-2xl sm:text-3xl bg-primary/10 text-primary font-bold">
                      {user.fullName.split(' ').map(n => n[0]).join('').toUpperCase()}
                    </AvatarFallback>
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
                    disabled={savingAvatar}
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-xl sm:text-2xl font-bold tracking-tight">{user.fullName}</h3>
                      <p className="text-sm sm:text-base text-muted-foreground font-medium">@{user.username}</p>
                    </div>
                    {user.avatar && (
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        onClick={handleRemoveAvatar} 
                        disabled={savingAvatar}
                        className="text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/50"
                      >
                        Remove Photo
                      </Button>
                    )}
                  </div>
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
          <Dialog open={isEditingPassword} onOpenChange={open => { if (!savingCredential) setIsEditingPassword(open) }}>
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
                  <Button type="button" variant="outline" disabled={savingCredential} onClick={() => setIsEditingPassword(false)} className="flex-1">
                    Cancel
                  </Button>
                  <Button type="submit" className="flex-1" disabled={savingCredential}>
                    {savingCredential && <Loader2 className="w-4 h-4 animate-spin mr-2" aria-hidden="true" />}
                    {savingCredential ? "Updating…" : "Update Password"}
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
                      disabled={savingCredential}
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

                  {savingCredential && <p role="status" className="flex items-center justify-center gap-2 text-sm"><Loader2 className="w-4 h-4 animate-spin" />Updating PIN…</p>}
                  <Button disabled={savingCredential} variant="ghost" className="w-full text-muted-foreground h-10" onClick={resetPinDialog}>
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
                {!summary && !summaryError && <div role="status" aria-label="Loading recent activity" className="space-y-3">{[0, 1, 2].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>}
                {summary && recentActivityFeed.length === 0 && (
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
