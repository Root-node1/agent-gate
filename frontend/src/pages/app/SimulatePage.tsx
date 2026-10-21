import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Play, Send } from 'lucide-react'
import { DemoError, submitSpendRequest, useDemoState, type SubmitInput } from '../../demo/store'
import { agentName, policyForAgent } from '../../demo/selectors'
import type { Source } from '../../demo/types'
import PageHeader from '../../ui/PageHeader'
import { DecisionStatus } from '../../ui/StatusBadges'
import { formatMoney } from '../../ui/format'
import { DECISION, SOURCE } from '../../ui/labels'
import { useToast } from '../../ui/toast-context'
import FlowDiagram from './simulate/FlowDiagram'
import PolicyLimits from './simulate/PolicyLimits'
import ResultPanel from './simulate/ResultPanel'
import { CURRENCIES, SCENARIOS, prefersReducedMotion, previewDecision, type Scenario } from './simulate/scenarios'
import './SimulatePage.css'

interface FormValues {
  agentId: number
  amount: string
  currency: string
  merchant: string
  purpose: string
  source: Source
}

type FieldErrors = Partial<Record<'amount' | 'merchant' | 'purpose', string>>

const CHECK_MS = 600

export default function SimulatePage() {
  const state = useDemoState()
  const toast = useToast()
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const timer = useRef<number | undefined>(undefined)

  const active = state.agents.filter((a) => a.status === 'active')
  const suspended = state.agents.filter((a) => a.status !== 'active')

  const [form, setForm] = useState<FormValues>({
    agentId: 1,
    amount: '45.00',
    currency: 'USD',
    merchant: 'github.com',
    purpose: 'Team seats for October',
    source: 'trusted',
  })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [checking, setChecking] = useState(false)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [label, setLabel] = useState('')

  useEffect(() => () => window.clearTimeout(timer.current), [])

  // Fall back to the first active agent if the chosen one was suspended meanwhile.
  const agent = active.find((a) => a.id === form.agentId) ?? active[0]
  const policy = agent ? policyForAgent(state, agent.id) : undefined
  const result = requestId ? state.requests.find((r) => r.id === requestId) : undefined

  function run(agentId: number, input: SubmitInput, what: string) {
    const reduced = prefersReducedMotion()
    window.clearTimeout(timer.current)
    setChecking(true)
    setRequestId(null)
    setRunError(null)
    setLabel(what)
    resultHeading.current?.closest('section')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    resultHeading.current?.focus({ preventScroll: true })

    timer.current = window.setTimeout(
      () => {
        setChecking(false)
        try {
          const request = submitSpendRequest(agentId, input)
          setRequestId(request.id)
          const money = formatMoney(request.amount, request.currency)
          toast.show(
            `${DECISION[request.decision].label}: ${money} to ${request.merchant}. Recorded in the audit log.`,
            request.decision === 'allow' ? 'success' : 'info',
          )
        } catch (err) {
          if (!(err instanceof DemoError)) throw err
          setRunError(err.message)
        }
      },
      reduced ? 150 : CHECK_MS,
    )
  }

  function update<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    if (key in errors) setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function loadScenario(s: Scenario) {
    setForm({ agentId: s.agentId, ...s.input, amount: s.input.amount.toFixed(2) })
    setErrors({})
    const reduced = prefersReducedMotion()
    document.getElementById('sim-form')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    document.getElementById('sim-amount')?.focus({ preventScroll: true })
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!agent) return
    const amount = Number(form.amount)
    const next: FieldErrors = {}
    if (form.amount.trim() === '' || !Number.isFinite(amount) || amount <= 0) {
      next.amount = 'Enter an amount above 0.'
    } else if (!/^\d+(\.\d{1,2})?$/.test(form.amount.trim())) {
      next.amount = 'Use at most 2 decimal places.'
    }
    if (!form.merchant.trim()) next.merchant = 'Enter the merchant, e.g. github.com.'
    if (!form.purpose.trim()) next.purpose = 'Say what the payment is for.'
    setErrors(next)
    if (Object.keys(next).length) {
      document.getElementById(`sim-${Object.keys(next)[0]}`)?.focus()
      return
    }
    run(
      agent.id,
      {
        amount,
        currency: form.currency,
        merchant: form.merchant.trim(),
        purpose: form.purpose.trim(),
        source: form.source,
      },
      'your request',
    )
  }

  return (
    <>
      <PageHeader
        title="Simulate a request"
        description="Play the AI agent. Send a payment request and watch AgentGate check it, block it or hold it for a person. Sample data only: no real money moves."
      />

      <div className="stack-lg">
        <section className="card" aria-labelledby="sim-how">
          <div className="card-header">
            <div>
              <h2 id="sim-how" className="card-title">
                What you are watching
              </h2>
              <p className="card-subtitle">
                Every request stops at AgentGate first. Only allowed or approved payments reach PayPal.
              </p>
            </div>
          </div>
          <FlowDiagram outcome={checking ? null : (result?.decision ?? null)} checking={checking} />
        </section>

        <section aria-labelledby="sim-scenarios">
          <h2 id="sim-scenarios" className="sim-heading">
            Try a scenario
          </h2>
          <p className="hint sim-heading-text">One click sends a real request through the same rules as the API.</p>
          <div className="grid grid-3">
            {SCENARIOS.map((s) => {
              const now = previewDecision(state, s.agentId, s.input)
              const changed = now !== null && now !== s.expected
              return (
                <article key={s.id} className="card sim-scenario">
                  <div className="sim-scenario-head">
                    <h3 className="card-title">{s.title}</h3>
                    <DecisionStatus decision={s.expected} />
                  </div>
                  <p className="sim-scenario-story">{s.story}</p>
                  <dl className="kv sim-scenario-kv">
                    <dt>Agent</dt>
                    <dd>{agentName(state, s.agentId)}</dd>
                    <dt>Payment</dt>
                    <dd>
                      {formatMoney(s.input.amount, s.input.currency)} to {s.input.merchant}
                    </dd>
                    <dt>Source</dt>
                    <dd>{SOURCE[s.input.source].short}</dd>
                  </dl>
                  {changed && (
                    <p className="hint sim-scenario-note">
                      The budget used in this demo now makes this one {DECISION[now].label.toLowerCase()}. Reset the
                      demo to start fresh.
                    </p>
                  )}
                  <div className="sim-scenario-actions">
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={checking}
                      onClick={() => run(s.agentId, s.input, s.title)}
                    >
                      <Play size={16} aria-hidden="true" />
                      Run scenario
                    </button>
                    <button type="button" className="btn btn-ghost" onClick={() => loadScenario(s)}>
                      Edit first
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        <ResultPanel
          state={state}
          checking={checking}
          requestId={requestId}
          error={runError}
          label={label}
          headingRef={resultHeading}
        />

        <div className="split" id="sim-form">
          <section className="card" aria-labelledby="sim-custom">
            <div className="card-header">
              <div>
                <h2 id="sim-custom" className="card-title">
                  Send your own request
                </h2>
                <p className="card-subtitle">Change any field to see which rule kicks in.</p>
              </div>
            </div>

            {!agent ? (
              <p className="hint">Every agent is suspended. Reactivate one on the Agents page to send requests.</p>
            ) : (
              <form onSubmit={submit} noValidate>
                <div className="field">
                  <label htmlFor="sim-agent">Agent</label>
                  <select
                    id="sim-agent"
                    value={agent.id}
                    onChange={(e) => update('agentId', Number(e.target.value))}
                    aria-describedby="sim-agent-hint"
                  >
                    {active.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                  <p id="sim-agent-hint" className="hint">
                    Only active agents are listed.
                    {suspended.length > 0 &&
                      ` ${suspended.map((a) => a.name).join(', ')} ${suspended.length === 1 ? 'is' : 'are'} suspended, so AgentGate rejects ${suspended.length === 1 ? 'its' : 'their'} requests before checking any rule.`}
                  </p>
                </div>

                <div className="sim-form-row">
                  <div className="field">
                    <label htmlFor="sim-amount">Amount</label>
                    <input
                      id="sim-amount"
                      inputMode="decimal"
                      autoComplete="off"
                      value={form.amount}
                      onChange={(e) => update('amount', e.target.value)}
                      aria-invalid={errors.amount ? true : undefined}
                      aria-describedby={errors.amount ? 'sim-amount-error' : undefined}
                    />
                    {errors.amount && (
                      <p id="sim-amount-error" className="field-error">
                        {errors.amount}
                      </p>
                    )}
                  </div>
                  <div className="field">
                    <label htmlFor="sim-currency">Currency</label>
                    <select
                      id="sim-currency"
                      value={form.currency}
                      onChange={(e) => update('currency', e.target.value)}
                      aria-describedby="sim-currency-hint"
                    >
                      {CURRENCIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    {policy && form.currency !== policy.currency && (
                      <p id="sim-currency-hint" className="hint">
                        The policy is in {policy.currency}, so this will be denied.
                      </p>
                    )}
                  </div>
                </div>

                <div className="field">
                  <label htmlFor="sim-merchant">Merchant</label>
                  <input
                    id="sim-merchant"
                    list="sim-merchants"
                    autoComplete="off"
                    placeholder="e.g. github.com"
                    value={form.merchant}
                    onChange={(e) => update('merchant', e.target.value)}
                    aria-invalid={errors.merchant ? true : undefined}
                    aria-describedby={errors.merchant ? 'sim-merchant-error' : undefined}
                  />
                  <datalist id="sim-merchants">
                    {policy?.allowed_merchants.map((m) => <option key={m} value={m} />)}
                    {policy?.blocked_merchants.map((m) => <option key={m} value={m} />)}
                  </datalist>
                  {errors.merchant && (
                    <p id="sim-merchant-error" className="field-error">
                      {errors.merchant}
                    </p>
                  )}
                </div>

                <div className="field">
                  <label htmlFor="sim-source">Where did the instruction come from?</label>
                  <select
                    id="sim-source"
                    value={form.source}
                    onChange={(e) => update('source', e.target.value as Source)}
                  >
                    {(Object.keys(SOURCE) as Source[]).map((s) => (
                      <option key={s} value={s}>
                        {SOURCE[s].label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="sim-purpose">Purpose</label>
                  <textarea
                    id="sim-purpose"
                    value={form.purpose}
                    onChange={(e) => update('purpose', e.target.value)}
                    aria-invalid={errors.purpose ? true : undefined}
                    aria-describedby={errors.purpose ? 'sim-purpose-error' : undefined}
                  />
                  {errors.purpose && (
                    <p id="sim-purpose-error" className="field-error">
                      {errors.purpose}
                    </p>
                  )}
                </div>

                <div className="form-actions">
                  <button type="submit" className="btn btn-primary" disabled={checking}>
                    <Send size={16} aria-hidden="true" />
                    {checking ? 'Checking…' : 'Send request'}
                  </button>
                </div>
              </form>
            )}
          </section>

          {agent && <PolicyLimits state={state} agent={agent} />}
        </div>
      </div>
    </>
  )
}
