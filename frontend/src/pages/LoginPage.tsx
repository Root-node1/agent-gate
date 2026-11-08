import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { getAuthOptions } from '../api/auth'
import Logo from '../components/Logo'
import { useSession } from '../session/context'
import './LoginPage.css'

export default function LoginPage() {
  const { login } = useSession()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [googleOptions, setGoogleOptions] = useState<
    { csrfToken: string; enabled: boolean } | null
  >(null)
  const [googleOptionsError, setGoogleOptionsError] = useState<string | null>(null)

  useEffect(() => {
    void getAuthOptions()
      .then(({ csrfToken, googleOAuthEnabled }) => {
        setGoogleOptions({ csrfToken, enabled: googleOAuthEnabled })
      })
      .catch((cause: unknown) => {
        setGoogleOptionsError(
          cause instanceof Error ? cause.message : 'Could not load Google sign-in options.',
        )
      })
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(username, password)
      navigate('/app', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sign-in failed.')
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <Link to="/" className="auth-brand" aria-label="AgentGate home">
          <Logo />
        </Link>
        <p className="auth-eyebrow">Dashboard access</p>
        <h1 id="auth-title">Sign in</h1>
        <p className="auth-intro">Use your dashboard account to continue to the sample workspace.</p>

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="auth-divider" aria-hidden="true">
          <span>or</span>
        </div>
        {googleOptions?.enabled ? (
          <form method="post" action="/accounts/google/login/">
            <input type="hidden" name="csrfmiddlewaretoken" value={googleOptions.csrfToken} />
            <input type="hidden" name="process" value="login" />
            <button type="submit" className="btn btn-secondary btn-block auth-google">
              <span className="auth-google-mark" aria-hidden="true">G</span>
              Continue with Google
            </button>
          </form>
        ) : googleOptionsError ? (
          <p className="auth-provider-note" role="status">{googleOptionsError}</p>
        ) : googleOptions ? (
          <p className="auth-provider-note">Google sign-in is not configured for this installation.</p>
        ) : null}

        <p className="auth-footnote">
          You can sign in with a dashboard account or create one with Google.
        </p>
      </section>
    </main>
  )
}
