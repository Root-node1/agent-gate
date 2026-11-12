import { Link } from 'react-router'
import { useMemo } from 'react'
import { AlertTriangle, CircleCheck, OctagonX, ShieldCheck } from 'lucide-react'
import { listPolicies, type Policy as ApiPolicy } from '../../api/policies'
import { useApiResource } from '../../api/useApiResource'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { formatMoney, timeAgo } from '../../ui/format'
import { useNow } from '../../ui/hooks'
import PageHeader from '../../ui/PageHeader'
import './PoliciesPage.css'


export default function PoliciesPage() {
  const now = useNow()
  const resource = useApiResource((signal) => listPolicies({ signal }))
  const loading = resource.status === 'loading'

  const policies = useMemo(() => {
    if (resource.status !== 'success' && resource.status !== 'empty') return []
    return Array.isArray(resource.data)
      ? resource.data
      : 'results' in resource.data
        ? (resource.data as { results: ApiPolicy[] }).results
        : []
  }, [resource])

  if (resource.status === 'error') {
    return (
      <div className="stack-lg">
        <PageHeader title="Policies" description="Failed to load policies" />
        <EmptyState
          icon={<ShieldCheck size={24} />}
          title="Unable to load policies"
          action={<button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Retry</button>}
        >
          <span role="alert">{resource.error.message}</span>
        </EmptyState>
      </div>
    )
  }

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
        ) : policies.length === 0 ? (
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
                {policies.map((policy: ApiPolicy) => (
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
                      <span className="po-agent-cell">
                        <span className="muted">{policy.agent_name}</span>
                      </span>
                    </td>
                    <td className="po-nowrap po-limits">
                      <span className="tone-approval">
                        <span aria-hidden="true">!</span> Approval above{' '}
                        <strong className="num">{formatMoney(policy.approval_threshold_minor / 100, policy.currency)}</strong>
                      </span>
                      <span className="tone-deny">
                        <span aria-hidden="true">✕</span> Blocked above{' '}
                        <strong className="num">{formatMoney(policy.per_transaction_cap_minor / 100, policy.currency)}</strong>
                      </span>
                    </td>
                    <td>
                      <span className="muted">—</span>
                    </td>
                    <td>
                      <span className="muted">—</span>
                    </td>
                    <td className="po-nowrap">
                      {policy.merchant_mode === 'allowlist_only' ? 'Allowlist only' : 'Any merchant'}
                      <span className="po-sub">{policy.merchant_rules.length ? `${policy.merchant_rules.length} rules` : 'None blocked'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && policies.length > 0 && (
          <div className="table-footer">
            <span>{policies.length} policies</span>
            <span>Select a policy to edit its rules.</span>
          </div>
        )}
      </section>
    </div>
  )
}
