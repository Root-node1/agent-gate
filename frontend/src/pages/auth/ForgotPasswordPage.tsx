import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import Logo from '../../components/Logo'
import { bootstrapCsrf, requestPasswordReset } from '../../api/auth'
import AuthField from './AuthField'
import './AuthPages.css'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  useEffect(() => {
    void bootstrapCsrf()
  }, [])

  function validate(): string | null {
    if (!email) return 'Enter your email address.'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Enter a valid email address.'
    return null
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setServerError(validate())
    if (validate()) return
    setSubmitting(true)
    setServerError(null)
    try {
      await requestPasswordReset(email)
      setSubmitted(true)
    } catch (err: unknown) {
      setServerError(
        err instanceof Error ? err.message : 'Could not send the reset email. Try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card card">
        <div className="auth-header">
          <Logo />
          <h1>Forgot your password?</h1>
          <p className="muted">Enter your email and we'll send you a reset link.</p>
        </div>
        {submitted ? (
          <div className="stack">
            <p className="hint">
              If an account matches that email, a reset link has been sent. It
              expires in 1 hour.
            </p>
            <p>
              Didn't receive it? Check your spam, or{' '}
              <button
                type="button"
                className="link"
                onClick={() => setSubmitted(false)}
              >
                try again
              </button>
              .
            </p>
            <Link to="/" className="btn btn-secondary btn-block">
              Back to home
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} noValidate>
            {serverError && <p className="form-error" role="alert">{serverError}</p>}
            <AuthField
              label="Email address"
              id="af-forgot-email"
              type="email"
              autoComplete="email"
              autoFocus
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={serverError && !email ? serverError : undefined}
            />
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send reset link'}
            </button>
          </form>
        )}
      </div>
      <p className="auth-foot muted">
        <Link to="/">Back to AgentGate home</Link>
      </p>
    </div>
  )
}
