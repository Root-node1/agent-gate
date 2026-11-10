import { useRef, useState, type ChangeEvent, type ClipboardEvent } from 'react'

export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete = 'new-password',
  error,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete?: string
  error?: string
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="auth-password">
        <input
          id={id}
          name={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          required
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        <button
          type="button"
          className="auth-password-toggle"
          aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? 'Hide' : 'Show'}
        </button>
      </div>
      {error ? (
        <span className="field-error" id={`${id}-error`}>
          {error}
        </span>
      ) : null}
    </div>
  )
}

export function PasswordGuidance({ password }: { password: string }) {
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

export function SixDigitCodeInput({
  value,
  onChange,
  disabled = false,
  error = false,
}: {
  value: string[]
  onChange: (value: string[]) => void
  disabled?: boolean
  error?: boolean
}) {
  const inputRefs = useRef<Array<HTMLInputElement | null>>([])

  function setDigit(index: number, input: string) {
    const next = [...value]
    const entered = input.replace(/\D/g, '')
    for (let offset = 0; offset < entered.length && index + offset < 6; offset += 1) {
      next[index + offset] = entered[offset]
    }
    onChange(next)
    if (entered && index + entered.length < 6) {
      inputRefs.current[index + entered.length]?.focus()
    }
  }

  function onInput(index: number, event: ChangeEvent<HTMLInputElement>) {
    setDigit(index, event.target.value.slice(-6))
  }

  function onPaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!pasted) return
    event.preventDefault()
    onChange(Array.from({ length: 6 }, (_, index) => pasted[index] ?? ''))
    inputRefs.current[Math.min(pasted.length, 5)]?.focus()
  }

  return (
    <div className="auth-code-inputs" role="group" aria-label="Six-digit authenticator code">
      {Array.from({ length: 6 }, (_, index) => (
        <input
          key={index}
          ref={(element) => {
            inputRefs.current[index] = element
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={6}
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          aria-label={`Digit ${index + 1} of 6`}
          aria-invalid={error}
          value={value[index]}
          disabled={disabled}
          onChange={(event) => onInput(index, event)}
          onPaste={onPaste}
          onKeyDown={(event) => {
            if (event.key === 'Backspace' && !value[index] && index > 0) {
              inputRefs.current[index - 1]?.focus()
            }
            if (event.key === 'ArrowLeft' && index > 0) inputRefs.current[index - 1]?.focus()
            if (event.key === 'ArrowRight' && index < 5) inputRefs.current[index + 1]?.focus()
          }}
        />
      ))}
    </div>
  )
}
