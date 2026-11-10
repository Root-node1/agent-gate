import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import {
  changeVerificationEmail,
  resendVerificationCode,
  verifyEmail,
} from '../../api/auth'
import { useSession } from '../../session/context'
import AuthField from './AuthField'
import AuthShell from './AuthShell'

interface VerifyEmailLocationState {
  email?: string
}

function maskedEmail(email: string) {
  const [name, domain] = email.split('@')
  if (!name || !domain) return 'your email address'
  return `${name.slice(0, 1)}${'*'.repeat(Math.min(Math.max(name.length - 1, 3), 6))}@${domain}`
}

export default function VerifyEmailPage() {
  const { refreshSession } = useSession()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const state = location.state as VerifyEmailLocationState | null
  const [email, setEmail] = useState(state?.email ?? '')
  const [key, setKey] = useState(searchParams.get('key') ?? '')
  const [newEmail, setNewEmail] = useState('')
  const [showChangeEmail, setShowChangeEmail] = useState(false)
  const [secondsUntilResend, setSecondsUntilResend] = useState(30)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [verified, setVerified] = useState(false)

  useEffect(() => {
    if (secondsUntilResend <= 0) return
    const timer = window.setTimeout(
      () => setSecondsUntilResend((remaining) => remaining - 1),
      1000,
    )
    return () => window.clearTimeout(timer)
  }, [secondsUntilResend])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    setSessionError(null)
    try {
      await verifyEmail(key.trim().toUpperCase())
      setVerified(true)
      try {
        const session = await refreshSession()
        if (session.status === 'authenticated') {
          navigate('/app', { replace: true })
          return
        }
      } catch {
        setSessionError(
          'Email verification succeeded, but the session could not be checked. Sign in to continue.',
        )
      }
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
      setSecondsUntilResend(30)
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
      const updatedEmail = newEmail.trim()
      await changeVerificationEmail(updatedEmail)
      setEmail(updatedEmail)
      setKey('')
      setSecondsUntilResend(30)
      setShowChangeEmail(false)
      setSuccess(`A verification code was sent to ${maskedEmail(updatedEmail)}.`)
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
        {sessionError ? <p className="auth-warning" role="alert">{sessionError}</p> : null}
        <Link className="btn btn-primary btn-block" to="/login" state={{ email }}>
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
      <form onSubmit={submit}>
        <AuthField
          label="Email verification code"
          required
          value={key}
          onChange={(event) => setKey(event.target.value.toUpperCase())}
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          hint="The code contains eight letters or numbers separated by a hyphen."
        />
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
          disabled={submitting || secondsUntilResend > 0}
        >
          {secondsUntilResend > 0
            ? `Resend code in ${secondsUntilResend}s`
            : 'Resend verification code'}
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
          <AuthField
            label="New email address"
            type="email"
            autoComplete="email"
            required
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
          />
          <button type="submit" className="btn btn-secondary" disabled={submitting}>
            Update
          </button>
        </form>
      ) : null}

      <Link className="auth-back-link" to="/login">Back to sign in</Link>
    </AuthShell>
  )
}
