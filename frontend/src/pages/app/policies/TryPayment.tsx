import { useState } from 'react'
import { evaluate, type Spent } from '../../../demo/rules'
import type { Source } from '../../../demo/types'
import { formatMoney } from '../../../ui/format'
import { DECISION, SOURCE } from '../../../ui/labels'
import ReasonList from '../../../ui/ReasonList'
import { DecisionStatus } from '../../../ui/StatusBadges'
import { currencySymbol, limitsFromValues, parseMoney, type PolicyValues } from './policyDraft'

interface Props {
  values: PolicyValues
  spent: Spent
  /** False while the draft has field errors. */
  valid: boolean
}

/** Runs the real rule engine against the unsaved draft. */
export default function TryPayment({ values, spent, valid }: Props) {
  const [amount, setAmount] = useState(() => String(Math.round(values.approval_threshold * 1.2) || 75))
  const [merchant, setMerchant] = useState(() => values.allowed_merchants[0] ?? 'github.com')
  const [source, setSource] = useState<Source>('trusted')

  const parsed = parseMoney(amount)
  const ready = valid && Number.isFinite(parsed) && merchant.trim() !== ''
  const result = ready
    ? evaluate({ amount: parsed, currency: values.currency, merchant, source }, limitsFromValues(values), spent)
    : null

  return (
    <div className="stack po-try">
      <div className="po-try-fields">
        <div className="field">
          <label htmlFor="po-try-amount">Amount</label>
          <div className="input-affix">
            <span>{currencySymbol(values.currency)}</span>
            <input
              id="po-try-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              autoComplete="off"
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="po-try-merchant">Merchant</label>
          <input
            id="po-try-merchant"
            value={merchant}
            onChange={(e) => setMerchant(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="field po-try-source">
          <label htmlFor="po-try-source">Instruction came from</label>
          <select id="po-try-source" value={source} onChange={(e) => setSource(e.target.value as Source)}>
            {(Object.keys(SOURCE) as Source[]).map((s) => (
              <option key={s} value={s}>
                {SOURCE[s].label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="po-try-result" aria-live="polite">
        {!valid ? (
          <p className="hint">Fix the highlighted fields to try a payment.</p>
        ) : !result ? (
          <p className="hint">Enter an amount and a merchant.</p>
        ) : (
          <div className="stack">
            <div className="cluster">
              <DecisionStatus decision={result.decision} />
              <span className="small">
                {formatMoney(parsed, values.currency)} to {merchant.trim()}: {DECISION[result.decision].summary}
              </span>
            </div>
            <ReasonList reasons={result.reasons} />
          </div>
        )}
      </div>
      <p className="hint">Uses this agent's real spend so far today and this month. Nothing is sent.</p>
    </div>
  )
}
