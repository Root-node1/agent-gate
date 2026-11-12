import { Navigate, Outlet, useLocation } from 'react-router'
import { useSession } from './context'
import { authenticatedHomePath, pendingAuthenticationPath } from './sessionModel'

function SessionProblem() {
  const { authenticationError, refreshSession } = useSession()
  return (
    <main className="session-gate" aria-live="polite">
      <h1>Could not verify your session</h1>
      <p role="alert">{authenticationError || 'The authentication service is unavailable.'}</p>
      <button
        type="button"
        className="btn btn-primary"
        onClick={() => void refreshSession().catch(() => undefined)}
      >
        Try again
      </button>
    </main>
  )
}

export function ProtectedDashboard() {
  const { authenticationStatus, currentUser, pendingFlow } = useSession()
  const location = useLocation()
  if (authenticationStatus === 'loading') {
    return <p className="session-gate" role="status">Checking your session…</p>
  }
  if (authenticationStatus === 'error') return <SessionProblem />
  if (authenticationStatus === 'pending' && pendingFlow) {
    const destination = pendingAuthenticationPath(pendingFlow)
    if (destination) return <Navigate to={destination} replace />
  }
  if (authenticationStatus !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (currentUser && authenticatedHomePath(currentUser) !== '/app') {
    return <Navigate to={authenticatedHomePath(currentUser)} replace />
  }
  return <Outlet />
}

export function PublicAuthentication() {
  const { authenticationStatus, currentUser, pendingFlow } = useSession()
  if (authenticationStatus === 'loading') {
    return <p className="session-gate" role="status">Checking your session…</p>
  }
  if (authenticationStatus === 'error') return <SessionProblem />
  if (authenticationStatus === 'authenticated') {
    return (
      <Navigate
        to={currentUser ? authenticatedHomePath(currentUser) : '/onboarding'}
        replace
      />
    )
  }
  if (authenticationStatus === 'pending' && pendingFlow) {
    const destination = pendingAuthenticationPath(pendingFlow)
    if (destination) return <Navigate to={destination} replace />
  }
  return <Outlet />
}
