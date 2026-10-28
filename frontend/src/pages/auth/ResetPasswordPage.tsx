import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import Logo from '../../components/Logo'
import { bootstrapCsrf, confirmPasswordReset } from '../../api/auth'
import AuthField from './AuthField'
import './AuthPages.css'

export default function ResetPasswordPage() {
  const { key = '' } = useParams()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [serverFieldErrors, setServerFieldErrors] = useState<Record<string, string>>({})
  const [done, setDone] = useState(false)

  useEffect(() => {
    void bootstrapCsrf()
  }, [])

  const passwordError = serverFieldErrors.password
  const confirmError =
    !passwordError && password && confirm && password !== confirm
      ? 'Passwords do not match.'
      : serverFieldErrors.new_password

  function validate(): string | null {
    if (!password) return 'Choose a new password.'
    if (password.length < 8) return 'Password must be at least 8 characters.'
    if (password !== confirm) return 'Passwords do not match.'
    return null
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const err = validate()
    setServerError(err)
    if (err) return
    setSubmitting(true)
    setServerError(null)
    setServerFieldErrors({})
    try {
      await confirmPasswordReset(key, password)
      setDone(true)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'HeadlessError') {
        const headless = err as unknown as {
          fieldErrors?: Record<string, string>
          status?: number
        }
        setServerFieldErrors(headless.fieldErrors ?? {})
        setServerError(
          headless.fieldErrors?.key ??
          headless.fieldErrors?.non_field ??
          (err.message || 'The password reset link is invalid or expired.'),
        )
      } else {
        setServerError(err instanceof Error ? err.message : 'Could not reset the password.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="auth-page">
        <div className="auth-card card">
          <div className="auth-header">
            <Logo />
            <h1>Password reset</h1>
          </div>
          <div className="stack">
            <p>Your password has been reset. You can now log in with your new password.</p>
            <Link to="/login" className="btn btn-primary btn-block">
              Go to login
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card card">
        <div className="auth-header">
          <Logo />
          <h1>Set a new password</h1>
          <p className="muted">Enter a strong, unique password below.</p>
        </div>
        <form onSubmit={submit} noValidate>
          {serverError && <p className="form-error" role="alert">{serverError}</p>}
          <AuthField
            label="New password"
            id="af-reset-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={passwordError}
            hint="At least 8 characters."
          />
          <AuthField
            label="Confirm new password"
            id="af-reset-confirm"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={confirmError}
          />
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting || !key}>
            {submitting ? 'Resetting…' : 'Reset password'}
          </button>
          {!key && (
            <p className="form-error" role="alert">
              The reset link is missing or malformed.
            </p>
          )}
        </form>
      </div>
      <p className="auth-foot muted">
        <Link to="/">Back to AgentGate home</Link>
      </p>
    </div>
  )
}
