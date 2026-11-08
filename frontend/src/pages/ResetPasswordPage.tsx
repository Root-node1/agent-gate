import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { resetPassword, validatePasswordResetKey } from '../api/auth'
import { PasswordField, PasswordGuidance } from './AuthFields'
import AuthShell from './AuthShell'

export default function ResetPasswordPage() {
  const { key = '' } = useParams()
  const [validating, setValidating] = useState(true)
  const [valid, setValid] = useState(false)
  const [complete, setComplete] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let active = true
    void validatePasswordResetKey(key).then(
      () => {
        if (active) setValid(true)
      },
      () => {
        if (active) setValid(false)
      },
    ).finally(() => {
      if (active) setValidating(false)
    })
    return () => {
      active = false
    }
  }, [key])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      await resetPassword(key, password)
      setComplete(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The reset link may have expired.')
      if (cause instanceof Error && cause.message.toLowerCase().includes('invalid')) {
        setValid(false)
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (validating) {
    return (
      <main className="auth-loading" role="status">
        <p>Checking your password reset link…</p>
      </main>
    )
  }

  if (complete) {
    return (
      <AuthShell eyebrow="Password updated" title="You’re all set">
        <p className="auth-success" role="status">
          Your password has been changed. Sign in with your new password to continue.
        </p>
        <Link to="/login" className="btn btn-primary btn-block">Continue to sign in</Link>
      </AuthShell>
    )
  }

  if (!valid) {
    return (
      <AuthShell eyebrow="Account recovery" title="This reset link has expired">
        <p className="auth-error" role="alert">
          The password reset link is invalid or has expired. Request a new link to continue.
        </p>
        <Link to="/forgot-password" className="btn btn-primary btn-block">
          Request a new reset link
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell eyebrow="Account recovery" title="Set a new password">
      <form onSubmit={submit}>
        <PasswordField
          id="new-password"
          label="New password"
          value={password}
          onChange={setPassword}
        />
        <PasswordGuidance password={password} />
        <p className="hint">Use at least 8 characters. Common and numeric-only passwords are rejected.</p>
        <PasswordField
          id="confirm-new-password"
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
        />
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Updating password…' : 'Reset password'}
        </button>
      </form>
    </AuthShell>
  )
}
