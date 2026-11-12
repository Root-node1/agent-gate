import { useState, type InputHTMLAttributes, useId } from 'react'

interface AuthFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'label'> {
  label: string
  error?: string
  hint?: string
  revealable?: boolean
  'aria-describedby'?: string
}

export default function AuthField({
  label,
  id: idProp,
  type = 'text',
  error,
  hint,
  revealable = false,
  ...inputProps
}: AuthFieldProps) {
  const generated = useId()
  const [visible, setVisible] = useState(false)
  const id = idProp ?? `af-${generated}`
  const errorId = error ? `${id}-error` : undefined
  const hintId = hint ? `${id}-hint` : undefined
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {revealable && type === 'password' ? (
        <div className="auth-password">
          <input
            id={id}
            type={visible ? 'text' : type}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={[hintId, errorId].filter(Boolean).join(' ')}
            aria-required={inputProps.required}
            {...inputProps}
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
      ) : (
        <input
          id={id}
          type={type}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={[hintId, errorId].filter(Boolean).join(' ')}
          aria-required={inputProps.required}
          {...inputProps}
        />
      )}
      {hint && (
        <span id={hintId} className="hint">
          {hint}
        </span>
      )}
      {error && (
        <span id={errorId} className="field-error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
