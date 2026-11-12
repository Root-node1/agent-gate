import { useRef, type ClipboardEvent, type ChangeEvent } from 'react'

export default function SixDigitCodeInput({
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

  function setDigits(index: number, input: string) {
    const digits = input.replace(/\D/g, '')
    const next = [...value]
    if (!digits) {
      next[index] = ''
      onChange(next)
      return
    }
    for (let offset = 0; offset < digits.length && index + offset < 6; offset += 1) {
      next[index + offset] = digits[offset]
    }
    onChange(next)
    if (index + digits.length < 6) {
      inputRefs.current[index + digits.length]?.focus()
    }
  }

  function paste(event: ClipboardEvent<HTMLInputElement>) {
    const digits = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!digits) return
    event.preventDefault()
    onChange(Array.from({ length: 6 }, (_, index) => digits[index] ?? ''))
    inputRefs.current[Math.min(digits.length, 5)]?.focus()
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
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            setDigits(index, event.target.value.slice(-6))
          }}
          onPaste={paste}
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
