import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import {
  changeVerificationEmail,
  resendVerificationCode,
  verifyEmail,
} from '../api/auth'
import AuthShell from './AuthShell'

interface VerificationState {
  email?: string
}

function maskedEmail(email: string) {
  const [name, domain] = email.split('@')
  if (!name || !domain) return 'your email address'
  return `${name.slice(0, 1)}${'*'.repeat(Math.min(Math.max(name.length - 1, 3), 6))}@${domain}`
}

export default function VerifyEmailPage() {
  const location = useLocation()
  const state = location.state as VerificationState | null
  const [email, setEmail] = useState(state?.email ?? '')
  const [nextResendIn, setNextResendIn] = useState(30)
  const [code, setCode] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [showChangeEmail, setShowChangeEmail] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [verified, setVerified] = useState(false)

  useEffect(() => {
    if (nextResendIn <= 0) return
    const timer = window.setTimeout(() => setNextResendIn((remaining) => remaining - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [nextResendIn])

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    try {
      await verifyEmail(code.trim().toUpperCase())
      setVerified(true)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'This verification code is invalid or has expired. Request a new one.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function resendCode() {
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    try {
      await resendVerificationCode()
      setNextResendIn(30)
      setSuccess(`A new verification code was sent to ${maskedEmail(email)}.`)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Could not resend the verification code. Please try again later.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function submitEmailChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    try {
      await changeVerificationEmail(newEmail.trim())
      setEmail(newEmail.trim())
      setCode('')
      setNextResendIn(30)
      setShowChangeEmail(false)
      setSuccess(`A new verification code was sent to ${maskedEmail(newEmail.trim())}.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not change the email address.')
    } finally {
      setSubmitting(false)
    }
  }

  if (verified) {
    return (
      <AuthShell eyebrow="Email confirmed" title="You’re verified">
        <p className="auth-success" role="status">
          Your email address has been verified. You can now sign in to AgentGate.
        </p>
        <Link className="btn btn-primary btn-block" to="/login">
          Continue to sign in
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      eyebrow="Check your inbox"
      title="Verify your email"
      description={
        email
          ? `We sent a verification code to ${maskedEmail(email)}. It expires after 15 minutes.`
          : 'Enter the verification code from your email to finish creating your account.'
      }
    >
      <form onSubmit={submitCode}>
        <div className="field">
          <label htmlFor="verification-code">Email verification code</label>
          <input
            id="verification-code"
            name="code"
            type="text"
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            required
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            aria-invalid={Boolean(error)}
          />
          <span className="hint">The code contains eight letters or numbers separated by a hyphen.</span>
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        {success ? <p className="auth-success" role="status">{success}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Verifying…' : 'Verify email'}
        </button>
      </form>

      <div className="auth-actions">
        <button
          type="button"
          className="auth-text-button"
          onClick={() => void resendCode()}
          disabled={submitting || nextResendIn > 0}
        >
          {nextResendIn > 0 ? `Resend code in ${nextResendIn}s` : 'Resend verification code'}
        </button>
        <button
          type="button"
          className="auth-text-button"
          onClick={() => setShowChangeEmail((shown) => !shown)}
          disabled={submitting}
        >
          Change email
        </button>
      </div>

      {showChangeEmail ? (
        <form className="auth-inline-form" onSubmit={submitEmailChange}>
          <div className="field">
            <label htmlFor="new-email">New email address</label>
            <input
              id="new-email"
              type="email"
              autoComplete="email"
              required
              value={newEmail}
              onChange={(event) => setNewEmail(event.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-secondary" disabled={submitting}>
            Update
          </button>
        </form>
      ) : null}

      <Link className="auth-back-link" to="/login">Back to sign in</Link>
    </AuthShell>
  )
}
