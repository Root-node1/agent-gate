import { useState, type FormEvent } from 'react'
import { changePassword } from '../../api/auth'
import AuthField from './AuthField'
import { useSession } from '../../session/context'

export default function PasswordChangeForm() {
  const { authenticationError, authenticationStatus, refreshSession } = useSession()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  const confirmError =
    !fieldErrors.new_password && next && confirm && next !== confirm
      ? 'Passwords do not match.'
      : fieldErrors.new_password

  function validate(): string | null {
    if (!current) return 'Enter your current password.'
    if (!next) return 'Enter a new password.'
    if (next.length < 8) return 'Password must be at least 8 characters.'
    if (next !== confirm) return 'Passwords do not match.'
    return null
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const err = validate()
    setServerError(err)
    if (err) return
    setSubmitting(true)
    setServerError(null)
    setFieldErrors({})
    setSaved(false)
    try {
      await changePassword(current, next)
      setSaved(true)
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'HeadlessError') {
        const headless = error as unknown as {
          fieldErrors?: Record<string, string>
          status?: number
        }
        setFieldErrors(headless.fieldErrors ?? {})
        setServerError(
          headless.fieldErrors?.current_password ||
            headless.fieldErrors?.new_password ||
            'Could not change the password. Check the values and try again.',
        )
      } else {
        setServerError(error instanceof Error ? error.message : 'Could not change the password.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (authenticationStatus === 'loading') {
    return <p className="hint" role="status">Checking session…</p>
  }

  if (authenticationStatus === 'error') {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {authenticationError || 'Could not verify the dashboard session.'}
        </p>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => void refreshSession().catch(() => undefined)}
        >
          Retry session check
        </button>
      </div>
    )
  }

  if (authenticationStatus !== 'authenticated') {
    return (
      <div className="stack">
        <p className="muted">
          You must be logged in to change your password. Log in via the dashboard,
          then return here to update it.
        </p>
        <p className="muted">
          Don't remember your password? Use the{' '}
          <a className="link" href="/forgot-password">
            password reset
          </a>
          .
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} noValidate>
      {serverError && <p className="form-error" role="alert">{serverError}</p>}
      {saved && (
        <p role="status" className="hint">
          Password updated.
        </p>
      )}
      <AuthField
        label="Current password"
        id="af-change-current"
        type="password"
        autoComplete="current-password"
        required
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        error={fieldErrors.current_password}
      />
      <AuthField
        label="New password"
        id="af-change-new"
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        value={next}
        onChange={(e) => setNext(e.target.value)}
        error={fieldErrors.new_password || undefined}
        hint="At least 8 characters."
      />
      <AuthField
        label="Confirm new password"
        id="af-change-confirm"
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        error={confirmError}
      />
      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? 'Saving…' : 'Change password'}
      </button>
    </form>
  )
}
