# `01_login_logout_flow.md` — Module 1: Login / Logout Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 1 (Login / Logout) |
| :--- | :--- |
| `frontend/src/App.tsx` | **SPA Router & Guards:** Lazy-loads `Login.tsx`, guards `/login` with `PublicRoute` (redirects authenticated users to `/dashboard`), and guards `/dashboard` and all staff routes with `ProtectedRoute` (redirects unauthenticated users to `/`). |
| `frontend/src/pages/Login.tsx` | **Login & First-Time Password Setup View:** Renders the Login Card UI, handles username/password state, password visibility toggle (`Eye`/`EyeOff`), double-submit prevention (`inFlight` ref), temporary-password forced setup flow (`isChangingPassword`), and Sonner toast feedback. |
| `frontend/src/context/AuthContext.tsx` | **Frontend Auth State Controller:** Implements `login()`, `setupPasswordAndLogin()`, and `logout()`, holding the in-memory `passwordSetup` ref (`{ username, token }`) and synchronizing React `user` state with `localStorage`. |
| `frontend/src/lib/auth.ts` | **Browser Storage Helper:** Manages `localStorage` keys `bananavision_token` (JWT) and `bananavision_user` (serialized `AuthUser`), and clears scan write/image caches on token change or logout. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `POST /api/v1/auth/login`, `POST /api/v1/auth/setup-password`, and `POST /api/v1/auth/logout`, attaches `Authorization: Bearer <token>`, and exempts `/api/v1/auth/login` from automatic 401 session-expiry redirects. |
| `frontend/src/components/AppSidebarFooter.tsx` | **Logout Trigger & Confirmation Modal:** Renders the signed-in user's avatar/role badge in the sidebar footer, opens a Popover with a `"Logout"` button, displays a Radix `AlertDialog` (`"Confirm Logout"`), and invokes `logout()` + `navigate("/")`. |
| `backend/app/api/v1/router.py` | **API v1 Router Aggregator:** Mounts `auth_router` under the `/api/v1` prefix (`/api/v1/auth/*`). |
| `backend/app/api/v1/auth.py` | **Backend Auth Controller:** Defines `POST /api/v1/auth/login`, `POST /api/v1/auth/setup-password`, and `POST /api/v1/auth/logout`; enforces `login_limiter` rate-limiting (`AUTH-04`), recovery-mode admin checks, and audit logging (`audit.emit`, `audit.record`, `audit.attach`). |
| `backend/app/schemas/auth.py` | **Pydantic Request/Response Contracts:** Validates `LoginRequest`, `SetupPasswordRequest`, and serializes `LoginResponse`, `TokenResponse`, and `AuthUser`. |
| `backend/app/core/rate_limiter.py` | **Brute-Force Rate Limiter (`AUTH-04`):** In-memory thread-safe sliding-window rate limiter (`MAX_ATTEMPTS = 5`, `WINDOW_SECONDS = 300`, `LOCKOUT_SECONDS = 300`) keyed by username. |
| `backend/app/services/auth_service.py` | **Core Authentication Business Logic:** Queries `UserAccount`, verifies bcrypt hashes, checks `ActiveStatusEnum.INACTIVE` and `requires_password_change`, updates `last_active = now_manila()`, issues 10-minute setup JWTs or full session JWTs, and locks rows (`SELECT ... FOR UPDATE`) on password setup and logout. |
| `backend/app/core/security.py` | **Cryptography & JWT Utility:** Wraps `bcrypt.hashpw` / `bcrypt.checkpw` and PyJWT `jwt.encode` / `jwt.decode` with `sub`, `username`, `role`, `tv` (`token_version`), `sg` (station generation), and `exp` claims. |
| `backend/app/api/deps.py` | **FastAPI Auth Dependency (`CurrentUser`):** Extracts `Authorization: Bearer <token>`, decodes the JWT, verifies `user.status == ActiveStatusEnum.ACTIVE`, and enforces `payload["tv"] == user.token_version` (`AUTH-02` session revocation check). |
| `backend/app/models/user_account.py` | **SQLAlchemy ORM Model (`user_account`):** Maps user credentials (`username`, `password_hash`, `status`, `requires_password_change`, `password_setup_reason`, `last_active`, `token_version`) and relationships (`role`, `operator_profile`). |
| `backend/app/models/activity_log.py` | **SQLAlchemy ORM Model (`activity_log`):** Stores audit rows for `login`, `login_failed`, `login_blocked`, `account_locked`, `login_denied`, `credential_setup_started`, `password_setup_completed`, and `logout`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A: Initial Page Load & UI/CSS Rendering

#### Step A1: Route Matching, Lazy Loading & `PublicRoute` Guard Interception
* **Step Title & Trigger:** Visitor clicks `"Login to System"` or `"Access Dashboard"` on the Landing Page (`navigate("/login")`) or visits `http://localhost:5173/login` directly.
* **Exact File Path & Line Numbers:** `frontend/src/App.tsx` (Lines 1–123)
* **Complete Uncut Code Block:**
```tsx
import React, { Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { useIsMobile } from "@/hooks/useIsMobile"
import { AuthProvider, useAuth } from "@/context/AuthContext"
import { AdminProvider } from "@/context/AdminContext"
import { ScanProvider } from "@/context/ScanContext"
import { InventoryProvider } from "@/context/InventoryContext"
import { ThemeProvider } from "@/components/theme-provider"

// Layouts and Core (Keep eager for fast initial load)
import AppLayout from "@/layouts/AppLayout"
import Landing from "@/pages/Landing"

// Lazy load feature pages
const Login = React.lazy(() => import("@/pages/Login"))
const Dashboard = React.lazy(() => import("@/pages/Dashboard"))
const Logs = React.lazy(() => import("@/pages/Logs"))
const Analytics = React.lazy(() => import("@/pages/Analytics"))
const DeviceStatus = React.lazy(() => import("@/pages/DeviceStatus"))
const Profile = React.lazy(() => import("@/pages/Profile"))
const Inventory = React.lazy(() => import("@/pages/Inventory"))
const ScanDetail = React.lazy(() => import("@/pages/ScanDetail"))
const PublicScanView = React.lazy(() => import("@/pages/PublicScanView"))
const Kiosk = React.lazy(() => import("@/pages/Kiosk"))

// Lazy load admin pages
const UserManagement = React.lazy(() => import("@/pages/admin/UserManagement"))
const SystemConfig = React.lazy(() => import("@/pages/admin/SystemConfig"))
const QualityControl = React.lazy(() => import("@/pages/admin/QualityControl"))
const ActivityLog = React.lazy(() => import("@/pages/admin/ActivityLog"))
const DeliveryIntake = React.lazy(() => import("@/pages/admin/DeliveryIntake"))
const SupplierManagement = React.lazy(() => import("@/pages/admin/SupplierManagement"))

// Loading fallback component
const PageLoader = () => (
  <div role="status" aria-label="Initializing page" className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
    <span className="sr-only">Initializing page…</span>
    <div aria-hidden="true" className="animate-spin motion-reduce:animate-none rounded-full h-8 w-8 border-b-2 border-primary"></div>
  </div>
)

// Protected Route Wrapper
function ProtectedRoute({ children, reqAdmin = false }: { children: React.ReactNode; reqAdmin?: boolean }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/" replace />
  if (reqAdmin && user.role !== "Admin") return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

// Public Route Wrapper
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (user) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function ResponsiveToaster() {
  const isMobile = useIsMobile()
  return <Toaster position={isMobile ? "bottom-center" : "top-center"} richColors />
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
        <Route path="/kiosk" element={<Kiosk />} />
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/devices" element={<DeviceStatus />} />
          <Route path="/scans/:scanId" element={<ScanDetail />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin/users" element={<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>} />
          <Route path="/admin/delivery-intakes" element={<ProtectedRoute reqAdmin><DeliveryIntake /></ProtectedRoute>} />
          <Route path="/admin/suppliers" element={<ProtectedRoute reqAdmin><SupplierManagement /></ProtectedRoute>} />

          <Route path="/admin/quality" element={<ProtectedRoute reqAdmin><QualityControl /></ProtectedRoute>} />
          <Route path="/admin/activity" element={<ProtectedRoute reqAdmin><ActivityLog /></ProtectedRoute>} />
          <Route path="/admin/config" element={<ProtectedRoute reqAdmin><SystemConfig /></ProtectedRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

function StaffApp() {
  return (
    <AdminProvider>
      <ScanProvider>
        <InventoryProvider>
          <AppRoutes />
          <ResponsiveToaster />
        </InventoryProvider>
      </ScanProvider>
    </AdminProvider>
  )
}

function App() {
  return (
    <ThemeProvider defaultTheme="light" storageKey="bananavision-theme">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* QR tracking page: public scan data only. It sits outside the staff data
                providers, so a phone holding a staff session never loads staff data, opens
                the staff socket or gets sent to /login from here. */}
            <Route path="/track/:scanId" element={<Suspense fallback={<PageLoader />}><PublicScanView /></Suspense>} />
            <Route path="*" element={<StaffApp />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Line 16:** `const Login = React.lazy(() => import("@/pages/Login"))` splits `Login.tsx` into a lazy-loaded bundle. While loading, `<Suspense fallback={<PageLoader />}>` (Line 65) displays the spinning primary border indicator defined on Lines 36–41.
  * **Lines 52–56 (`PublicRoute` Guest Guard):** Reads `const { user } = useAuth()`. If `user` is already present in `AuthContext`, the user cannot view `/login` and is redirected via `<Navigate to="/dashboard" replace />`.
  * **Line 68:** Matches `path="/login"` and renders `<PublicRoute><Login /></PublicRoute>`.
  * **Lines 58–61 (`ResponsiveToaster`):** Mounts the Sonner `<Toaster richColors />` at `"bottom-center"` on mobile or `"top-center"` on desktop, which renders all login success/error toast popups triggered by `Login.tsx`.

---

### Phase B: User Input & Client-Side Handling

#### Step B1: Login Form Rendering, CSS Styling, State & Submit Handler (`Login.tsx`)
* **Step Title & Trigger:** `<Login />` mounts when `user === null` on `/login`. The user types their `username` and `password` (or `newPassword` + `confirmPassword` during mandatory password setup) and submits `<form onSubmit={handleSubmit}>`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/Login.tsx` (Lines 1–216)
* **Complete Uncut Code Block:**
```tsx
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 12 & 29–30 (`inFlight` Concurrency Guard):** `inFlight = useRef(false)` prevents double-submitting if the user presses Enter twice rapidly before React re-renders `disabled={loading}`.
  * **Lines 82–93 (Layout & CSS Styling):**
    * Outer container uses `min-h-screen flex items-center justify-center bg-linear-to-br from-banana-light via-background to-background p-4` with two blurred decorative circles (`bg-banana/20` top-right and `bg-banana/10` bottom-left).
    * `<Card>` uses `w-full max-w-md relative animate-fade-in shadow-xl border-border/50 rounded-2xl`.
    * Logo wrapper on Line 91 applies `.animate-pulse-glow` (defined in `frontend/src/index.css` as a 2-second infinite golden OKLCH box-shadow pulse).
  * **Lines 101–138 (Standard Login Form Fields):** Rendered when `!isChangingPassword`. Both `<Input id="username">` and `<Input id="password">` have `required` HTML5 validation and `className="h-11 rounded-xl"`. The password field adds `pr-10` to make room for the absolute-positioned eye toggle button (`onClick={() => setShowPassword(!showPassword)}`), which switches `type` between `"password"` and `"text"`.
  * **Lines 54–55:** On form submit, sets `setLoading(true)` and awaits `login(username, password)` from `AuthContext`.
  * **Lines 56–67 (Forced Password Setup Transition):** If the user logged in with a temporary password (new account or admin reset), `login()` returns `"requires_password_change_new_account"`, `"requires_password_change_reset"`, or `"requires_password_change"`. `Login.tsx` sets the corresponding banner message in `passwordChangePrompt` (rendered inside `bg-primary/5 border border-primary/20 p-3 rounded-xl mb-2` on Lines 141–145) and flips `setIsChangingPassword(true)` to swap the form fields to `newPassword` and `confirmPassword`.
  * **Lines 33–52 (Client-Side Validation for Password Setup):** When `isChangingPassword === true`, checks `newPassword !== confirmPassword` (toast error `"Passwords do not match"`) and `newPassword.length < 6` (toast error `"Password too weak"`), then calls `setupPasswordAndLogin(username, newPassword)`.

---

#### Step B2: `AuthContext` Login & Setup-Password Dispatch + `api.ts` HTTP Request
* **Step Title & Trigger:** `Login.tsx` calls `login(username, password)` (or `setupPasswordAndLogin(username, newPassword)`), which invokes `api.auth.login` (or `api.auth.setupPassword`) in `frontend/src/lib/api.ts`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AuthContext.tsx` (Lines 45–86 & 152–170) and `frontend/src/lib/api.ts` (Lines 37–101 & 138–198)
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 45–86 & 152–170):**
```tsx
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())

  const passwordSetup = useRef<{ username: string; token: string } | null>(null)
  const pinSetup = useRef<{ username: string; token: string } | null>(null)

  // ── Login ───────────────────────────────────────────────────────────────

  const login = useCallback(async (username: string, password?: string) => {
    try {
      passwordSetup.current = null
      const res = await api.auth.login(username, password || "")

      // Check status for password change requirements
      if (res.status === "requires_password_change") {
        if (!res.setup_token) return "failed" as const
        passwordSetup.current = { username, token: res.setup_token }
        if (res.reason === "new_account") return "requires_password_change_new_account" as const
        if (res.reason === "password_reset") return "requires_password_change_reset" as const
        return "requires_password_change" as const
      }

      if (res.status === "inactive") {
        return "inactive" as const
      }

      if (res.status === "failed" || !res.token || !res.user) {
        return "failed" as const
      }

      // Save token and user
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch {
      return "failed" as const
    }
  }, [])
```
```tsx
  // ── First-time / Post-reset Password Setup ──────────────────────────────

  const setupPasswordAndLogin = useCallback(async (username: string, newPassword: string) => {
    if (!newPassword || passwordSetup.current?.username !== username) return false
    try {
      const res = await api.auth.setupPassword(passwordSetup.current.token, newPassword)
      passwordSetup.current = null
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch {
      return false
    }
  }, [])
```
* **Complete Uncut Code Block (`frontend/src/lib/api.ts`, Lines 37–101 & 138–198):**
```ts
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts?: RequestOptions
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (body instanceof FormData) delete headers["Content-Type"]
  if (body instanceof Blob) headers["Content-Type"] = "application/octet-stream"
  if (token) headers["Authorization"] = `Bearer ${token}`

  // Build query string
  let url = `${BASE_URL}${path}`
  if (opts?.params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(opts.params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    }
    const str = qs.toString()
    if (str) url += `?${str}`
  }

  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body instanceof FormData || body instanceof Blob ? body : body ? JSON.stringify(body) : undefined,
      signal: opts?.signal,
      cache: "no-store",
    })
  } catch (e) {
    // Network error (connection refused, DNS failure, etc.) — don't clear auth
    if (e instanceof DOMException && e.name === "AbortError") throw e
    throw Object.assign(new Error("Backend unavailable — please check the server and retry"), { status: 0 })
  }

  // Credential rejection must not expire an existing operator/admin session.
  const isCredentialSubmission = path === "/api/v1/auth/login" || path === "/api/v1/auth/swap"
  // Handle 401 — token expired / invalid on protected requests.
  if (res.status === 401 && !isCredentialSubmission) {
    clearAuth()
    window.location.href = "/login"
    throw new Error("Session expired")
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof err.detail === "string" ? err.detail : Array.isArray(err.detail)
      ? err.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ") : `API error ${res.status}`
    // Machine-readable outcome of a refused scan. Copied by name: the body also has a
    // text `status`, which must never replace the numeric HTTP status below.
    const code = typeof err.code === "string" ? err.code : undefined
    const reason = typeof err.reason === "string" ? err.reason : undefined
    throw Object.assign(new Error(detail), { status: res.status, code, reason })
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json()
}
```
```ts
export const api = {
  // ── Auth ─────────────────────────────────────────────────────────────────
  auth: {
    login: (username: string, password: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
        reason?: string | null
        setup_token?: string | null
      }>("/api/v1/auth/login", { username, password }),

    swap: (username: string, pin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
        reason?: string | null
        setup_token?: string | null
      }>("/api/v1/auth/swap", { username, pin }, "PIN verification timed out. Your current session has not changed."),

    /** Self-service password change — requires JWT auth + current password. */
    changePassword: (currentPassword: string, newPassword: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/change-password", { current_password: currentPassword, new_password: newPassword }),

    /** First-time / post-reset password setup — requires limited setup authorization issued at login. */
    setupPassword: (setupToken: string, newPassword: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/setup-password", { setup_token: setupToken, new_password: newPassword }),

    /** Self-service PIN change — requires JWT auth + current PIN. */
    changePin: (currentPin: string, newPin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/change-pin", { current_pin: currentPin, new_pin: newPin }),

    /** First-time / post-reset PIN setup — requires limited setup authorization issued at PIN swap. */
    setupPin: (setupToken: string, newPin: string) =>
      post<{
        status: string
        token: { access_token: string; token_type: string } | null
        user: { id: string; username: string; full_name: string; role: string; avatar_url?: string } | null
      }>("/api/v1/auth/setup-pin", { setup_token: setupToken, new_pin: newPin }, "PIN setup timed out; its result is unknown. Go back to operator selection and sign in with the new PIN to check whether it was saved."),

    logout: () => post<void>("/api/v1/auth/logout"),

    /** Public endpoint — no auth needed. Returns active operators for kiosk selection. */
    kioskOperators: () =>
      get<{ id: string; username: string; full_name: string; role: string; status: string; avatar_url?: string }[]>(
        "/api/v1/auth/operators"
      ),
  },
```
* **Line-by-Line Connection & Trace Explanation:**
  * **No CSRF Cookies Needed (Stateless Bearer JWT Architecture):** BananaVision authenticates via JSON payloads and `Authorization: Bearer <token>` headers rather than browser session cookies, eliminating cookie-based CSRF vulnerabilities.
  * **`api.ts` Lines 64–70:** Sends `fetch("${BASE_URL}/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }), cache: "no-store" })`.
  * **`api.ts` Lines 78–84:** `isCredentialSubmission` checks if `path === "/api/v1/auth/login" || path === "/api/v1/auth/swap"` so a 401 from a credential check never triggers a hard `window.location.href = "/login"` reload.
  * **`AuthContext.tsx` Lines 59–65:** When `res.status === "requires_password_change"`, `AuthContext` stores `{ username, token: res.setup_token }` inside `passwordSetup.current` (an in-memory React ref, never written to `localStorage`) so `setupPasswordAndLogin` can present `setup_token` on the second step.

---

### Phase C: Request Routing, Schema Validation & Rate-Limit Interception

#### Step C1: API v1 Router Prefixing & Pydantic Request Schema Validation
* **Step Title & Trigger:** FastAPI receives `POST /api/v1/auth/login` (or `POST /api/v1/auth/setup-password`), routes it through `v1_router` (`/api/v1`) to `auth_router` (`/auth`), and validates the JSON body against `LoginRequest` (or `SetupPasswordRequest`).
* **Exact File Path & Line Numbers:** `backend/app/api/v1/router.py` (Lines 1–48) and `backend/app/schemas/auth.py` (Lines 1–68)
* **Complete Uncut Code Block (`backend/app/api/v1/router.py`, Lines 1–48):**
```python
"""
Aggregated v1 API router.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.scans import router as scans_router
from app.api.v1.devices import router as devices_router
from app.api.v1.sensors import router as sensors_router
from app.api.v1.users import router as users_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.intakes import router as intakes_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.activity import router as activity_router
from app.api.v1.config import router as config_router
from app.api.v1.quality import router as quality_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.system import router as system_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.scan_logs import router as scan_logs_router
from app.api.v1.printing import router as printing_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(scans_router)
v1_router.include_router(devices_router)
v1_router.include_router(sensors_router)
v1_router.include_router(users_router)
v1_router.include_router(suppliers_router)
v1_router.include_router(intakes_router)
v1_router.include_router(analytics_router)
v1_router.include_router(activity_router)
v1_router.include_router(config_router)
v1_router.include_router(quality_router)
v1_router.include_router(notifications_router)
v1_router.include_router(cameras_router)
v1_router.include_router(system_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(scan_logs_router)
v1_router.include_router(printing_router)

from app.api.v1.maintenance import router as maintenance_router
v1_router.include_router(maintenance_router)
```
* **Complete Uncut Code Block (`backend/app/schemas/auth.py`, Lines 1–68):**
```python
"""
Pydantic schemas for authentication requests/responses.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


# ── Requests ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    """Self-service password change — requires current password for verification."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class SetupPasswordRequest(BaseModel):
    """First-time / post-reset password setup — user proved identity at login."""
    setup_token: str
    new_password: str = Field(..., min_length=6, max_length=128)


class PinSwapRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class ChangePinRequest(BaseModel):
    """Self-service PIN change — requires current PIN for verification."""
    current_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    new_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class SetupPinRequest(BaseModel):
    """First-time / post-reset PIN setup — user proved identity at PIN swap."""
    setup_token: str
    new_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


# ── Responses ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthUser(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: str
    avatar_url: str | None = None


class LoginResponse(BaseModel):
    status: str  # "success" | "requires_password_change" | "requires_pin_change" etc.
    token: TokenResponse | None = None
    user: AuthUser | None = None
    reason: str | None = None  # "new_account" | "password_reset" etc.
    setup_token: str | None = None
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`router.py` Lines 27 & 29:** Combines `prefix="/api/v1"` with `auth_router` (`prefix="/auth"`), registering `/api/v1/auth/login`, `/api/v1/auth/setup-password`, and `/api/v1/auth/logout`.
  * **`schemas/auth.py` Lines 14–16 (`LoginRequest`):** Rejects empty usernames, usernames > 50 characters, or empty passwords with HTTP 422 before hitting the database.
  * **`schemas/auth.py` Lines 25–28 (`SetupPasswordRequest`):** Enforces `min_length=6, max_length=128` on `new_password` at the Pydantic boundary, matching the frontend check (`newPassword.length < 6`).

---

#### Step C2: Per-Username Sliding-Window Rate Limiter (`AUTH-04`)
* **Step Title & Trigger:** The `login` endpoint calls `login_limiter.is_locked(body.username)` before querying PostgreSQL, and calls `login_limiter.record_failure(body.username)` or `login_limiter.record_success(body.username)` after authentication.
* **Exact File Path & Line Numbers:** `backend/app/core/rate_limiter.py` (Lines 1–101)
* **Complete Uncut Code Block:**
```python
"""
AUTH-04: In-memory rate limiter for login and PIN swap attempts.

Limits authentication attempts per-username to prevent brute-force attacks.
No external dependency (no Redis needed) — uses an in-memory sliding window.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field

# ── Configuration ────────────────────────────────────────────────────────────

MAX_ATTEMPTS = 5           # Max failed attempts before lockout
LOCKOUT_SECONDS = 300      # 5-minute lockout window
WINDOW_SECONDS = 300       # Sliding window for counting attempts


@dataclass
class _AttemptRecord:
    timestamps: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class RateLimiter:
    """Per-username sliding-window rate limiter with lockout."""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        lockout_seconds: int = LOCKOUT_SECONDS,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._window_seconds = window_seconds
        self._records: dict[str, _AttemptRecord] = defaultdict(_AttemptRecord)
        self._lock = threading.Lock()

    def is_locked(self, key: str) -> tuple[bool, int]:
        """Check if the key is currently locked out.

        Returns:
            (is_locked, remaining_seconds)
        """
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if not record:
                return False, 0
            if record.locked_until > now:
                return True, int(record.locked_until - now)
            return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and check if lockout should trigger.

        Returns:
            (is_now_locked, remaining_seconds)
        """
        now = time.time()
        with self._lock:
            record = self._records[key]

            # If already locked, extend lockout
            if record.locked_until > now:
                return True, int(record.locked_until - now)

            # Prune old timestamps outside the sliding window
            cutoff = now - self._window_seconds
            record.timestamps = [t for t in record.timestamps if t > cutoff]

            # Add this failure
            record.timestamps.append(now)

            # Check if we exceeded the threshold
            if len(record.timestamps) >= self._max_attempts:
                record.locked_until = now + self._lockout_seconds
                record.timestamps.clear()
                return True, self._lockout_seconds

            remaining_attempts = self._max_attempts - len(record.timestamps)
            return False, remaining_attempts

    def record_success(self, key: str) -> None:
        """Clear the failure record on successful authentication."""
        with self._lock:
            if key in self._records:
                del self._records[key]


# Singleton instances — one for login (password), one for PIN swap, and one for
# re-checking a signed-in user's current password or PIN (change-password, change-pin,
# maintenance re-authentication). Keys: "password:<user id>", "pin:<user id>",
# "reauth:<user id>".
login_limiter = RateLimiter()
pin_limiter = RateLimiter()
credential_limiter = RateLimiter()
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 17–19:** Sets `MAX_ATTEMPTS = 5` failed attempts within `WINDOW_SECONDS = 300` (5 minutes), triggering a `LOCKOUT_SECONDS = 300` (5-minute) lockout.
  * **Lines 43–56 (`is_locked`):** Acquires `self._lock` and checks if `record.locked_until > now`. If true, returns `(True, int(record.locked_until - now))` so the controller can immediately return HTTP 429 (`"Too many failed login attempts. Try again in X seconds."`).
  * **Lines 58–86 (`record_failure`):** Prunes timestamps older than `now - 300`, appends `now`, and if `len(record.timestamps) >= 5`, sets `record.locked_until = now + 300`, clears `timestamps`, and returns `(True, 300)`. Otherwise returns `(False, remaining_attempts)`.
  * **Lines 88–92 (`record_success`):** Deletes `self._records[key]` on successful login so previous failed attempts are wiped clean.

---

### Phase D: Backend Controller & Core Logic

#### Step D1: Auth Controller (`POST /api/v1/auth/login` & `POST /api/v1/auth/setup-password`)
* **Step Title & Trigger:** `login()` in `backend/app/api/v1/auth.py` orchestrates rate-limit checks, recovery-mode restrictions, `authenticate_user()`, audit logging (`audit.emit` / `audit.record`), and token generation.
* **Exact File Path & Line Numbers:** `backend/app/api/v1/auth.py` (Lines 1–260 & 396–413)
* **Complete Uncut Code Block:**
```python
"""
Authentication routes — login, logout, operator swap, password/PIN changes.

AUTH-04: Login and PIN swap endpoints are rate-limited per-username. Changing a password or
PIN re-checks the current secret under a per-account limit (``credential_limiter``).

Audit (``app.services.audit``):
* Sign-in outcomes before a session exists are written with ``audit.emit``: the login session
  holds no row locks, the row survives the 429 that a lockout raises, and while the station
  is in recovery the event is deferred instead of touching the data being verified.
* Failures after ``lock_current_account`` (``SELECT ... FOR UPDATE``) are attached to the
  raised error and written by the audit handler after the request has rolled back.
* Successful sign-ins and credential changes use ``audit.record`` so the row commits with
  the change.
* A typed username that is not an existing account is written only as "an unrecognized
  username"; passwords, PINs and tokens are never written.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import CurrentCredentialIncorrect, SetupTokenRejected
from app.core.http import get_client_ip
from app.core.rate_limiter import MAX_ATTEMPTS, credential_limiter, login_limiter, pin_limiter
from app.schemas.auth import (
    AuthUser,
    ChangePasswordRequest,
    ChangePinRequest,
    LoginRequest,
    LoginResponse,
    PinSwapRequest,
    SetupPasswordRequest,
    SetupPinRequest,
    TokenResponse,
)
from app.services import audit
from app.services.audit import AuditAction
from app.services.auth_service import (
    authenticate_user,
    change_password,
    change_pin,
    create_setup_token,
    create_user_token,
    find_account,
    lock_current_account,
    setup_password,
    setup_pin,
    swap_operator,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

UNRECOGNIZED = "an unrecognized username"
BLOCKED_WINDOW = 60  # seconds between login_blocked rows for the same channel and key
BLOCKED_KEYS = 1024

_clock = time.monotonic
# (channel, username or user id) -> [window start, refused attempts not written since]
_blocked_seen: dict[tuple[str, str], list[float]] = {}


# ── Audit wording ─────────────────────────────────────────────────────────────

def _name(account) -> str:
    """An existing account's stored username, quoted (never the typed text)."""
    return audit.quoted(account.username)


def _account(account) -> str:
    return f"account {_name(account)} (id {account.id})"


def _subject(account) -> str:
    return _account(account) if account is not None else UNRECOGNIZED


def _user(account) -> str:
    return f"user {_name(account)}"


def _attempts_left(count: int) -> str:
    return f"{count} attempt{'' if count == 1 else 's'} left"


def _locked(account, scope: str, seconds: int, attempts: str) -> str:
    """'Account 'x' (id …) <scope> locked for <n> s after <k> failed <attempts>'."""
    if account is None:
        return (f"{scope[0].upper()}{scope[1:]} for {UNRECOGNIZED} locked for {seconds} s "
                f"after {MAX_ATTEMPTS} failed {attempts}")
    return (f"Account {_name(account)} (id {account.id}) {scope} locked for {seconds} s "
            f"after {MAX_ATTEMPTS} failed {attempts}")


def _with_suppressed(details: str, suppressed: int) -> str:
    return f"{details}; {suppressed} similar suppressed" if suppressed else details


def _blocked_suppressed(channel: str, key: str) -> int | None:
    """None when a refused attempt for this channel and key was written in the last window;
    otherwise how many refused attempts were left unwritten since the previous row."""
    now = _clock()
    seen = _blocked_seen
    entry = seen.get((channel, key))
    if entry and now - entry[0] < BLOCKED_WINDOW:
        entry[1] += 1
        return None
    suppressed = int(entry[1]) if entry else 0
    if len(seen) >= BLOCKED_KEYS:
        for stale in [k for k, (start, _) in seen.items() if now - start >= BLOCKED_WINDOW]:
            del seen[stale]
        while len(seen) >= BLOCKED_KEYS:
            seen.pop(next(iter(seen)))
    seen[(channel, key)] = [now, 0]
    return suppressed


def _session_response(user, token: str) -> LoginResponse:
    return LoginResponse(
        status="success",
        token=TokenResponse(access_token=token),
        user=AuthUser(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=getattr(user.role, "name", "Unknown") if user.role else "Unknown",
            avatar_url=user.avatar_url,
        ),
    )


async def _refused_while_locked(db, channel: str, username: str, what: str, remaining: int,
                                ip: str | None) -> None:
    """One login_blocked row per username and channel per window, naming only real accounts."""
    suppressed = _blocked_suppressed(channel, username)
    if suppressed is None:
        return
    account = await find_account(db, username)
    await audit.emit(AuditAction.LOGIN_BLOCKED, _with_suppressed(
        f"{what} refused for {_subject(account)}: locked for another {remaining} s", suppressed,
    ), ip=ip, capped=account is None)


@router.get("/operators")
async def list_kiosk_operators(db: DbSession):
    """
    Public endpoint — returns active operators for the kiosk selection modal.
    No authentication required so fresh kiosk sessions can populate the operator list.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.user_account import UserAccount
    from app.models.user_role import UserRole
    from app.schemas.enums import ActiveStatusEnum, RoleEnum

    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .join(UserAccount.role)
        .where(UserAccount.status == ActiveStatusEnum.ACTIVE)
        .where(UserRole.name == RoleEnum.OPERATOR.value)
        .order_by(UserAccount.full_name)
    )
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "Operator",
            "status": u.status.value if u.status else "Active",
            "avatar_url": u.avatar_url,
        }
        for u in users
    ]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, request: Request):
    """Authenticate a user by username + password. Rate-limited (AUTH-04)."""
    ip = get_client_ip(request)
    # ── AUTH-04: Check rate limit ────────────────────────────────────────
    locked, remaining = login_limiter.is_locked(body.username)
    if locked:
        await _refused_while_locked(db, "login", body.username, "Sign-in", remaining, ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
        )

    from app.services.runtime_operations import coordinator
    recovery_login = coordinator.state in {"power-accepted", "recovery-required"}
    status, user, reason = await authenticate_user(db, body.username, body.password, readonly=recovery_login)
    # Only these statuses mean the password was accepted; ``user`` otherwise only names the
    # account for the audit log.
    accepted = status in {"success", "requires_password_change"}
    if recovery_login and accepted and (
            not user.role or user.role.name != 'Admin' or user.requires_password_change):
        denial = 'Recovery requires an active administrator with completed credential setup'
        raise audit.attach(
            HTTPException(403, denial), AuditAction.LOGIN_DENIED,
            f"Recovery sign-in denied for {_account(user)}: {denial[0].lower()}{denial[1:]}",
            ip=ip,
        )

    if status == "failed":
        is_locked, info = login_limiter.record_failure(body.username)
        failure = f"Sign-in failed for {_subject(user)}"
        if reason == "incorrect_password":
            failure += ": incorrect password"
        if is_locked:
            await audit.emit(AuditAction.LOGIN_FAILED, f"{failure}; sign-in locked", ip=ip,
                             capped=user is None)
            await audit.emit(AuditAction.ACCOUNT_LOCKED,
                             _locked(user, "sign-in", info, "sign-in attempts"), ip=ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Account locked for {info} seconds.",
            )
        await audit.emit(AuditAction.LOGIN_FAILED, f"{failure}; {_attempts_left(info)}", ip=ip,
                         capped=user is None)
        return LoginResponse(status="failed")

    if status == "inactive":
        await audit.emit(AuditAction.LOGIN_DENIED,
                         f"Sign-in denied for {_account(user)}: account is inactive", ip=ip)
        return LoginResponse(status="inactive", reason="Account is inactive")

    if status == "requires_password_change":
        login_limiter.record_success(body.username)
        await audit.record(
            db, AuditAction.CREDENTIAL_SETUP_STARTED,
            f"User {_name(user)} signed in with a temporary password; password setup started "
            f"(reason {audit.clean(reason, 40)})",
            actor=user, ip=ip,
        )
        return LoginResponse(status="requires_password_change", reason=reason,
                             setup_token=create_setup_token(user, "setup_password"))

    # Success — clear rate limit record
    login_limiter.record_success(body.username)
    if recovery_login:
        from sqlalchemy import select
        from app.models.maintenance_state import MaintenanceState
        generation = await db.scalar(select(MaintenanceState.auth_generation).where(MaintenanceState.id == 1))
        token = create_user_token(user, generation=generation or 'initial')
        # Deferred by the audit writer until the station is ready; recovery writes nothing.
        await audit.emit(AuditAction.LOGIN, f"User {user.username} logged in (recovery mode)",
                         actor=user, ip=ip)
    else:
        token = create_user_token(user)
        await audit.record(db, AuditAction.LOGIN, f"User {user.username} logged in",
                           actor=user, ip=ip)

    return _session_response(user, token)
```
```python
@router.post("/setup-password", response_model=LoginResponse)
async def setup_password_route(body: SetupPasswordRequest, db: DbSession, request: Request):
    """
    First-time / post-reset password setup.
    Only allowed for accounts with requires_password_change=True.
    The user proved identity by logging in with the temporary password.
    """
    ip = get_client_ip(request)
    try:
        user = await setup_password(db, body.setup_token, body.new_password)
    except SetupTokenRejected as error:
        raise _rejected_setup(error, "Password setup", ip) from None
    token = create_user_token(user)
    await audit.record(db, AuditAction.PASSWORD_SETUP_COMPLETED,
                       f"User {_name(user)} completed password setup; other sessions revoked",
                       actor=user, ip=ip)
    return _session_response(user, token)
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 187–193:** Checks `login_limiter.is_locked(body.username)`. If locked, writes at most one `LOGIN_BLOCKED` audit entry per 60-second window (`_refused_while_locked`) and raises HTTP 429.
  * **Lines 195–208:** Checks if the station is in maintenance recovery (`coordinator.state in {"power-accepted", "recovery-required"}`). During recovery, `authenticate_user` runs with `readonly=True` (so `user.last_active` is not mutated) and only an active Admin who does not require a password change is allowed to sign in.
  * **Lines 210–226 (`status == "failed"`):** Calls `login_limiter.record_failure(body.username)`. If this was the 5th failure, emits both `LOGIN_FAILED` and `ACCOUNT_LOCKED` to `activity_log` via `audit.emit()` (which uses a separate DB session so the rows survive the HTTP 429 exception rollback) and raises HTTP 429. Otherwise emits `LOGIN_FAILED` with remaining attempts and returns `LoginResponse(status="failed")`. Note: if `user is None` (unknown username), `_subject(user)` logs `"an unrecognized username"` so unknown typed text is never stored in the database.
  * **Lines 228–231 (`status == "inactive"`):** Emits `LOGIN_DENIED` (`"Sign-in denied for account 'x' (id ...): account is inactive"`) and returns `LoginResponse(status="inactive", reason="Account is inactive")`.
  * **Lines 233–242 (`status == "requires_password_change"`):** Clears the rate limiter (`record_success`), records `CREDENTIAL_SETUP_STARTED` in the transaction, issues a 10-minute scoped setup token (`create_setup_token(user, "setup_password")`), and returns `LoginResponse(status="requires_password_change", reason=reason, setup_token=...)`.
  * **Lines 245–259 (`status == "success"`):** Clears the rate limiter, generates the JWT via `create_user_token(user)`, records `AuditAction.LOGIN` (`"User <username> logged in"`), and returns `_session_response(user, token)`.
  * **Lines 396–413 (`POST /api/v1/auth/setup-password`):** Verifies `body.setup_token` and updates the password via `setup_password()`, issues a fresh session JWT (`create_user_token(user)`), records `AuditAction.PASSWORD_SETUP_COMPLETED`, and returns `_session_response(user, token)`.

---

#### Step D2: Authentication Service (`authenticate_user`, `setup_password`, `create_user_token`) & Bcrypt/JWT Security (`security.py`)
* **Step Title & Trigger:** Called by `backend/app/api/v1/auth.py` to query `UserAccount`, verify bcrypt password hashes, check account status and password-change flags, and sign JWTs.
* **Exact File Path & Line Numbers:** `backend/app/services/auth_service.py` (Lines 35–148, 213–240, 300–312) and `backend/app/core/security.py` (Lines 1–79)
* **Complete Uncut Code Block (`backend/app/services/auth_service.py`, Lines 35–148, 213–240, 300–312):**
```python
def create_setup_token(user: UserAccount, purpose: str) -> str:
    """Ten-minute proof of temporary-credential authentication, never an access token."""
    return create_access_token(
        {"sub": str(user.id), "tv": user.token_version, "scope": purpose},
        expires_delta=timedelta(minutes=10),
    )


def _token_subject(payload: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


async def verify_setup_token(db: AsyncSession, token: str, purpose: str) -> UserAccount:
    """Return the locked account a setup token was issued to.

    Raises ``SetupTokenRejected`` (401) with an audit ``reason`` and, when the signed token
    names one, the ``user_id``. The token text itself is never part of the exception.
    """
    payload = decode_access_token(token)
    if not payload:
        raise SetupTokenRejected("Invalid or expired setup authorization; sign in again",
                                 reason="invalid or expired")
    user_id = _token_subject(payload)
    if payload.get("scope") != purpose:
        raise SetupTokenRejected("Invalid or expired setup authorization; sign in again",
                                 reason="has the wrong purpose", user_id=user_id)
    from app.services.maintenance_state import generation_matches
    if not await generation_matches(db, payload):
        raise SetupTokenRejected("Station data changed; sign in again",
                                 reason="was issued before the station data changed",
                                 user_id=user_id)
    if user_id is None:
        raise SetupTokenRejected("Invalid setup authorization", reason="is malformed")
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if not user or user.status != ActiveStatusEnum.ACTIVE or payload.get("tv") != user.token_version:
        reason = ("revoked: account not found" if not user
                  else "revoked: account inactive" if user.status != ActiveStatusEnum.ACTIVE
                  else "revoked")
        raise SetupTokenRejected("Setup authorization revoked; sign in again",
                                 reason=reason, user_id=user_id)
    return user


async def lock_current_account(db: AsyncSession, user: UserAccount) -> UserAccount:
    """Refresh under lock so concurrent credential changes cannot reuse a version."""
    version = user.token_version
    account = (await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not account or account.status != ActiveStatusEnum.ACTIVE or account.token_version != version:
        raise CredentialsException("Session has been revoked; sign in again")
    return account


async def find_account(db: AsyncSession, username: str) -> UserAccount | None:
    """The account with exactly this username, read without a lock (for audit wording)."""
    return (await db.execute(
        select(UserAccount).where(UserAccount.username == username)
    )).scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, username: str, password: str, *, readonly: bool = False
) -> tuple[str, UserAccount | None, str | None]:
    """
    Authenticate a user by username + password.

    Returns:
        (status, account_or_none, reason_or_none)
        status: "success" | "failed" | "inactive" | "requires_password_change"
        reason: for "failed": "unknown_username" | "incorrect_password";
                for "requires_password_change": "new_account" | "password_reset" | ...

    Only "success" and "requires_password_change" mean the credentials were accepted. The
    account is also returned for "failed" (incorrect password) and "inactive" so the caller
    can name it in the audit log; it must not be treated as signed in.
    """
    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.username == username)
    )
    user = result.scalar_one_or_none()

    if not user:
        return "failed", None, "unknown_username"
    if not verify_password(password, user.password_hash):
        return "failed", user, "incorrect_password"

    if user.status == ActiveStatusEnum.INACTIVE:
        return "inactive", user, None

    if user.requires_password_change:
        reason = user.password_setup_reason or "password_change"
        return "requires_password_change", user, reason

    # Recovery login must not mutate data being verified against a restore archive.
    if not readonly:
        user.last_active = now_manila()
    return "success", user, None
```
```python
async def setup_password(
    db: AsyncSession, setup_token: str, new_password: str
) -> UserAccount:
    """
    First-time / post-reset password setup.
    Only allowed when the account has requires_password_change=True.

    This is called after the user proved identity by logging in with their
    temporary password.
    """
    user = await verify_setup_token(db, setup_token, "setup_password")

    if not user.requires_password_change:
        raise SetupTokenRejected(
            "Password setup is only allowed for accounts that require a password change",
            reason="not needed (no password change is required)", user_id=user.id,
        )

    if verify_password(new_password, user.password_hash):
        raise CredentialsException("Choose a different password from the temporary password")

    user.password_hash = hash_password(new_password)
    user.requires_password_change = False
    user.password_setup_reason = None
    user.token_version += 1  # Revoke all prior sessions (AUTH-02)
    user.last_active = now_manila()
    return user
```
```python
def create_user_token(user: UserAccount, *, generation: str | None = None) -> str:
    """Create a JWT access token for the given user."""
    # Check if role is populated, otherwise fallback dynamically
    role_name = getattr(user.role, "name", "Unknown") if hasattr(user, "role") and user.role else "Unknown"

    return create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": role_name,
            "tv": user.token_version,
        }, generation=generation
    )
```
* **Complete Uncut Code Block (`backend/app/core/security.py`, Lines 1–79):**
```python
"""
Security utilities: JWT token creation/verification and password/PIN hashing.

Uses `bcrypt` directly instead of passlib (passlib is incompatible with
bcrypt >= 4.1 and Python >= 3.13).
"""

from __future__ import annotations

from datetime import timedelta
from app.core.time import now_manila

import jwt
from jwt.exceptions import PyJWTError
import bcrypt

from app.config import get_settings

settings = get_settings()

# ── Password Hashing ────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── PIN Hashing (same bcrypt, separate functions for clarity) ────────────────

def hash_pin(plain_pin: str) -> str:
    """Hash a plain-text PIN using bcrypt."""
    return bcrypt.hashpw(plain_pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify a plain-text PIN against a bcrypt hash."""
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))


# ── JWT Tokens ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
    *, generation: str | None = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    from app.services.maintenance_state import auth_generation
    to_encode["sg"] = generation if generation is not None else auth_generation
    expire = now_manila() + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict | None:
    """Decode and verify a JWT access token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except PyJWTError:
        return None
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`auth_service.py` Lines 125–138 (`authenticate_user` Order of Checks):**
    1. Queries `UserAccount` by `username` with `selectinload(UserAccount.role)` and `selectinload(UserAccount.operator_profile)`.
    2. If `not user`: returns `("failed", None, "unknown_username")`.
    3. If `not verify_password(password, user.password_hash)` (calls `bcrypt.checkpw` in `security.py` Line 31): returns `("failed", user, "incorrect_password")`.
    4. **Password is verified BEFORE checking `INACTIVE`:** Only after the password matches does Line 137 check `if user.status == ActiveStatusEnum.INACTIVE: return "inactive", user, None`. This prevents an attacker without the password from probing whether an account is active or inactive.
    5. **Line 140:** Checks `if user.requires_password_change:` and returns `("requires_password_change", user, user.password_setup_reason or "password_change")`.
    6. **Lines 145–147:** Updates `user.last_active = now_manila()` and returns `("success", user, None)`.
  * **`auth_service.py` Lines 35–40 (`create_setup_token`):** Creates a 10-minute JWT containing `"scope": "setup_password"`. Because `_resolve_user` in `deps.py` requires `payload.get("scope", "access") == "access"`, a setup token can **never** be used as a general bearer token to access protected endpoints.
  * **`auth_service.py` Lines 213–240 (`setup_password`):** Calls `verify_setup_token` (which locks the `UserAccount` row with `.with_for_update()`), ensures the new password differs from the temporary password (`if verify_password(new_password, user.password_hash): raise CredentialsException(...)`), hashes the new password with `hash_password(new_password)`, clears `requires_password_change = False` and `password_setup_reason = None`, increments `user.token_version += 1`, and updates `user.last_active = now_manila()`.
  * **`security.py` Lines 48–66 (`create_access_token`):** Signs a JWT containing `"sub"` (UUID string), `"username"`, `"role"`, `"tv"` (`user.token_version`), `"sg"` (`auth_generation` from `maintenance_state`), and `"exp"` (`now_manila() + timedelta(minutes=settings.jwt_access_token_expire_minutes)`).

---

### Phase E: Database Operations & ORM Models

#### Step E1: `UserAccount` (`user_account`) & `ActivityLog` (`activity_log`) ORM Schemas and Queries
* **Step Title & Trigger:** Executed during `authenticate_user()`, `setup_password()`, `logout()`, and `audit.record()` / `audit.emit()`.
* **Exact File Path & Line Numbers:** `backend/app/models/user_account.py` (Lines 1–71) and `backend/app/models/activity_log.py` (Lines 1–34)
* **Complete Uncut Code Block (`backend/app/models/user_account.py`, Lines 1–71):**
```python
"""
UserAccount ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


from app.schemas.enums import ActiveStatusEnum

class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("user_role.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ActiveStatusEnum] = mapped_column(
        SAEnum(ActiveStatusEnum),
        nullable=False,
        default=ActiveStatusEnum.ACTIVE,
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    requires_password_change: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    password_setup_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    last_active: Mapped[datetime | None] = mapped_column(
        ManilaDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(), default=now_manila
    )
    updated_at: Mapped[datetime] = mapped_column(
        ManilaDateTime(),
        default=now_manila,
        onupdate=now_manila,
    )
    token_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False,
        doc="Incremented on logout/credential change to revoke prior JWTs.",
    )

    # Relationships
    role = relationship("UserRole", back_populates="accounts", lazy="selectin")
    admin_profile = relationship(
        "AdminProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    operator_profile = relationship(
        "OperatorProfile", back_populates="account", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    activity_logs = relationship("ActivityLog", back_populates="user", lazy="raise")
```
* **Complete Uncut Code Block (`backend/app/models/activity_log.py`, Lines 1–34):**
```python
"""
ActivityLog ORM model — audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from app.core.time import now_manila

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import ManilaDateTime


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(ManilaDateTime(), default=now_manila, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    user = relationship("UserAccount", back_populates="activity_logs")
```
* **Line-by-Line Connection & Trace Explanation:**
  * **SQL Equivalent Queries Executed During Login / Setup / Logout:**
    1. **Lookup on Login (`authenticate_user`):**
       `SELECT * FROM user_account WHERE username = :username` + eager `SELECTIN` loads on `user_role` (`role_id`) and `operator_profile` (`account_id`).
    2. **Success Login Update:**
       `UPDATE user_account SET last_active = :now_manila, updated_at = :now_manila WHERE id = :id`
    3. **Row Lock on Password Setup or Logout (`verify_setup_token` / `lock_current_account`):**
       `SELECT * FROM user_account WHERE id = :user_id FOR UPDATE`
    4. **Password Setup Update (`setup_password`):**
       `UPDATE user_account SET password_hash = :hash, requires_password_change = false, password_setup_reason = NULL, token_version = token_version + 1, last_active = :now_manila, updated_at = :now_manila WHERE id = :id`
    5. **Audit Trail Insert (`audit.record` / `audit.emit`):**
       `INSERT INTO activity_log (id, timestamp, user_id, action, details, ip_address, actor_name) VALUES (...)`
  * **Timestamps:** All datetime columns (`last_active`, `created_at`, `updated_at`, `timestamp`) use `ManilaDateTime()` and `now_manila()` (`Asia/Manila`, UTC+8).

---

### Phase F: Response, Redirects & Error Display

#### Step F1: Token Persistence, `/dashboard` Redirect & Toast Feedback
* **Step Title & Trigger:** FastAPI returns `LoginResponse` (HTTP 200 or HTTP 429) to `AuthContext.login()`, which updates `localStorage` and returns the status string to `Login.tsx`.
* **Exact File Path & Line Numbers:** `frontend/src/context/AuthContext.tsx` (Lines 53–85) and `frontend/src/pages/Login.tsx` (Lines 54–79)
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 53–85):**
```tsx
  const login = useCallback(async (username: string, password?: string) => {
    try {
      passwordSetup.current = null
      const res = await api.auth.login(username, password || "")

      // Check status for password change requirements
      if (res.status === "requires_password_change") {
        if (!res.setup_token) return "failed" as const
        passwordSetup.current = { username, token: res.setup_token }
        if (res.reason === "new_account") return "requires_password_change_new_account" as const
        if (res.reason === "password_reset") return "requires_password_change_reset" as const
        return "requires_password_change" as const
      }

      if (res.status === "inactive") {
        return "inactive" as const
      }

      if (res.status === "failed" || !res.token || !res.user) {
        return "failed" as const
      }

      // Save token and user
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch {
      return "failed" as const
    }
  }, [])
```
* **Complete Uncut Code Block (`frontend/src/pages/Login.tsx`, Lines 54–79):**
```tsx
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
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Outcome 1 — `"success"`:**
    1. `AuthContext.tsx` Lines 76–80 call `setToken(res.token.access_token)` (saves `"bananavision_token"` in `localStorage` and clears stale scan write cache), maps `res.user` (`full_name` → `fullName`, `avatar_url` → `avatar`), calls `setStoredUser(authUser)` (saves `"bananavision_user"` in `localStorage`), and calls `setUser(authUser)`.
    2. `Login.tsx` Lines 68–70 fire `toast.success("Welcome back!", { description: "Logged in successfully" })` and call `navigate("/dashboard")`.
    3. `ProtectedRoute` in `App.tsx` sees `user !== null` and renders `<AppLayout />` → `<Dashboard />`.
  * **Outcome 2 — `"requires_password_change*"`:**
    1. `AuthContext.tsx` Lines 59–65 save `res.setup_token` in `passwordSetup.current` and return the specific reason code.
    2. `Login.tsx` Lines 56–67 update `passwordChangePrompt`, set `isChangingPassword = true`, and re-render the form with the `bg-primary/5 border border-primary/20 p-3 rounded-xl mb-2` prompt banner and `New Password` / `Confirm Password` inputs.
  * **Outcome 3 — `"inactive"`:**
    1. `Login.tsx` Line 72 displays `toast.error("Account Inactive", { description: "Your account is inactive. Please contact an administrator." })`.
  * **Outcome 4 — `"failed"` (Invalid Credentials or 429 Lockout):**
    1. `Login.tsx` Line 74 displays `toast.error("Login failed", { description: "Check your username and password, or contact an administrator." })`.

---

### Phase G: Logout / Cleanup Flow

#### Step G1: Sidebar Footer Logout Trigger & Confirmation Dialog (`AppSidebarFooter.tsx`)
* **Step Title & Trigger:** Signed-in user clicks their user profile card at the bottom of the sidebar (`AppSidebarFooter`), clicks `"Logout"` inside the Popover menu, and confirms by clicking `"Logout"` inside the `AlertDialog`.
* **Exact File Path & Line Numbers:** `frontend/src/components/AppSidebarFooter.tsx` (Lines 1–93)
* **Complete Uncut Code Block:**
```tsx
import { useState } from "react"
import { NavLink, useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { LogOut, ShieldCheck, ShieldAlert, User } from "lucide-react"

export default function AppSidebarFooter() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [showLogoutDialog, setShowLogoutDialog] = useState(false)

  const handleLogout = () => {
    logout()
    navigate("/")
  }

  const [popoverOpen, setPopoverOpen] = useState(false)

  return (
    <div className="px-3 pb-4 shrink-0">
      <Separator className="mb-3" />

      <div className="flex items-center gap-3 px-2">
        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <button className="flex items-center gap-3 hover:bg-accent rounded-lg p-2 transition-colors w-full">
              <Avatar className="h-9 w-9 border-2 border-primary/20">
                <AvatarImage src={user?.avatar || undefined} className="object-cover" />
                <AvatarFallback className="bg-primary/10 text-primary text-xs font-bold">
                  {user?.fullName?.split(" ").map((n) => n[0]).join("")?.toUpperCase() || "?"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-sm font-semibold truncate">{user?.fullName}</p>
                <Badge variant="outline" className={`text-[10px] h-5 px-1.5 gap-1 ${user?.role === "Admin" ? "bg-primary/10 text-primary border-primary/20" : ""}`}>
                  {user?.role === "Admin" ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
                  {user?.role}
                </Badge>
              </div>
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-56 p-2 rounded-xl" align="start" side="top" sideOffset={8}>
            <div className="space-y-1">
              <NavLink to="/profile" onClick={() => setPopoverOpen(false)} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm font-medium transition-colors">
                <User className="w-4 h-4" />
                My Profile
              </NavLink>
              <Separator className="my-1" />
              <button
                onClick={() => { setPopoverOpen(false); setShowLogoutDialog(true) }}
                className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 hover:text-destructive text-sm font-medium transition-colors w-full text-left"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Logout Confirmation Dialog */}
      <AlertDialog open={showLogoutDialog} onOpenChange={setShowLogoutDialog}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Logout</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to log out? You will need to sign in again to access your account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={handleLogout}>
              Logout
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 62–68:** Clicking the red-hover `"Logout"` button (`hover:bg-destructive/10 hover:text-destructive`) inside `PopoverContent` closes the popover (`setPopoverOpen(false)`) and opens the confirmation modal (`setShowLogoutDialog(true)`).
  * **Lines 75–90:** Renders the Radix `AlertDialog`. Clicking `<AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={handleLogout}>` triggers `handleLogout()` (Lines 25–28), which calls `logout()` from `AuthContext` and navigates to `"/"` (the Landing Page).

---

#### Step G2: Frontend Storage Cleanup (`AuthContext.logout` & `auth.ts`) and Backend Token Version Revocation (`POST /api/v1/auth/logout` & `deps.py`)
* **Step Title & Trigger:** `handleLogout()` calls `logout()` in `AuthContext.tsx`, which fires `api.auth.logout()` (`POST /api/v1/auth/logout`) while synchronously clearing local session state and caches.
* **Exact File Path & Line Numbers:**
  * `frontend/src/context/AuthContext.tsx` (Lines 125–134)
  * `frontend/src/lib/auth.ts` (Lines 25–34 & 51–64)
  * `backend/app/api/deps.py` (Lines 1–104)
  * `backend/app/api/v1/auth.py` (Lines 458–466)
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 125–134):**
```tsx
  // ── Logout ──────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    api.auth.logout().catch(() => {})
    passwordSetup.current = null
    pinSetup.current = null
    clearAuth()
    setUser(null)
  }, [])
```
* **Complete Uncut Code Block (`frontend/src/lib/auth.ts`, Lines 25–34 & 51–64):**
```ts
export function setToken(token: string): void {
  clearScanWrites()
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  clearScanWrites()
  clearImageCache()
  localStorage.removeItem(TOKEN_KEY)
}
```
```ts
export function clearStoredUser(): void {
  localStorage.removeItem(USER_KEY)
}

// ── Helpers ─────────────────────────────────────────────────────────────────

export function isAuthenticated(): boolean {
  return !!getToken()
}

export function clearAuth(): void {
  clearToken()
  clearStoredUser()
}
```
* **Complete Uncut Code Block (`backend/app/api/deps.py`, Lines 1–104):**
```python
"""
Shared FastAPI dependencies — database session, current user extraction.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_stream_db
from app.core.exceptions import CredentialsException, ForbiddenException
from app.core.security import decode_access_token
from app.models.user_account import UserAccount
from sqlalchemy.orm import selectinload
from app.schemas.enums import ActiveStatusEnum, RoleEnum

async def _resolve_user(db: AsyncSession, token: str) -> UserAccount:
    payload = decode_access_token(token)

    if not payload or "sub" not in payload or payload.get("scope", "access") != "access":
        raise CredentialsException("Invalid or expired token")

    from app.services.maintenance_state import generation_matches
    if not await generation_matches(db, payload):
        raise CredentialsException("Station data changed; please log in again")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise CredentialsException("Malformed token payload")

    result = await db.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.role), selectinload(UserAccount.operator_profile))
        .where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise CredentialsException("User not found")

    # Refused-access audit rows name the account, even when it is inactive or revoked.
    from app.services.audit import remember_actor
    remember_actor(user)

    if user.status != ActiveStatusEnum.ACTIVE:
        raise ForbiddenException("Account is inactive")

    # ── Token version check (AUTH-02 fix) ────────────────────────────────
    # Reject tokens issued before the latest logout / credential change.
    token_version = payload.get("tv")
    if token_version is None or token_version != user.token_version:
        raise CredentialsException("Session has been revoked — please log in again")

    return user


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    authorization: str = Header(default=""),
) -> UserAccount:
    """Extract and validate the current user from the Authorization header."""
    if not authorization.startswith("Bearer "):
        raise CredentialsException("Missing or invalid Authorization header")
    return await _resolve_user(db, authorization.removeprefix("Bearer ").strip())


async def get_media_user(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    authorization: str = Header(default=""),
    token: str | None = Query(default=None),
) -> UserAccount:
    """Media elements cannot send headers, so they may pass the session as a query token."""
    raw = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else (token or "").strip()
    )
    if not raw:
        raise CredentialsException("Missing or invalid session token")
    return await _resolve_user(db, raw)


async def require_admin(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserAccount:
    """Require the current user to have Admin role."""
    from app.services.audit import remember_actor
    remember_actor(user)
    if not user.role or user.role.name != RoleEnum.ADMIN.value:
        raise ForbiddenException("Admin access required")
    return user


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
StreamDbSession = Annotated[AsyncSession, Depends(get_stream_db, scope="request")]
CurrentUser = Annotated[UserAccount, Depends(get_current_user)]
AdminUser = Annotated[UserAccount, Depends(require_admin)]
MediaUser = Annotated[UserAccount, Depends(get_media_user)]
```
* **Complete Uncut Code Block (`backend/app/api/v1/auth.py`, Lines 458–466):**
```python
@router.post("/logout")
async def logout(user: CurrentUser, db: DbSession, request: Request):
    """Logout — revokes all existing tokens by bumping token_version."""
    user = await lock_current_account(db, user)
    # Increment token_version so every previously issued JWT becomes invalid
    user.token_version += 1
    await audit.record(db, AuditAction.LOGOUT, f"User {user.username} logged out; sessions revoked",
                       actor=user, ip=get_client_ip(request))
    return {"message": "Logged out successfully"}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Order of Execution in `AuthContext.logout()` (Lines 127–133):**
    1. `api.auth.logout().catch(() => {})` is called **first** while `bananavision_token` is still in `localStorage`, so `request()` in `api.ts` reads `getToken()` synchronously and attaches `Authorization: Bearer <token>` to `POST /api/v1/auth/logout`.
    2. `clearAuth()` runs immediately after `fetch()` is initiated: it calls `clearScanWrites()`, `clearImageCache()`, `localStorage.removeItem("bananavision_token")`, and `localStorage.removeItem("bananavision_user")`.
    3. `setUser(null)` clears React auth state, and `AppSidebarFooter` navigates to `"/"` (or `ProtectedRoute` redirects to `"/"`).
  * **Server-Side JWT Revocation (`POST /api/v1/auth/logout`):**
    1. `CurrentUser` (`get_current_user` → `_resolve_user` in `deps.py`) validates the Bearer token and loads the `UserAccount`.
    2. `lock_current_account(db, user)` locks the row with `SELECT ... FOR UPDATE`.
    3. `user.token_version += 1` increments the integer column in `user_account`.
    4. `audit.record(db, AuditAction.LOGOUT, f"User {user.username} logged out; sessions revoked", ...)` inserts the `"logout"` row into `activity_log` in the same transaction.
    5. Any subsequent API request using the old JWT fails on `deps.py` Line 56 (`if token_version is None or token_version != user.token_version: raise CredentialsException("Session has been revoked — please log in again")`).

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Component / Layer | Exact Name / Value / Location |
| :--- | :--- |
| **Frontend Login Route** | `/login` wrapped in `<PublicRoute><Login /></PublicRoute>` (`frontend/src/App.tsx` Line 68) |
| **Backend Auth Endpoints** | `POST /api/v1/auth/login`, `POST /api/v1/auth/setup-password`, `POST /api/v1/auth/logout` (`backend/app/api/v1/auth.py`) |
| **Rate Limiter (`AUTH-04`)** | `login_limiter` in `backend/app/core/rate_limiter.py`: `MAX_ATTEMPTS = 5`, `WINDOW_SECONDS = 300`, `LOCKOUT_SECONDS = 300` |
| **LocalStorage Keys** | `bananavision_token` (JWT string) and `bananavision_user` (`AuthUser` JSON) in `frontend/src/lib/auth.ts` (Lines 8–9) |
| **JWT Claims (`security.py`)** | `sub` (User UUID), `username`, `role`, `tv` (`token_version`), `sg` (station `auth_generation`), `exp` (Manila expiration) |
| **Setup Token Claim** | `scope: "setup_password"` with 10-minute expiry (`auth_service.py` Lines 35–40), stored only in `passwordSetup.current` ref |
| **Session Revocation (`AUTH-02`)** | `user.token_version += 1` on logout/password change; verified by `payload.get("tv") != user.token_version` (`deps.py` Line 56) |
| **Database Tables & Columns** | `user_account` (`username`, `password_hash`, `status`, `requires_password_change`, `password_setup_reason`, `last_active`, `token_version`); `activity_log` (`action`, `details`, `user_id`, `ip_address`, `actor_name`, `timestamp`) |
| **Audit Actions (`AuditAction`)** | `login`, `logout`, `login_failed`, `login_blocked`, `account_locked`, `login_denied`, `credential_setup_started`, `password_setup_completed` |
| **Key CSS Classes (`Login.tsx`)** | `bg-linear-to-br from-banana-light via-background to-background`, `animate-fade-in`, `animate-pulse-glow`, `bg-primary/5 border border-primary/20` |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Surface the Exact Backend Lockout Countdown (HTTP 429 Message) in the Login Error Toast
* **Examiner Prompt:** *"Currently, when a user fails login 5 times and triggers a 429 lockout, `AuthContext.login()` catches the error and returns `'failed'`, so `Login.tsx` shows the generic `'Check your username and password'` toast instead of the 300-second lockout countdown from FastAPI. Modify `AuthContext.tsx` and `Login.tsx` so a 429 lockout displays the exact backend countdown message."*
* **Files to Edit:**
  1. `frontend/src/context/AuthContext.tsx` (Lines 82–84)
  2. `frontend/src/pages/Login.tsx` (Lines 73–78)

* **Modification 1 — `frontend/src/context/AuthContext.tsx` (Lines 82–84):**
  * **Before:**
```tsx
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch {
      return "failed" as const
    }
  }, [])
```
  * **After:**
```tsx
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch (err) {
      if ((err as { status?: number })?.status === 429) {
        throw err
      }
      return "failed" as const
    }
  }, [])
```

* **Modification 2 — `frontend/src/pages/Login.tsx` (Lines 73–78):**
  * **Before:**
```tsx
      } else {
        toast.error("Login failed", { description: "Check your username and password, or contact an administrator." })
      }
      setLoading(false)
    } catch { toast.error("Sign in unavailable", { description: "Please try again." }) }
    finally { inFlight.current = false; setLoading(false) }
```
  * **After:**
```tsx
      } else {
        toast.error("Login failed", { description: "Check your username and password, or contact an administrator." })
      }
      setLoading(false)
    } catch (err) {
      const status = (err as { status?: number })?.status
      const message = err instanceof Error ? err.message : "Please try again."
      if (status === 429) {
        toast.error("Account Temporarily Locked", { description: message })
      } else {
        toast.error("Sign in unavailable", { description: "Please try again." })
      }
    }
    finally { inFlight.current = false; setLoading(false) }
```

---

#### Drill Scenario 2: Role-Based Post-Login Redirect (Send Admins to `/admin/users` and Operators to `/dashboard`)
* **Examiner Prompt:** *"Change the post-login redirect so that users with the `'Admin'` role are automatically redirected to `/admin/users` upon login, while `'Operator'` users continue to `/dashboard`."*
* **File to Edit:** `frontend/src/pages/Login.tsx` (Lines 1–30 & 68–71)
* **Before (`frontend/src/pages/Login.tsx`, Lines 68–71):**
```tsx
      if (result === "success") {
        toast.success("Welcome back!", { description: "Logged in successfully" })
        navigate("/dashboard")
      } else if (result === "inactive") {
```
* **After (`frontend/src/pages/Login.tsx`, Lines 1–5 & 68–72):**
```tsx
import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { getStoredUser } from "@/lib/auth"
```
```tsx
      if (result === "success") {
        toast.success("Welcome back!", { description: "Logged in successfully" })
        const signedInUser = getStoredUser()
        navigate(signedInUser?.role === "Admin" ? "/admin/users" : "/dashboard")
      } else if (result === "inactive") {
```

---

#### Drill Scenario 3: Change the Brute-Force Rate Limiter Threshold to 3 Attempts and 60-Second Lockout
* **Examiner Prompt:** *"For the live defense demonstration, reduce the login brute-force rate limiter from 5 failed attempts / 300 seconds lockout to 3 failed attempts / 60 seconds lockout."*
* **File to Edit:** `backend/app/core/rate_limiter.py` (Lines 17–19)
* **Before (`backend/app/core/rate_limiter.py`, Lines 17–19):**
```python
MAX_ATTEMPTS = 5           # Max failed attempts before lockout
LOCKOUT_SECONDS = 300      # 5-minute lockout window
WINDOW_SECONDS = 300       # Sliding window for counting attempts
```
* **After (`backend/app/core/rate_limiter.py`, Lines 17–19):**
```python
MAX_ATTEMPTS = 3           # Max failed attempts before lockout
LOCKOUT_SECONDS = 60       # 1-minute lockout window
WINDOW_SECONDS = 300       # Sliding window for counting attempts
```
