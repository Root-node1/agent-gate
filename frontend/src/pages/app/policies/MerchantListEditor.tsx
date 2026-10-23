import { useState, type KeyboardEvent } from 'react'
import { Plus, X } from 'lucide-react'
import { normalizeMerchant } from '../../../demo/rules'
import { merchantError, type MerchantList, type PolicyDraft } from './policyDraft'

interface Props {
  list: MerchantList
  label: string
  hint: string
  draft: PolicyDraft
  onChange: (merchants: string[]) => void
  /** Error from validatePolicy for this list. */
  error?: string
  tone: 'allow' | 'deny'
  emptyText: string
}

export default function MerchantListEditor({ list, label, hint, draft, onChange, error, tone, emptyText }: Props) {
  const [value, setValue] = useState('')
  const [inputError, setInputError] = useState<string | null>(null)
  const items = draft[list]
  const id = `po-${list}`

  function add() {
    const merchant = normalizeMerchant(value)
    const problem = merchantError(merchant, list, draft)
    if (problem) {
      setInputError(problem)
      return
    }
    onChange([...items, merchant])
    setValue('')
    setInputError(null)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  const shownError = inputError ?? error
  return (
    <div className="field po-merchants">
      <label htmlFor={id}>{label}</label>
      <span id={`${id}-hint`} className="hint">
        {hint}
      </span>
      <div className="po-merchant-add">
        <input
          id={id}
          className="input"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setInputError(null)
          }}
          onKeyDown={onKeyDown}
          placeholder="e.g. github.com"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={shownError ? 'true' : undefined}
          aria-describedby={`${id}-hint ${id}-error`}
        />
        <button type="button" className="btn btn-secondary" onClick={add}>
          <Plus size={16} aria-hidden="true" />
          Add
        </button>
      </div>
      {shownError && (
        <span id={`${id}-error`} className="field-error" role="alert">
          {shownError}
        </span>
      )}
      {items.length === 0 ? (
        <p className="po-merchant-empty">{emptyText}</p>
      ) : (
        <ul className="po-chips" aria-label={`${label}: ${items.length}`}>
          {items.map((merchant) => (
            <li key={merchant} className={`po-chip tone-${tone}`}>
              <span aria-hidden="true">{tone === 'allow' ? '✓' : '✕'}</span>
              <span className="po-chip-text">{merchant}</span>
              <button
                type="button"
                className="po-chip-remove"
                onClick={() => onChange(items.filter((m) => m !== merchant))}
                aria-label={`Remove ${merchant} from the ${tone === 'allow' ? 'allow' : 'block'} list`}
              >
                <X size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
