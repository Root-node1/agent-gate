import { AlertTriangle, CircleCheck, OctagonX } from 'lucide-react'
import type { Spent } from '../../../demo/rules'
import { formatMoney } from '../../../ui/format'
import type { PolicyValues } from './policyDraft'

interface Props {
  values: PolicyValues
  spent: Spent
}

/**
 * Live picture of what the draft policy does to a payment: a $0 to above-cap
 * scale split into allowed, needs approval and blocked, with the conditions
 * that move a payment out of each zone.
 */
export default function PaymentPreview({ values, spent }: Props) {
  const { approval_threshold: threshold, per_transaction_cap: cap, currency } = values
  const money = (n: number) => formatMoney(n, currency)
  const valid = Number.isFinite(threshold) && Number.isFinite(cap) && threshold > 0 && cap > 0 && threshold <= cap

  if (!valid) {
    return (
      <p className="notice tone-neutral po-preview-invalid">
        Enter a valid approval threshold and per-transaction cap to see what happens to a payment.
      </p>
    )
  }

  const scaleMax = cap * 1.3
  const greenPct = (threshold / scaleMax) * 100
  const amberPct = ((cap - threshold) / scaleMax) * 100
  const leftToday = Number.isFinite(values.daily_budget) ? Math.max(0, values.daily_budget - spent.today) : NaN
  const leftMonth = Number.isFinite(values.monthly_budget) ? Math.max(0, values.monthly_budget - spent.this_month) : NaN
  const budgetLeft = Math.min(leftToday, leftMonth)
  const budgetBinds = Number.isFinite(budgetLeft) && budgetLeft < cap
  const allowList = values.allowed_merchants.length
  const blockList = values.blocked_merchants.length

  const merchantRule = allowList
    ? `The merchant is one of the ${allowList} on the allow list`
    : blockList
      ? 'The merchant is not on the block list'
      : 'Any merchant (no merchant rules set)'

  return (
    <div className="stack po-preview">
      <div className="po-scale-wrap" aria-hidden="true">
        <div className="po-scale-ticks po-scale-ticks-top">
          <span className="po-tick" style={{ left: `${greenPct}%` }}>
            {money(threshold)}
          </span>
        </div>
        <div className="po-scale">
          <div className="po-zone tone-allow" style={{ width: `${greenPct}%` }}>
            <CircleCheck size={16} />
          </div>
          {amberPct > 0 && (
            <div className="po-zone tone-approval" style={{ width: `${amberPct}%` }}>
              <AlertTriangle size={16} />
            </div>
          )}
          <div className="po-zone tone-deny po-zone-last">
            <OctagonX size={16} />
          </div>
        </div>
        <div className="po-scale-ticks">
          <span className="po-tick po-tick-start">{money(0)}</span>
          <span className="po-tick" style={{ left: `${greenPct + amberPct}%` }}>
            {money(cap)}
          </span>
        </div>
      </div>

      <ul className="po-zones">
        <li className="po-zone-card tone-allow">
          <CircleCheck size={20} className="po-zone-icon" aria-hidden="true" />
          <div>
            <p className="po-zone-title">Paid automatically</p>
            <p className="po-zone-range">Up to {money(threshold)}</p>
            <p className="po-zone-text">Only when all of these are true:</p>
            <ul className="po-zone-list">
              <li>The instruction came from a trusted source (the operator or user)</li>
              <li>{merchantRule}</li>
              <li>It fits in today's and this month's budget</li>
            </ul>
          </div>
        </li>
        <li className="po-zone-card tone-approval">
          <AlertTriangle size={20} className="po-zone-icon" aria-hidden="true" />
          <div>
            <p className="po-zone-title">Waits for a person to approve</p>
            <p className="po-zone-range">
              {amberPct > 0 ? `${money(threshold + 0.01)} to ${money(cap)}` : 'No amount needs approval on its own'}
            </p>
            <p className="po-zone-text">
              Also any amount up to {money(cap)} when the instruction came from a web page, email, invoice or an unknown
              source.
            </p>
          </div>
        </li>
        <li className="po-zone-card tone-deny">
          <OctagonX size={20} className="po-zone-icon" aria-hidden="true" />
          <div>
            <p className="po-zone-title">Blocked automatically</p>
            <p className="po-zone-range">Above {money(cap)}</p>
            <p className="po-zone-text">Also any amount when:</p>
            <ul className="po-zone-list">
              {allowList > 0 && <li>The merchant is not on the allow list</li>}
              {blockList > 0 && <li>The merchant is on the block list ({blockList})</li>}
              <li>
                It would go over the daily budget
                {Number.isFinite(leftToday) && ` (${money(leftToday)} left today)`}
              </li>
              <li>
                It would go over the monthly budget
                {Number.isFinite(leftMonth) && ` (${money(leftMonth)} left this month)`}
              </li>
              <li>It is not in {currency}</li>
            </ul>
          </div>
        </li>
      </ul>

      {budgetBinds && (
        <p className="notice tone-approval po-budget-note">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>
            Right now only {money(budgetLeft)} of budget is left, so any payment above that is blocked, even under the
            cap.
          </span>
        </p>
      )}
    </div>
  )
}
