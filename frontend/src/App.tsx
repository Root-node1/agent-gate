import type { ComponentType } from 'react'
import { createBrowserRouter, createRoutesFromElements, Route, RouterProvider } from 'react-router'
import SessionProvider from './session/SessionProvider'
import { ProtectedDashboard, PublicAuthentication } from './session/SessionGuards'
import AppLayout from './ui/AppLayout'
import ToastProvider from './ui/ToastProvider'

/** Load each page on demand, so the landing page does not download the whole dashboard. */
function page(load: () => Promise<{ default: ComponentType }>) {
  return async () => ({ Component: (await load()).default })
}

const router = createBrowserRouter(
  createRoutesFromElements(
    <Route hydrateFallbackElement={<p className="visually-hidden">Loading…</p>}>
      <Route index lazy={page(() => import('./pages/LandingPage'))} />
      <Route path="how-it-works" lazy={page(() => import('./pages/HowItWorksPage'))} />
      <Route path="features" lazy={page(() => import('./pages/FeaturesPage'))} />
      <Route path="downloads" lazy={page(() => import('./pages/DownloadsPage'))} />
      <Route path="system-requirements" lazy={page(() => import('./pages/SystemRequirementsPage'))} />
      <Route path="install" lazy={page(() => import('./pages/InstallationPage'))} />
      <Route path="onboarding" lazy={page(() => import('./pages/auth/OnboardingPage'))} />
      <Route element={<ProtectedDashboard />}>
        <Route path="app" element={<AppLayout />}>
          <Route index lazy={page(() => import('./pages/app/OverviewPage'))} />
          <Route path="approvals" lazy={page(() => import('./pages/app/ApprovalsPage'))} />
          <Route path="approvals/:id" lazy={page(() => import('./pages/app/ApprovalDetailPage'))} />
          <Route path="transactions" lazy={page(() => import('./pages/app/TransactionsPage'))} />
          <Route path="transactions/:id" lazy={page(() => import('./pages/app/TransactionDetailPage'))} />
          <Route path="agents" lazy={page(() => import('./pages/app/AgentsPage'))} />
          <Route path="agents/:id" lazy={page(() => import('./pages/app/AgentDetailPage'))} />
          <Route path="policies" lazy={page(() => import('./pages/app/PoliciesPage'))} />
          <Route path="policies/:id" lazy={page(() => import('./pages/app/PolicyEditPage'))} />
          <Route path="audit" lazy={page(() => import('./pages/app/AuditLogPage'))} />
          <Route path="settings" lazy={page(() => import('./pages/app/SettingsPage'))} />
          <Route path="simulate" lazy={page(() => import('./pages/app/SimulatePage'))} />
          <Route path="live" lazy={page(() => import('./pages/live/TesterPage'))} />
          <Route path="live/requests" lazy={page(() => import('./pages/live/RequestsPage'))} />
          <Route path="live/requests/:id" lazy={page(() => import('./pages/live/RequestDetailPage'))} />
          <Route path="*" lazy={page(() => import('./pages/NotFoundPage'))} />
        </Route>
      </Route>
      <Route element={<PublicAuthentication />}>
        <Route path="login" lazy={page(() => import('./pages/auth/LoginPage'))} />
        <Route path="register" lazy={page(() => import('./pages/auth/RegisterPage'))} />
      </Route>
      <Route path="mfa" lazy={page(() => import('./pages/auth/MfaPage'))} />
      <Route path="verify-email" lazy={page(() => import('./pages/auth/VerifyEmailPage'))} />
      <Route path="forgot-password" lazy={page(() => import('./pages/auth/ForgotPasswordPage'))} />
      <Route path="reset-password/:key" lazy={page(() => import('./pages/auth/ResetPasswordPage'))} />
      <Route path="*" lazy={page(() => import('./pages/NotFoundPage'))} />
    </Route>,
  ),
)

export default function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </SessionProvider>
  )
}
