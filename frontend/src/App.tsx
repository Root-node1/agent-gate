import { BrowserRouter, Route, Routes } from 'react-router'
import LandingPage from './pages/LandingPage'
import NotFoundPage from './pages/NotFoundPage'
import AgentDetailPage from './pages/app/AgentDetailPage'
import AgentsPage from './pages/app/AgentsPage'
import ApprovalDetailPage from './pages/app/ApprovalDetailPage'
import ApprovalsPage from './pages/app/ApprovalsPage'
import AuditLogPage from './pages/app/AuditLogPage'
import OverviewPage from './pages/app/OverviewPage'
import PoliciesPage from './pages/app/PoliciesPage'
import PolicyEditPage from './pages/app/PolicyEditPage'
import SettingsPage from './pages/app/SettingsPage'
import SimulatePage from './pages/app/SimulatePage'
import TransactionDetailPage from './pages/app/TransactionDetailPage'
import TransactionsPage from './pages/app/TransactionsPage'
import RequestDetailPage from './pages/live/RequestDetailPage'
import RequestsPage from './pages/live/RequestsPage'
import TesterPage from './pages/live/TesterPage'
import SessionProvider from './session/SessionProvider'
import AppLayout from './ui/AppLayout'
import ToastProvider from './ui/ToastProvider'

export default function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route index element={<LandingPage />} />
            <Route path="app" element={<AppLayout />}>
              <Route index element={<OverviewPage />} />
              <Route path="approvals" element={<ApprovalsPage />} />
              <Route path="approvals/:id" element={<ApprovalDetailPage />} />
              <Route path="transactions" element={<TransactionsPage />} />
              <Route path="transactions/:id" element={<TransactionDetailPage />} />
              <Route path="agents" element={<AgentsPage />} />
              <Route path="agents/:id" element={<AgentDetailPage />} />
              <Route path="policies" element={<PoliciesPage />} />
              <Route path="policies/:id" element={<PolicyEditPage />} />
              <Route path="audit" element={<AuditLogPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="simulate" element={<SimulatePage />} />
              <Route path="live" element={<TesterPage />} />
              <Route path="live/requests" element={<RequestsPage />} />
              <Route path="live/requests/:id" element={<RequestDetailPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
            <Route path="*" element={<AppLayout />}>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </SessionProvider>
  )
}
