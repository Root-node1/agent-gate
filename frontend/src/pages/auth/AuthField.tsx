import { type InputHTMLAttributes, useId } from 'react'

interface AuthFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'label'> {
  label: string
  error?: string
  hint?: string
  'aria-describedby'?: string
}

export default function AuthField({
  label,
  id: idProp,
  type = 'text',
  error,
  hint,
  ...inputProps
}: AuthFieldProps) {
  const generated = useId()
  const id = idProp ?? `af-${generated}`
  const errorId = error ? `${id}-error` : undefined
  const hintId = hint ? `${id}-hint` : undefined
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type={type}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ')}
        aria-required={inputProps.required}
        {...inputProps}
      />
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
