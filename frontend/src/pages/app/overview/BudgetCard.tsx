import { Link } from 'react-router'
import { budgetUsage, policyForAgent, workspaceBudget } from '../../../demo/selectors'
import type { DemoState } from '../../../demo/types'
import { formatMoney, percent } from '../../../ui/format'
import Meter from '../../../ui/Meter'

export default function BudgetCard({ state, now }: { state: DemoState; now: number }) {
  const at = new Date(now)
  const total = workspaceBudget(state, at)
  const agents = state.agents
    .filter((a) => a.status === 'active')
    .flatMap((agent) => {
      const usage = budgetUsage(state, agent.id, at)
      const policy = policyForAgent(state, agent.id)
      return usage && policy ? [{ agent, usage, policy, pct: percent(usage.month, usage.monthlyBudget) }] : []
    })
    // Closest to a limit first, so trouble surfaces at the top.
    .sort((a, b) => b.pct - a.pct)

  return (
    <section className="card" aria-labelledby="ov-budget-title">
      <div className="card-header">
        <div>
          <h2 className="card-title" id="ov-budget-title">
            Budget
          </h2>
          <p className="card-subtitle">Spending that counts against limits, all active agents</p>
        </div>
        <Link to="/app/policies" className="card-link">
          Policies
        </Link>
      </div>

      <div className="stack">
        <Meter label="Today" used={total.today} limit={total.dailyBudget} currency={total.currency} />
        <Meter label="This month" used={total.month} limit={total.monthlyBudget} currency={total.currency} />
      </div>

      <h3 className="ov-subheading">By agent, this month</h3>
      {agents.length === 0 ? (
        <p className="muted small">No active agents. Spending limits apply once an agent is active.</p>
      ) : (
        <ul className="ov-agent-budgets">
          {agents.map(({ agent, usage, policy }) => (
            <li key={agent.id}>
              <div className="ov-agent-budget-head">
                <Link to={`/app/agents/${agent.id}`} className="ov-agent-link">
                  {agent.name}
                </Link>
                <Link to={`/app/policies/${policy.id}`} className="ov-policy-link">
                  Edit limits<span className="visually-hidden"> for {agent.name}</span>
                </Link>
              </div>
              <Meter
                label={`${agent.name}, this month`}
                used={usage.month}
                limit={usage.monthlyBudget}
                currency={usage.currency}
              />
              <p className="ov-agent-today">
                Today {formatMoney(usage.today, usage.currency)} of{' '}
                {formatMoney(usage.dailyBudget, usage.currency)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
