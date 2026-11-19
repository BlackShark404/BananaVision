# `13_landing_page_flow.md` — Module 13: Landing Page Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

BananaVision uses a decoupled **React 19 + TypeScript + Vite Single-Page Application (SPA)** frontend (`frontend/`) paired with a **FastAPI** backend (`backend/`). When a visitor hits the root URL (`/`), the request is handled entirely by the frontend SPA router and client-side authentication state without making an HTTP API call to FastAPI.

| Relative File Path | Layer / Role in Module 13 (Landing Page) |
| :--- | :--- |
| `frontend/index.html` | **HTML Entry Shell:** Defines `<div id="root"></div>`, favicon (`/bananavision-logo.svg`), viewport meta tags, and loads `/src/main.tsx`. |
| `frontend/src/main.tsx` | **React DOM Bootstrap:** Mounts `<App />` inside `<StrictMode>` into `#root` and imports global stylesheet `./index.css`. |
| `frontend/src/App.tsx` | **Router & Route Guard Middleware:** Wraps the app in `ThemeProvider`, `AuthProvider`, and `BrowserRouter`. Defines the `PublicRoute` guard and maps `<Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />`. |
| `frontend/src/context/AuthContext.tsx` | **Authentication State Provider:** Initializes `user` state synchronously from `localStorage` via `getStoredUser()` and exposes `useAuth()` consumed by `PublicRoute`. |
| `frontend/src/lib/auth.ts` | **Token & Session Storage Helper:** Reads and parses `bananavision_user` and `bananavision_token` from browser `localStorage`. |
| `frontend/src/pages/Landing.tsx` | **Landing Page View Component:** Eagerly loaded root page rendering the sticky glassmorphic header, mobile `Sheet` drawer, Hero section, About section, Key Features grid, System Modules cards, FAQs `Accordion`, Contact CTA, and Asia/Manila copyright footer. |
| `frontend/src/lib/manilaTime.ts` | **Asia/Manila Timezone Helper:** Exports `manilaDayKey()` used by the Landing Page footer (`manilaDayKey().slice(0, 4)`) to enforce Philippine Standard Time (`Asia/Manila`) year rendering. |
| `frontend/src/index.css` | **Global Styles, Tailwind v4 Theme & Keyframes:** Defines OKLCH color tokens (`--primary`, `--banana`, `--banana-light`, `--background`, etc.), dark mode variants, custom scrollbars, and the `.animate-fade-in` keyframe animation used in the Hero section. |
| `frontend/src/components/ui/button.tsx` | **Shadcn UI Button Primitive:** Renders CVA-styled buttons (`variant="default"`, `variant="outline"`, `variant="ghost"`, sizes `sm`, `lg`, `icon`) for desktop/mobile Login, Hero CTAs, and Contact Support. |
| `frontend/src/components/ui/sheet.tsx` | **Radix Dialog / Sheet Primitive:** Renders the slide-out right drawer (`side="right"`) for mobile navigation (`lg:hidden`). |
| `frontend/src/components/ui/accordion.tsx` | **Radix Accordion Primitive:** Renders the collapsible single-item FAQ accordion in the `#faqs` section. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Step 1: HTML Document Shell & Script Entry
* **Step Title & Trigger:** Visitor navigates to `http://localhost:5173/` (or the station host root `/`). The web server returns `index.html`.
* **Exact File Path & Line Numbers:** `frontend/index.html` (Lines 1–17)
* **Complete Uncut Code Block:**
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/bananavision-logo.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>BananaVision</title>
    <meta name="apple-mobile-web-app-title" content="BananaVision" />
    <meta name="application-name" content="BananaVision" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="mobile-web-app-capable" content="yes" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Line 5:** Loads `/bananavision-logo.svg` from `frontend/public/bananavision-logo.svg` as the browser tab icon (the same SVG asset is rendered inside the Landing Page navbar, mobile drawer header, and About section 3D card).
  * **Line 6:** Sets responsive viewport scaling (`width=device-width, initial-scale=1.0`), which governs Tailwind responsive breakpoints (`sm:`, `md:`, `lg:`) across the Landing Page.
  * **Line 14:** Declares `<div id="root"></div>`, the DOM mount container for React.
  * **Line 15:** Executes `/src/main.tsx` as an ES module, transferring control to React initialization.

---

### Step 2: React DOM Root Mounting & Global CSS Registration
* **Step Title & Trigger:** Browser executes `/src/main.tsx` referenced by `<script type="module" src="/src/main.tsx">`.
* **Exact File Path & Line Numbers:** `frontend/src/main.tsx` (Lines 1–11)
* **Complete Uncut Code Block:**
```tsx
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Line 4:** Imports `./index.css`, injecting Tailwind CSS v4 utility classes, custom theme variables (`--primary`, `--banana`, `--background`), and keyframe animations (`.animate-fade-in`) into the document prior to component render.
  * **Line 5:** Imports the top-level `<App />` component from `./App.tsx`.
  * **Lines 7–11:** Calls `createRoot(document.getElementById("root")!).render(...)` wrapping `<App />` in `<StrictMode>`, passing execution to `frontend/src/App.tsx`.

---

### Step 3: Client-Side Session Inspection (`localStorage` & `AuthProvider`)
* **Step Title & Trigger:** `<App />` mounts `<AuthProvider>`, which synchronously reads `localStorage` via `getStoredUser()` to determine whether the visitor is unauthenticated (show Landing Page) or already logged in (redirect to `/dashboard`).
* **Exact File Path & Line Numbers:** `frontend/src/lib/auth.ts` (Lines 1–64) and `frontend/src/context/AuthContext.tsx` (Lines 1–244)
* **Complete Uncut Code Block (`frontend/src/lib/auth.ts`, Lines 1–64):**
```ts
/**
 * Auth token management — localStorage wrappers.
 */

import { clearImageCache } from "@/lib/imageCache"
import { clearScanWrites } from "@/lib/scanWrites"

const TOKEN_KEY = "bananavision_token"
const USER_KEY = "bananavision_user"

export interface AuthUser {
  id: string
  username: string
  fullName: string
  role: "Admin" | "Operator"
  avatar?: string
}

// ── Token ───────────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  clearScanWrites()
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  clearScanWrites()
  clearImageCache()
  localStorage.removeItem(TOKEN_KEY)
}

// ── User ────────────────────────────────────────────────────────────────────

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

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
* **Complete Uncut Code Block (`frontend/src/context/AuthContext.tsx`, Lines 1–244):**
```tsx
import React, { createContext, useContext, useState, useCallback, useRef } from "react"
import { api } from "@/lib/api"
import {
  setToken,
  clearAuth,
  getStoredUser,
  setStoredUser,
  type AuthUser,
} from "@/lib/auth"
import type { Role } from "@/types"

// ── Types ───────────────────────────────────────────────────────────────────

interface AuthContextType {
  user: AuthUser | null
  login: (username: string, password?: string) =>
    Promise<
      | "success"
      | "failed"
      | "inactive"
      | "requires_password_change"
      | "requires_password_change_new_account"
      | "requires_password_change_reset"
    >
  /** Self-service password change — requires current password for verification. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>
  /** First-time / post-reset password setup — user proved identity at login. */
  setupPasswordAndLogin: (username: string, newPassword: string) => Promise<boolean>
  /** Self-service PIN change — requires current PIN for verification. */
  changePin: (currentPin: string, newPin: string) => Promise<boolean>
  /** First-time / post-reset PIN setup — user proved identity at PIN swap. */
  setupPinAndLogin: (username: string, newPin: string) => Promise<boolean>
  logout: () => void
  switchOperator: (username: string, pin: string) => Promise<"success" | "failed" | "inactive" | "requires_pin_change" | "requires_pin_change_new_account" | "requires_pin_change_reset">
  /** Update the currently authenticated user's data (for cross-context profile edits). */
  updateAuthUser: (data: Partial<AuthUser>, expectedUser?: Pick<AuthUser, "id" | "role">) => void
}

// ── Context ─────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | null>(null)

// ── Provider ────────────────────────────────────────────────────────────────

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

  // ── Switch Operator ─────────────────────────────────────────────────────

  const switchOperator = useCallback(async (username: string, pin: string) => {
    try {
      pinSetup.current = null
      const res = await api.auth.swap(username, pin)

      // Check status for PIN change requirements
      if (res.status === "requires_pin_change") {
        if (!res.setup_token) return "failed" as const
        pinSetup.current = { username, token: res.setup_token }
        if (res.reason === "new_account") return "requires_pin_change_new_account" as const
        if (res.reason === "pin_reset") return "requires_pin_change_reset" as const
        return "requires_pin_change" as const
      }

      if (res.status === "inactive") {
        return "inactive" as const
      }

      if (res.status === "failed" || !res.token || !res.user) {
        return "failed" as const
      }

      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return "success" as const
    } catch (error) {
      const status = (error as { status?: number } | null)?.status
      if (status === 401) return "failed" as const
      if (status === 403) return "inactive" as const
      throw error
    }
  }, [])

  // ── Logout ──────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    api.auth.logout().catch(() => {})
    passwordSetup.current = null
    pinSetup.current = null
    clearAuth()
    setUser(null)
  }, [])

  // ── Self-service Password Change (requires current password) ────────────

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    try {
      const res = await api.auth.changePassword(currentPassword, newPassword)
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

  // ── Self-service PIN Change (requires current PIN) ──────────────────────

  const changePin = useCallback(async (currentPin: string, newPin: string) => {
    try {
      const res = await api.auth.changePin(currentPin, newPin)
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

  // ── First-time / Post-reset PIN Setup ───────────────────────────────────

  const setupPinAndLogin = useCallback(async (username: string, newPin: string) => {
    if (!newPin || pinSetup.current?.username !== username) return false
    try {
      const res = await api.auth.setupPin(pinSetup.current.token, newPin)
      pinSetup.current = null
      if (!res.token || !res.user) return false
      setToken(res.token.access_token)
      const u = res.user
      const authUser: AuthUser = { id: u.id, username: u.username, fullName: u.full_name, role: u.role as Role, avatar: u.avatar_url }
      setStoredUser(authUser)
      setUser(authUser)
      return true
    } catch (error) {
      const status = (error as { status?: number } | null)?.status
      if (status === 0 || status === 429 || (status !== undefined && status >= 500)) throw error
      return false
    }
  }, [])

  // ── Update Auth User (cross-context) ────────────────────────────────────

  const updateAuthUser = useCallback((data: Partial<AuthUser>, expectedUser?: Pick<AuthUser, "id" | "role">) => {
    setUser((prev) => {
      if (!prev) return prev
      if (expectedUser && (prev.id !== expectedUser.id || prev.role !== expectedUser.role)) return prev
      const updated = { ...prev, ...data }
      setStoredUser(updated)
      return updated
    })
  }, [])

  return (
    <AuthContext value={{
      user,
      login,
      changePassword,
      setupPasswordAndLogin,
      changePin,
      setupPinAndLogin,
      logout,
      switchOperator,
      updateAuthUser,
    }}>
      {children}
    </AuthContext>
  )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be inside AuthProvider")
  return ctx
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`auth.ts` Lines 8–9 & 38–45:** `getStoredUser()` reads `localStorage.getItem("bananavision_user")`. If a JSON string is present, it parses and returns the `AuthUser` object (`{ id, username, fullName, role, avatar }`); otherwise, or on JSON parse failure, it returns `null`.
  * **`AuthContext.tsx` Line 46:** `useState<AuthUser | null>(() => getStoredUser())` uses a lazy initializer so `user` is populated on the very first render pass before any route guard runs.
  * **`AuthContext.tsx` Lines 240–244:** `useAuth()` provides `{ user, ... }` to route guards (`PublicRoute` and `ProtectedRoute`) in `App.tsx`.

---

### Step 4: Route Matching & `PublicRoute` Guard Execution
* **Step Title & Trigger:** `BrowserRouter` matches the URL path `/` against the route tree in `App.tsx` and evaluates `<PublicRoute><Landing /></PublicRoute>`.
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
  * **Line 13:** `import Landing from "@/pages/Landing"` imports `Landing` **eagerly** (not wrapped in `React.lazy`), ensuring zero chunk-loading delay on the initial root visit.
  * **Lines 52–56 (`PublicRoute` Middleware Guard):** Calls `const { user } = useAuth()`. If `user` is truthy (already logged in), it immediately returns `<Navigate to="/dashboard" replace />`. If `user` is `null`, it renders `<>{children}</>` (`<Landing />`).
  * **Line 67:** Maps `path="/"` to `<PublicRoute><Landing /></PublicRoute>`.
  * **Line 86:** Maps any unknown URL (`path="*"`) to `<Navigate to="/" replace />`, funneling invalid routes back to the Landing Page (or `/dashboard` if authenticated).
  * **Line 107:** `ThemeProvider` sets `defaultTheme="light"` under `localStorage` key `"bananavision-theme"` (and also binds the global `D` keyboard shortcut to toggle light/dark mode).
  * **Lines 110–116:** The outer `<Routes>` checks `/track/:scanId` first; for `/`, it matches `path="*"` on Line 115 and renders `<StaffApp />` → `<AppRoutes />` → `<PublicRoute><Landing /></PublicRoute>`.

---

### Step 5: Complete Landing Page Component (`Landing.tsx`) — State, Scroll-Spy, Navbar, Hero, Sections, FAQs, Contact & Footer
* **Step Title & Trigger:** `PublicRoute` allows unauthenticated access and mounts `Landing` in `frontend/src/pages/Landing.tsx`.
* **Exact File Path & Line Numbers:** `frontend/src/pages/Landing.tsx` (Lines 1–350)
* **Complete Uncut Code Block:**
```tsx
import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { CheckCircle2, Factory, BarChart3, ShieldCheck, Mail, ChevronRight, Menu, ScanLine, PackageOpen, ScrollText } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { manilaDayKey } from "@/lib/manilaTime"

const navLinks = [
  { label: "Home", id: "home" },
  { label: "About", id: "about" },
  { label: "Key Features", id: "features" },
  { label: "Modules", id: "modules" },
  { label: "FAQs", id: "faqs" },
  { label: "Contact", id: "contact" },
]

export default function Landing() {
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSection, setActiveSection] = useState("home")
  
  const scrollToSection = (id: string) => {
    setMobileOpen(false)
    // Small delay so sheet closes before scrolling
    setTimeout(() => {
      const el = document.getElementById(id)
      if (el) {
        window.scrollTo({
          top: el.offsetTop - 80,
          behavior: "smooth"
        })
      }
    }, 150)
  }

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        })
      },
      { rootMargin: "-40% 0px -40% 0px" }
    )

    navLinks.forEach((link) => {
      const el = document.getElementById(link.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-background flex flex-col font-sans">
      {/* Navigation Bar */}
      <header className="sticky top-0 z-50 w-full border-b border-white/20 dark:border-white/5 bg-white/70 dark:bg-background/70 backdrop-blur-xl shadow-sm">
        <div className="container mx-auto px-4 h-16 sm:h-20 flex items-center justify-between">
          <button className="flex items-center gap-2 cursor-pointer bg-transparent border-none p-0" onClick={() => scrollToSection("home")} aria-label="Go to home section">
            <div className="flex items-center justify-center">
              <img src="/bananavision-logo.svg" alt="Logo" className="w-10 h-10 object-contain" />
            </div>
            <span className="font-bold text-lg text-foreground">BananaVision</span>
          </button>

          {/* Desktop Nav */}
          <nav className="hidden lg:flex items-center gap-1">
            {navLinks.map((link) => (
              <button
                key={link.label}
                onClick={() => scrollToSection(link.id)}
                className={`px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  activeSection === link.id
                    ? "text-primary bg-primary/10"
                    : "text-foreground/70 hover:text-primary hover:bg-primary/5"
                }`}
              >
                {link.label}
              </button>
            ))}
            <Button onClick={() => navigate("/login")} variant="default" size="sm" className="ml-2">
              Login to System
            </Button>
          </nav>

          {/* Mobile Nav */}
          <div className="lg:hidden flex items-center">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Menu className="h-5 w-5" />
                  <span className="sr-only">Toggle menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-70 sm:w-[320px] p-0">
                <SheetTitle className="sr-only">Navigation Menu</SheetTitle>
                <div className="flex flex-col h-full">
                  {/* Sheet Header */}
                  <div className="flex items-center gap-2 px-6 py-4 border-b bg-banana/30">
                    <div className="flex items-center justify-center">
                      <img src="/bananavision-logo.svg" alt="Logo" className="w-10 h-10 object-contain" />
                    </div>
                    <span className="font-bold text-lg">BananaVision</span>
                  </div>
                  {/* Sheet Links */}
                  <nav className="flex flex-col flex-1 px-4 py-4">
                    {navLinks.map((link) => (
                      <button
                        key={link.label}
                        onClick={() => scrollToSection(link.id)}
                        className={`text-left text-base font-medium px-3 py-3 rounded-lg transition-colors ${
                          activeSection === link.id
                            ? "text-primary bg-primary/10"
                            : "text-foreground/80 hover:text-primary hover:bg-primary/5"
                        }`}
                      >
                        {link.label}
                      </button>
                    ))}
                  </nav>
                  {/* Sheet Footer */}
                  <div className="px-6 pb-6">
                    <Button onClick={() => { setMobileOpen(false); navigate("/login") }} variant="default" className="w-full h-11">
                      Login to System
                    </Button>
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Home / Hero Section */}
        <section id="home" className="relative pt-24 pb-24 lg:pt-32 lg:pb-32 overflow-hidden px-4 flex flex-col items-center justify-center min-h-[85vh]">
          {/* Enhanced Background Blurs */}
          <div className="absolute top-[-5%] left-1/2 -translate-x-1/2 w-full max-w-250 h-125 bg-primary/20 rounded-full blur-[120px] -z-10" />
          <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCI+PHBhdGggZD0iTTAgMGg0MHY0MEgweiIgZmlsbD0ibm9uZSIvPjxwYXRoIGQ9Ik0wIDBoMXY0MEgwek0zOSAwaDF2NDBIMzl6IiBmaWxsPSJyZ2JhKDAsIDAsIDAsIDAuMDIpIi8+PHBhdGggZD0iTTAgMGg0MHYxSDB6TTAgMzloNDB2MUgweiIgZmlsbD0icmdiYSgwLCAwLCAwLCAwLjAyKSIvPjwvc3ZnPg==')] opacity-60 -z-10 mix-blend-overlay" />
          
          <div className="container mx-auto text-center max-w-4xl animate-fade-in relative z-10 w-full">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/60 dark:bg-card/60 text-primary mb-6 text-sm font-bold border border-primary/20 shadow-[0_4px_20px_rgba(234,179,8,0.15)] backdrop-blur-xl">
              <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse"></span>
              Banana Classification System
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight mb-6 text-foreground drop-shadow-sm leading-[1.15]">
              Smarter Classification with <br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-linear-to-r from-primary via-yellow-500 to-orange-500 pb-1 drop-shadow-md inline-block mt-1">BananaVision</span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed">
              An AI-powered banana classification system built for Medium and Large Enterprises. 
              Classify cultivar and ripeness in seconds, keep track of your stock, and reduce waste.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full max-w-md mx-auto sm:max-w-none">
              <Button onClick={() => navigate("/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                Access Dashboard <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
              <Button onClick={() => scrollToSection("about")} variant="outline" size="lg" className="h-14 px-10 w-full sm:w-auto text-lg font-bold border-2 bg-white/50 backdrop-blur-sm hover:bg-primary/5 transition-all duration-300">
                Learn More
              </Button>
            </div>
          </div>
        </section>

        {/* About Section */}
        <section id="about" className="relative py-24 px-4 border-y border-border/50 overflow-hidden bg-linear-to-b from-primary/5 to-background">
          <div className="absolute left-0 right-0 top-0 h-px bg-linear-to-r from-transparent via-primary/20 to-transparent" />
          <div className="container mx-auto max-w-5xl relative z-10">
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div className="space-y-6">
                <div className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold bg-banana-light text-banana-foreground">
                  Our Mission
                </div>
                <h2 className="text-3xl md:text-4xl font-bold">About BananaVision</h2>
                <p className="text-muted-foreground leading-relaxed">
                  BananaVision is an enterprise-grade AI solution built to solve real challenges faced by medium and large enterprises in the banana supply chain. 
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  Using AI and camera-based recognition, the system identifies the banana variety, determines how ripe it is, and estimates how long it will last — helping businesses speed up their scanning process and reduce product waste.
                </p>
              </div>
              <div className="relative perspective-1000">
                <div className="aspect-4/3 md:aspect-square rounded-[3rem] bg-linear-to-br from-white/90 to-white/40 dark:from-white/10 dark:to-white/5 backdrop-blur-2xl border border-white/60 dark:border-white/20 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] flex items-center justify-center relative overflow-hidden group hover:rotate-3 transition-transform duration-700 ease-out">
                  <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-size-[24px_24px]" />
                  <div className="absolute -inset-2 bg-linear-to-tr from-primary/40 via-transparent to-orange-400/40 blur-2xl opacity-50 group-hover:opacity-100 transition-opacity duration-700" />
                  <div className="w-32 h-32 sm:w-48 sm:h-48 bg-white/90 dark:bg-black/50 backdrop-blur-2xl rounded-full flex items-center justify-center shadow-2xl border border-white/50 dark:border-white/10 relative z-10 transition-transform duration-700 group-hover:scale-110">
                    <img src="/bananavision-logo.svg" alt="BananaVision Logo" className="w-20 h-20 sm:w-28 sm:h-28 object-contain drop-shadow-xl" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Key Features Section */}
        <section id="features" className="relative py-24 px-4 overflow-hidden bg-linear-to-b from-background to-primary/5">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-200 h-200 bg-primary/20 rounded-full blur-[120px] -z-10 pointer-events-none" />
          <div className="container mx-auto max-w-5xl text-center space-y-12 relative z-10">
            <div className="space-y-4">
              <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">Key Features</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto text-lg">
                Everything your business needs to modernize banana handling and classification.
              </p>
            </div>
            
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8 text-left relative z-10">
              {[
                { icon: ScanLine, title: "AI-Assisted Scanning", desc: "Recognizes banana varieties (Lakatan, Latundan, Cardaba), determines ripeness level, and automatically estimates shelf life." },
                { icon: Factory, title: "Operator Kiosk", desc: "A simple, touch-friendly screen where warehouse workers can quickly scan bananas one delivery at a time." },
                { icon: ShieldCheck, title: "Scan Review", desc: "Unsure classification results are easily flagged so a manager can double-check and correct them later." },
                { icon: PackageOpen, title: "Inventory Tracking", desc: "See how much stock you have by variety and ripeness, with alerts when items are about to spoil." },
                { icon: BarChart3, title: "Reports & Charts", desc: "View easy-to-read charts showing daily output, intake results, and worker performance." },
                { icon: ScrollText, title: "Full Scan History", desc: "Browse and search through every scan ever made, filtered by date, intake, or worker." },
              ].map((feature, i) => (
                <div key={i} className="group p-8 rounded-[2.5rem] bg-white/70 dark:bg-card/40 backdrop-blur-xl border border-white/60 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_20px_40px_rgb(234,179,8,0.1)] hover:-translate-y-2 transition-all duration-500 relative overflow-hidden flex flex-col">
                  {/* Subtle top glare */}
                  <div className="absolute top-0 left-0 right-0 h-25 bg-linear-to-b from-white/80 dark:from-white/5 to-transparent opacity-60 pointer-events-none" />
                  <div className="absolute inset-0 bg-linear-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                  
                  <div className="w-14 h-14 bg-linear-to-br from-primary/20 to-primary/5 border border-primary/20 rounded-[1rem] flex items-center justify-center mb-6 text-primary group-hover:scale-110 group-hover:shadow-lg group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-all duration-500 relative z-10">
                    <feature.icon className="w-7 h-7 drop-shadow-sm" />
                  </div>
                  <h3 className="text-2xl font-bold mb-3 group-hover:text-primary transition-colors relative z-10 tracking-tight">{feature.title}</h3>
                  <p className="text-muted-foreground leading-relaxed flex-1 relative z-10 font-medium">{feature.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Modules Section */}
        <section id="modules" className="relative py-24 px-4 border-y border-border/50 overflow-hidden bg-linear-to-b from-primary/5 to-background">
          <div className="absolute inset-0 bg-grid-black/[0.02] bg-size-[32px_32px] -z-10 pointer-events-none" />
          <div className="container mx-auto max-w-5xl space-y-12 relative z-10">
            <div className="text-center space-y-4">
              <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">System Modules</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto text-lg">
                Different views for different roles — operators scan, managers oversee.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-8 relative z-10">
              {[
                { 
                  num: "1", title: "Operator Kiosk", desc: "A focused scanning screen for warehouse workers.", 
                  items: ["Quick switch between operators using a PIN", "Multi-angle camera capture", "Choose which delivery source to scan for", "Accept good scans or flag for review", "See recent scan results instantly"]
                },
                { 
                  num: "2", title: "Operator Dashboard", desc: "A simplified dashboard showing only the operator's own work.", 
                  items: ["View your own scan results", "Personal scan history", "Charts showing your performance", "Check current stock & freshness alerts", "See if cameras are working"]
                },
                { 
                  num: "3", title: "Admin Dashboard", desc: "Complete visibility and control for managers.", 
                  items: ["Monitor all scans across the system", "Track inventory with freshness alerts", "View detailed charts and reports", "Review and correct scan results", "Manage users, suppliers & devices", "View activity history & system settings"]
                }
              ].map((module) => (
                <div key={module.num} className="group relative p-8 lg:p-10 rounded-[2.5rem] bg-white/80 dark:bg-card/40 backdrop-blur-2xl border border-white/60 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_20px_40px_rgb(234,179,8,0.12)] hover:-translate-y-2 transition-all duration-500 overflow-hidden flex flex-col">
                  {/* Glassmorphic glare */}
                  <div className="absolute top-0 left-0 right-0 h-37.5 bg-linear-to-b from-white/70 dark:from-white/5 to-transparent opacity-80 pointer-events-none" />
                  
                  <div className="absolute -right-24 -top-24 w-48 h-48 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/25 transition-all duration-700" />
                  
                  <h3 className="text-2xl lg:text-3xl font-bold mb-4 flex items-center gap-4 relative z-10 tracking-tight">
                    <span className="w-12 h-12 rounded-[1rem] bg-linear-to-br from-primary/20 to-primary/5 border border-primary/20 flex items-center justify-center text-primary group-hover:bg-primary group-hover:text-primary-foreground group-hover:shadow-lg group-hover:scale-110 transition-all duration-500 text-lg font-black">
                      {module.num}
                    </span>
                    {module.title}
                  </h3>
                  <p className="text-base text-muted-foreground mb-8 relative z-10 flex-1 leading-relaxed font-medium">
                    {module.desc}
                  </p>
                  
                  <div className="w-full h-px bg-linear-to-r from-border/50 to-transparent mb-6 relative z-10" />
                  
                  <ul className="space-y-4 relative z-10">
                    {module.items.map((item, i) => (
                      <li key={i} className="flex items-start gap-3 text-muted-foreground text-sm group-hover:text-foreground/90 transition-colors">
                        <CheckCircle2 className="w-5 h-5 text-primary shrink-0 mt-0.5 drop-shadow-sm" /> 
                        <span className="leading-snug">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQs Section */}
        <section id="faqs" className="relative py-24 px-4 overflow-hidden bg-linear-to-b from-background to-primary/5">
          <div className="container mx-auto max-w-3xl space-y-12 relative z-10">
            <div className="text-center space-y-4">
              <h2 className="text-3xl md:text-4xl font-bold">Frequently Asked Questions</h2>
            </div>
            
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="item-1">
                <AccordionTrigger className="text-left text-lg">Who is this system built for?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  BananaVision is made for medium and large enterprises that handle banana packaging and distribution. It helps workers classify bananas faster and gives managers a clear picture of their inventory.
                </AccordionContent>
              </AccordionItem>
              <AccordionItem value="item-2">
                <AccordionTrigger className="text-left text-lg">Does it need an internet connection?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  Internet access is optional. On-site scanning, AI analysis, dashboards, and the database all run on the local mini PC with no cloud service, so tablets or computers on the same LAN or hotspot work without internet. Internet is only needed for remote access or for a public QR tracking link to open from outside the station network.
                </AccordionContent>
              </AccordionItem>
              <AccordionItem value="item-3">
                <AccordionTrigger className="text-left text-lg">What hardware is needed?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  The scanning station uses a mini PC that runs the entire system. It connects to external webcams for capturing banana images and an external monitor that displays the Kiosk interface for the operator. Other devices can access the dashboard by connecting to the mini PC over the local network.
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </section>

        {/* Contact Support Section */}
        <section id="contact" className="relative py-24 px-4 border-t border-border/50 text-center overflow-hidden bg-linear-to-b from-primary/5 to-primary/10">
          <div className="absolute bottom-0 left-0 right-0 h-px bg-linear-to-r from-transparent via-primary/30 to-transparent" />
          <div className="container mx-auto max-w-2xl space-y-8 relative z-10">
            <div className="w-16 h-16 bg-primary/10 rounded-2xl mx-auto flex items-center justify-center text-primary">
              <Mail className="w-8 h-8" />
            </div>
            <h2 className="text-3xl md:text-4xl font-bold">Need Help?</h2>
            <p className="text-muted-foreground">
              Have questions about setting up BananaVision for your business? We're here to help.
            </p>
            <Button 
              size="lg" 
              className="h-12 px-8"
              onClick={() => window.location.href = "mailto:support@bananavision.com"}
            >
              Contact Support Team
            </Button>
          </div>
        </section>
      </main>

      <footer className="py-8 border-t bg-background text-center text-muted-foreground text-sm">
        <p>© {manilaDayKey().slice(0, 4)} BananaVision. All rights reserved.</p>
      </footer>
    </div>
  )
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 10–17 (`navLinks`):** Defines the 6 single-page section descriptors (`home`, `about`, `features`, `modules`, `faqs`, `contact`). Every `id` matches a `<section id="...">` element inside `<main>`.
  * **Lines 20–22:** Initializes React Router `navigate = useNavigate()`, mobile Sheet drawer state `mobileOpen` (`false`), and scroll-spy state `activeSection` (`"home"`).
  * **Lines 24–36 (`scrollToSection`):** Closes the mobile drawer (`setMobileOpen(false)`), waits `150ms` via `setTimeout` for the drawer close transition, looks up `document.getElementById(id)`, and smoothly scrolls to `el.offsetTop - 80` (`80px` sticky navbar offset).
  * **Lines 38–56 (`useEffect` Scroll-Spy):** Instantiates an `IntersectionObserver` with `rootMargin: "-40% 0px -40% 0px"` (central 20% viewport band), observes all 6 sections, and updates `activeSection` when a section intersects.
  * **Lines 61–136 (`<header>` Sticky Navbar):**
    * **Line 61:** Frosted glass sticky header (`sticky top-0 z-50 w-full border-b border-white/20 dark:border-white/5 bg-white/70 dark:bg-background/70 backdrop-blur-xl shadow-sm`).
    * **Lines 63–68:** Logo button calling `scrollToSection("home")`.
    * **Lines 71–88:** Desktop navigation (`hidden lg:flex`) highlighting the active section with `"text-primary bg-primary/10"` and rendering `<Button onClick={() => navigate("/login")} variant="default" size="sm" className="ml-2">Login to System</Button>`.
    * **Lines 91–134:** Mobile navigation (`lg:hidden`) rendering `<Sheet open={mobileOpen} onOpenChange={setMobileOpen}>` with a right-side drawer (`side="right"`), `bg-banana/30` header, section buttons, and a mobile `"Login to System"` button calling `{ setMobileOpen(false); navigate("/login") }`.
  * **Lines 140–167 (`#home` Hero Section):**
    * **Lines 142–143:** Radial golden blur (`bg-primary/20 rounded-full blur-[120px] -z-10`) and inline base64 SVG grid background.
    * **Line 145:** Hero text wrapper using `.animate-fade-in`.
    * **Lines 150–153:** Extra-bold headline with gradient text (`text-transparent bg-clip-text bg-linear-to-r from-primary via-yellow-500 to-orange-500`).
    * **Lines 159–164:** Primary CTA `"Access Dashboard"` (`onClick={() => navigate("/login")}`) and Secondary CTA `"Learn More"` (`onClick={() => scrollToSection("about")}`).
  * **Lines 170–197 (`#about` Section):** 2-column grid (`grid md:grid-cols-2 gap-12 items-center`) with `"Our Mission"` pill (`bg-banana-light text-banana-foreground`) and 3D hover-rotating logo card (`group hover:rotate-3`).
  * **Lines 200–233 (`#features` Section):** 3-column grid (`grid sm:grid-cols-2 lg:grid-cols-3 gap-8`) rendering 6 glassmorphic feature cards (`ScanLine`, `Factory`, `ShieldCheck`, `PackageOpen`, `BarChart3`, `ScrollText`).
  * **Lines 236–291 (`#modules` Section):** 3-column grid (`grid md:grid-cols-3 gap-8`) detailing `1: Operator Kiosk`, `2: Operator Dashboard`, and `3: Admin Dashboard`.
  * **Lines 294–321 (`#faqs` Section):** Single-collapsible `<Accordion type="single" collapsible className="w-full">` with 3 items (`item-1`, `item-2`, `item-3`).
  * **Lines 324–342 (`#contact` Section):** Support CTA executing `window.location.href = "mailto:support@bananavision.com"`.
  * **Lines 345–347 (`<footer>`):** Displays `© {manilaDayKey().slice(0, 4)} BananaVision. All rights reserved.` in Philippine Standard Time (`Asia/Manila`).

---

### Step 6: Asia/Manila Footer Timezone Helper (`manilaTime.ts`)
* **Step Title & Trigger:** Called on Line 346 of `frontend/src/pages/Landing.tsx` (`manilaDayKey().slice(0, 4)`) during footer render.
* **Exact File Path & Line Numbers:** `frontend/src/lib/manilaTime.ts` (Lines 1–49)
* **Complete Uncut Code Block:**
```ts
/**
 * The one frontend time zone. Every date or time the app shows, groups by day or puts in
 * a file name is Asia/Manila, whatever zone the viewing machine uses. The backend
 * counterpart is backend/app/core/time.py. tests/manilaTime.test.mjs rejects any other
 * date formatting in src/.
 */
export const MANILA_TIME_ZONE = "Asia/Manila"

/** The caller's format options with the Manila zone; the zone cannot be overridden. */
export function inManila<T extends Intl.DateTimeFormatOptions>(options?: T): T & { timeZone: string } {
  return { ...(options ?? ({} as T)), timeZone: MANILA_TIME_ZONE }
}

const dayParts = new Intl.DateTimeFormat("en-CA", inManila({ year: "numeric", month: "2-digit", day: "2-digit" }))

/** Manila calendar day of an instant as YYYY-MM-DD (business dates, file names). */
export function manilaDayKey(time: number | Date = Date.now()): string {
  const parts: Record<string, string> = {}
  for (const part of dayParts.formatToParts(time)) parts[part.type] = part.value
  return `${parts.year}-${parts.month}-${parts.day}`
}

/**
 * The Manila calendar day as a local Date at midnight. Date pickers work in local
 * calendar days, so this marks "today" as the day it is in Manila.
 */
export function manilaToday(time: number | Date = Date.now()): Date {
  const [year, month, day] = manilaDayKey(time).split("-").map(Number)
  return new Date(year, month - 1, day)
}

const BUSINESS_DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Whether a stored business date (YYYY-MM-DD, already a Manila day) or an instant falls on
 * today's Manila calendar day. Unreadable values are never today.
 */
export function isManilaToday(value: string | null | undefined, now: number | Date = Date.now()): boolean {
  if (!value) return false
  let day: string
  if (BUSINESS_DATE.test(value)) {
    day = value
  } else {
    const instant = Date.parse(value)
    if (Number.isNaN(instant)) return false
    day = manilaDayKey(instant)
  }
  return day === manilaDayKey(now)
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 7–15:** Enforces `MANILA_TIME_ZONE = "Asia/Manila"` inside `Intl.DateTimeFormat("en-CA", ...)`.
  * **Lines 17–21:** `manilaDayKey()` formats the current timestamp into `"YYYY-MM-DD"` in Manila time. Slicing `(0, 4)` in `Landing.tsx` extracts the 4-digit year while passing `frontend/tests/manilaTime.test.mjs`.

---

### Step 7: UI Primitives (`button.tsx`, `sheet.tsx`, `accordion.tsx`) & Global Stylesheet (`index.css`)
* **Step Title & Trigger:** Invoked by `Landing.tsx` to render styled buttons, the mobile navigation drawer, the FAQ accordion, and Tailwind v4 theme variables/animations.
* **Exact File Path & Line Numbers:**
  * `frontend/src/components/ui/button.tsx` (Lines 1–67)
  * `frontend/src/components/ui/sheet.tsx` (Lines 1–145)
  * `frontend/src/components/ui/accordion.tsx` (Lines 1–79)
  * `frontend/src/index.css` (Lines 1–333)
* **Complete Uncut Code Block (`frontend/src/components/ui/button.tsx`, Lines 1–67):**
```tsx
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
```
* **Complete Uncut Code Block (`frontend/src/components/ui/sheet.tsx`, Lines 1–145):**
```tsx
import * as React from "react"
import { Dialog as SheetPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { XIcon } from "lucide-react"

function Sheet({ ...props }: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetPortal({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      {...props}
    />
  )
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: "top" | "right" | "bottom" | "left"
  showCloseButton?: boolean
}) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        data-side={side}
        className={cn(
          "fixed z-50 flex flex-col gap-4 bg-popover bg-clip-padding text-sm text-popover-foreground shadow-lg transition duration-200 ease-in-out data-[side=bottom]:inset-x-0 data-[side=bottom]:bottom-0 data-[side=bottom]:h-auto data-[side=bottom]:border-t data-[side=left]:inset-y-0 data-[side=left]:left-0 data-[side=left]:h-full data-[side=left]:w-3/4 data-[side=left]:border-r data-[side=right]:inset-y-0 data-[side=right]:right-0 data-[side=right]:h-full data-[side=right]:w-3/4 data-[side=right]:border-l data-[side=top]:inset-x-0 data-[side=top]:top-0 data-[side=top]:h-auto data-[side=top]:border-b data-[side=left]:sm:max-w-sm data-[side=right]:sm:max-w-sm data-open:animate-in data-open:fade-in-0 data-[side=bottom]:data-open:slide-in-from-bottom-10 data-[side=left]:data-open:slide-in-from-left-10 data-[side=right]:data-open:slide-in-from-right-10 data-[side=top]:data-open:slide-in-from-top-10 data-closed:animate-out data-closed:fade-out-0 data-[side=bottom]:data-closed:slide-out-to-bottom-10 data-[side=left]:data-closed:slide-out-to-left-10 data-[side=right]:data-closed:slide-out-to-right-10 data-[side=top]:data-closed:slide-out-to-top-10",
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close data-slot="sheet-close" asChild>
            <Button
              variant="ghost"
              className="absolute top-3 right-3"
              size="icon-sm"
            >
              <XIcon
              />
              <span className="sr-only">Close</span>
            </Button>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-0.5 p-4", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  )
}

function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn(
        "font-heading text-base font-medium text-foreground",
        className
      )}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
```
* **Complete Uncut Code Block (`frontend/src/components/ui/accordion.tsx`, Lines 1–79):**
```tsx
import * as React from "react"
import { Accordion as AccordionPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { ChevronDownIcon, ChevronUpIcon } from "lucide-react"

function Accordion({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Root>) {
  return (
    <AccordionPrimitive.Root
      data-slot="accordion"
      className={cn("flex w-full flex-col", className)}
      {...props}
    />
  )
}

function AccordionItem({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Item>) {
  return (
    <AccordionPrimitive.Item
      data-slot="accordion-item"
      className={cn("not-last:border-b", className)}
      {...props}
    />
  )
}

function AccordionTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="flex">
      <AccordionPrimitive.Trigger
        data-slot="accordion-trigger"
        className={cn(
          "group/accordion-trigger relative flex flex-1 items-start justify-between rounded-lg border border-transparent py-2.5 text-left text-sm font-medium transition-all outline-none hover:underline focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:after:border-ring disabled:pointer-events-none disabled:opacity-50 **:data-[slot=accordion-trigger-icon]:ml-auto **:data-[slot=accordion-trigger-icon]:size-4 **:data-[slot=accordion-trigger-icon]:text-muted-foreground",
          className
        )}
        {...props}
      >
        {children}
        <ChevronDownIcon data-slot="accordion-trigger-icon" className="pointer-events-none shrink-0 group-aria-expanded/accordion-trigger:hidden" />
        <ChevronUpIcon data-slot="accordion-trigger-icon" className="pointer-events-none hidden shrink-0 group-aria-expanded/accordion-trigger:inline" />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
}

function AccordionContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content
      data-slot="accordion-content"
      className="overflow-hidden text-sm data-open:animate-accordion-down data-closed:animate-accordion-up"
      {...props}
    >
      <div
        className={cn(
          "h-(--radix-accordion-content-height) pt-0 pb-2.5 [&_a]:underline [&_a]:underline-offset-3 [&_a]:hover:text-foreground [&_p:not(:last-child)]:mb-4",
          className
        )}
      >
        {children}
      </div>
    </AccordionPrimitive.Content>
  )
}

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent }
```
* **Complete Uncut Code Block (`frontend/src/index.css`, Lines 1–333):**
```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/plus-jakarta-sans";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Plus Jakarta Sans Variable', sans-serif;
    --color-sidebar-ring: var(--sidebar-ring);
    --color-sidebar-border: var(--sidebar-border);
    --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
    --color-sidebar-accent: var(--sidebar-accent);
    --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
    --color-sidebar-primary: var(--sidebar-primary);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --color-sidebar: var(--sidebar);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
    --color-ring: var(--ring);
    --color-input: var(--input);
    --color-border: var(--border);
    --color-destructive: var(--destructive);
    --color-accent-foreground: var(--accent-foreground);
    --color-accent: var(--accent);
    --color-muted-foreground: var(--muted-foreground);
    --color-muted: var(--muted);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-secondary: var(--secondary);
    --color-primary-foreground: var(--primary-foreground);
    --color-primary: var(--primary);
    --color-popover-foreground: var(--popover-foreground);
    --color-popover: var(--popover);
    --color-card-foreground: var(--card-foreground);
    --color-card: var(--card);
    --color-foreground: var(--foreground);
    --color-background: var(--background);
    --color-banana: var(--banana);
    --color-banana-foreground: var(--banana-foreground);
    --color-banana-light: var(--banana-light);
    --color-banana-dark: var(--banana-dark);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: oklch(0.99 0.002 90);
    --foreground: oklch(0.12 0.01 80);
    --card: oklch(1 0 0);
    --card-foreground: oklch(0.12 0.01 80);
    --popover: oklch(1 0 0);
    --popover-foreground: oklch(0.12 0.01 80);
    --primary: oklch(0.68 0.20 85);
    --primary-foreground: oklch(0.99 0.005 85);
    --secondary: oklch(0.96 0.01 90);
    --secondary-foreground: oklch(0.15 0.01 80);
    --muted: oklch(0.97 0.005 90);
    --muted-foreground: oklch(0.48 0.01 80);
    --accent: oklch(0.96 0.015 85);
    --accent-foreground: oklch(0.15 0.01 80);
    --destructive: oklch(0.577 0.245 27.325);
    --border: oklch(0.88 0.015 85);
    --input: oklch(0.88 0.015 85);
    --ring: oklch(0.68 0.20 85);
    --banana: oklch(0.82 0.18 88);
    --banana-foreground: oklch(0.20 0.06 75);
    --banana-light: oklch(0.95 0.08 90);
    --banana-dark: oklch(0.60 0.18 82);
    --chart-1: oklch(0.82 0.18 88);
    --chart-2: oklch(0.68 0.16 145);
    --chart-3: oklch(0.62 0.22 25);
    --chart-4: oklch(0.58 0.14 250);
    --chart-5: oklch(0.72 0.12 320);
    --radius: 0.75rem;
    --sidebar: oklch(0.995 0.002 85);
    --sidebar-foreground: oklch(0.20 0.02 80);
    --sidebar-primary: oklch(0.68 0.20 85);
    --sidebar-primary-foreground: oklch(0.99 0.005 85);
    --sidebar-accent: oklch(0.95 0.015 85);
    --sidebar-accent-foreground: oklch(0.15 0.01 80);
    --sidebar-border: oklch(0.90 0.015 85);
    --sidebar-ring: oklch(0.68 0.20 85);
}

.dark {
    --background: oklch(0.11 0.015 80);
    --foreground: oklch(0.97 0.005 80);
    --card: oklch(0.16 0.015 80);
    --card-foreground: oklch(0.97 0.005 80);
    --popover: oklch(0.16 0.015 80);
    --popover-foreground: oklch(0.97 0.005 80);
    --primary: oklch(0.85 0.18 88);
    --primary-foreground: oklch(0.12 0.04 80);
    --secondary: oklch(0.22 0.015 80);
    --secondary-foreground: oklch(0.97 0.005 80);
    --muted: oklch(0.20 0.015 80);
    --muted-foreground: oklch(0.65 0.01 80);
    --accent: oklch(0.24 0.02 85);
    --accent-foreground: oklch(0.97 0.005 80);
    --destructive: oklch(0.65 0.22 25);
    --border: oklch(0.28 0.02 80);
    --input: oklch(0.22 0.02 80);
    --ring: oklch(0.85 0.18 88);
    --banana: oklch(0.85 0.18 88);
    --banana-foreground: oklch(0.12 0.04 80);
    --banana-light: oklch(0.32 0.08 88);
    --banana-dark: oklch(0.72 0.16 85);
    --chart-1: oklch(0.85 0.18 88);
    --chart-2: oklch(0.68 0.16 145);
    --chart-3: oklch(0.62 0.20 25);
    --chart-4: oklch(0.58 0.14 250);
    --chart-5: oklch(0.72 0.12 320);
    --sidebar: oklch(0.14 0.015 80);
    --sidebar-foreground: oklch(0.88 0.01 80);
    --sidebar-primary: oklch(0.85 0.18 88);
    --sidebar-primary-foreground: oklch(0.12 0.04 80);
    --sidebar-accent: oklch(0.22 0.02 85);
    --sidebar-accent-foreground: oklch(0.97 0.005 80);
    --sidebar-border: oklch(0.25 0.02 80);
    --sidebar-ring: oklch(0.85 0.18 88);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
  html {
    @apply font-sans scroll-smooth;
  }

  /* Custom Scrollbar Styles */
  ::-webkit-scrollbar {
    width: 12px;
    height: 12px;
  }

  ::-webkit-scrollbar-track {
    background: var(--muted);
    border-radius: 6px;
  }

  ::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 6px;
    border: 2px solid var(--muted);
    transition: background 0.2s ease;
  }

  ::-webkit-scrollbar-thumb:hover {
    background: var(--banana);
  }

  ::-webkit-scrollbar-thumb:active {
    background: var(--primary);
  }

  /* Firefox Scrollbar */
  * {
    scrollbar-width: thin;
    scrollbar-color: var(--border) var(--muted);
  }

  /* Kiosk scrollbar — narrower but still theme-aware */
  .kiosk-scroll::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  .kiosk-scroll::-webkit-scrollbar-track {
    background: var(--muted);
    border-radius: 4px;
  }

  .kiosk-scroll::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 4px;
    border: 1px solid var(--muted);
  }

  .kiosk-scroll::-webkit-scrollbar-thumb:hover {
    background: var(--banana);
  }

  .kiosk-scroll::-webkit-scrollbar-thumb:active {
    background: var(--primary);
  }

  .kiosk-scroll {
    scrollbar-width: thin;
    scrollbar-color: var(--border) var(--muted);
  }
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slide-in-left {
  from { opacity: 0; transform: translateX(-16px); }
  to { opacity: 1; transform: translateX(0); }
}

@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 0 0 oklch(0.88 0.17 90 / 0.4); }
  50% { box-shadow: 0 0 20px 6px oklch(0.88 0.17 90 / 0.25); }
}

@keyframes scan-line {
  0% { transform: translateY(0); }
  100% { transform: translateY(100%); }
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}

.animate-fade-in {
  animation: fade-in 0.4s ease-out forwards;
}

@keyframes fade-in-row {
  from { opacity: 0; }
  to { opacity: 1; }
}

.animate-fade-in-row {
  animation: fade-in-row 0.35s ease-out forwards;
}

.animate-slide-in-left {
  animation: slide-in-left 0.3s ease-out forwards;
}

.animate-pulse-glow {
  animation: pulse-glow 2s ease-in-out infinite;
}

.animate-shimmer {
  animation: shimmer 2s ease-in-out infinite;
}

.animate-slide {
  animation: slide 1.5s ease-in-out infinite;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  15% { transform: translateX(-6px); }
  30% { transform: translateX(5px); }
  45% { transform: translateX(-4px); }
  60% { transform: translateX(3px); }
  75% { transform: translateX(-2px); }
}

.animate-shake {
  animation: shake 0.45s ease-in-out;
}

.stagger-1 { animation-delay: 0.05s; }
.stagger-2 { animation-delay: 0.1s; }
.stagger-3 { animation-delay: 0.15s; }
.stagger-4 { animation-delay: 0.2s; }
.stagger-5 { animation-delay: 0.25s; }
.stagger-6 { animation-delay: 0.3s; }

/* Print Styles */
@media print {
  @page {
    margin: 1cm;
  }
  
  body {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  
  aside, nav, button:not(.print-keep), .print\:hidden, .no-print {
    display: none !important;
  }
  
  main {
    width: 100% !important;
    max-width: 100% !important;
    padding: 0 !important;
  }
  
  table {
    page-break-inside: auto;
  }
  
  tr {
    page-break-inside: avoid;
    page-break-after: auto;
  }
  
  thead {
    display: table-header-group;
  }
  
  .rounded-2xl, .rounded-xl {
    border-radius: 0 !important;
  }
  
  .shadow-lg, .shadow-md {
    box-shadow: none !important;
  }
}

/* Hide tooltips on mobile / touch — no hover available */
@media (max-width: 767px) {
  [data-slot="tooltip-content"] {
    display: none !important;
  }
}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`index.css` Lines 42–45 & 74–77:** Registers the custom BananaVision color tokens (`--banana`, `--banana-foreground`, `--banana-light`, `--banana-dark`) and maps them to Tailwind utility classes (`bg-banana/30` in the mobile Sheet header, `bg-banana-light text-banana-foreground` in the About section badge).
  * **`index.css` Lines 62–63 & 101–102:** Defines `--primary: oklch(0.68 0.20 85)` in light mode and `--primary: oklch(0.85 0.18 88)` in dark mode, driving all `text-primary`, `bg-primary`, and `border-primary` classes across `Landing.tsx`.
  * **`index.css` Lines 206–209 & 236–238:** Defines `@keyframes fade-in` and `.animate-fade-in`, animating the Hero container on initial load.
  * **`sheet.tsx` Lines 69–81:** `SheetContent` automatically renders a top-right close button (`<XIcon />`) unless `showCloseButton={false}` is passed.
  * **`accordion.tsx` Lines 49–50:** `AccordionTrigger` renders both `<ChevronDownIcon>` and `<ChevronUpIcon>`, toggling visibility via `group-aria-expanded/accordion-trigger:hidden` and `group-aria-expanded/accordion-trigger:inline`.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Concept | Exact Value / Location in Codebase |
| :--- | :--- |
| **Root Route Definition** | `<Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />` in `frontend/src/App.tsx` (Line 67) |
| **Route Guard Component** | `PublicRoute` in `frontend/src/App.tsx` (Lines 52–56) — redirects to `/dashboard` if `useAuth().user` is non-null |
| **Landing Page Component** | `frontend/src/pages/Landing.tsx` (Lines 19–350, eagerly imported on Line 13 of `App.tsx`) |
| **Section IDs (`navLinks`)** | `home`, `about`, `features`, `modules`, `faqs`, `contact` (`Landing.tsx` Lines 10–17) |
| **Scroll Offset & Delay** | `el.offsetTop - 80` (`80px` sticky navbar offset) after a `150ms` `setTimeout` (`Landing.tsx` Lines 24–36) |
| **Scroll-Spy Mechanism** | `IntersectionObserver` with `rootMargin: "-40% 0px -40% 0px"` (`Landing.tsx` Lines 38–56) |
| **Navigation CTAs to Login** | Desktop Header (`Line 85`), Mobile Sheet Footer (`Line 127`), Hero Primary Button (`Line 159`) — all call `navigate("/login")` |
| **Hero Secondary CTA** | `"Learn More"` (`Line 162`) — calls `scrollToSection("about")` |
| **Contact Support CTA** | `"Contact Support Team"` (`Line 337`) — sets `window.location.href = "mailto:support@bananavision.com"` |
| **Footer Year Rule** | `manilaDayKey().slice(0, 4)` from `frontend/src/lib/manilaTime.ts` (`Landing.tsx` Line 346) — **never** use `new Date().getFullYear()` |
| **Key Custom CSS Classes** | `.animate-fade-in`, `bg-banana/30`, `bg-banana-light`, `text-banana-foreground`, `bg-linear-to-r` (Tailwind v4 syntax) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Allow Logged-In Users to View the Landing Page and Conditionally Render `"Go to Dashboard"` vs. `"Login to System"`
* **Examiner Prompt:** *"Right now, an authenticated user visiting `/` is immediately redirected to `/dashboard`. Modify the app so logged-in users can view the Landing Page at `/`, and conditionally change the navbar and hero buttons to say `'Go to Dashboard'` (navigating to `/dashboard`) when logged in, or `'Login to System'` / `'Access Dashboard'` (navigating to `/login`) when logged out."*
* **Files to Edit:**
  1. `frontend/src/App.tsx` (Line 67)
  2. `frontend/src/pages/Landing.tsx` (Lines 1–23, 85–87, 127–129, 159–161)

* **Modification 1 — `frontend/src/App.tsx` (Line 67):**
  * **Before:**
```tsx
        <Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />
```
  * **After:**
```tsx
        <Route path="/" element={<Landing />} />
```

* **Modification 2 — `frontend/src/pages/Landing.tsx` (Imports & Hook at Lines 1–23):**
  * **Before:**
```tsx
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { manilaDayKey } from "@/lib/manilaTime"
```
  * **After:**
```tsx
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { useAuth } from "@/context/AuthContext"
import { manilaDayKey } from "@/lib/manilaTime"
```
  *(Inside `export default function Landing()`, add `const { user } = useAuth()` right below `const navigate = useNavigate()` on Line 20.)*

* **Modification 3 — `frontend/src/pages/Landing.tsx` (Desktop Nav, Mobile Sheet Footer, and Hero CTA at Lines 85–87, 127–129, 159–161):**
  * **Before (Desktop Nav, Lines 85–87):**
```tsx
            <Button onClick={() => navigate("/login")} variant="default" size="sm" className="ml-2">
              Login to System
            </Button>
```
  * **After (Desktop Nav):**
```tsx
            <Button onClick={() => navigate(user ? "/dashboard" : "/login")} variant="default" size="sm" className="ml-2">
              {user ? "Go to Dashboard" : "Login to System"}
            </Button>
```
  * **Before (Mobile Sheet Footer, Lines 127–129):**
```tsx
                    <Button onClick={() => { setMobileOpen(false); navigate("/login") }} variant="default" className="w-full h-11">
                      Login to System
                    </Button>
```
  * **After (Mobile Sheet Footer):**
```tsx
                    <Button onClick={() => { setMobileOpen(false); navigate(user ? "/dashboard" : "/login") }} variant="default" className="w-full h-11">
                      {user ? "Go to Dashboard" : "Login to System"}
                    </Button>
```
  * **Before (Hero Primary CTA, Lines 159–161):**
```tsx
              <Button onClick={() => navigate("/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                Access Dashboard <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
```
  * **After (Hero Primary CTA):**
```tsx
              <Button onClick={() => navigate(user ? "/dashboard" : "/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                {user ? "Go to Dashboard" : "Access Dashboard"} <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
```

---

#### Drill Scenario 2: Add a Direct `"Open Operator Kiosk"` CTA Button to the Hero Section and Update the Hero Headline
* **Examiner Prompt:** *"Warehouse tablets often boot to the Landing Page and need a 1-tap button to open the `/kiosk` route directly without going through the staff `/login` screen, plus an updated hero headline reading `'Enterprise Banana Grading with BananaVision'`."*
* **File to Edit:** `frontend/src/pages/Landing.tsx` (Lines 150–165)
* **Before (`frontend/src/pages/Landing.tsx`, Lines 150–165):**
```tsx
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight mb-6 text-foreground drop-shadow-sm leading-[1.15]">
              Smarter Classification with <br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-linear-to-r from-primary via-yellow-500 to-orange-500 pb-1 drop-shadow-md inline-block mt-1">BananaVision</span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed">
              An AI-powered banana classification system built for Medium and Large Enterprises. 
              Classify cultivar and ripeness in seconds, keep track of your stock, and reduce waste.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full max-w-md mx-auto sm:max-w-none">
              <Button onClick={() => navigate("/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                Access Dashboard <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
              <Button onClick={() => scrollToSection("about")} variant="outline" size="lg" className="h-14 px-10 w-full sm:w-auto text-lg font-bold border-2 bg-white/50 backdrop-blur-sm hover:bg-primary/5 transition-all duration-300">
                Learn More
              </Button>
            </div>
```
* **After (`frontend/src/pages/Landing.tsx`, Lines 150–168):**
```tsx
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight mb-6 text-foreground drop-shadow-sm leading-[1.15]">
              Enterprise Banana Grading with <br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-linear-to-r from-primary via-yellow-500 to-orange-500 pb-1 drop-shadow-md inline-block mt-1">BananaVision</span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed">
              An AI-powered banana classification system built for Medium and Large Enterprises. 
              Classify cultivar and ripeness in seconds, keep track of your stock, and reduce waste.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full max-w-md mx-auto sm:max-w-none">
              <Button onClick={() => navigate("/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                Access Dashboard <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
              <Button onClick={() => navigate("/kiosk")} variant="secondary" size="lg" className="h-14 px-10 w-full sm:w-auto text-lg font-bold transition-all duration-300">
                Open Operator Kiosk
              </Button>
              <Button onClick={() => scrollToSection("about")} variant="outline" size="lg" className="h-14 px-10 w-full sm:w-auto text-lg font-bold border-2 bg-white/50 backdrop-blur-sm hover:bg-primary/5 transition-all duration-300">
                Learn More
              </Button>
            </div>
```
