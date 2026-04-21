import React, { Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { AppProvider, useApp } from "@/context/AppContext"
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
const Kiosk = React.lazy(() => import("@/pages/Kiosk"))

// Lazy load admin pages
const UserManagement = React.lazy(() => import("@/pages/admin/UserManagement"))
const SystemConfig = React.lazy(() => import("@/pages/admin/SystemConfig"))
const QualityControl = React.lazy(() => import("@/pages/admin/QualityControl"))
const ActivityLog = React.lazy(() => import("@/pages/admin/ActivityLog"))
const IntakeManagement = React.lazy(() => import("@/pages/admin/IntakeManagement"))
const SupplierManagement = React.lazy(() => import("@/pages/admin/SupplierManagement"))

// Loading fallback component
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
  </div>
)

// Protected Route Wrapper
function ProtectedRoute({ children, reqAdmin = false }: { children: React.ReactNode; reqAdmin?: boolean }) {
  const { user } = useApp()
  if (!user) return <Navigate to="/" replace />
  if (reqAdmin && user.role !== "Admin") return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

// Public Route Wrapper
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user } = useApp()
  if (user) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
        <Route path="/kiosk" element={<ProtectedRoute><Kiosk /></ProtectedRoute>} />
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/devices" element={<DeviceStatus />} />
          <Route path="/scans/:scanId" element={<ScanDetail />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin/users" element={<ProtectedRoute reqAdmin><UserManagement /></ProtectedRoute>} />
          <Route path="/admin/intakes" element={<ProtectedRoute reqAdmin><IntakeManagement /></ProtectedRoute>} />
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

function App() {
  return (
    <ThemeProvider defaultTheme="light" storageKey="bananavision-theme">
      <AppProvider>
        <BrowserRouter>
          <AppRoutes />
          <Toaster position="top-center" richColors />
        </BrowserRouter>
      </AppProvider>
    </ThemeProvider>
  )
}

export default App
