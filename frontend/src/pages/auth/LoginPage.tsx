import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import AuthField from './AuthField'
import AuthShell from './AuthShell'
import { useSession } from '../../session/context'

interface LoginLocationState {
  from?: { pathname?: string }
  email?: string
}

export default function LoginPage() {
  const { login } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = location.state as LoginLocationState | null
  const [email, setEmail] = useState(locationState?.email ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await login(email.trim(), password)
      setPassword('')
      if (result.kind === 'authenticated') {
        const destination = locationState?.from?.pathname
        navigate(destination?.startsWith('/app') ? destination : '/app', { replace: true })
      } else if (result.kind === 'mfa') {
        navigate('/mfa', { state: { email: email.trim(), types: result.types } })
      } else {
        navigate('/verify-email', { state: { email: email.trim() } })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sign-in failed.')
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Dashboard access"
      title="Sign in"
      description="Sign in to continue to the AgentGate dashboard."
    >
      <form onSubmit={submit}>
        <AuthField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <AuthField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          revealable
        />
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/register">Create an account</Link>
      </div>
    </AuthShell>
  )
}
