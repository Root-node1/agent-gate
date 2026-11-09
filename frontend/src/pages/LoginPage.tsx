import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { getAuthOptions, setRememberSession, type AuthOptions } from '../api/auth'
import { useSession } from '../session/context'
import { PasswordField } from './AuthFields'
import AuthProviders from './AuthProviders'
import AuthShell from './AuthShell'

export default function LoginPage() {
  const { login } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [options, setOptions] = useState<AuthOptions | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)

  useEffect(() => {
    void getAuthOptions()
      .then(setOptions)
      .catch((cause: unknown) => {
        setOptionsError(
          cause instanceof Error ? cause.message : 'Could not load sign-in options.',
        )
      })
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await login(email.trim(), password)
      if (result.kind === 'authenticated') {
        await setRememberSession(remember)
        navigate('/app', { replace: true })
      } else if (result.kind === 'mfa') {
        navigate('/mfa', { state: { email, remember, types: result.types } })
      } else {
        navigate('/verify-email', { state: { email } })
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
      description="Sign in to review and govern your AI agents’ spending."
    >
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={Boolean(error)}
          />
        </div>
        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        <div className="auth-form-options">
          <label className="auth-check-row">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            <span>Remember me</span>
          </label>
          <Link to="/forgot-password">Forgot password?</Link>
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <div className="auth-divider" aria-hidden="true">
        <span>or continue with</span>
      </div>
      {options ? <AuthProviders options={options} /> : optionsError ? (
        <p className="auth-error" role="alert">{optionsError}</p>
      ) : (
        <p className="auth-provider-note" role="status">Loading sign-in options…</p>
      )}

      <p className="auth-form-footer">
        New to AgentGate? <Link to="/register">Create an account</Link>
      </p>
    </AuthShell>
  )
}
