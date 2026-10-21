import { useEffect, useState, type FormEvent } from 'react'
import { Link, useBlocker } from 'react-router'
import { Info } from 'lucide-react'
import { DemoError, spentWindows, updatePolicy, useDemoState, validatePolicy } from '../../../demo/store'
import { agentById } from '../../../demo/selectors'
import type { Policy } from '../../../demo/types'
import { timeAgo } from '../../../ui/format'
import { useNow } from '../../../ui/hooks'
import Modal from '../../../ui/Modal'
import { AgentStatusBadge } from '../../../ui/StatusBadges'
import { useToast } from '../../../ui/toast-context'
import MerchantListEditor from './MerchantListEditor'
import PaymentPreview from './PaymentPreview'
import {
  CURRENCIES,
  currencySymbol,
  draftFromPolicy,
  isDirty,
  valuesFromDraft,
  type MoneyField,
  type PolicyDraft,
} from './policyDraft'
import TryPayment from './TryPayment'

type FieldErrors = Partial<Record<keyof PolicyDraft, string>>

const MONEY_INPUTS: { field: MoneyField; label: string; hint: string }[] = [
  {
    field: 'approval_threshold',
    label: 'Ask a person above',
    hint: 'Payments above this wait for someone to approve them.',
  },
  {
    field: 'per_transaction_cap',
    label: 'Per-payment limit',
    hint: 'Any single payment above this is blocked.',
  },
  {
    field: 'daily_budget',
    label: 'Daily budget',
    hint: 'A payment that would take today’s total over this is blocked.',
  },
  {
    field: 'monthly_budget',
    label: 'Monthly budget',
    hint: 'A payment that would take this month’s total over this is blocked.',
  },
]

/** Order used to focus the first invalid field on save. */
const FIELD_ORDER: (keyof PolicyDraft)[] = [
  'name',
  'currency',
  'approval_threshold',
  'per_transaction_cap',
  'daily_budget',
  'monthly_budget',
  'allowed_merchants',
  'blocked_merchants',
]

export default function PolicyForm({ policy }: { policy: Policy }) {
  const state = useDemoState()
  const toast = useToast()
  const now = useNow()
  const [draft, setDraft] = useState<PolicyDraft>(() => draftFromPolicy(policy))
  const [touched, setTouched] = useState<Partial<Record<keyof PolicyDraft, boolean>>>({})
  const [submitted, setSubmitted] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const agent = agentById(state, policy.agent_id)
  const values = valuesFromDraft(draft)
  const errors: FieldErrors = { ...(validatePolicy(values) as FieldErrors | null) }
  if (!values.name) errors.name = 'Enter a name.'
  const hasErrors = Object.keys(errors).length > 0
  const dirty = isDirty(draft, policy)
  const spent = spentWindows(state, policy.agent_id, values.currency, new Date(now))

  const errorFor = (field: keyof PolicyDraft) => (submitted || touched[field] ? errors[field] : undefined)

  // Ask before leaving with unsaved edits: in-app links and Back via the router,
  // closing or reloading the tab via beforeunload.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!dirty) return
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  function set<K extends keyof PolicyDraft>(field: K, value: PolicyDraft[K]) {
    setDraft((d) => ({ ...d, [field]: value }))
    setSaveError(null)
  }

  function touch(field: keyof PolicyDraft) {
    setTouched((t) => ({ ...t, [field]: true }))
  }

  function save(e: FormEvent) {
    e.preventDefault()
    setSubmitted(true)
    if (hasErrors) {
      const first = FIELD_ORDER.find((f) => errors[f])
      if (first) document.getElementById(`po-${first}`)?.focus()
      setSaveError('Some fields need fixing before you can save.')
      return
    }
    try {
      updatePolicy(policy.id, values)
      setDraft(draftFromPolicy({ ...policy, ...values }))
      setSubmitted(false)
      setTouched({})
      setSaveError(null)
      toast.show('Policy saved. New requests use these rules from now on.', 'success')
    } catch (err) {
      setSaveError(err instanceof DemoError ? err.message : 'Could not save the policy. Try again.')
    }
  }

  function discard() {
    setDraft(draftFromPolicy(policy))
    setSubmitted(false)
    setTouched({})
    setSaveError(null)
    toast.show('Changes discarded.', 'info')
  }

  const currencyOptions = CURRENCIES.some((c) => c.code === draft.currency)
    ? CURRENCIES
    : [{ code: draft.currency, label: draft.currency }, ...CURRENCIES]
  const symbol = currencySymbol(draft.currency)

  return (
    <div className="split po-split">
      <form className="card po-form" onSubmit={save} noValidate aria-labelledby="po-form-title">
        <h2 id="po-form-title" className="visually-hidden">
          Policy settings
        </h2>

        <section className="form-section">
          <div>
            <h3 className="form-section-title">Policy</h3>
            <p className="form-section-text">Each agent has exactly one policy. It cannot be moved to another agent.</p>
          </div>
          <div>
            <div className="field">
              <label htmlFor="po-name">Name</label>
              <input
                id="po-name"
                value={draft.name}
                onChange={(e) => set('name', e.target.value)}
                onBlur={() => touch('name')}
                aria-invalid={errorFor('name') ? 'true' : undefined}
                aria-describedby="po-name-error"
              />
              {errorFor('name') && (
                <span id="po-name-error" className="field-error">
                  {errorFor('name')}
                </span>
              )}
            </div>
            <div className="field">
              <span className="field-label" id="po-agent-label">
                Assigned agent
              </span>
              <div className="po-agent" aria-labelledby="po-agent-label">
                {agent ? (
                  <>
                    <Link to={`/app/agents/${agent.id}`} className="po-agent-link">
                      {agent.name}
                    </Link>
                    <AgentStatusBadge status={agent.status} />
                  </>
                ) : (
                  <span className="muted">Unknown agent</span>
                )}
              </div>
            </div>
            <div className="field">
              <label htmlFor="po-currency">Currency</label>
              <select
                id="po-currency"
                value={draft.currency}
                onChange={(e) => set('currency', e.target.value)}
                aria-invalid={errorFor('currency') ? 'true' : undefined}
                aria-describedby="po-currency-hint po-currency-error"
              >
                {currencyOptions.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
              </select>
              <span id="po-currency-hint" className="hint">
                Requests in any other currency are blocked.
              </span>
              {errorFor('currency') && (
                <span id="po-currency-error" className="field-error">
                  {errorFor('currency')}
                </span>
              )}
            </div>
          </div>
        </section>

        <section className="form-section">
          <div>
            <h3 className="form-section-title">Spending limits</h3>
            <p className="form-section-text">
              Small payments go through on their own. Bigger ones wait for a person. Anything over a limit is blocked.
            </p>
          </div>
          <div className="po-money-grid">
            {MONEY_INPUTS.map(({ field, label, hint }) => {
              const error = errorFor(field)
              return (
                <div key={field} className="field">
                  <label htmlFor={`po-${field}`}>{label}</label>
                  <div className="input-affix">
                    <span aria-hidden="true">{symbol}</span>
                    <input
                      id={`po-${field}`}
                      inputMode="decimal"
                      autoComplete="off"
                      value={draft[field]}
                      onChange={(e) => set(field, e.target.value)}
                      onBlur={() => touch(field)}
                      aria-invalid={error ? 'true' : undefined}
                      aria-describedby={`po-${field}-hint po-${field}-error`}
                    />
                  </div>
                  <span id={`po-${field}-hint`} className="hint">
                    {hint}
                  </span>
                  {error && (
                    <span id={`po-${field}-error`} className="field-error">
                      {error}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        <section className="form-section">
          <div>
            <h3 className="form-section-title">Merchants</h3>
            <p className="form-section-text">
              Limit where this agent can pay. Paste a URL or a domain; we keep just the domain.
            </p>
          </div>
          <div>
            <MerchantListEditor
              list="allowed_merchants"
              label="Allow list"
              hint="If this list has entries, every other merchant is blocked."
              draft={draft}
              onChange={(m) => set('allowed_merchants', m)}
              error={errorFor('allowed_merchants')}
              tone="allow"
              emptyText="Empty: the agent can pay any merchant that is not blocked."
            />
            <MerchantListEditor
              list="blocked_merchants"
              label="Block list"
              hint="Payments to these merchants are always blocked."
              draft={draft}
              onChange={(m) => set('blocked_merchants', m)}
              error={errors.blocked_merchants}
              tone="deny"
              emptyText="Empty: no merchants are blocked by name."
            />
          </div>
        </section>

        <div className="po-savebar" role="region" aria-label="Save changes">
          <div className="po-save-status" aria-live="polite">
            {dirty ? (
              <span className="pill pill-solid tone-approval">
                <span aria-hidden="true">●</span>
                Unsaved changes
              </span>
            ) : (
              <span className="small muted">
                All changes saved · updated <time dateTime={policy.updated_at}>{timeAgo(policy.updated_at, now)}</time>
              </span>
            )}
            {saveError && (
              <span className="field-error" role="alert">
                {saveError}
              </span>
            )}
          </div>
          <div className="cluster">
            <button type="button" className="btn btn-secondary" onClick={discard} disabled={!dirty}>
              Discard changes
            </button>
            <button type="submit" className="btn btn-primary" disabled={!dirty}>
              Save policy
            </button>
          </div>
        </div>
        <p className="hint po-apply-note">
          <Info size={14} aria-hidden="true" /> Changes apply to new requests only. Past decisions and payments waiting
          for approval keep their outcome. Every save is recorded in the audit log.
        </p>
      </form>

      <aside className="stack-lg po-aside" aria-label="Preview">
        <section className="card" aria-labelledby="po-preview-title">
          <div className="card-header">
            <div>
              <h2 id="po-preview-title" className="card-title">
                What happens to a payment
              </h2>
              <p className="card-subtitle">{dirty ? 'Preview of your unsaved changes.' : 'With the saved rules.'}</p>
            </div>
          </div>
          <PaymentPreview values={values} spent={spent} />
        </section>
        <section className="card" aria-labelledby="po-try-title">
          <div className="card-header">
            <div>
              <h2 id="po-try-title" className="card-title">
                Try a payment
              </h2>
              <p className="card-subtitle">See the decision these rules would make.</p>
            </div>
          </div>
          <TryPayment values={values} spent={spent} valid={!hasErrors} />
        </section>
      </aside>

      <Modal
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        title="Leave without saving?"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => blocker.reset?.()}>
              Keep editing
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => blocker.proceed?.()}
            >
              Discard and leave
            </button>
          </>
        }
      >
        <p>Your changes to this policy have not been saved. If you leave now, they are lost.</p>
      </Modal>
    </div>
  )
}
