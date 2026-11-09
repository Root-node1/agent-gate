import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { confirmPasswordReset } from '../api/auth'
import { PasswordField, PasswordGuidance } from './AuthFields'
import AuthShell from './AuthShell'

export default function ResetPasswordPage() {
  const { key = '' } = useParams()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      await confirmPasswordReset(key, password)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The reset link may have expired.')
    } finally {
      setSubmitting(false)
    }
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
      <p className="auth-form-footer">
        <Link to="/forgot-password" className="btn btn-outline btn-block">
          Request a new reset link
        </Link>
      </p>
    </AuthShell>
  )
}
