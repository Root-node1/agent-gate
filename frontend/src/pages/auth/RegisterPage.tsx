import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { useSession } from '../../session/context'
import AuthField from './AuthField'
import AuthShell from './AuthShell'
import PasswordGuidance from './PasswordGuidance'

export default function RegisterPage() {
  const { register } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (!acceptTerms) {
      setError('Confirm that you accept the terms before creating an account.')
      return
    }
    setSubmitting(true)
    try {
      const result = await register(email.trim(), password)
      setPassword('')
      setConfirmPassword('')
      if (result.kind === 'authenticated') {
        navigate('/app', { replace: true })
        return
      }
      if (result.kind === 'mfa') {
        navigate('/mfa', { state: { email: email.trim(), types: result.types } })
      } else {
        navigate('/verify-email', { state: { email: email.trim() } })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create your account.')
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Create a dashboard account"
      title="Create an account"
      description="An email verification step may be required before signing in."
    >
      <form onSubmit={submit}>
        <AuthField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <AuthField
          label="Password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          revealable
          hint="Use at least 8 characters. The server applies additional password checks."
        />
        <PasswordGuidance password={password} />
        <AuthField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          revealable
        />
        <label className="auth-check-row">
          <input
            type="checkbox"
            checked={acceptTerms}
            onChange={(event) => setAcceptTerms(event.target.checked)}
            required
          />
          <span>I agree to AgentGate’s Terms of Service and Privacy Policy.</span>
        </label>
        <p className="auth-warning" role="note">
          Terms of Service and Privacy Policy URLs have not been provided. Publish and link
          approved documents before opening registration to external users.
        </p>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="auth-form-footer">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthShell>
  )
}
