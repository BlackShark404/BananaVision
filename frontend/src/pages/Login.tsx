import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Eye, EyeOff } from "lucide-react"
import { toast } from "sonner"

export default function Login() {
  const inFlight = useRef(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [passwordChangePrompt, setPasswordChangePrompt] = useState(
    "Welcome back! Please set a new secure password to continue."
  )

  const { login, setupPasswordAndLogin } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (inFlight.current) return
    inFlight.current = true
    try {

      if (isChangingPassword) {
        if (newPassword !== confirmPassword) {
          toast.error("Passwords do not match", { description: "Please ensure both password fields match." })
          return
        }
        if (newPassword.length < 6) {
          toast.error("Password too weak", { description: "Password must be at least 6 characters long." })
          return
        }
        setLoading(true)
        const ok = await setupPasswordAndLogin(username, newPassword)
        if (ok) {
          toast.success("Welcome back!", { description: "Your password was updated successfully." })
          navigate("/dashboard")
        } else {
          toast.error("Failed to update password")
        }
        setLoading(false)
        return
      }

      setLoading(true)
      const result = await login(username, password)
      if (result === "requires_password_change" || result === "requires_password_change_new_account" || result === "requires_password_change_reset") {
        if (result === "requires_password_change_new_account") {
          setPasswordChangePrompt("Welcome! Your account was newly created. Please set a new secure password to continue.")
        } else if (result === "requires_password_change_reset") {
          setPasswordChangePrompt("Welcome back! Because your password was recently reset, please set a new secure password to continue.")
        } else {
          setPasswordChangePrompt("Welcome back! Please set a new secure password to continue.")
        }
        setIsChangingPassword(true)
        setLoading(false)
        return
      }
      if (result === "success") {
        toast.success("Welcome back!", { description: "Logged in successfully" })
        navigate("/dashboard")
      } else if (result === "inactive") {
        toast.error("Account Inactive", { description: "Your account is inactive. Please contact an administrator." })
      } else {
        toast.error("Login failed", { description: "Check your username and password, or contact an administrator." })
      }
      setLoading(false)
    } catch { toast.error("Sign in unavailable", { description: "Please try again." }) }
    finally { inFlight.current = false; setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-linear-to-br from-banana-light via-background to-background p-4">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-banana/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-32 -left-32 w-125 h-125 bg-banana/10 rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-md relative animate-fade-in shadow-xl border-border/50 rounded-2xl">
        <CardHeader className="text-center pb-2 pt-8">
          <div className="mx-auto mb-4 flex items-center justify-center animate-pulse-glow">
            <img src="/bananavision-logo.svg" alt="BananaVision Logo" className="w-20 h-20 object-contain drop-shadow-md" />
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight">BananaVision</CardTitle>
          <CardDescription className="text-muted-foreground">
            AI-Powered Banana Classification System
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-2 pb-8 px-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            {!isChangingPassword ? (
              <div className="space-y-5 animate-fade-in">
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-sm font-medium">Username</Label>
                  <Input
                    id="username"
                    placeholder="Enter your username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="h-11 rounded-xl"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="h-11 rounded-xl pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-1 top-1.5 h-8 w-8 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4 transition-none" /> : <Eye className="w-4 h-4 transition-none" />}
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-5 animate-fade-in transition-all duration-300">
                <div className="bg-primary/5 border border-primary/20 p-3 rounded-xl mb-2">
                  <p className="text-sm text-primary font-medium text-center">
                    {passwordChangePrompt}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="newPassword" className="text-sm font-medium">New Password</Label>
                  <div className="relative">
                    <Input
                      id="newPassword"
                      type={showPassword ? "text" : "password"}
                      placeholder="Enter new password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      className="h-11 rounded-xl pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-1 top-1.5 h-8 w-8 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4 transition-none" /> : <Eye className="w-4 h-4 transition-none" />}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirmPassword" className="text-sm font-medium">Confirm Password</Label>
                  <div className="relative">
                    <Input
                      id="confirmPassword"
                      type={showPassword ? "text" : "password"}
                      placeholder="Confirm new password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      className="h-11 rounded-xl pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-1 top-1.5 h-8 w-8 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4 transition-none" /> : <Eye className="w-4 h-4 transition-none" />}
                    </Button>
                  </div>
                </div>
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-11 text-[15px] font-semibold shadow-md"
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 border-2 border-primary-foreground/40 border-r-primary-foreground rounded-full animate-spin" />
                  {isChangingPassword ? "Updating..." : "Signing in..."}
                </span>
              ) : (
                isChangingPassword ? "Save & Continue to Dashboard" : "Login"
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
