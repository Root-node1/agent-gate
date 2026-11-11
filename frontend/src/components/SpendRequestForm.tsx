import { useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  submitSpendRequest,
  type FieldErrors,
  type SpendRequest,
  type SpendRequestInput,
} from '../api/spendRequests'
import { useSession } from '../session/context'
import AgentKeyField from './AgentKeyField'

const EMPTY_INPUT: SpendRequestInput = {
  amount: '',
  currency: 'USD',
  merchant: '',
  purpose: '',
}

interface Props {
  onResult: (request: SpendRequest) => void
}

export default function SpendRequestForm({ onResult }: Props) {
  const { agentKey } = useSession()
  const [input, setInput] = useState<SpendRequestInput>(EMPTY_INPUT)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [keyError, setKeyError] = useState('')
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const requestKey = useRef<{ fingerprint: string; value: string } | null>(null)

  function update<K extends keyof SpendRequestInput>(field: K, value: SpendRequestInput[K]) {
    setInput((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFieldErrors({})
    setFormError('')
    setKeyError('')
    if (!agentKey) {
      setKeyError('Paste the agent key first.')
      return
    }
    if (!crypto.randomUUID) {
      setFormError('This browser cannot create a secure request identifier. Update your browser and retry.')
      return
    }
    setSubmitting(true)
    try {
      const fingerprint = JSON.stringify({ agentKey, input })
      let requestIdentity = requestKey.current
      if (requestIdentity?.fingerprint !== fingerprint) {
        requestIdentity = { fingerprint, value: crypto.randomUUID() }
        requestKey.current = requestIdentity
      }
      onResult(await submitSpendRequest(agentKey, input, requestIdentity.value))
      requestKey.current = null
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message)
        setFieldErrors(err.fieldErrors)
      } else {
        setFormError('Something went wrong. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  function fieldProps(field: keyof SpendRequestInput) {
    const error = fieldErrors[field]
    return {
      id: field,
      'aria-invalid': error ? true : undefined,
      'aria-describedby': error ? `${field}-error` : undefined,
    }
  }

  function errorFor(field: keyof SpendRequestInput) {
    const error = fieldErrors[field]
    return error ? (
      <span id={`${field}-error`} className="field-error">
        {error}
      </span>
    ) : null
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate>
      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}

      <AgentKeyField error={keyError} />

      <div className="row">
        <div className="field">
          <label htmlFor="amount">Amount</label>
          <input
            {...fieldProps('amount')}
            inputMode="decimal"
            placeholder="25.00"
            value={input.amount}
            onChange={(e) => update('amount', e.target.value)}
            required
          />
          {errorFor('amount')}
        </div>
        <div className="field">
          <label htmlFor="currency">Currency</label>
          <input
            {...fieldProps('currency')}
            maxLength={3}
            value={input.currency}
            onChange={(e) => update('currency', e.target.value.toUpperCase())}
            required
          />
          {errorFor('currency')}
        </div>
      </div>

      <div className="field">
        <label htmlFor="merchant">Merchant</label>
        <input
          {...fieldProps('merchant')}
          placeholder="acme.com"
          value={input.merchant}
          onChange={(e) => update('merchant', e.target.value)}
          required
        />
        {errorFor('merchant')}
      </div>

      <div className="field">
        <label htmlFor="purpose">Purpose (optional)</label>
        <textarea
          {...fieldProps('purpose')}
          placeholder="Monthly hosting bill"
          value={input.purpose}
          onChange={(e) => update('purpose', e.target.value)}
        />
        {errorFor('purpose')}
      </div>

      <button className="button" type="submit" disabled={submitting}>
        {submitting ? 'Checking…' : 'Check payment'}
      </button>
    </form>
  )
}
