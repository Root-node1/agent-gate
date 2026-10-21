import { Link } from 'react-router'
import { AlertTriangle, CircleCheck, OctagonX, ShieldCheck } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import { agentById, budgetUsage } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { formatMoney, percent, timeAgo } from '../../ui/format'
import { useNow, useSimulatedLoad } from '../../ui/hooks'
import PageHeader from '../../ui/PageHeader'
import { AgentStatusBadge } from '../../ui/StatusBadges'
import './PoliciesPage.css'

function Usage({ used, limit, currency }: { used: number; limit: number; currency: string }) {
  const pct = percent(used, limit)
  const tone = pct >= 90 ? 'deny' : pct >= 75 ? 'approval' : 'allow'
  return (
    <div className={`po-usage tone-${tone}`}>
      <span className="num">{formatMoney(limit, currency)}</span>
      <span className="po-usage-track" aria-hidden="true">
        <span className="po-usage-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="po-usage-text">
        {formatMoney(used, currency)} used · {pct}%
      </span>
    </div>
  )
}

export default function PoliciesPage() {
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const now = useNow()

  return (
    <div className="stack-lg">
      <PageHeader
        title="Policies"
        description="The spending rules AgentGate checks before any payment. Each agent has exactly one policy."
      />

      <ul className="po-legend" aria-label="How rules decide">
        <li className="tone-allow">
          <CircleCheck size={18} aria-hidden="true" />
          <span>
            <strong>Paid automatically</strong> up to the approval threshold, from a trusted source.
          </span>
        </li>
        <li className="tone-approval">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>
            <strong>Needs approval</strong> above the threshold up to the cap, or from untrusted content.
          </span>
        </li>
        <li className="tone-deny">
          <OctagonX size={18} aria-hidden="true" />
          <span>
            <strong>Blocked</strong> above the cap, over budget, or to a merchant that is not allowed.
          </span>
        </li>
      </ul>

      <section className="card card-flush" aria-labelledby="po-list-title">
        <div className="card-header">
          <div>
            <h2 id="po-list-title" className="card-title">
              All policies
            </h2>
            <p className="card-subtitle">Budgets show what has been spent today and this month.</p>
          </div>
        </div>
        {loading ? (
          <SkeletonRows rows={4} />
        ) : state.policies.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={24} />}
            title="No policies yet"
            action={
              <Link to="/app/agents" className="btn btn-primary">
                Register an agent
              </Link>
            }
          >
            Every agent you register gets a policy with safe default limits.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table po-table">
              <thead>
                <tr>
                  <th scope="col">Policy</th>
                  <th scope="col">Agent</th>
                  <th scope="col">Per payment</th>
                  <th scope="col">Daily budget</th>
                  <th scope="col">Monthly budget</th>
                  <th scope="col">Merchants</th>
                </tr>
              </thead>
              <tbody>
                {state.policies.map((policy) => {
                  const agent = agentById(state, policy.agent_id)
                  const usage = budgetUsage(state, policy.agent_id, new Date(now))
                  const allowed = policy.allowed_merchants.length
                  const blocked = policy.blocked_merchants.length
                  return (
                    <tr key={policy.id} className="row-link">
                      <td>
                        <Link to={`/app/policies/${policy.id}`} className="row-anchor">
                          {policy.name}
                        </Link>
                        <span className="po-sub">
                          {policy.currency} · updated{' '}
                          <time dateTime={policy.updated_at}>{timeAgo(policy.updated_at, now)}</time>
                        </span>
                      </td>
                      <td>
                        {agent ? (
                          <span className="po-agent-cell">
                            <Link to={`/app/agents/${agent.id}`} className="po-cell-link">
                              {agent.name}
                            </Link>
                            {agent.status === 'suspended' && <AgentStatusBadge status={agent.status} />}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="po-nowrap po-limits">
                        <span className="tone-approval">
                          <span aria-hidden="true">!</span> Approval above{' '}
                          <strong className="num">{formatMoney(policy.approval_threshold, policy.currency)}</strong>
                        </span>
                        <span className="tone-deny">
                          <span aria-hidden="true">✕</span> Blocked above{' '}
                          <strong className="num">{formatMoney(policy.per_transaction_cap, policy.currency)}</strong>
                        </span>
                      </td>
                      <td>
                        <Usage used={usage?.today ?? 0} limit={policy.daily_budget} currency={policy.currency} />
                      </td>
                      <td>
                        <Usage used={usage?.month ?? 0} limit={policy.monthly_budget} currency={policy.currency} />
                      </td>
                      <td className="po-nowrap">
                        {allowed ? `Only ${allowed} allowed` : 'Any merchant'}
                        <span className="po-sub">{blocked ? `${blocked} blocked` : 'None blocked'}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {!loading && state.policies.length > 0 && (
          <div className="table-footer">
            <span>{state.policies.length} policies</span>
            <span>Select a policy to edit its rules.</span>
          </div>
        )}
      </section>
    </div>
  )
}
