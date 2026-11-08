import type { ComponentType } from 'react'
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
  useLoaderData,
} from 'react-router'
import { getAuthStatus, type AuthStatus } from './api/auth'
import SessionProvider from './session/SessionProvider'
import AppLayout from './ui/AppLayout'
import ToastProvider from './ui/ToastProvider'

/** Load each page on demand, so the landing page does not download the whole dashboard. */
function page(load: () => Promise<{ default: ComponentType }>) {
  return async () => ({ Component: (await load()).default })
}

async function loadDashboardSession() {
  try {
    return await getAuthStatus()
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Could not verify the dashboard session.',
    }
  }
}

function ProtectedAppLayout() {
  const session = useLoaderData() as AuthStatus | { error: string }

  if ('error' in session) {
    return (
      <main className="auth-loading" role="alert">
        <p>{session.error}</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => window.location.reload()}
        >
          Try again
        </button>
      </main>
    )
  }
  if (!session.authenticated) return <Navigate to="/login" replace />
  return <AppLayout user={session.user} />
}

// A data router (not BrowserRouter) so pages can use useBlocker to guard unsaved edits.
const router = createBrowserRouter(
  createRoutesFromElements(
    <Route hydrateFallbackElement={<p className="visually-hidden">Loading…</p>}>
      <Route index lazy={page(() => import('./pages/LandingPage'))} />
      <Route path="login" lazy={page(() => import('./pages/LoginPage'))} />
      <Route path="app" loader={loadDashboardSession} element={<ProtectedAppLayout />}>
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
