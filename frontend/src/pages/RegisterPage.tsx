import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  getAuthOptions,
  signUp,
  type AuthOptions,
} from '../api/auth'
import { PasswordField, PasswordGuidance } from './AuthFields'
import AuthProviders from './AuthProviders'
import AuthShell from './AuthShell'

export default function RegisterPage() {
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [organization, setOrganization] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [options, setOptions] = useState<AuthOptions | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)

  useEffect(() => {
    void getAuthOptions()
      .then(setOptions)
      .catch((cause: unknown) =>
        setOptionsError(
          cause instanceof Error ? cause.message : 'Could not load sign-in options.',
        ),
      )
  }, [])

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
      await signUp({
        email: email.trim(),
        password,
        full_name: fullName.trim(),
        organization: organization.trim(),
        accept_terms: acceptTerms,
      })
      navigate('/verify-email', { state: { email: email.trim() } })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create your account.')
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Create your workspace account"
      title="Create an account"
      description="Set up secure access to AgentGate’s spending controls."
      wide
    >
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="full-name">Full name</label>
          <input
            id="full-name"
            name="full_name"
            autoComplete="name"
            required
            maxLength={150}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="register-email">Work email</label>
          <input
            id="register-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="organization">Organization or company</label>
          <input
            id="organization"
            name="organization"
            autoComplete="organization"
            required
            maxLength={150}
            value={organization}
            onChange={(event) => setOrganization(event.target.value)}
          />
        </div>
        <PasswordField
          id="register-password"
          label="Password"
          value={password}
          onChange={setPassword}
        />
        <PasswordGuidance password={password} />
        <p className="hint">Use at least 8 characters. Common and numeric-only passwords are rejected.</p>
        <PasswordField
          id="confirm-password"
          label="Confirm password"
          value={confirmPassword}
          onChange={setConfirmPassword}
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
          Terms of Service and Privacy Policy URLs have not been provided yet. Publish and link
          approved documents before opening registration to external users.
        </p>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <div className="auth-divider" aria-hidden="true">
        <span>or continue with</span>
      </div>
      {options ? <AuthProviders options={options} /> : optionsError ? (
        <p className="auth-error" role="alert">{optionsError}</p>
      ) : (
        <p className="auth-provider-note" role="status">Loading sign-in options…</p>
      )}
      <p className="auth-form-footer">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthShell>
  )
}
