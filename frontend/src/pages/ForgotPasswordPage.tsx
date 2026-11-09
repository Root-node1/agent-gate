import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { requestPasswordReset } from '../api/auth'
import AuthShell from './AuthShell'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await requestPasswordReset(email.trim())
      setSent(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not request a password reset.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Account recovery"
      title={sent ? 'Check your email' : 'Forgot your password?'}
      description={
        sent
          ? 'If an account exists for that address, we sent instructions to reset its password.'
          : 'Enter the work email associated with your account and we’ll send password reset instructions.'
      }
    >
      {!sent ? (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="reset-email">Work email</label>
            <input
              id="reset-email"
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(error)}
            />
          </div>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? 'Sending…' : 'Send reset instructions'}
          </button>
        </form>
      ) : (
        <p className="auth-success" role="status">
          The message may take a few minutes to arrive. You can safely close this page.
        </p>
      )}
      <p className="auth-form-footer">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthShell>
  )
}
