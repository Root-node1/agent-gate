import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
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

        <p className="auth-footnote">
          Dashboard accounts are created by an administrator. There is no public sign-up.
        </p>
      </section>
    </main>
  )
}
