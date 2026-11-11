import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { createOrganization } from '../../api/auth'
import { useSession } from '../../session/context'
import { authenticatedHomePath, pendingAuthenticationPath } from '../../session/sessionModel'
import AuthField from './AuthField'
import AuthShell from './AuthShell'

export default function OnboardingPage() {
  const {
    authenticationError,
    authenticationStatus,
    currentUser,
    logout,
    pendingFlow,
    refreshSession,
  } = useSession()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (authenticationStatus === 'loading') {
    return <p className="session-gate" role="status">Checking your session…</p>
  }
  if (authenticationStatus === 'error') {
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
  if (authenticationStatus === 'pending' && pendingFlow) {
    return <Navigate to={pendingAuthenticationPath(pendingFlow) || '/login'} replace />
  }
  if (authenticationStatus !== 'authenticated') {
    return <Navigate to="/login" replace />
  }
  if (currentUser && authenticatedHomePath(currentUser) === '/app') {
    return <Navigate to="/app" replace />
  }
  if (!currentUser) {
    return (
      <main className="session-gate">
        <h1>Account details are unavailable</h1>
        <p role="alert">Your session was confirmed, but the account profile could not be loaded.</p>
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const organization = await createOrganization(name.trim())
      const session = await refreshSession()
      if (
        session.status !== 'authenticated' ||
        !session.user.memberships.some(
          (membership) => membership.organization_id === organization.id,
        )
      ) {
        throw new Error('Workspace creation was not confirmed by your account session.')
      }
      navigate('/app', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create the workspace.')
      setSubmitting(false)
    }
  }

  async function signOut() {
    setError(null)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign out.')
    }
  }

  return (
    <AuthShell
      eyebrow="Set up your workspace"
      title="Create your workspace"
      description="Your workspace is where AgentGate keeps its agents, policies, approvals, and audit history."
    >
      <form onSubmit={submit}>
        <AuthField
          label="Workspace name"
          autoComplete="organization"
          minLength={2}
          maxLength={200}
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          hint="You will become its initial administrator. A name does not join an existing workspace."
        />
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Creating workspace…' : 'Create workspace'}
        </button>
      </form>
      <p className="auth-form-footer">
        Signed in as {currentUser.email}.{' '}
        <button type="button" className="auth-text-button" onClick={() => void signOut()}>
          Sign out
        </button>
      </p>
    </AuthShell>
  )
}
