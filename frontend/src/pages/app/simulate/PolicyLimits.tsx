import { Link } from 'react-router'
import { budgetUsage, policyForAgent } from '../../../demo/selectors'
import type { Agent, DemoState } from '../../../demo/types'
import Meter from '../../../ui/Meter'
import { formatMoney } from '../../../ui/format'

/** The selected agent's limits, shown next to the request form. */
export default function PolicyLimits({ state, agent }: { state: DemoState; agent: Agent }) {
  const policy = policyForAgent(state, agent.id)
  const usage = budgetUsage(state, agent.id)

  return (
    <section className="card" aria-labelledby="sim-limits">
      <div className="card-header">
        <div>
          <h2 id="sim-limits" className="card-title">
            {agent.name}&apos;s limits
          </h2>
          {policy && <p className="card-subtitle">Policy: {policy.name}</p>}
        </div>
        {policy && (
          <Link to={`/app/policies/${policy.id}`} className="card-link">
            Edit policy
          </Link>
        )}
      </div>
      {!policy || !usage ? (
        <p className="hint">This agent has no policy, so every request is rejected.</p>
      ) : (
        <div className="stack">
          <dl className="kv">
            <dt>Currency</dt>
            <dd>{policy.currency}</dd>
            <dt>Max per payment</dt>
            <dd>{formatMoney(policy.per_transaction_cap, policy.currency)}</dd>
            <dt>Needs a person above</dt>
            <dd>{formatMoney(policy.approval_threshold, policy.currency)}</dd>
          </dl>
          <MerchantList title="Allowed merchants" items={policy.allowed_merchants} empty="Any merchant" />
          <MerchantList title="Blocked merchants" items={policy.blocked_merchants} empty="None" />
          <Meter label="Spent today" used={usage.today} limit={usage.dailyBudget} currency={usage.currency} />
          <Meter label="Spent this month" used={usage.month} limit={usage.monthlyBudget} currency={usage.currency} />
          <p className="hint">Requests from untrusted or unknown sources always need a person, whatever the amount.</p>
        </div>
      )}
    </section>
  )
}

function MerchantList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <h3 className="sim-subtitle">{title}</h3>
      {items.length ? (
        <ul className="sim-chips">
          {items.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : (
        <p className="hint">{empty}</p>
      )}
    </div>
  )
}
