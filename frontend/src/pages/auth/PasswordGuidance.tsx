export default function PasswordGuidance({ password }: { password: string }) {
  const score =
    (password.length >= 8 ? 1 : 0) +
    (password.length >= 12 ? 1 : 0) +
    (/[A-Z]/.test(password) && /[a-z]/.test(password) ? 1 : 0) +
    (/\d/.test(password) || /[^A-Za-z0-9]/.test(password) ? 1 : 0)
  const label = score >= 4 ? 'Strong' : score >= 2 ? 'Fair' : 'Weak'

  return (
    <div className="auth-password-strength" aria-live="polite">
      <span className="auth-strength-meter" aria-hidden="true">
        {[1, 2, 3, 4].map((segment) => (
          <span key={segment} className={score >= segment ? 'active' : ''} />
        ))}
      </span>
      <span>Password strength: {password ? label : 'not entered'}</span>
      <span className="visually-hidden">
        Use at least 8 characters. Avoid common, numeric-only, and personal-information-based
        passwords.
      </span>
    </div>
  )
}
