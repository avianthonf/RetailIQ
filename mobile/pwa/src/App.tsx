import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { MaintenanceBanner } from '@/components/MaintenanceBanner'
import { Layout } from '@/components/Layout'

// Auth pages
import { WelcomePage } from '@/pages/auth/WelcomePage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { OTPPage } from '@/pages/auth/OTPPage'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage'
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage'

// Main pages
import { DashboardPage } from '@/pages/dashboard/DashboardPage'
import { InventoryPage } from '@/pages/inventory/InventoryPage'
import { POSPage } from '@/pages/pos/POSPage'
import { SuppliersPage } from '@/pages/suppliers/SuppliersPage'
import { PricingPage } from '@/pages/pricing/PricingPage'
import { LoyaltyPage } from '@/pages/loyalty/LoyaltyPage'
import { AnalyticsPage } from '@/pages/analytics/AnalyticsPage'
import { SettingsPage } from '@/pages/settings/SettingsPage'

function App() {
  const { isAuthenticated, isMaintenance } = useAuthStore()

  if (isMaintenance) {
    return (
      <>
        <MaintenanceBanner />
        <div className="min-h-screen flex items-center justify-center bg-neutral-900 text-white">
          <div className="text-center">
            <h1 className="text-4xl font-bold mb-4">System Under Maintenance</h1>
            <p className="text-lg text-neutral-300">We'll be back shortly. Thank you for your patience.</p>
          </div>
        </div>
      </>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <Routes>
        {/* Public routes */}
        <Route path="/auth/welcome" element={<WelcomePage />} />
        <Route path="/auth/register" element={<RegisterPage />} />
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="/auth/otp" element={<OTPPage />} />
        <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/auth/reset-password" element={<ResetPasswordPage />} />

        {/* Redirect root to welcome or dashboard */}
        <Route 
          path="/" 
          element={
            isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/auth/welcome" replace />
          } 
        />

        {/* Protected routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Layout>
                <DashboardPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/inventory"
          element={
            <ProtectedRoute>
              <Layout>
                <InventoryPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/pos"
          element={
            <ProtectedRoute>
              <Layout>
                <POSPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/suppliers"
          element={
            <ProtectedRoute>
              <Layout>
                <SuppliersPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/pricing"
          element={
            <ProtectedRoute>
              <Layout>
                <PricingPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/loyalty"
          element={
            <ProtectedRoute>
              <Layout>
                <LoyaltyPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/analytics"
          element={
            <ProtectedRoute>
              <Layout>
                <AnalyticsPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <Layout>
                <SettingsPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        {/* 404 */}
        <Route path="*" element={<div>Page not found</div>} />
      </Routes>
    </div>
  )
}

export default App
